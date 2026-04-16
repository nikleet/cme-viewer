# utils.py
import numpy as np
import datetime as dt
from glob import glob
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
from pathlib import Path

from pyvisual.core.mesh3d import build_slice_polydata, build_spline_polydata
import pyvisual.core.parsers as parsers

# ========= COLOR UTILITIES =========
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

    def get_rgba(self, val):
        r, g, b, a = self.scalarMap.to_rgba(val)
        return int(r * 255), int(g * 255), int(b * 255), a


# ========= TIME UTILITIES =========

def round_seconds(obj: dt.datetime) -> dt.datetime:
    if obj.microsecond >= 500_000:
        obj += dt.timedelta(seconds=1)
    return obj.replace(microsecond=0)


def mastime_to_ut(mas_times: str, t0: dt.datetime = None) -> list[dt.datetime]:
    """
    Converts mastimes dict to a list of UT datetimes.
    
    fname:  dict of sequence and mastimes from dumps or masTime.txt file  
    t0:     datetime initial time at start of run
    
    Returns:
    times_ut        A list of UT datetimes.
    """

    t_mas = np.asarray(list(mas_times.values()))
    
    # Convert MAS times to UT time
    t_fac_mas = 1445.87 / (3600) 
    t_hrs = t_mas*t_fac_mas

    if not t0:
        # If no initial time is given, will begin from Jan 1, 1990
        t0 = dt.datetime(1990, 1, 1)
        print("No initial time is given, will begin from Jan 1, 1990")
    
    times_ut = []
    for j in range(0,len(t_hrs)):
        t_shift = round_seconds(t0 + dt.timedelta(hours=t_hrs[j]))
        times_ut.append(t_shift)

    return times_ut
    
# taken from psipytools.tbd.trace.mapfl
def get_hdf_times(fname):
    """retrieves hdf time stamps from file"""
    times = dict()
    with open(fname) as f:
        for i, line in enumerate(f.readlines()):
            row = line.strip().split()
            if len(row) == 2:
                t_, t_val = line.strip().split()
            else:
                t_ = '{:03d}'.format(i+1) # steps begin at 1
                t_val = row[0]
            times[t_] = float(t_val)
    return times

# ======== MESH UTILITIES =========

def create_mgram_mesh(r, t, p, values=None, frame='spherical'):
    """
    Create a 3D spherical magnetogram mesh.
    """
    # Infer the slice axis (constant R, T, or P)
    mesh_shape = (np.size(r), np.size(t), np.size(p))
    try:
        # Find the index of the dimension with size 1
        axis = next(i for i, s in enumerate(mesh_shape) if s == 1)
    except StopIteration:
        # Fallback to radial slice if not specified
        axis = 0

    # Broadcast 1D axes to 3D grid
    r_3d, t_3d, p_3d = parsers.parse_grid_mesh(r, t, p)
    
    # Build the PolyData (points still in Spherical coordinates)
    mesh = build_slice_polydata(r_3d, t_3d, p_3d, axis=axis, frame=frame)
    
    # Align scalar data with the mesh points and add to the mesh
    if values is not None:
        mesh['data'] = parsers.parse_data(values, r_3d.shape, axis=axis)
        mesh.set_active_scalars('data')

    # Transform to cartensian coordinates
    mesh = parsers.apply_mesh_transform(mesh, frame, 'cartesian')
        
    return mesh


def create_fieldline_mesh(r, t, p, data=None, frame='spherical'):
    """
    Create line-connected fieldline mesh transformed to physical space.
    """
    # Validate and normalize stacked coordinates
    r, t, p = parsers.parse_stack_mesh(r, t, p)
    
    # Build splines
    mesh = build_spline_polydata(r, t, p, axis=0, frame=frame)
    
    if data is not None:
        mesh['data'] = parsers.parse_data(data, r.shape, axis=0)
        mesh.set_active_scalars('data')

    # Transform to cartensian coordinates
    mesh = parsers.apply_mesh_transform(mesh, frame, 'cartesian')
        
    return mesh

