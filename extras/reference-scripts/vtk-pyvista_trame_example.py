# save as run_trame_app.py and run with: python run_trame_app.py
from __future__ import annotations
import asyncio
import pyvista as pv
from pyvista.trame.ui.vuetify3 import button, divider, select, slider, text_field
from pyvista.trame.ui import plotter_ui
from trame.app import get_server
from trame.ui.vuetify3 import SinglePageLayout

# --- your UI builder and callbacks (same as notebook) ------------------------
def custom_tools():
    divider(vertical=True, classes="mx-1")
    button(click=button_play, icon="mdi-play", tooltip="Play")
    slider(
        model=("resolution", 10),
        tooltip="Resolution slider",
        min=3,
        max=20,
        step=1,
        dense=True,
        hide_details=True,
        style="width: 300px",
        classes="my-0 py-0 ml-1 mr-1",
    )
    text_field(
        model=("resolution", 10),
        tooltip="Resolution value",
        readonly=True,
        type="number",
        dense=True,
        hide_details=True,
        style="min-width: 40px; width: 60px",
        classes="my-0 py-0 ml-1 mr-1",
    )
    divider(vertical=True, classes="mx-1")
    select(
        model=("visibility", "Show"),
        tooltip="Toggle visibility",
        items=["Visibility", ["Hide", "Show"]],
        hide_details=True,
        dense=True,
    )

def button_play():
    state.play = not state.play
    state.flush()

# --- create plotter and scene (NOT notebook) --------------------------------
pv.OFF_SCREEN = True            # required for Trame apps (do this before Plotter)
server = get_server()           # create Trame server
state, ctrl = server.state, server.controller

pl = pv.Plotter()               # do NOT use notebook=True here
algo = pv.ConeSource()          # same pipeline as your notebook
mesh_actor = pl.add_mesh(algo)

# --- build Trame layout and attach the Plotter UI ---------------------------
with SinglePageLayout(server) as layout:
    # place custom tools into the top toolbar
    with layout.toolbar:
        # you can add layout.toolbar items directly or call your builder
        custom_tools()

    # main content container with the Plotter UI
    with (layout.content,):
        view = plotter_ui(pl, default_server_rendering=False)  # or omit arg
        # connect the controller to the view updater used in callbacks
        ctrl.view_update = view.update

# --- initialize state variables and register callbacks ----------------------
state.play = False
# async play handler
@state.change("play")
async def _play(play, **kwargs):
    while state.play:
        state.resolution += 1
        state.flush()
        if state.resolution >= 20:
            state.play = False
        await asyncio.sleep(0.3)

@state.change("resolution")
def update_resolution(resolution, **kwargs):
    algo.resolution = resolution
    ctrl.view_update()

@state.change("visibility")
def set_visibility(visibility, **kwargs):
    toggle = {"Hide": 0, "Show": 1}
    mesh_actor.visibility = toggle[visibility]
    ctrl.view_update()

# --- start the server when script is executed --------------------------------
if __name__ == "__main__":
    # open_browser=True will spawn the browser; set False to avoid opening automatically
    server.start(open_browser=True)
