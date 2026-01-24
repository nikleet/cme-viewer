import config
import os
import numpy as np
import pyvista as pv
from pyvisual.core.plot3d import Plot3d
import matplotlib.pyplot as plt
from custom_pyvis_utils import *

# BR_IFILE = os.getenv("BR_IFILE")
# BT_IFILE = os.getenv("BT_IFILE")
# BP_IFILE = os.getenv("BP_IFILE")

# User-defined params
rad = 1.01
n_images = 11
cmin = -400
cmax = 400
cam_config = None
run_dir = 'examples/custom'
file_id = 'csheet-front'

out_dir = os.path.join(run_dir, file_id)
os.makedirs(out_dir, exist_ok=True)
out_fp = os.path.join(out_dir, file_id)    


# Set camera position interactively if not pre-set
if not cam_config:
    BR_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/br{str(n_images).zfill(6)}.hdf"
    BT_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/bt{str(n_images).zfill(6)}.hdf"
    BP_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/bp{str(n_images).zfill(6)}.hdf"
    plot3d = Plot3d()
    plot3d.set_scene_properties()
    plot3d.add_mgram(BR_IFILE, cmin=cmin, cmax=cmax)
    plot3d.add_csheet(BR_IFILE)
    plot3d.display_interactive_scene()
    cam_config = plot3d.get_camera()
    plot3d.end_session()

# Render frames
for n in range(1, n_images+1):
    print(f"Frame {n}")
    plot3d = Plot3d(pv.Plotter(off_screen=True))
    BR_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/br{str(n).zfill(6)}.hdf"
    BT_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/bt{str(n).zfill(6)}.hdf"
    BP_IFILE = f"/home/niklas/PSI/cmecme/runs/cor_mhd/bp{str(n).zfill(6)}.hdf"
    plot3d.set_scene_properties(show_axes=True)
    plot3d.add_mgram(BR_IFILE, cmin=cmin, cmax=cmax)
    plot3d.add_csheet(BR_IFILE)
    plot3d.p.add_title(f"Frame {n}", font_size=9, color="white", font="courier")
    plot3d.set_with_existing_camera(cam_config)
    plot3d.export_png(ofile=f"{out_fp}_{n}.png")
    plot3d.end_session()
    
# Create GIF from frames
make_gif(out_fp, fps=2)