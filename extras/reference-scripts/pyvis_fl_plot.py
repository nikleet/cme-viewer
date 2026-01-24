import config
import os
import sys
import numpy as np
import pandas as pd
import pyvista as pv
from psipytools.psihdf.psihdf import *
from pyvisual.core.plot3d import Plot3d
from argparse import Namespace
from scipy import stats
import imageio.v2 as imageio
from glob import glob
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
from pyhdf.SD import *

PY_POST_PROCESSING_DIR='/opt/psi/gcc/corhel/tools/ps_python/psiweb/py_post_processing/'
sys.path.append(PY_POST_PROCESSING_DIR)
from predsci.mapfl.mapfl_sequence import get_labels, get_tracers, get_launch_points, write_labels, write_launch_points



class MplColorHelper:
    """
        Helper class to get evently spaced color samples from continuous 
        matplotlib colormaps. 
    """
    def __init__(self, cmap_name, start_val, stop_val):
        self.cmap_name = cmap_name
        self.cmap = plt.get_cmap(cmap_name)
        self.norm = mpl.colors.Normalize(vmin=start_val, vmax=stop_val)
        self.scalarMap = cm.ScalarMappable(norm=self.norm, cmap=self.cmap)

    def get_rgb(self, val):
        return self.scalarMap.to_rgba(val)


def gaussian_point_dist(center, scale, lower_bound, upper_bound, n_pts):
    dist = stats.norm(loc=center, scale=scale)
    bounds = dist.cdf([lower_bound, upper_bound])
    pp = np.linspace(*bounds, num=n_pts)
    pts = dist.ppf(pp)
    return pts


def generate_gaussian_lps(t_center=75 *(np.pi/180), p_center=np.pi, t_scale=.5, p_scale=1, n_tpts=25, n_ppts=25, rad=1.01):
    # Gaussian launch point distribution:
    tpts = gaussian_point_dist(center=t_center, scale=t_scale, lower_bound=0, upper_bound=0.999*np.pi, n_pts=n_tpts)
    ppts = gaussian_point_dist(center=p_center, scale=p_scale, lower_bound=0, upper_bound=1.999*np.pi, n_pts=n_ppts)
    rpts = np.full(n_tpts * n_ppts, rad)
    tt, pp = np.meshgrid(tpts, ppts, indexing='ij')

    # # Plot distribution
    # plt.scatter(pp, tt, s=1.5)
    # plt.xlabel('phi')
    # plt.ylabel('theta')
    # plt.savefig(os.path.join(out_dir, 'lp_distribution.png'))

    # Create launch points
    r = np.random.randint(0, 256, size=rpts.shape[0])
    g = np.random.randint(0, 256, size=rpts.shape[0])
    b = np.random.randint(0, 256, size=rpts.shape[0])
    launch_pts = np.column_stack((rpts, tt.ravel(), pp.ravel(), r, g, b))
    return launch_pts


def make_gif(img_dir, fps):
    basename = os.path.basename(os.path.norm(img_dir))
    filenames = glob(os.path.join(img_dir, '*.png'))
    with imageio.get_writer(os.path.join(img_dir, f'{basename}.gif'), mode='I', fps=fps) as writer:
        for filename in filenames:
            image = imageio.imread(filename)
            writer.append_data(image)

    
def setup_scene(br, bt, bp, **kwargs):
    
    off_screen = kwargs.get('off_screen', False)
    cmin = kwargs.get('cmin', -400)
    cmax = kwargs.get('cmax', 400)
    camera = kwargs.get('camera', None)
    chmap = kwargs.get('chmap', None)
    legend = kwargs.get('legend', None)
    title = kwargs.get('title', None)
    
    plot3d = Plot3d(pv.Plotter(off_screen=off_screen))
    plot3d.set_scene_properties()
    if chmap:
        plot3d.add_chmap(chmap)
    else:
        plot3d.add_mgram(br, cmin=cmin, cmax=cmax)
    if camera:
        plot3d.set_with_existing_camera(camera)
    else:
        plot3d.set_camera()
    if legend:
        plot3d.p.add_legned(legend)
    if title:
        plot3d.p.add_title(title, font_size=9, color='white', font='courier')
    return plot3d


def choose_cam_interactive(br, bt, bp, out_dir, **kwargs):
    
    plot3d = setup_scene(br, bp, bt, title="Set camera position... (press q when done)")
    plot3d.display_interactive_scene()
    camera = plot3d.get_camera()
    file_id = os.path.basename(os.path.normpath(out_dir))
    out_fp = os.path.join(out_dir, f'{file_id}_camera.pvcc')
    camera = camera.to_paraview_pvcc(out_fp)
    plot3d.end_session()
    return camera


