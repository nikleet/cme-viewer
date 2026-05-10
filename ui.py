# ui.py

import asyncio
from trame.widgets import vuetify3, html

FRAME_TIME = 0.1

MGRAM_CMAPS = [
    {"title": "Seismic",   "value": "seismic"},
    {"title": "Red-Blue",  "value": "RdBu_r"},
    {"title": "BWR",       "value": "bwr"},
    {"title": "Coolwarm",  "value": "coolwarm"},
    {"title": "PuOr",      "value": "PuOr"},
    {"title": "Grayscale", "value": "gray"},
]

FL_DEFAULT_COLORS = [
    "#e74c3c", "#3498db", "#2ecc71", "#f39c12",
    "#9b59b6", "#1abc9c", "#e67e22", "#c0392b",
]


# State

def init_state(state, scene):
    state.total_frames   = scene.total_frames if scene else 1
    state.current_frame  = 0
    state.playing        = False
    state.frame_label    = "Frame: 1"
    state.drawer         = False
    # open_panels controls which expansion panels start expanded.
    # Values match the `value=` prop on each VExpansionPanel below.
    state.open_panels    = ["mgram", "fl"]
    state.mgram_visible  = True
    state.mgram_cmap     = "seismic"
    state.mgram_clim_min = -10.0
    state.mgram_clim_max =  10.0
    state.fl_coloring_mode = "random"
    if scene:
        for i, label in enumerate(scene.fl_group_labels):
            state[f"fl_{label}_visible"] = True
            state[f"fl_{label}_color"]   = FL_DEFAULT_COLORS[i % len(FL_DEFAULT_COLORS)]


# Callbacks

def setup_callbacks(state, ctrl, resources):
    scene        = resources.get("scene")
    _loop_id     = [0]
    _is_updating = [False]

    # Playback

    @state.change("playing")
    async def on_play(playing, **kwargs):
        if not playing:
            return
        _loop_id[0] += 1
        my_id = _loop_id[0]
        while state.playing and _loop_id[0] == my_id:
            state.current_frame = (state.current_frame + 1) % state.total_frames
            # flush() pushes the updated state to the browser AND calls any
            # synchronous @state.change callbacks inline, so on_frame_change
            # runs to completion (scene update + view push) before we sleep.
            state.flush()
            await asyncio.sleep(FRAME_TIME)

    @state.change("current_frame")
    def on_frame_change(current_frame, **kwargs):
        if _is_updating[0]:
            return
        _is_updating[0] = True
        try:
            if scene:
                scene.set_frame(current_frame)
                state.frame_label = f"Frame: {current_frame + 1}"
                if ctrl.view_update:
                    ctrl.view_update()
        finally:
            _is_updating[0] = False

    # Magnetogram 

    @state.change("mgram_visible")
    def on_mgram_visible(mgram_visible, **kwargs):
        if scene:
            scene.set_actor_property("mgram", visibility=mgram_visible)

    @state.change("mgram_cmap")
    def on_mgram_cmap(mgram_cmap, **kwargs):
        if scene:
            clim = (float(state.mgram_clim_min), float(state.mgram_clim_max))
            scene.set_mgram_style(cmap=mgram_cmap, clim=clim)

    @state.change("mgram_clim_min", "mgram_clim_max")
    def on_mgram_clim(**kwargs):
        if scene:
            try:
                clim = (float(state.mgram_clim_min), float(state.mgram_clim_max))
                scene.set_mgram_style(clim=clim)
            except (TypeError, ValueError):
                pass

    # Fieldlines

    @state.change("fl_coloring_mode")
    def on_fl_coloring_mode(fl_coloring_mode, **kwargs):
        if not scene:
            return
        if fl_coloring_mode == "custom":
            for label in scene.fl_group_labels:
                color = state[f"fl_{label}_color"]
                scene.apply_fl_coloring(None, group_label=label, color=color)
        else:
            scene.apply_fl_coloring(fl_coloring_mode)

    if scene:
        for label in scene.fl_group_labels:
            _register_group_callbacks(state, scene, label)


def _register_group_callbacks(state, scene, label: str):
    """Factory to avoid the Python loop-closure bug (see earlier notes)."""
    @state.change(f"fl_{label}_visible")
    def on_visible(**kwargs):
        scene.set_actor_property(f"fl_{label}", visibility=kwargs.get(f"fl_{label}_visible", True))

    @state.change(f"fl_{label}_color")
    def on_color(**kwargs):
        if state.fl_coloring_mode == "custom":
            scene.apply_fl_coloring(None, group_label=label,
                                    color=kwargs.get(f"fl_{label}_color", "#ffffff"))


# Toolbar

