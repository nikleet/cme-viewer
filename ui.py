# ui.py

import asyncio
from trame.widgets import vuetify3

# Delay in seconds between frames
FRAME_TIME = 0.1 

def setup_callbacks(state, ctrl, resources):
    """
    Define state change behaviors here.
    """
    scene = resources.get("scene")
        
    def toggle_play():
        state.playing = not state.playing
        
    ctrl.toggle_play = toggle_play
    # Prevent race conditions from simultaneous play loops
    state.is_loop_running = False
    
    # Playback Loop
    @state.change("playing")
    async def on_play(playing, **kwargs):
        # If turning off, or if a loop is already running, do nothing
        if not playing or state.is_loop_running:
            return
            
        state.is_loop_running = True
        try:
            while state.playing:
        
                # Suggested by AI (idk about this): Micro-yield: Let the server process any pending "Pause" clicks before locking up the thread
                await asyncio.sleep(0.001)
                    
                # Increment frame, loop back to 0 if at the end
                next_frame = (state.current_frame + 1) % state.total_frames
                state.current_frame = next_frame
                
                # Ensure state changes are sent to the client immediately (don't wait for the end of the function)
                state.flush() 
                
                # Wait for the designated frame time
                await asyncio.sleep(FRAME_TIME)
        finally:
            state.is_loop_running = False


    # Frame Change Handler
    @state.change("current_frame")
    async def on_frame_change(current_frame, **kwargs):
        if scene:
            scene.set_frame(current_frame)
            
            if scene.get_frame_time(current_frame) is not None:
                state.frame_label = f"Time: {scene.get_frame_time(current_frame)}"
            else:
                state.frame_label = f"Frame: {current_frame + 1}"

            if ctrl.view_update:
                ctrl.view_update()
            
            # Still needed?
            # Yield to the event loop so user interactions (slider drags, button clicks) can be processed between frame pushes.
            await asyncio.sleep(0)


def build_toolbar(state, ctrl, resources):
    """
    Builds the top toolbar UI components.
    """
    scene = resources.get("scene")
    
    # Initialize UI state variables
    state.total_frames = scene.total_frames if scene else 1
    state.current_frame = 0
    state.playing = False
    if scene.get_frame_time(0) is not None:
        state.frame_label = f"Time: {scene.get_frame_time(0)}"
    else:
        state.frame_label = "Frame: 1"
    
    # Register callbacks
    setup_callbacks(state, ctrl, resources)

    # Build the Vuetify 3 layout
    with vuetify3.VRow(align="center", no_gutters=True, style="width: 100%; padding: 0 16px;"):
        
        # Play/Pause Button
        # Clicking toggles the 'playing' boolean, which triggers the @state.change("playing") callback
        with vuetify3.VBtn(
            icon=True, 
            click=ctrl.toggle_play, 
            variant="text",
            color="primary"
        ):
            # Dynamically switch the icon based on the 'playing' state
            vuetify3.VIcon("{{ playing ? 'mdi-pause' : 'mdi-play' }}")

        # Progress Slider
        vuetify3.VSlider(
            v_model=("current_frame", 0),
            min=0,
            max=("total_frames - 1", 0), # 0-indexed to match your list of cached frames
            step=1,
            hide_details=True,
            density="compact",
            style="max-width: 400px; margin: 0 16px;"
        )

        # Frame/Timestamp Label
        vuetify3.VChip(
            "{{ frame_label }}",
            variant="outlined",
            size="small",
            color="secondary"
        )
        
        # Pushes everything to the left
        vuetify3.VSpacer()