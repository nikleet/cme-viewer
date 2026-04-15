# app/config.py
from dataclasses import dataclass

@dataclass
class RunConfig:
    mode: str
    host: str
    open_browser: bool
    render_mode: str
    offscreen: bool

def make_config(mode: str) -> RunConfig:
    if mode == "local":
        return RunConfig(
            mode="local",
            host="127.0.0.1",
            open_browser=True,
            render_mode="client",   # WebGL locally is fast
            offscreen=False,
        )
    elif mode == "remote":
        return RunConfig(
            mode="remote",
            host="127.0.0.1",
            open_browser=False,
            render_mode="server",   # safe for SSH
            offscreen=True,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}")
    

# Old overcomplicated config code for reference, might want to re-implement some of this later for more advanced features

# from dataclasses import dataclass, asdict, field
# from pathlib import Path
# import yaml
# from typing import Optional, Any, Dict

# CONFIG_FILE = Path("config.yaml")
# DEFAULT_MAX_TRACES = 50
# DEFAULT_MAX_STEPS = 500
# DEFAULT_HOST = "127.0.0.1"
# DEFAULT_PORT = 8080

# @dataclass
# class RunConfig:
#     # runtime defaults
#     mode: str = "local"              # "local" or "remote"
#     host: str = DEFAULT_HOST
#     open_browser: bool = True
#     render_mode: str = "client"      # "client" or "server"
#     offscreen: bool = False
#     port: int = DEFAULT_PORT
#     verbose: bool = False
#     max_steps: int = DEFAULT_MAX_STEPS

#     # CME / tracer defaults
#     cme_directory: Optional[Path] = None
#     time_stamps: Optional[str] = "mas_dumps_3d.txt"
#     t0: Optional[str] = None        # format: "%m/%d/%y %H:%M:%S"
#     tracer_header: Optional[str] = "tracer_header.dat"
#     tracer_prefix: Optional[str] = "tracers_pos"
#     launch_point_prefix: Optional[str] = None
#     max_traces: int = DEFAULT_MAX_TRACES
#     label_select: Optional[str] = None
#     bg_lp: Optional[str] = None

#     def to_dict(self) -> Dict[str, Any]:
#         data = asdict(self)
#         # convert Path objects to strings for YAML
#         for k, v in data.items():
#             if isinstance(v, Path):
#                 data[k] = str(v)
#         return data

#     @classmethod
#     def from_dict(cls, data: Dict[str, Any]) -> "RunConfig":
#         # convert back Path fields if present
#         if data.get("cme_directory") is not None:
#             data = dict(data)
#             data["cme_directory"] = Path(data["cme_directory"])
#         return cls(**data)

#     @classmethod
#     def from_args(cls, args) -> "RunConfig":
#         # Accept an argparse Namespace (only read needed fields)
#         mode = getattr(args, "mode", "local")
#         runtime = {}
#         if mode == "local":
#             runtime = dict(open_browser=True, render_mode="client", offscreen=False, host=DEFAULT_HOST)
#         else:
#             runtime = dict(open_browser=False, render_mode="server", offscreen=True, host=DEFAULT_HOST)

#         return cls(
#             mode=mode,
#             port=getattr(args, "port", DEFAULT_PORT),
#             verbose=getattr(args, "verbose", False),
#             max_steps=getattr(args, "max_steps", DEFAULT_MAX_STEPS),
#             cme_directory=Path(getattr(args, "cme_dir", "")) if getattr(args, "cme_dir", None) else None,
#             time_stamps=getattr(args, "time_stamps", None),
#             t0=getattr(args, "t0", None),
#             tracer_header=getattr(args, "tracer_header", None),
#             tracer_prefix=getattr(args, "tracer_prefix", None),
#             launch_point_prefix=getattr(args, "launch_point_prefix", None),
#             max_traces=getattr(args, "max_traces", DEFAULT_MAX_TRACES),
#             label_select=getattr(args, "label_select", None),
#             bg_lp=getattr(args, "bg_lp", None),
#             **runtime,
#         )

#     @classmethod
#     def load(cls, path: Path = CONFIG_FILE) -> "RunConfig":
#         with path.open("r") as f:
#             data = yaml.safe_load(f) or {}
#         return cls.from_dict(data)

#     def save(self, path: Path = CONFIG_FILE):
#         data = self.to_dict()
#         with Path(path).open("w") as f:
#             yaml.safe_dump(data, f, sort_keys=False)


# def get_config(args=None, config_path: Path = CONFIG_FILE, save_if_new: bool = True) -> RunConfig:
#     """
#     Resolve a RunConfig object.
#     Priority:
#       1) if config file exists -> load it
#       2) elif args provided -> build from args (and optionally save)
#       3) else -> return default RunConfig()
#     """
#     if Path(config_path).exists():
#         return RunConfig.load(Path(config_path))

#     if args is not None:
#         cfg = RunConfig.from_args(args)
#         if save_if_new:
#             cfg.save(Path(config_path))
#         return cfg

#     # fallback to sensible defaults
#     return RunConfig()


