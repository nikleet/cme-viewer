# ui.py

import asyncio
from trame.widgets import vuetify3, html

FRAME_TIME = 0.2

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
    state.total_frames     = scene.total_frames if scene else 1
    state.current_frame    = 0
    state.playing          = False
    state.frame_label      = "Frame: 1"
    state.time_label       = ""
    state.drawer           = False
    state.open_panels      = ["mgram", "fl"]
    state.mgram_visible    = True
    state.mgram_cmap       = "seismic"
    state.mgram_clim_min   = -10.0
    state.mgram_clim_max   = 10.0
    state.fl_coloring_mode = "random"
    state.fl_global_line_width = 5.0

    # Warmup state; only relevant in local mode
    state.is_warming_up    = False
    state.warmup_progress  = 0   # 0–100

    if scene:
        initial_time = scene.get_frame_time(0)
        if initial_time:
            state.time_label = initial_time.strftime("%Y-%m-%d %H:%M:%S")
        for i, label in enumerate(scene.fl_group_labels):
            state[f"fl_{label}_visible"]    = True
            state[f"fl_{label}_color"]      = FL_DEFAULT_COLORS[i % len(FL_DEFAULT_COLORS)]
            state[f"fl_{label}_opacity"]    = 1.0
            state[f"fl_{label}_line_width"] = 5.0


# Callbacks

def setup_callbacks(state, ctrl, resources):
    scene        = resources.get("scene")
    _loop_id     = [0]
    _is_updating = [False]

    # Warmup only needed once, only in local mode
    is_local = scene and scene.mode == 'local'
    _warmed_up = [not is_local]   # True for remote → skip warmup entirely

    # Playback 

    @state.change("playing")
    async def on_play(playing, **kwargs):
        if not playing:
            return

        # Local mode: warm up vtk.js cache on first play press 
        # vtk.js fetches geometry arrays by content hash.  Without warming up,
        # each frame triggers ~15 MB of WebSocket transfers that block the
        # asyncio event loop.  We cycle through every frame once so vtk.js
        # caches all arrays; subsequent frame changes serve from cache only.
        if not _warmed_up[0]:
            _warmed_up[0] = True
            state.playing        = False   # hold playback until cache is ready
            state.is_warming_up  = True
            state.warmup_progress = 0
            state.flush()

            def report_progress(done, total):
                state.warmup_progress = int(done / total * 100)
                state.flush()

            await scene._warm_up_vtk_cache(on_progress=report_progress)

            state.is_warming_up   = False
            state.warmup_progress = 100
            state.playing         = True   # re-triggers on_play with warmed cache
            state.flush()
            return

        # Continue with normal playback loop
        _loop_id[0] += 1
        my_id = _loop_id[0]
        while state.playing and _loop_id[0] == my_id:
            state.current_frame = (state.current_frame + 1) % state.total_frames
            state.flush()
            await asyncio.sleep(0)   # yield before view push
            if ctrl.view_update:
                ctrl.view_update()
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
                frame_time = scene.get_frame_time(current_frame)
                state.time_label = frame_time.strftime("%Y-%m-%d %H:%M:%S") if frame_time else ""
                if not state.playing and ctrl.view_update:
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
            
    @state.change("fl_global_line_width")
    def on_fl_global_line_width(fl_global_line_width, **kwargs):
        if not scene:
            return
        try:
            lw = float(fl_global_line_width)
        except (TypeError, ValueError):
            return
        for label in scene.fl_group_labels:
            state[f"fl_{label}_line_width"] = lw
            scene.set_actor_property(f"fl_{label}", line_width=lw)

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
    
    @state.change(f"fl_{label}_opacity")
    def on_opacity(**kwargs):
        scene.set_actor_property(f"fl_{label}", opacity=(kwargs.get(f"fl_{label}_opacity", 1)))
            
    @state.change(f"fl_{label}_line_width")
    def on_line_width(**kwargs):
        try:
            line_width = float(kwargs.get(f"fl_{label}_line_width", 5.0))
        except (TypeError, ValueError):
            line_width = 5.0
        scene.set_actor_property(f"fl_{label}", line_width=line_width)

# Toolbar

