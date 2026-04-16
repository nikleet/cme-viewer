# server.py

from __future__ import annotations

import argparse
import logging
import pyvista as pv
from pathlib import Path

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from pyvista.trame.ui import plotter_ui

import config
from scene_manager import SceneManager
from ui import build_toolbar


def parse_args():
    p = argparse.ArgumentParser(
        description="CME Viewer Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Core Arguments
    p.add_argument("--mode", choices=["local", "remote"], required=True,
                   help="Runtime mode: 'local' (browser) or 'remote' (headless).")
    p.add_argument("--data-dir", type=Path, required=True,
                   help="Directory containing magnetic field and tracer .hdf files.")

    # Server & Rendering
    render = p.add_argument_group("Server & Render Settings")
    render.add_argument("--port", type=int, default=None)
    render.add_argument("--still-ratio", type=float, default=None, 
                        help="Render quality for still frames.")
    render.add_argument("--interactive-ratio", type=float, default=None, 
                        help="Render quality for interactive frames.")
    render.add_argument("--aa", choices=["ssaa", "fxaa", "msaa"], default=None, 
                        help="Enable anti-aliasing.")
    render.add_argument("--multi-samples", type=int, default=None,
                        help="Number of samples for MSAA.")

    # Simulation & Time
    sim = p.add_argument_group("Simulation Metadata")
    sim.add_argument("--time-file", default=None,
                     help="Name of file storing simulation time steps.")
    sim.add_argument("--t0", default=None,
                     help="Initial time of simulation in 'mm/dd/yyyy HH:MM:SS' format.")

    # Tracer Settings
    tracer = p.add_argument_group("Tracer & Fieldline Settings")
    tracer.add_argument("--tracer-header", default=None,
                        help="Name of tracer header file.")
    tracer.add_argument("--tracer-prefix", default=None,
                        help="Prefix of input tracer files.")
    tracer.add_argument("--lp-prefix", default=None,
                        help="Prefix of output launch point files.")
    tracer.add_argument("--max-traces", type=int, default=None,
                        help="Max fieldlines per group.")
    tracer.add_argument("--max-steps", type=int, default=None,
                        help="Max number of steps to generate.")
    tracer.add_argument("--label-select", default=None,
                        help="Comma-separated tracer labels for launch points.")
    tracer.add_argument("--bg-lp", default=None,
                        help="Fixed points for background fieldlines.")

    # --- Debug ---
    p.add_argument("--verbose", action="store_true", help="Enable debug logs.")

    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)

    cfg = config.resolve_config(args)
    pv.OFF_SCREEN = cfg.runtime.offscreen

    server = get_server()
    state, ctrl = server.state, server.controller
    
    # Initialize Scene Manager
    if cfg.sim.data_dir and cfg.sim.data_dir.exists():
        scene = SceneManager(cfg.sim, line_smoothing=True)
    else:
        logging.error(f"Data directory {cfg.sim.data_dir} does not exist. Exiting.")
        return 1
    
    # Enable AA on the plotter instance if specified in the config (put other graphical runtime settings here if needed)
    if cfg.runtime.aa:
        scene.plotter.enable_anti_aliasing(cfg.runtime.aa, multi_samples=cfg.runtime.multi_samples)
    
    # Setup initial frame and preload
    # TODO: Might want to preload asynchronously eventually so there's less 
    # delay on startup, but for now, we load sequentially.
    scene.initialize()
    scene.preload_all_frames()
    
    # Expose resources to the UI
    resources = {
        "scene": scene,
        "plotter": scene.plotter, 
        "actors": scene.actors
    }

    still_ratio = cfg.runtime.still_ratio
    interactive_ratio = cfg.runtime.interactive_ratio
    
    with SinglePageLayout(server) as layout:
        with layout.toolbar:
            build_toolbar(state, ctrl, resources)
        with layout.content:
            view = plotter_ui(scene.plotter, 
                              mode=cfg.runtime.render_mode, 
                              still_ratio=still_ratio, 
                              interactive_ratio=interactive_ratio)
            ctrl.view_update = view.update

    print("Starting Trame server...")
    server.start(
        host=cfg.runtime.host,
        port=cfg.runtime.port,
        open_browser=cfg.runtime.open_browser,
        disable_logging=not cfg.runtime.verbose
    )


if __name__ == "__main__":
    main()