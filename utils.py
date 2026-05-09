# utils.py
import numpy as np
import datetime as dt
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
from pathlib import Path
import pyhdf.SD as h4

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

def get_mag_files(data_dir: Path) -> list[tuple]:
    """Returns list of (br, bt, bp) file path tuples from data directory."""
    br_files = sorted(data_dir.glob('br*'))
    bt_files = sorted(data_dir.glob('bt*'))
    bp_files = sorted(data_dir.glob('bp*'))
    return list(zip(br_files, bt_files, bp_files))


def read_lps(fname: Path) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Reads launch point positions from file, returns (r, theta, phi) arrays or None if not found."""
    if not fname.exists():
        print(f"Failed to find launch point file: {fname}.")
        return None

    r_posns, theta_posns, phi_posns = [], [], []
    with open(fname, 'r') as lp_file:
        lp_file.readline()  # skip header
        for line in lp_file.readlines():
            r_pos, theta_pos, phi_pos = [float(col) for col in line.split('\t')]
            r_posns.append(r_pos)
            theta_posns.append(theta_pos)
            phi_posns.append(phi_pos)
    return np.array(r_posns), np.array(theta_posns), np.array(phi_posns)


def read_labels(fname: Path) -> list[str]:
    """Reads labels from a tracer header file."""
    with open(fname) as label_file:
        label_file.readline()  # skip header
        labels = [label.strip() for label in label_file.readlines()]
    return labels


def read_tracers(hdf_filename: Path) -> np.ndarray:
    """Reads tracer data in (r, theta, phi) from an HDF4 file."""
    sd_id = h4.SD(str(hdf_filename))
    sds_id = sd_id.select('Data-Set-2')
    return sds_id.get()


def write_labels(fname: Path, labels: list[str]) -> None:
    """Writes labels to file with r/t/p header."""
    with open(fname, 'w') as label_file:
        label_file.write('\t'.join(list('rtp')) + '\n')
        for label in labels:
            label_file.write(label + '\n')


def write_lps(lp_fpath: Path, r_lps, theta_lps, phi_lps) -> None:
    """Writes launch point positions to file with r/t/p header."""
    with open(lp_fpath, 'w') as lp_file:
        lp_file.write('\t'.join(list('rtp')) + '\n')
        for r, theta, phi in zip(r_lps, theta_lps, phi_lps):
            lp_file.write(f'{r:e}\t{theta:e}\t{phi:e}\n')


# ========= LAUNCH POINTS UTILITIES =========

def get_steps(steps, max_steps=None):
    """
    max = 1: use end step
    max = 2: use start and end step
    max = 3: use start, middle, end
    max = 4: start, middle, middle, end
    """
    if max_steps is not None:
        max_steps = min(max_steps, len(steps))
        indices = np.linspace(0, len(steps)-1, max_steps).astype(int)
        return np.array(steps)[indices].tolist()

    return steps


def get_cadence(fl, max_points):
    '''get the maximum sampling cadence for this field line'''
    return max(1, int(len(fl)/max_points))


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