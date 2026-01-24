import psipytools.psihdf
import psipytools.util
import config
import os
import numpy as np
import pyvista as pv
from pyvisual.core.plot3d import Plot3d
import matplotlib.pyplot as plt
from custom_pyvis_utils import *
import pickle
import dill
import psipytools

BR_IFILE = os.getenv("BR_IFILE")
BT_IFILE = os.getenv("BT_IFILE")
BP_IFILE = os.getenv("BP_IFILE")
MGRAM_IFILE = os.getenv("MGRAM_IFILE")

# User-defined params
n_tpts = 25
n_ppts = 25
t_scale = .25
p_scale = .5
t_center = 75 * (np.pi / 180)
p_center = np.pi
rad = 1.01
n_images = 11
cmin = -400
cmax = 400
linewidth = 0.5
closed_only = False
camera = None
run_dir = 'custom_2'

user_input = input("Enter name of camera position: ")

file_id = user_input
out_dir = os.path.join(run_dir, file_id)
os.makedirs(out_dir, exist_ok=True)
out_fp = os.path.join(out_dir, file_id)    

# Gaussian point dist:
tpts = gaussian_point_dist(center=t_center, scale=t_scale, lower_bound=0, upper_bound=0.999*np.pi, n_pts=n_tpts)
ppts = gaussian_point_dist(center=p_center, scale=p_scale, lower_bound=0, upper_bound=1.999*np.pi, n_pts=n_ppts)
rpts = np.full(n_tpts * n_ppts, rad)
tt, pp = np.meshgrid(tpts, ppts, indexing='ij')

# # Plot point distribution
# plt.scatter(pp, tt, s=1.5)
# plt.xlabel('phi')
# plt.ylabel('theta')
# plt.savefig(os.path.join(out_dir, 'lp_dist.png'))

# Create launch points
r = np.random.randint(0, 256, size=rpts.shape[0])
g = np.random.randint(0, 256, size=rpts.shape[0])
b = np.random.randint(0, 256, size=rpts.shape[0])
launch_pts = np.column_stack((rpts, tt.ravel(), pp.ravel(), r, g, b))

plot3d = Plot3d()
plot3d.set_scene_properties()
br_r, br_t, br_p, br = psipytools.psihdf.rdhdf_3d(MGRAM_IFILE)
plot3d.add_chmap(MGRAM_IFILE, r=1, cmin=cmin, cmax=cmax)
splines = plot3d.add_fls(BR_IFILE, BT_IFILE, BP_IFILE, lp=launch_pts, closed_only=closed_only, linewidth=linewidth)
plot3d.p.add_title(f"Set camera position...", font_size=9, color="white", 
                font="courier")
plot3d.set_camera()
plot3d.display_interactive_scene()
camera = plot3d.get_camera()
camera.to_paraview_pvcc(os.path.join(out_dir, f'{file_id}_camera.pvcc'))
plot3d.end_session()