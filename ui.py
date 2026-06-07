# ui.py

import asyncio
from trame.widgets import vuetify3, html

FRAME_TIME_DEFAULT = 0.3

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



# ── State ──────────────────────────────────────────────────────────────────────

def init_state(state, scene):
    state.total_frames     = scene.total_frames if scene else 1
    state.current_frame    = 0
    state.playing          = False
    state.frame_label      = "Frame: 1"
    state.time_label       = ""
    state.drawer           = False
    state.open_panels      = ["playback", "mgram", "fl"]  # playback panel open by default
    state.mgram_visible    = True
    state.mgram_cmap       = "seismic"
    state.mgram_clim_min   = -10.0
    state.mgram_clim_max   = 10.0
    state.fl_coloring_mode = "random"
    state.fl_global_line_width = 5.0
    # Playback
    state.frame_time       = FRAME_TIME_DEFAULT  # user-adjustable frame duration in seconds
    state.is_rendering     = False               # True while a frame is being processed
    state.is_warming_up    = False
    state.warmup_progress  = 0
    if scene:
        initial_time = scene.get_frame_time(0)
        if initial_time:
            state.time_label = initial_time.strftime("%Y-%m-%d %H:%M:%S")
        for i, label in enumerate(scene.fl_group_labels):
            state[f"fl_{label}_visible"]    = True
            state[f"fl_{label}_color"]      = FL_DEFAULT_COLORS[i % len(FL_DEFAULT_COLORS)]
            state[f"fl_{label}_opacity"]    = 1.0
            state[f"fl_{label}_line_width"] = 5.0


# ── Callbacks ──────────────────────────────────────────────────────────────────

def setup_callbacks(state, ctrl, resources):
    scene        = resources.get("scene")
    _loop_id     = [0]
    _is_updating = [False]
    is_local     = scene and scene.mode == 'local'
    _warmed_up   = [not is_local]

    # ── Playback ──────────────────────────────────────────────────────────────

    @state.change("playing")
    async def on_play(playing, **kwargs):
        if not playing:
            return

        # ── Local mode: warm up vtk.js array cache on first play ─────────────
        if not _warmed_up[0]:
            _warmed_up[0] = True
            state.playing = False
            state.is_warming_up = True
            state.warmup_progress = 0
            state.flush()

            def report_progress(done, total):
                state.warmup_progress = int(done / total * 100)
                state.flush()

            await scene._warm_up_vtk_cache(on_progress=report_progress)
            state.is_warming_up = False
            state.warmup_progress = 100
            state.playing = True
            state.flush()
            return
        # ─────────────────────────────────────────────────────────────────────

        _loop_id[0] += 1
        my_id = _loop_id[0]
        loop  = asyncio.get_running_loop()

        while state.playing and _loop_id[0] == my_id:
            t_start    = loop.time()
            next_frame = (state.current_frame + 1) % state.total_frames

            # --- Update geometry (synchronous) ----------------------
            # Set is_rendering=True and advance the slider in one atomic flush.
            # state.flush() is synchronous: it pushes the state to the browser
            # AND calls on_frame_change inline, which calls scene.set_frame().
            # By the time flush() returns, the new geometry is loaded but NOT
            # yet sent to the browser; that happens when pushing to the browser..
            state.is_rendering  = True
            state.current_frame = next_frame
            state.flush()

            # Immediately check whether pause was pressed during the render.
            # If so, discard this frame rather than pushing it to the browser.
            if not state.playing or _loop_id[0] != my_id:
                state.is_rendering = False
                state.flush()
                break

            # --- Push to browser (yield first) ----------------------
            # Yielding before view_update lets the event loop drain any queued
            # events (play/pause clicks, camera drags) before spending time on
            # the potentially-heavy WebSocket push. This should hopefully keep the UI responsive.
            await asyncio.sleep(0)

            if ctrl.view_update:
                ctrl.view_update()

            state.is_rendering = False
            # is_rendering=False will be batched into the next state.flush().

            # --- Wall-clock throttle --------------------------------
            # Sleep only what remains of the frame budget, accounting for the
            # time already spent in Phases 1 and 2. This prevents:
            #   • Acceleration when rendering is fast (no extra sleep = no gap).
            #   • Rubberbanding when rendering is slow (remaining ≤ 0 = no sleep).
            elapsed   = loop.time() - t_start
            budget    = max(0.1, float(getattr(state, 'frame_time', FRAME_TIME_DEFAULT)))
            remaining = budget - elapsed
            if remaining > 0.005:
                await asyncio.sleep(remaining)

    @state.change("current_frame")
    def on_frame_change(current_frame, **kwargs):
        """
        Updates geometry and labels for the given frame.

        During playback:  only loads geometry; on_play handles the view push.
        During scrubbing: also calls ctrl.view_update() for immediate feedback.

        Keeping view_update OUT of this callback during playback eliminates
        the "backed-up frames" problem: there is now exactly one view push per
        loop iteration, called after yielding, so the browser queue never grows.
        """
        if _is_updating[0]:
            return
        _is_updating[0] = True
        try:
            if scene:
                scene.set_frame(current_frame)
                state.frame_label = f"Frame: {current_frame + 1}"
                frame_time_val    = scene.get_frame_time(current_frame)
                state.time_label  = (
                    frame_time_val.strftime("%Y-%m-%d %H:%M:%S")
                    if frame_time_val else ""
                )
                # Push immediately only when the user is manually scrubbing.
                # During playback this is handled by on_play (Phase 2 above).
                if not state.playing and ctrl.view_update:
                    ctrl.view_update()
        finally:
            _is_updating[0] = False

    # --- Magnetogram ------------------------------------------------ 

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

    # --- Fieldlines ------------------------------------------------ 

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

