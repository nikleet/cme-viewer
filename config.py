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
    # defaults:
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
    # Start with defaults or load from YAML
    if config_path.exists():
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
                # cfg.runtime.offscreen = False
                cfg.runtime_cfg.offscreen = True
            elif args.mode == "remote":
                cfg.runtime_cfg.host = "0.0.0.0"
                cfg.runtime_cfg.port = 8080
                cfg.runtime_cfg.open_browser = False
                cfg.runtime_cfg.render_mode = "server"
                cfg.runtime_cfg.offscreen = True
                cfg.runtime_cfg.still_ratio = 1.0
                cfg.runtime_cfg.interactive_ratio = 1.0
                cfg.runtime_cfg.aa = 'ssaa'
                cfg.runtime_cfg.multi_samples = 2
        
        if hasattr(args, 'port') and args.port: cfg.runtime_cfg.port = args.port
        if hasattr(args, 'still_ratio') and args.still_ratio: cfg.runtime_cfg.still_ratio = args.still_ratio
        if hasattr(args, 'interactive_ratio') and args.interactive_ratio: cfg.runtime_cfg.interactive_ratio = args.interactive_ratio
        if hasattr(args, 'aa') and args.aa: cfg.runtime_cfg.aa = args.aa
        if hasattr(args, 'multi_samples') and args.multi_samples: cfg.runtime_cfg.multi_samples = args.multi_samples
        if hasattr(args, 'verbose') and args.verbose is not None: cfg.runtime_cfg.verbose = args.verbose

        # Simulation Overrides
        if hasattr(args, 'data_dir') and args.data_dir: cfg.scene_cfg.data_dir = Path(args.data_dir)
        if hasattr(args, 'max_traces') and args.max_traces: cfg.scene_cfg.max_traces = args.max_traces
        if hasattr(args, 'max_steps') and args.max_steps: cfg.scene_cfg.max_steps = args.max_steps
        if hasattr(args, 'label_select') and args.label_select: cfg.scene_cfg.label_select = args.label_select
        if hasattr(args, 'bg_lp') and args.bg_lp: cfg.scene_cfg.bg_lp = args.bg_lp
        if hasattr(args, 'time_file') and args.time_file: cfg.scene_cfg.time_file = args.time_file
        if hasattr(args, 't0') and args.t0: cfg.scene_cfg.t0 = args.t0
        if hasattr(args, 'tracer_header') and args.tracer_header: cfg.scene_cfg.tracer_header = args.tracer_header
        if hasattr(args, 'tracer_prefix') and args.tracer_prefix: cfg.scene_cfg.tracer_prefix = args.tracer_prefix
        if hasattr(args, 'lp_prefix') and args.lp_prefix: cfg.scene_cfg.lp_prefix = args.lp_prefix
        
        # ... add remaining args as needed ...
        
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
    
    return cfg




