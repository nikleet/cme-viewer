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
    # defaults: (default mode is local)
    mode: str = "local"
    host: str = "127.0.0.1"
    port: int = 8080
    open_browser: bool = True
    render_mode: str = "client"
    offscreen: bool = False
    verbose: bool = False
    
    # defined only for remote mode:
    still_ratio: Optional[float] = None
    interactive_ratio: Optional[float] = None
    aa: Optional[str] = None
    multi_samples: Optional[int] = None

@dataclass
class SceneConfig:
    """Settings related to the CME data and simulation metadata."""
    # Argument defaults:
    data_dir: Optional[Path] = None
    t0: Optional[str] = None
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
    preserve_cache: bool = False

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
        if scene_data.get("data_dir"):
            scene_data["data_dir"] = Path(scene_data["data_dir"])

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
    Priority: CLI Args > YAML File > Defaults.
    """
    config_exists = config_path.exists()
    # Start with defaults or load from YAML
    if config_exists:
        with open(config_path, "r") as f:
            cfg = AppConfig.from_dict(yaml.safe_load(f) or {})
    else:
        cfg = AppConfig()

    # Override with CLI args if present
    if args:
        # Runtime Overrides
        if hasattr(args, 'mode') and args.mode:
            cfg.runtime_cfg.mode = args.mode
            if args.mode == "local":
                cfg.runtime_cfg.host = "127.0.0.1"
                cfg.runtime_cfg.port = None
                cfg.runtime_cfg.open_browser = True
                cfg.runtime_cfg.render_mode = "client"
                cfg.runtime_cfg.offscreen = True
            elif args.mode == "remote":
                cfg.runtime_cfg.host = "127.0.0.1"
                cfg.runtime_cfg.port = 8080
                cfg.runtime_cfg.open_browser = False
                cfg.runtime_cfg.render_mode = "server"
                cfg.runtime_cfg.offscreen = True
                cfg.runtime_cfg.still_ratio = 1.0
                cfg.runtime_cfg.interactive_ratio = 0.8
                cfg.runtime_cfg.aa = 'ssaa'
                cfg.runtime_cfg.multi_samples = 2
        
        # Extract active CLI options (ignoring unset parameters)
        cli_dict = {k: v for k, v in vars(args).items() if v is not None}

        # Apply Runtime overrides
        for key, value in cli_dict.items():
            if hasattr(cfg.runtime_cfg, key):
                setattr(cfg.runtime_cfg, key, value)

        # Apply Scene overrides
        for key, value in cli_dict.items():
            if hasattr(cfg.scene_cfg, key):
                # Cast string paths to Path objects if necessary
                if key == "data_dir" and isinstance(value, str):
                    value = Path(value)
                setattr(cfg.scene_cfg, key, value)
        
        # Normalize label_select to always be a list 
        if isinstance(cfg.scene_cfg.label_select, str):
            # Split by comma, strip whitespace, and filter out empty strings
            cfg.scene_cfg.label_select = [
                item.strip() 
                for item in cfg.scene_cfg.label_select.split(',') 
                if item.strip()
            ]
        elif cfg.scene_cfg.label_select is None:
            cfg.scene_cfg.label_select = []
    
    if args and not config_exists:
        cfg.save(config_path)
    
    return cfg