def build_toolbar(state, ctrl, resources):
    scene = resources.get("scene")
    init_state(state, scene)
    setup_callbacks(state, ctrl, resources)

    # Play button: shows spinner and is disabled while the vtk.js cache warms up on the first play press.  
    # In remote mode is_warming_up is always False so this has no effect there.
    with vuetify3.VBtn(
        icon=True,
        click="playing = !playing",
        variant="text",
        color="primary",
        disabled=("is_warming_up", False),
        loading=("is_warming_up", False),   # Vuetify spinner replaces icon
    ):
        vuetify3.VIcon("{{ playing ? 'mdi-pause' : 'mdi-play' }}")

    # Frame Slider
    vuetify3.VSlider(
        v_model=("current_frame", 0),
        min=0,
        max=("total_frames - 1", 0),
        step=1,
        hide_details=True,
        density="compact",
        style="max-width: 400px; margin: 0 16px;",
    )
    # Frame Chip
    vuetify3.VChip(
        "{{ frame_label }}", 
        variant="outlined", 
        size="small", 
        color="secondary",
        classes='me-3'
    )
    
    # Warmup/date chip
    vuetify3.VChip(
        "{{ is_warming_up ? 'Caching frames… ' + warmup_progress + '%' : time_label }}",
        v_show="time_label || is_warming_up",
        prepend_icon=("is_warming_up ? 'mdi-cached' : 'mdi-calendar-clock'",),
        variant="tonal",
        size="small",
        color=("is_warming_up ? 'warning' : 'info'",),
    )
    
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
            # Coloring Mode Buttons
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
            
            # Global Line Width
            vuetify3.VDivider(classes="mb-2")
            vuetify3.VLabel("Global Width", classes="text-caption text-medium-emphasis mb-1")
            
            with vuetify3.VRow(align="center", no_gutters=True, classes="mb-4"):
                with vuetify3.VCol(style="flex-grow: 1;"):
                    vuetify3.VSlider(
                        v_model=("fl_global_line_width", 5.0),
                        min=1.0, max=20.0, step=0.5,
                        hide_details=True, density="compact",
                    )
                with vuetify3.VCol(cols="auto", classes="ps-3"):
                    vuetify3.VTextField(
                        v_model=("fl_global_line_width", 5.0),
                        density="compact", style="width: 45px;",
                        type="number", variant="plain", hide_details=True,
                    )
            
            # Groups Label
            if scene and scene.fl_group_labels:
                vuetify3.VLabel("Groups", classes="text-caption text-medium-emphasis")
                vuetify3.VDivider(classes="mt-1 mb-1")
                # Build FL Group Rows
                for i, label in enumerate(scene.fl_group_labels):
                    _build_fl_group_row(label, FL_DEFAULT_COLORS[i % len(FL_DEFAULT_COLORS)])


def _build_fl_group_row(label: str, default_color: str):
    with vuetify3.VRow(
        align="center", no_gutters=True, classes="py-1",
        style="border-bottom: 1px solid rgba(128,128,128,0.15); flex-wrap: nowrap;",
    ):
        # Label Column
        with vuetify3.VCol(style="min-width: 0; flex-grow: 1; flex-shrink: 1; overflow: hidden;"):
            html.Span(
                label, classes="text-body-2",
                style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block;",
            )  

        # Color Picker
        with vuetify3.VCol(cols="auto", classes="px-1", v_show=f"fl_coloring_mode === 'custom' && fl_{label}_visible === true"):
            with vuetify3.VMenu(close_on_content_click=False):
                with vuetify3.Template(v_slot_activator="{ props }"):
                    with vuetify3.VBtn(v_bind="props", icon=True, size="small", variant="text"):
                        vuetify3.VIcon("mdi-circle", color=(f"fl_{label}_color", default_color))
                vuetify3.VColorPicker(
                    v_model=(f"fl_{label}_color", default_color),
                    modes=["hex"], show_swatches=False, width=280,
                )

        # Options Cog
        with vuetify3.VCol(cols="auto", classes="px-1", v_show=f"fl_{label}_visible"):
            with vuetify3.VMenu(close_on_content_click=False, location="bottom end"):
                with vuetify3.Template(v_slot_activator="{ props }"):
                    with vuetify3.VBtn(v_bind="props", icon="mdi-cog", size="small", variant="text", color="grey"):
                        pass
                with vuetify3.VCard(classes="pa-4", style="min-width: 300px;"):
                    html.Div("Field Line Options", classes="text-subtitle-2 mb-2")
                    with vuetify3.VSlider(
                        v_model=(f"fl_{label}_opacity", 1.0),
                        label="Opacity", min=0.0, max=1.0, step=0.05, hide_details=True, density="compact"
                    ):
                        with vuetify3.Template(v_slot_append=True):
                            vuetify3.VTextField(
                                v_model=(f"fl_{label}_opacity", 1.0),
                                density="compact", style="width: 65px", type="number", variant="plain", hide_details=True
                            )
                    
                    with vuetify3.VSlider(
                        v_model=(f"fl_{label}_line_width", 5.0),
                        label="Line Width",
                        min=1.0, max=20.0, step=0.5,
                        hide_details=True, density="compact", classes="mb-2",
                    ):
                        with vuetify3.Template(v_slot_append=True):
                            vuetify3.VTextField(
                                v_model=(f"fl_{label}_line_width", 5.0),
                                density="compact", style="width: 65px",
                                type="number", variant="plain", hide_details=True,
                            )
        
        # Switch Column
        with vuetify3.VCol(
            cols="auto", 
            classes="ps-1",
            style="display: flex; justify-content: flex-end; min-width: 48px;"
        ):
            vuetify3.VSwitch(
                v_model=(f"fl_{label}_visible", True),
                color="primary", 
                density="compact", 
                hide_details=True,
                style="height: 32px; display: inline-flex;"
            )
            