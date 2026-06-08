# app/config.py

from dataclasses import dataclass, asdict, field
from pathlib import Path
import yaml
import argparse
from typing import List, Optional, Any, Dict, Union

CONFIG_FILE = Path("config.yaml")

@dataclass
class RuntimeConfig:
    """Settings related to application state and server rendering."""
    # Initialize defaults: (default mode is local)
    mode: str = "local"
    host: str = "127.0.0.1"
    port: int = 8080
    open_browser: bool = True
    render_mode: str = "client"
    offscreen: bool = False
    verbose: bool = False
    clear_cache: bool = False

    # Defined only for remote mode:
    still_ratio: Optional[float] = None
    interactive_ratio: Optional[float] = None
    aa: Optional[str] = None
    multi_samples: Optional[int] = None

    def __post_init__(self):
        """Enforce strict synchronization between application mode and rendering parameters."""
        if self.mode == "remote":
            if self.render_mode != "server":
                print(f"WARNING: 'render_mode' was set to '{self.render_mode}' but remote mode requires 'server'. Forcing render_mode=server.")
                self.render_mode = "server"
            if not self.offscreen:
                print(f"WARNING: 'offscreen' was set to '{self.offscreen}' but remote mode requires True. Forcing offscreen=True.")
                self.offscreen = True
            if self.open_browser:
                print(f"WARNING: 'open_browser' was set to '{self.open_browser}' but remote mode requires False. Forcing open_browser=False.")
                self.open_browser = False
        elif self.mode == "local":
            if self.render_mode != "client":
                print(f"WARNING: 'render_mode' was set to '{self.render_mode}' but local mode requires 'client'. Forcing render_mode=client.")
                self.render_mode = "client"
            if self.offscreen:
                print(f"WARNING: 'offscreen' was set to '{self.offscreen}' but local mode requires False. Forcing offscreen=False.")
                self.offscreen = False
            if not self.open_browser:
                print(f"WARNING: 'open_browser' was set to '{self.open_browser}' but local mode requires True. Forcing open_browser=True.")
                self.open_browser = True


@dataclass
class SceneConfig:
    """Settings related to the CME data and simulation metadata."""
    # Initialize argument defaults:
    cor_dir: Optional[Path] = None
    hel_dir: Optional[Path] = None          
    r_hel: float = 30.0   # solar radii          
    helio_shift: float = 0.0    # longitudinal shift in radians between coronal and heliospheric domains
    auto_align: bool = False    # whether to automatically compute time step matching and longitudinal shift for best alignment                
    t0_cor: Optional[str] = None    # cor simulation start time as string (e.g. "01/01/1990 00:00:00")
    t0_hel: Optional[str] = None    # hel simulation start time as string (e.g. "01/01/1990 00:00:00")
    time_file: str = "mas_dumps_3d.txt"
    tracer_header: str = "tracer_header.dat"
    tracer_prefix: str = "tracers_pos"
    lp_prefix: Optional[str] = "lp_"
    bg_lp: Optional[str] = None
    label_select: Union[str, List[str]] = "apex,axis,arcade,ring_lp_03,ring_lp_05, \
                                    ring_lp_07,ring_lp_09,ring_lp_11,ring_lp_13, \
                                    ring_lp_15,ring_lp_17,background"  
    max_traces: int = 50
    max_steps: int = 500
    start_frame: Optional[int] = 0
    end_frame: Optional[int] = None
    ignore_manifest: bool = False


@dataclass
class AppConfig:
    """The root configuration object."""
    runtime_cfg: RuntimeConfig = field(default_factory=RuntimeConfig)
    scene_cfg: SceneConfig = field(default_factory=SceneConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Converts to dict, casting Paths to strings for YAML."""
        def _serialize(obj):
            if isinstance(obj, Path): 
                return str(obj)
            if isinstance(obj, dict): 
                return {k: _serialize(v) for k, v in obj.items()}
            if isinstance(obj, list): 
                return [_serialize(v) for v in obj]
            return obj
        return _serialize(asdict(self))

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Reconstructs the object hierarchy, casting strings back to Paths."""
        runtime_data = data.get("runtime_cfg", {})
        scene_data = data.get("scene_cfg", {})
        
        # Handle Path casting
        if scene_data.get("cor_dir"):
            scene_data["cor_dir"] = Path(scene_data["cor_dir"])
        if scene_data.get("hel_dir"):                       
            scene_data["hel_dir"] = Path(scene_data["hel_dir"]) 

        return cls(
            runtime_cfg=RuntimeConfig(**runtime_data),
            scene_cfg=SceneConfig(**scene_data)
        )

    def save(self, path: Path = CONFIG_FILE):
        with open(path, "w") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=False)


def resolve_config(args: Optional[argparse.Namespace] = None, config_path: Path = CONFIG_FILE) -> AppConfig:
    """
    Builds the final config. 
    Priority: CLI Args > YAML File > Mode Profile > Base Defaults.
    """
    config_exists = config_path.exists()
    
    # Extract CLI args (ignoring unset parameters)
    cli_dict = {k: v for k, v in vars(args).items() if v is not None} if args else {}

    # Load YAML data
    yaml_data = {}
    if config_exists:
        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f) or {}

    # Determine the effective mode (CLI > YAML > default)
    mode = cli_dict.get('mode') or yaml_data.get('runtime_cfg', {}).get('mode') or "local"

    # Build base configuration dictionary from Dataclass defaults
    base_cfg = {
        "runtime_cfg": asdict(RuntimeConfig()),
        "scene_cfg": asdict(SceneConfig())
    }

    # Apply Mode Profile defaults (YAML and CLI will overwrite these)
    base_cfg["runtime_cfg"]["mode"] = mode
    if mode == "local":
        base_cfg["runtime_cfg"].update({
            "host": "127.0.0.1", "port": 8080, "open_browser": True,
            "render_mode": "client", "offscreen": False
        })
    elif mode == "remote":
        base_cfg["runtime_cfg"].update({
            "host": "127.0.0.1", "port": 8080, "open_browser": False,
            "render_mode": "server", "offscreen": True,
            "still_ratio": 1.0, "interactive_ratio": 0.8,
            "aa": "ssaa", "multi_samples": 2
        })

    # Apply YAML Overrides
    if "runtime_cfg" in yaml_data:
        for key, value in yaml_data["runtime_cfg"].items():
            if value not in (None, "None", "null", ""):
                base_cfg["runtime_cfg"][key] = value
                
    if "scene_cfg" in yaml_data:
        for key, value in yaml_data["scene_cfg"].items():
            if value not in (None, "None", "null", ""):
                base_cfg["scene_cfg"][key] = value

    # Apply CLI Overrides
    for key, value in cli_dict.items():
        if hasattr(RuntimeConfig, key):
            base_cfg["runtime_cfg"][key] = value
        elif hasattr(SceneConfig, key):
            base_cfg["scene_cfg"][key] = value

    # Reconstruct the object hierarchy (triggers __post_init__ validation)
    cfg = AppConfig.from_dict(base_cfg)
    
    # Normalize label_select
    if isinstance(cfg.scene_cfg.label_select, str):
        cfg.scene_cfg.label_select = [
            item.strip() for item in cfg.scene_cfg.label_select.split(',') if item.strip()
        ]
    elif cfg.scene_cfg.label_select is None:
        cfg.scene_cfg.label_select = []

    # Save if generating for the first time
    if args and not config_exists:
        cfg.save(config_path)

    return cfg