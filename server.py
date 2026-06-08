# server.py

from __future__ import annotations

import argparse
import logging
import pyvista as pv
from pathlib import Path

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageWithDrawerLayout
from pyvista.trame.ui import plotter_ui

import config
from scene_manager import SceneManager
from ui import build_toolbar
from ui import build_sidebar


def parse_args():
    p = argparse.ArgumentParser(
        description="CME Viewer Server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Domain Arguments
    p.add_argument("--cor-dir", type=Path, default=None,
                   help="Directory containing coronal magnetic field and tracer .hdf files.")
    
    p.add_argument("--hel-dir", type=Path, default=None,
                   help="Directory containing heliospheric magnetic field and tracer .hdf files (optional).")
    p.add_argument("--r-hel", type=float, default=None,
                   help="Radial inner boundary (in Solar Radii) of heliospheric domain or the interface connecting \
                   the coronal and heliospheric domains if both are present.")
    p.add_argument("--helio-shift", type=float, default=None,
                   help="Constant longitudinal shift angle (in RADIANS) between heliospheric and coronal domains.")
    p.add_argument('--auto-align', action='store_true', default=None,
                   help="Automatically match time steps and compute longitudinal shift between domains for best alignment.")
    
    # Server & Rendering Arguments
    p.add_argument("--mode", choices=["local", "remote"], default=None,
                   help="Runtime mode: 'local' (browser) or 'remote' (headless).")
    server_args = p.add_argument_group("Server & Render Settings")
    server_args.add_argument("--host", default=None,
                        help="Interface to bind to. Default 127.0.0.1 (SSH tunnel access). "
                        "Pass 0.0.0.0 to expose on all interfaces.")
    server_args.add_argument("--port", type=int, default=None)
    server_args.add_argument("--still-ratio", type=float, default=None, 
                        help="Render quality for still frames.")
    server_args.add_argument("--interactive-ratio", type=float, default=None, 
                        help="Render quality for interactive frames.")
    server_args.add_argument("--aa", choices=["ssaa", "fxaa", "msaa"], default=None, 
                        help="Enable anti-aliasing.")
    server_args.add_argument("--multi-samples", type=int, default=None,
                        help="Number of samples for MSAA.")

    # Simulation & Time Arguments
    scene_args = p.add_argument_group("Scene Metadata")
    scene_args.add_argument("--start-frame", type=int, default=None,
                            help="Initial frame to load.")
    scene_args.add_argument("--end-frame", type=int, default=None,
                            help="Last frame to load in sequence.")
    scene_args.add_argument("--time-file", default=None,
                     help="Name of file storing simulation time steps.")
    scene_args.add_argument("--t0-cor", default=None,
                     help="Initial time of coronal simulation in 'mm/dd/yyyy HH:MM:SS' format.")
    scene_args.add_argument("--t0-hel", default=None,
                     help="Initial time of heliospheric simulation in 'mm/dd/yyyy HH:MM:SS' format.")
    
    # Tracer Arguments
    fl_args = p.add_argument_group("Tracer & Fieldline Settings")
    fl_args.add_argument("--tracer-header", default=None,
                        help="Name of tracer header file.")
    fl_args.add_argument("--tracer-prefix", default=None,
                        help="Prefix of input tracer files.")
    fl_args.add_argument("--lp-prefix", default=None,
                        help="Prefix of output launch point files.")
    fl_args.add_argument("--max-traces", type=int, default=None,
                        help="Max fieldlines per group.")
    fl_args.add_argument("--max-steps", type=int, default=None,
                        help="Max number of steps to generate.")
    fl_args.add_argument("--label-select", default=None,
                        help="Comma-separated tracer labels for launch points.")
    fl_args.add_argument("--bg-lp", default=None,
                        help="Fixed points for background fieldlines.")

    # Other Arguments 
    p.add_argument("--verbose", action="store_true", default=None, 
                   help="Enable debug logs.")
    p.add_argument("--ignore-manifest", action="store_true", default=None, 
                   help="Preserve old cached data if new run data directory is used.")
    p.add_argument("--clear-cache", action="store_true", default=None, 
                   help="Clear cached data before starting for a fresh run.")

    return p.parse_args()


def main():
    args = parse_args()
    cfg = config.resolve_config(args)
    
    # Setup logging
    if cfg.runtime_cfg.verbose:
        print("Verbose logging enabled.")
        main_log_level = logging.DEBUG
        noisy_log_level = logging.DEBUG
    else:
        main_log_level = logging.INFO
        noisy_log_level = logging.WARNING  # Mutes spam from Trame 
        
    logging.basicConfig(
        level=main_log_level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    
    logger = logging.getLogger(__name__)
    
    # Restrict the chatty modules to the noisy_log_level
    logging.getLogger("trame_client").setLevel(noisy_log_level)
    logging.getLogger("trame_server").setLevel(noisy_log_level)
    logging.getLogger("wslink").setLevel(noisy_log_level)
    logging.getLogger("asyncio").setLevel(noisy_log_level)
    
    if cfg.runtime_cfg.mode not in ["local", "remote"]:
        logger.error(f"Invalid mode '{cfg.runtime_cfg.mode}' specified. Use 'local' or 'remote'.")
        return 1
    logger.info(f"Starting CME Viewer in {cfg.runtime_cfg.mode} mode")
    
    # Set Pyvista to offscreen rendering and initialize Trame server
    pv.OFF_SCREEN = cfg.runtime_cfg.offscreen
    server = get_server()
    state, ctrl = server.state, server.controller
    
    # Initialize Scene Manager
    try:
        scene = SceneManager(cfg.scene_cfg, line_smoothing=True, mode=cfg.runtime_cfg.mode)
    except FileNotFoundError as e:
        logger.critical(str(e))
        logger.info("Please verify the data directory paths in your config.yaml or CLI arguments.")
        return 1
    except Exception as e:
        logger.critical(f"An unexpected error occurred during SceneManager initialization: {e}")
        return 1
    
    # Enable AA on the plotter instance if specified in the config (put other graphical runtime settings here if needed)
    if cfg.runtime_cfg.aa:
        scene.plotter.enable_anti_aliasing(cfg.runtime_cfg.aa, multi_samples=cfg.runtime_cfg.multi_samples)
    
    if cfg.runtime_cfg.clear_cache:
        logger.info("Clearing cache as per configuration...")
        scene.clear_cache(all_runs=True)
    
    logger.info("Initializing scene manager...")
    # Setup initial frame and preload
    scene.initialize()
    logger.info("Scene initialized.")
    scene.preload_all_frames()
    logger.info("All frames preloaded.")
    
    # Expose resources to the UI
    resources = {
        "scene": scene,
        "plotter": scene.plotter, 
        "actors": scene.actors
    }

    still_ratio = cfg.runtime_cfg.still_ratio
    interactive_ratio = cfg.runtime_cfg.interactive_ratio
    
    # Build Trame UI
    with SinglePageWithDrawerLayout(server, title="CME Viewer") as layout:
        layout.drawer.width = 350
        with layout.toolbar:
            build_toolbar(state, ctrl, resources)
        with layout.drawer:
            build_sidebar(state, resources)
        with layout.content:
            view = plotter_ui(
                scene.plotter,
                mode=cfg.runtime_cfg.render_mode,
                still_ratio=still_ratio,
                interactive_ratio=interactive_ratio,
            )
            ctrl.view_update = view.update
            scene.set_view_update(view.update)

    # Start the server
    logger.info(f"Starting Trame server in {cfg.runtime_cfg.mode} mode...")
    server.start(
        host=cfg.runtime_cfg.host,
        port=cfg.runtime_cfg.port,
        open_browser=cfg.runtime_cfg.open_browser,
        disable_logging=not cfg.runtime_cfg.verbose
    )


if __name__ == "__main__":
    main()