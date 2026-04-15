# server.py

from __future__ import annotations

import argparse
import logging
import pyvista as pv

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from pyvista.trame.ui import plotter_ui

from config import make_config
from scene_manager import SceneManager
from ui import build_toolbar
from utils import get_mag_files


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", 
                   required=True,
                   help="Directory containing magnetic field and tracer .hdf files and CME run metadata")
    p.add_argument("--mode", choices=["local", "remote"], default="local")
    p.add_argument("--port", type=int, default=8080)
    
    # p.add_argument("--time_stamps", default="masTime.txt",
    #               help="name of file storing hdf times")
    # p.add_argument("--t0", default="1/1/1990 00:00:00",
    #                help="initial time of simulation in \"mm/dd/yyyy %H:%M:%S\" format (default: %(default)s)")
    # p.add_argument("--tracer_header", default="tracer_header.dat",
    #               help="name of tracer header file in cme_directory")
    # p.add_argument("--tracer_prefix", default="tracers_pos",
    #               help="prefix of input tracer files")
    # p.add_argument("--launch_point_prefix", default="lp_",
    #               help="prefix of output launch point files")
    # # p.add_argument("--max_traces",
    # #                type=int,
    # #                default=50,
    # #                help="max fieldlines per group (default: %(default)s)")

    # p.add_argument("--label_select",
    #                help="list of tracers to select from",
    #                default="apex,axis,arcade,ring_lp_03,ring_lp_05,ring_lp_07,ring_lp_09,"+\
    #                 "ring_lp_11,ring_lp_13,ring_lp_15,ring_lp_17,background")
    # p.add_argument("--bg_lp", default="launch_pts.dat",
    #                help="fixed points for background fieldlines (default: %(default)s)")
    # # p.add_argument("--verbose", default=False)
    # # p.add_argument("--max_steps",
    # #                default=50,
    # #                type=int,
    # #                help="max number of steps to generate (default: %(default)s)")
    
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)

    cfg = make_config(args.mode)
    pv.OFF_SCREEN = cfg.offscreen

    server = get_server()
    state, ctrl = server.state, server.controller

    # TODO: Add anti aliasing to and line_smoothing config
    
    # Initialize Scene Manager
    scene = SceneManager(args.data_dir, line_smoothing=True)
    
    # Enable AA on the plotter instance
    # 'ssaa' is high quality; 'fxaa' is faster but blurrier
    scene.plotter.enable_anti_aliasing('ssaa', multi_samples=2)
    
    # Setup initial frame and preload
    mag_files_list = get_mag_files(args.data_dir)
    if mag_files_list:
        scene.initialize_scene(mag_files_list[0])
        
        # TODO: Might want this to run asynchronously eventually so the UI 
        # doesn't freeze on boot, but for now, we load sequentially.
        scene.preload_all_frames(mag_files_list)
    
    # Expose resources to the UI
    resources = {
        "scene": scene,           # The UI can now call scene.set_frame(x)
        "plotter": scene.plotter, 
        "actors": scene.actors    # UI can iterate through keys ('mgram', 'fl') to build menus
    }

    # TODO: should add these to the config instead of hardcoding here
    still_ratio = 1.0
    interactive_ratio = 0.8
    
    with SinglePageLayout(server) as layout:
        with layout.toolbar:
            build_toolbar(state, ctrl, resources)
        with layout.content:
            view = plotter_ui(scene.plotter, 
                              mode=cfg.render_mode, 
                              still_ratio=still_ratio, 
                              interactive_ratio=interactive_ratio)
            ctrl.view_update = view.update

    print("Starting Trame server...")
    server.start(
        host=cfg.host,
        port=args.port,
        open_browser=cfg.open_browser,
        disable_logging=True    # This is just to keep the console clean for now
    )

if __name__ == "__main__":
    main()