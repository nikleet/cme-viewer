from __future__ import annotations

import argparse
import logging
import pyvista as pv

from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout
from pyvista.trame.ui import plotter_ui

from app.config import make_config
from app.plotter_wrapper import make_plotter
from app.ui import build_toolbar


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["local", "remote"], default="local")
    p.add_argument("--data-dir", required=True)
    p.add_argument("--port", type=int, default=8080)
    return p.parse_args()


def main():
    args = parse_args()
    logging.basicConfig(level=logging.INFO)


    cfg = make_config(args.mode)
    pv.OFF_SCREEN = cfg.offscreen


    server = get_server()
    state, ctrl = server.state, server.controller


    plotter, resources = make_plotter(args.data_dir)


    with SinglePageLayout(server) as layout:
        with layout.toolbar:
            build_toolbar(state, ctrl, resources)
        with layout.content:
            view = plotter_ui(plotter, mode=cfg.render_mode)
            ctrl.view_update = view.update


    server.start(
        host=cfg.host,
        port=args.port,
        open_browser=cfg.open_browser,
    )

if __name__ == "__main__":
    main()