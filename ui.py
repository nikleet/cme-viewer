# ui.py

import asyncio
from trame.widgets import vuetify3

# Delay in seconds between frames
FRAME_TIME = 0.1 

def setup_callbacks(state, ctrl, resources):
    """
    Define all state change behaviors here.
    """
    scene = resources.get("scene")
    
    # Playback Loop
    @state.change("playing")
    async def on_play(playing, **kwargs):
        while state.playing:
            # Increment frame, loop back to 0 if at the end
            next_frame = (state.current_frame + 1) % state.total_frames
            state.current_frame = next_frame
            
            # Force Trame to sync the state (moving the slider) right now
            state.flush()
            
            # Yield control so the UI doesn't freeze
            await asyncio.sleep(FRAME_TIME)

    # Frame Change Handler
    @state.change("current_frame")
    def on_frame_change(current_frame, **kwargs):
        if scene:
            # Update the underlying PyVista actors
            scene.set_frame(current_frame)
            
            # Update the label (Future timestamp code goes here!)
            # Example: state.frame_label = get_timestamp_for_frame(current_frame)
            state.frame_label = f"Frame: {current_frame}"
            
            # Push the updated meshes to the browser renderer
            if ctrl.view_update:
                ctrl.view_update()


def build_toolbar(state, ctrl, resources):
    """
    Builds the top toolbar UI components.
    """
    scene = resources.get("scene")
    
    # Initialize UI state variables
    state.total_frames = scene.total_frames if scene else 1
    state.current_frame = 0
    state.playing = False
    state.frame_label = "Frame: 0"
    
    # Register callbacks
    setup_callbacks(state, ctrl, resources)

    # Build the Vuetify 3 layout
    with vuetify3.VRow(align="center", no_gutters=True, style="width: 100%; padding: 0 16px;"):
        
        # Play/Pause Button
        # Clicking toggles the 'playing' boolean, which triggers the @state.change("playing") callback
        with vuetify3.VBtn(
            icon=True, 
            click="playing = !playing", 
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