# ========= IO UTILITIES =========

def get_mag_files(data_dir: Path):
    data_dir = str(data_dir)
    br_files = glob(data_dir + '/br*')
    bt_files = glob(data_dir + '/bt*')
    bp_files = glob(data_dir + '/bp*')
    return list(zip(br_files, bt_files, bp_files))


# def get_launch_points(fname):
#     """load launch points from launch_pts.dat file
#     format is r\tt\tp\tred\tgreen\tblue
#     """
#     r_posns, theta_posns, phi_posns = [], [], []
#     with open(fname, 'r') as bg_file:
#         bg_file.readline()
#         for line in bg_file.readlines():
#             # r_pos, theta_pos, phi_pos, _, _, _ = [float(col_) for col_ in line.split('\t')]
#             r_pos, theta_pos, phi_pos = [float(col_) for col_ in line.split('\t')]
#             r_posns.append(r_pos)
#             theta_posns.append(theta_pos)
#             phi_posns.append(phi_pos)
#     return np.array(r_posns), np.array(theta_posns), np.array(phi_posns)


# def write_labels(labels, fname):
#     with open(fname, 'w') as label_file:
#         label_file.write('\t'.join(list('rtp')) + '\n')
#         for label in labels:
#             label_file.write(label + '\n')
            

# def write_launch_points(args):
#     times = get_hdf_times('{}/{}'.format(args.cme_directory, args.time_stamps))

#     # choose every other launch_pts from 3 - 17
#     label_select = args.label_select.split(',')

#     for step_name in get_steps(list(times.keys()), args.max_steps):
#         # time = times[step_name]

#         hdf_filename = '{}/{}{}.hdf'.format(args.cme_directory, args.tracer_prefix, step_name)
#         try:
#             r, theta, phi = get_tracers(hdf_filename)
#         except:
#             print('could not get tracers from {}'.format(hdf_filename))
#             raise

#         labels = get_labels('{}/{}'.format(args.cme_directory, args.tracer_header))


#         print('number of labels:{}'.format(len(labels)))

#         if args.bg_lp is not None:
#             r_bg, theta_bg, phi_bg = get_launch_points(args.bg_lp)
#             r = np.hstack((r, r_bg))
#             theta = np.hstack((theta, theta_bg))
#             phi = np.hstack((phi, phi_bg))
#             labels.extend(len(phi_bg)*['background'])
#             print('after adding background, number of labels:{}'.format(len(labels)))
#             # have to do this for forward and reverse?


#         labels, label_ids, label_orig = np.unique(
#             np.array(labels),
#             return_index=True,
#             return_inverse=True, # access original indices
#             )

#         r_group, theta_group, phi_group, label_group = [], [], [], []
#         for label_id, label in enumerate(labels):
#             group_ids = np.where(label_orig == label_id)[0]
#             if label not in ['background']:
#                 group_ids = group_ids[::get_cadence(group_ids, args.max_traces)]
#             if label in label_select:
#                 r_group.append(r[group_ids])
#                 theta_group.append(theta[group_ids])
#                 phi_group.append(phi[group_ids])
#                 label_group.append(len(group_ids)*[label])
#         r_select = np.hstack(r_group)
#         theta_select = np.hstack(theta_group)
#         phi_select = np.hstack(phi_group)
#         label_select = np.hstack(label_group)

#         with open('lp_{}.dat'.format(step_name), 'w') as lp_file:
#             lp_file.write('\t'.join(list('rtp')) + '\n')
#             for i in range(len(r_select)):
#                 lp_file.write('{:e}\t{:e}\t{:e}'.format(
#                     r_select[i], theta_select[i], phi_select[i]) + '\n')

#         write_labels(label_select, 'tracer_header_select.dat')
        

# def cache_lps(cfg: RunConfig):
#     """
#     Caches launch points for the entire run in dat/cache. The following keys are
#     expected to be defined in the RunConfig:
#         cme_directory,
#         time_stample,
#         tracer_header,
#         tracer_prefix,
#         max_traces,
#         label_select
    
