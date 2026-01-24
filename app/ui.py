# app/ui.py
import asyncio
import pyvista as pv
from pyvista.trame.ui.vuetify3 import button, divider, select, slider, text_field

MIN_RES = 3
MAX_RES = 40
DEFAULT_RES = 10
FRAME_TIME = 0.25

def build_toolbar(state, ctrl, resources):
    """
    Build toolbar widgets and register callbacks.

    Parameters
    ----------
    state : trame.server.state
    ctrl : trame.server.controller
    resources : dict
        Expecting keys:
          - 'plotter': pv.Plotter
          - 'actor'  : returned actor from add_mesh
    """
    divider(vertical=True, classes="mx-1")

    def play_cb():
        state.play = not state.play
        state.flush()

    button(icon="mdi-play", click=play_cb, tooltip="Play")

    # Slider and text field bound to the same state variable 'resolution'
    slider(
        model=("resolution", DEFAULT_RES),
        tooltip="Resolution slider",
        min=MIN_RES,
        max=MAX_RES,
        step=1,
        dense=True,
        hide_details=True,
        style="width: 300px",
    )

    text_field(
        model=("resolution", DEFAULT_RES),
        tooltip="Resolution value",
        readonly=False,          # allow manual input
        type="number",
        dense=True,
        hide_details=True,
        style="min-width: 40px; width: 80px",
    )

    divider(vertical=True, classes="mx-1")

    select(
        model=("visibility", "Show"),
        tooltip="Toggle visibility",
        items=["Visibility", ["Hide", "Show"]],
        hide_details=True,
        dense=True,
    )

    # Reset camera control
    def reset_camera_cb():
        pl = resources.get("plotter")
        if pl is not None:
            try:
                pl.reset_camera()
            except Exception:
                pass
        try:
            ctrl.view_update()
        except Exception:
            pass

    button(icon="mdi-crop-free", click=reset_camera_cb, tooltip="Reset camera")

    # initialize state defaults
    # If resolution already present leave it, otherwise set default
    if getattr(state, "resolution", None) is None:
        state.resolution = DEFAULT_RES
    if getattr(state, "play", None) is None:
        state.play = False
    if getattr(state, "visibility", None) is None:
        state.visibility = "Show"

    @state.change("play")
    async def _play(play, **kwargs):
        # animate resolution while play is True
        while state.play:
            # increment, wrap around if necessary
            current = int(getattr(state, "resolution", DEFAULT_RES) or DEFAULT_RES)
            new_res = current + 1
            if new_res > MAX_RES:
                new_res = MIN_RES
            state.resolution = new_res
            # ensure clients see the new resolution value immediately
            state.flush()
            await asyncio.sleep(FRAME_TIME)
        
    @state.change("resolution")
    def _update_resolution(resolution, **kwargs):
        """
        Called when the slider / textfield changes resolution.
        Normalize/clamp the incoming value, write back corrected value if needed,
        then update the VTK source and request a view update.
        """
        try:
            # resolution may come as str/float/int from client; coerce to int
            if resolution is None:
                return
            # handle values like "12.0" or "12"
            res_int = int(float(resolution))
        except Exception:
            # ignore invalid input
            return

        # clamp
        if res_int < MIN_RES:
            res_int_clamped = MIN_RES
        elif res_int > MAX_RES:
            res_int_clamped = MAX_RES
        else:
            res_int_clamped = res_int

        # if we corrected the value, write it back so client widgets show exact value
        if res_int_clamped != res_int:
            state.resolution = res_int_clamped
            # push corrected value to client
            state.flush()
            # handler will be called again with the corrected value -> return now
            return

        # At this point res_int_clamped is a valid integer within [MIN_RES, MAX_RES]
        # Update the VTK source if present
        source = resources.get("source") or resources.get("algo")
        pl = resources.get("plotter")
        actor = resources.get("actor")

        # If we have a source object with a 'resolution' attribute, update it.
        if source is not None and hasattr(source, "resolution"):
            try:
                source.resolution = res_int_clamped
            except Exception:
                # Some source wrappers expose the underlying VTK object differently;
                # best-effort: try to set attribute on underlying object if present.
                try:
                    if hasattr(source, "_algorithm"):
                        setattr(source._algorithm, "resolution", res_int_clamped)
                except Exception:
                    pass
        else:
            # Fallback: recreate mesh and swap actor (robust if source isn't available)
            try:
                if pl is not None:
                    new_mesh = pv.Cone(resolution=res_int_clamped)
                    # remove old actor if exists
                    try:
                        if actor is not None:
                            pl.remove_actor(actor)
                    except Exception:
                        pass
                    new_actor = pl.add_mesh(new_mesh)
                    resources["actor"] = new_actor
            except Exception:
                pass

        # Trigger view update
        try:
            ctrl.view_update()
        except Exception:
            import traceback
            traceback.print_exception()

    @state.change("visibility")
    def _set_visibility(visibility, **kwargs):
        actor = resources.get("actor")
        if actor is not None:
            try:
                actor.visibility = 1 if visibility == "Show" else 0
            except Exception:
                # some actor wrappers differ; try setting property on underlying actor
                try:
                    if hasattr(actor, "_actor"):
                        actor._actor.SetVisibility(1 if visibility == "Show" else 0)
                except Exception:
                    pass
        try:
            ctrl.view_update()
        except Exception:
            pass