def build_toolbar(state, ctrl, resources):
    """
    NOTE: No VAppBarNavIcon here. SinglePageWithDrawerLayout adds one
    automatically; adding another creates duplicates.
    """
    scene = resources.get("scene")
    init_state(state, scene)
    setup_callbacks(state, ctrl, resources)

    with vuetify3.VBtn(icon=True, click="playing = !playing", variant="text", color="primary"):
        vuetify3.VIcon("{{ playing ? 'mdi-pause' : 'mdi-play' }}")

    vuetify3.VSlider(
        v_model=("current_frame", 0),
        min=0,
        max=("total_frames - 1", 0),
        step=1,
        hide_details=True,
        density="compact",
        style="max-width: 400px; margin: 0 16px;",
    )
    vuetify3.VChip("{{ frame_label }}", variant="outlined", size="small", color="secondary")
    vuetify3.VSpacer()


# Sidebar

def build_sidebar(state, resources):
    scene = resources.get("scene")
    with vuetify3.VContainer(fluid=True, classes="pa-3"):
        vuetify3.VListSubheader("Scene Controls", classes="px-0 mb-2")

        with vuetify3.VExpansionPanels(multiple=True, v_model=("open_panels", ["mgram", "fl"])):
            _build_mgram_panel()
            _build_fl_panel(scene)

        vuetify3.VDivider(classes="my-4")
        vuetify3.VBtn(
            "Add Feature",
            prepend_icon="mdi-plus-circle-outline",
            block=True,
            variant="tonal",
            disabled=True,
            size="small",
        )


def _build_mgram_panel():
    with vuetify3.VExpansionPanel(value="mgram", title="Magnetogram"):
        with vuetify3.VExpansionPanelText():
            vuetify3.VSwitch(
                v_model=("mgram_visible", True),
                label="Visible",
                color="primary",
                density="compact",
                hide_details=True,
                classes="mb-3",
            )
            vuetify3.VSelect(
                v_model=("mgram_cmap", "seismic"),
                items=("mgram_cmap_options", MGRAM_CMAPS),
                item_title="title",
                item_value="value",
                label="Colormap",
                density="compact",
                hide_details=True,
                classes="mb-3",
            )
            vuetify3.VLabel("Color Range", classes="text-caption text-medium-emphasis")
            with vuetify3.VRow(no_gutters=True, classes="mt-1"):
                with vuetify3.VCol(cols=6, classes="pr-1"):
                    vuetify3.VTextField(
                        v_model=("mgram_clim_min", -10.0),
                        label="Min", type="number",
                        density="compact", hide_details=True,
                    )
                with vuetify3.VCol(cols=6, classes="pl-1"):
                    vuetify3.VTextField(
                        v_model=("mgram_clim_max", 10.0),
                        label="Max", type="number",
                        density="compact", hide_details=True,
                    )


def _build_fl_panel(scene):
    with vuetify3.VExpansionPanel(value="fl", title="Field Lines"):
        with vuetify3.VExpansionPanelText():
            vuetify3.VLabel("Coloring Mode", classes="text-caption text-medium-emphasis")
            with vuetify3.VBtnToggle(
                v_model=("fl_coloring_mode", "random"),
                mandatory=True,
                divided=True,
                density="compact",
                color="primary",
                classes="mt-1 mb-4",
                style="width: 100%;",
            ):
                vuetify3.VBtn("Random",   value="random",   style="flex:1;")
                vuetify3.VBtn("Polarity", value="polarity", style="flex:1;")
                vuetify3.VBtn("Custom",   value="custom",   style="flex:1;")

            if scene and scene.fl_group_labels:
                vuetify3.VLabel("Groups", classes="text-caption text-medium-emphasis")
                vuetify3.VDivider(classes="mt-1 mb-1")
                for i, label in enumerate(scene.fl_group_labels):
                    _build_fl_group_row(label, FL_DEFAULT_COLORS[i % len(FL_DEFAULT_COLORS)])


def _build_fl_group_row(label: str, default_color: str):
    with vuetify3.VRow(
        align="center", no_gutters=True, classes="py-1",
        style="border-bottom: 1px solid rgba(128,128,128,0.15);",
    ):
        with vuetify3.VCol(style="min-width:0; overflow:hidden;"):
            html.Span(
                label, classes="text-body-2",
                style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block;",
            )

        with vuetify3.VCol(cols="auto"):
            vuetify3.VSwitch(
                v_model=(f"fl_{label}_visible", True),
                color="primary", density="compact", hide_details=True,
            )

        with vuetify3.VCol(cols="auto", v_show="fl_coloring_mode === 'custom'"):
            with vuetify3.VMenu(close_on_content_click=False):
                with vuetify3.Template(v_slot_activator="{ props }"):
                    with vuetify3.VBtn(v_bind="props", icon=True, size="small", variant="text"):
                        # VIcon color bound to the group's color state key
                        vuetify3.VIcon("mdi-circle", color=(f"fl_{label}_color", default_color))
                vuetify3.VColorPicker(
                    v_model=(f"fl_{label}_color", default_color),
                    modes=["hex"],
                    show_swatches=False,
                    width=280,
                )