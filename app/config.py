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