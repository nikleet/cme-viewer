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
class SimulationConfig:
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
    runtime: RuntimeConfig = field(default_factory=RuntimeConfig)
    sim: SimulationConfig = field(default_factory=SimulationConfig)

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
        runtime_data = data.get("runtime", {})
        simulation_data = data.get("simulation", {})
        
        # Handle Path casting
        if simulation_data.get("data_dir"):
            simulation_data["data_dir"] = Path(simulation_data["data_dir"])

        return cls(
            runtime=RuntimeConfig(**runtime_data),
            sim=SimulationConfig(**simulation_data)
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
            cfg.runtime.mode = args.mode
            if args.mode == "local":
                cfg.runtime.host = "127.0.0.1"
                cfg.runtime.port = None
                cfg.runtime.open_browser = True
                cfg.runtime.render_mode = "client"
                # cfg.runtime.offscreen = False
                cfg.runtime.offscreen = True
            elif args.mode == "remote":
                cfg.runtime.host = "127.0.0.1"
                cfg.runtime.port = 8080
                cfg.runtime.open_browser = False
                cfg.runtime.render_mode = "server"
                cfg.runtime.offscreen = True
                cfg.runtime.still_ratio = 1.0
                cfg.runtime.interactive_ratio = 1.0
                cfg.runtime.aa = 'ssaa'
                cfg.runtime.multi_samples = 2
        
        if hasattr(args, 'port') and args.port: cfg.runtime.port = args.port
        if hasattr(args, 'still_ratio') and args.still_ratio: cfg.runtime.still_ratio = args.still_ratio
        if hasattr(args, 'interactive_ratio') and args.interactive_ratio: cfg.runtime.interactive_ratio = args.interactive_ratio
        if hasattr(args, 'aa') and args.aa: cfg.runtime.aa = args.aa
        if hasattr(args, 'multi_samples') and args.multi_samples: cfg.runtime.multi_samples = args.multi_samples
        if hasattr(args, 'verbose') and args.verbose is not None: cfg.runtime.verbose = args.verbose

        # Simulation Overrides
        if hasattr(args, 'data_dir') and args.data_dir: cfg.sim.data_dir = Path(args.data_dir)
        if hasattr(args, 'max_traces') and args.max_traces: cfg.sim.max_traces = args.max_traces
        if hasattr(args, 'max_steps') and args.max_steps: cfg.sim.max_steps = args.max_steps
        if hasattr(args, 'label_select') and args.label_select: cfg.sim.label_select = args.label_select
        if hasattr(args, 'bg_lp') and args.bg_lp: cfg.sim.bg_lp = args.bg_lp
        if hasattr(args, 'time_file') and args.time_file: cfg.sim.time_file = args.time_file
        if hasattr(args, 't0') and args.t0: cfg.sim.t0 = args.t0
        if hasattr(args, 'tracer_header') and args.tracer_header: cfg.sim.tracer_header = args.tracer_header
        if hasattr(args, 'tracer_prefix') and args.tracer_prefix: cfg.sim.tracer_prefix = args.tracer_prefix
        if hasattr(args, 'lp_prefix') and args.lp_prefix: cfg.sim.lp_prefix = args.lp_prefix
        
        # ... add remaining args as needed ...
        
        # Normalization 
        if isinstance(cfg.sim.label_select, str):
            # Split by comma, strip whitespace, and filter out empty strings
            cfg.sim.label_select = [
                item.strip() 
                for item in cfg.sim.label_select.split(',') 
                if item.strip()
            ]
        elif cfg.sim.label_select is None:
            cfg.sim.label_select = []
    
    return cfg