#     Parameters
#     ----------
#     cfg : RunConfig     An object containing information about the run.
#     """
#     app_dir = os.getcwd()
#     os.chdir('dat/cache/')
#     write_launch_points(cfg)
#     os.chdir(app_dir)
    
    
# def get_cached_lps(lp_ifile = None):
#     # TODO: Might want to check that the cwd is actually the install dir
#     # TODO: Might want to move to frame.py and combine with get_launch_points
#     # lp_ifile = cache_dir / f"{"lp_"}{step_index:06d}"
#     if not os.path.exists(lp_ifile):
#         print(f"Failed to find {lp_ifile} in cache.")
#         return None
#     r_posns, theta_posns, phi_posns = get_launch_points(lp_ifile)
#     return r_posns, theta_posns, phi_posns


# def get_tracers(hdf_filename):
#     """gets tracer data in r, theta, phi"""
#     # Open the HDF file
#     sd_id = h4.SD(hdf_filename)

#     #Read dataset.  In all PSI hdf4 files, the
#     #data is stored in "Data-Set-2":
#     sds_id = sd_id.select('Data-Set-2')
#     f = sds_id.get()
#     return f


# def get_labels(fname):
#     """retrieves labels from a tracer header file"""
#     with open(fname) as label_file:
#         label_file.readline() # header
#         labels = [label.strip() for label in label_file.readlines()]
#     return labels

# # ========= LAUNCH POINTS UTILITIES =========

# def get_steps(steps, max_steps=None):
#     """
#     max = 1: use end step
#     max = 2: use start and end step
#     max = 3: use start, middle, end
#     max = 4: start, middle, middle, end
#     """
#     if max_steps is not None:
#         max_steps = min(max_steps, len(steps))
#         indices = np.linspace(0, len(steps)-1, max_steps).astype(int)
#         return np.array(steps)[indices].tolist()

#     return steps


# def get_cadence(fl, max_points):
#     '''get the maximum sampling cadence for this field line'''
#     return max(1, int(len(fl)/max_points))

# def lps_from_tracer(args, step_name=None, return_groups=False):
#     # times = get_hdf_times('{}/{}'.format(args.cme_directory, args.time_stamps))
#     # choose every other launch_pts from 3 - 17
#     label_select = args.label_select.split(',')

#     # time = times[step_name]

#     hdf_filename = '{}/{}{}.hdf'.format(args.cme_directory, args.tracer_prefix, step_name)
    
#     print(f'getting tracers from {hdf_filename}')
#     try:
#         r, theta, phi = get_tracers(hdf_filename)
#     except:
#         print('could not get tracers from {}'.format(hdf_filename))
#         raise

#     labels = get_labels('{}/{}'.format(args.cme_directory, args.tracer_header))


#     print('number of labels:{}'.format(len(labels)))


#     labels, label_ids, label_orig = np.unique(
#         np.array(labels),
#         return_index=True,
#         return_inverse=True, # access original indices
#         )

#     r_group, theta_group, phi_group, label_group = [], [], [], []
#     for label_id, label in enumerate(labels):
#         group_ids = np.where(label_orig == label_id)[0]
#         # if label not in ['background']:
#         #     group_ids = group_ids[::get_cadence(group_ids, args.max_traces)]
#         if label in label_select:
#             r_group.append(r[group_ids])
#             theta_group.append(theta[group_ids])
#             phi_group.append(phi[group_ids])
#             label_group.append(len(group_ids)*[label])

#     if return_groups:
#         group_labels = [labels_of_group[0] for labels_of_group in label_group]
#         return r_group, theta_group, phi_group, group_labels
      
#     r_select = np.hstack(r_group)
#     theta_select = np.hstack(theta_group)
#     phi_select = np.hstack(phi_group)
#     label_select = np.hstack(label_group)
    
#     return r_select, theta_select, phi_select, label_select