def lps_from_tracers(tr_ifile, tr_header_ifile, cmap_name='gist_ncar', slice=None):
    
    # Read tracer header file and get labels
    tl_s = pd.Series(pd.read_csv(tr_header_ifile, delimiter='\t')['label'])
    labels = tl_s.unique()
    # Create dict of launch point indices keyed by labels
    tr_idxs = {}
    for label in labels:
        tr_idxs[label] = tl_s[tl_s == label].index.tolist()
        
    # Remove undesired labels
    labels = [l for l in labels if not 'tr' in l]
    labels = [l for l in labels if not 'lp' in l]
    labels = [l for l in labels if len(tr_idxs[l]) > 1]
    # Read tracer file
    sd_id = SD(tr_ifile)
    tracers = np.array(sd_id.select('Data-Set-2').get()).T
    COL = MplColorHelper(cmap_name, 0, len(labels)-1)

    # Make launch points and legend
    legend = []
    tr_lps = []
    for i, label in enumerate(labels):
        idxs = idxs[label]
        lp_coords = tracers[idxs]
        rpts = lp_coords[:,0]
        tpts = lp_coords[:,1]
        ppts = lp_coords[:,2]
        # Get color for label
        rgba = COL.get_rgb(i)     
        r = np.full(len(idxs), int(rgba[0] * 255))
        g = np.full(len(idxs), int(rgba[1] * 255))
        b = np.full(len(idxs), int(rgba[2] * 255))
        launch_pts = np.column_stack((rpts, tpts, ppts, r, g, b))
        # Slice launch points for faster plotting (optional)
        if slice:
            launch_pts = launch_pts[0::slice]
        tr_lps.append(launch_pts)
        legend.append([label, [r[0], g[0], b[0]]])
        
    return tr_lps, legend
    
    

def main():
    
    # sys.path.append(os.getenv("MAPFLPY_DIR"))
    # import psiweb.py_post_processing as py_post_processing

    # args = Namespace(bg_lp='lp.dat', cme_directory='/home/niklas/PSI/cmecme/runs/old/', 
    #                  label_select='apex,axis,arcade,ring_lp_04,ring_lp_07,ring_lp_10,ring_lp_13,ring_lp_16,background', 
    #                  launch_point_prefix='lp_', max_steps=50, max_traces=20, 
    #                  time_stamps='masTimes.txt', tracer_header='tracer_header.dat', 
    #                  tracer_prefix='tracers_pos', verbose=False)

    
    # TRACER_HEADER = '/home/niklas/PSI/cmecme/new_data/tracer_header.dat'
    # frame_num = 1
    # tracer_ifile = '/home/niklas/PSI/cmecme/new_data/tracers_pos' + str(frame_num).zfill(6) + '.hdf'
    # br = '/home/niklas/PSI/cmecme/new_data/br' + str(frame_num).zfill(6) + '.hdf'
    # bt = '/home/niklas/PSI/cmecme/new_data/bt' + str(frame_num).zfill(6) + '.hdf'
    # bp = '/home/niklas/PSI/cmecme/new_data/bp' + str(frame_num).zfill(6) + '.hdf'
    # camera = pv.Camera().from_paraview_pvcc('cameras/front/front_camera.pvcc')

    
    # launch_pts = kwargs.get('launch_pts', None)
    # closed_only = kwargs.get('closed_only', False)
    # linewidth = kwargs.get('linewidth', 2)
    
    # if not out_dir:
    #     out_dir = os.path.join(os.getcwd(), file_id)
    # os.makedirs(out_dir, exist_ok=True)  

    # br_ifiles = glob(os.path.join(run_dir, 'br*.hdf'))
    # bt_ifiles = glob(os.path.join(run_dir, 'bt*.hdf'))
    # bp_ifiles = glob(os.path.join(run_dir, 'bp*.hdf'))
    
    # # Set camera position interactively if not pre-set
    # if camera_path:
    #     camera = pv.Camera().from_paraview_pvcc(camera_path)
    # else:
    #     br = br_ifiles[-1]
    #     bt = bt_ifiles[-1]
    #     bp = bp_ifiles[-1]
    #     camera, _ = choose_cam_interactive(br, bt, bp, out_dir=out_dir, **kwargs)
    # # Render frames
    # for i, br, bt, bp in enumerate(zip(br_ifiles, bt_ifiles, bp_ifiles)):
    #     plot3d = setup_scene(br, bt, bp, camera=camera, off_screen=True, **kwargs)
    #     plot3d.add_fls(br, bt, bp, lp=launch_pts, closed_only=closed_only, linewidth=linewidth)
    #     plot3d.p.add_title(f"Frame {i+1}", font_size=9, color="white", font="courier")
    #     plot3d.export_png(ofile=os.path.join(out_dir, f"{file_id}_{i+1}.png"))
    #     plot3d.end_session()
        
    # # Create GIF from frames
    # make_gif(out_dir, fps=2)
    # print("Done.")
    
    # plot3d.display_interactive_scene()    
    pass
    

if __name__ == '__main__':
    main()