# ── Toolbar ────────────────────────────────────────────────────────────────────

def build_toolbar(state, ctrl, resources):
    scene = resources.get("scene")
    init_state(state, scene)
    setup_callbacks(state, ctrl, resources)

    # Play / Pause
    # `loading` + `disabled` only during warmup; during is_rendering the button
    # stays clickable so the user can pause mid-frame without waiting.
    with vuetify3.VBtn(
        icon=True,
        click="playing = !playing",
        variant="text",
        color="primary",
        disabled=("is_warming_up", False),
        loading=("is_warming_up", False),
    ):
        vuetify3.VIcon("{{ playing ? 'mdi-pause' : 'mdi-play' }}")

    # Thin indeterminate bar at the toolbar bottom — visible while a frame is
    # actively being rendered during playback. Tells the user "something is
    # happening" without blocking interaction.
    vuetify3.VProgressLinear(
        v_show="is_rendering && playing",
        indeterminate=True,
        color="primary",
        style=(
            "position: absolute; bottom: 0; left: 0; right: 0;"
            " height: 3px; margin: 0; border-radius: 0; z-index: 10;"
        ),
    )

    vuetify3.VSlider(
        v_model=("current_frame", 0),
        min=0,
        max=("total_frames - 1", 0),
        step=1,
        hide_details=True,
        density="compact",
        style="max-width: 400px; margin: 0 16px;",
    )
    vuetify3.VChip(
        "{{ frame_label }}",
        variant="outlined",
        size="small",
        color="secondary",
        classes="me-3",
    )
    # Warmup/date chip
    vuetify3.VChip(
        "{{ is_warming_up ? 'Caching frames… ' + warmup_progress + '%' : time_label }}",
        v_show="time_label || is_warming_up",
        variant="tonal",
        size="small",
        **{
            ":prepend-icon": "is_warming_up ? 'mdi-cached' : 'mdi-calendar-clock'",
            ":color": "is_warming_up ? 'warning' : 'info'",
        }
    )
    vuetify3.VSpacer()



# ── Sidebar ────────────────────────────────────────────────────────────────────

def build_sidebar(state, resources):
    scene = resources.get("scene")
    with vuetify3.VContainer(fluid=True, classes="pa-3"):
        vuetify3.VListSubheader("Scene Controls", classes="px-0 mb-2")

        with vuetify3.VExpansionPanels(
            multiple=True,
            v_model=("open_panels", ["playback", "mgram", "fl"]),
        ):
            _build_playback_panel()   # ← new, first so it's immediately visible
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


def _build_playback_panel():
    """Frame duration slider and single-step buttons."""
    with vuetify3.VExpansionPanel(value="playback", title="Playback"):
        with vuetify3.VExpansionPanelText():

            # Frame duration (= time budget per frame)
            vuetify3.VLabel(
                "Frame Duration (s)",
                classes="text-caption text-medium-emphasis",
            )
            with vuetify3.VRow(align="center", no_gutters=True, classes="mt-1 mb-4"):
                with vuetify3.VCol(style="flex-grow: 1;"):
                    vuetify3.VSlider(
                        v_model=("frame_time", FRAME_TIME_DEFAULT),
                        min=0.1,
                        max=3.0,
                        step=0.1,
                        hide_details=True,
                        density="compact",
                    )
                with vuetify3.VCol(cols="auto", classes="ps-2"):
                    vuetify3.VTextField(
                        v_model=("frame_time", FRAME_TIME_DEFAULT),
                        density="compact",
                        style="width: 65px;",
                        type="number",
                        variant="plain",
                        hide_details=True,
                    )

            # Single-step buttons (disabled during playback)
            vuetify3.VLabel("Step", classes="text-caption text-medium-emphasis")
            with vuetify3.VRow(no_gutters=True, classes="mt-1"):
                with vuetify3.VCol(cols=6, classes="pr-1"):
                    vuetify3.VBtn(
                        "← Prev",
                        click="current_frame = Math.max(0, current_frame - 1)",
                        variant="outlined",
                        density="compact",
                        block=True,
                        size="small",
                        disabled=("playing", False),
                    )
                with vuetify3.VCol(cols=6, classes="pl-1"):
                    vuetify3.VBtn(
                        "Next →",
                        click="current_frame = Math.min(total_frames - 1, current_frame + 1)",
                        variant="outlined",
                        density="compact",
                        block=True,
                        size="small",
                        disabled=("playing", False),
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
            