import numpy as np
from glob import glob
from mapflpy.scripts import run_forward_tracing
from mapflpy.data import fetch_cor_magfiles
from mapflpy.utils import fetch_default_launch_points
from psi_io import read_hdf_by_index

from pyvisual.core.plot3d import Plot3d
import pyvista as pv
from pyvista.trame.ui.vuetify3 import button
from pyvista.trame.ui.vuetify3 import divider
from pyvista.trame.ui.vuetify3 import select
from pyvista.trame.ui.vuetify3 import slider
from pyvista.trame.ui.vuetify3 import text_field


def get_mag_files(data_folder):
    br_files = glob(data_folder + '/br*')
    bt_files = glob(data_folder + '/bt*')
    bp_files = glob(data_folder + '/bp*')
    return list(zip(br_files, bt_files, bp_files))

def make_sun_actors(plotter: pv.Plotter, mag_files):
    values, r, t, p = read_hdf_by_index(0, None, None, ifile=mag_files[0])
    mgram_actor = plotter.add_2d_slice(r, t, p, values, clim=(-1e1, 1e1), cmap='seismic', v_name='Radial Boundary')
    lps = fetch_default_launch_points(100)
    traces = run_forward_tracing(*mag_files, launch_points=lps)
    trace_geometry = traces.geometry
    mask = trace_geometry[:, 0, :] > 100
    a = np.where(mask[:, None, :], np.nan, trace_geometry)
    trace_r, trace_t, trace_p = (a[:, i, :] for i in range(3))
    fl_actor = plotter.add_fieldlines(trace_r, trace_t, trace_p,
                                            coloring='random',
                                            cmap='hsv',
                                            n_colors=256,
                                            line_width=1)
    return [fl_actor, mgram_actor]



def main():
    data_folder = '/home/niklas/PSI/cmecme/2024-data/new_data/run-data'    
    mag_files_seq = get_mag_files(data_folder)
    N_FRAMES = len(mag_files_seq)
    
    plotter = Plot3d()
    plotter.add_axes()
    
    current_actors = []
    current_actors[:] = make_sun_actors(plotter, mag_files_seq[0])

    frame_text = plotter.add_text("Frame: 0", position="upper_left", font_size=14, name="frame_text")

    def slider_callback(value):
        frame = int(round(value))
        mag_files = mag_files_seq[frame]
        
        # Remove previous actors (ignore errors if actor already removed)
        for actor in list(current_actors):
            try:
                # pass reset_camera=False to avoid resetting the camera each time
                plotter.remove_actor(actor, reset_camera=False)
            except Exception:
                # ignore if actor not present
                pass
        current_actors.clear()
        # Add new actors for this frame
        current_actors[:] = make_sun_actors(plotter, mag_files)
        
        # Update the frame text
        try:
            # remove and re-add named text (safe and simple)
            plotter.remove_actor("frame_text", reset_camera=False)
        except Exception:
            pass
        plotter.add_text(f"Frame: {frame}", position="upper_left", font_size=14, name="frame_text")
        
        # Render the updated scene
        plotter.render()
        
        
    # Add slider widget to plotter
    plotter.add_slider_widget(
        callback=slider_callback,
        rng=[0, N_FRAMES - 1],
        value=0,
        title="Time (frame)",
        style="modern",
        )
    
    # plotter.show(auto_close=False, interactive_update=True)
    plotter.show()
    
    
if __name__ == "__main__":
    main()
