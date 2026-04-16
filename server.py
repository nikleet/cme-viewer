# server.py

from __future__ import annotations

import argparse
import logging
import pyvista as pv

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from pyvista.trame.ui import plotter_ui

import config
from scene_manager import SceneManager
from ui import build_toolbar
from utils import get_mag_files


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["local", "remote"], required=True,
                   help="Runtime mode: 'local' opens browser with client-side rendering; 'remote' is headless with server-side rendering.")
    p.add_argument("--data-dir", required=True,
                   help="Directory containing magnetic field and tracer .hdf files and CME run metadata")
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--still_ratio", type=float, default=None, 
                   help="Render quality for still frames in 'remote' mode (0.0-1.0)")
    p.add_argument("--interactive_ratio", type=float, default=None, 
                   help="Render quality for interactive frames in 'remote' mode (0.0-1.0)")
    p.add_argument("--time_stamps", default=None,
                   help="Name of file storing hdf times")
    p.add_argument("--t0", default=None,
                   help="Initial time of simulation in \"mm/dd/yyyy %H:%M:%S\" format")
    p.add_argument("--tracer_header", default=None,
                   help="Name of tracer header file in cme_directory")
    p.add_argument("--tracer_prefix", default=None,
                   help="Prefix of input tracer files")
    p.add_argument("--lp_prefix", default=None,
                   help="Prefix of output launch point files")
    p.add_argument("--max_traces", type=int, default=None,
                   help="Max fieldlines per group")
    p.add_argument("--max_steps", default=None, type=int,
                   help="Max number of steps to generate")
    p.add_argument("--label_select",
                   default=None,
                   help="Comma-separated tracer labels to select launch points from")
    p.add_argument("--bg_lp", 
                   default=None,
                   help="Fixed points for background fieldlines")
    p.add_argument("--aa", 
                   choices=["ssaa", "fxaa", "msaa"], 
                   default=None, 
                   help="Enable anti-aliasing on the plotter.")
    p.add_argument("--multi_samples", 
                   type=int,
                   default=None,
                   help="Number of samples for anti-aliasing (only applies if --anti_aliasing is set to 'msaa')")
    p.add_argument("--verbose", action="store_true", 
                   default=None, 
                   help="Enable debug logs")
    
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
    
    # Enable AA on the plotter instance
    if cfg.runtime.aa:
        scene.plotter.enable_anti_aliasing(cfg.runtime.aa, multi_samples=cfg.runtime.multi_samples)

    # Setup initial frame and preload
    mag_files_list = get_mag_files(str(cfg.sim.data_dir))
    if mag_files_list:
        scene.initialize_scene(mag_files_list[0])
        
        # TODO: Might want this to run asynchronously eventually so the UI doesn't freeze on boot, but for now, we load sequentially.
        scene.preload_all_frames(mag_files_list)
    
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