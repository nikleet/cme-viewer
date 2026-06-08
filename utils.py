# utils.py
import logging
import numpy as np
import datetime as dt
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm
import pyvista as pv
from pathlib import Path
import pyhdf.SD as h4
from pyparsing import Optional

# PSI Imports
from pyvisual.core.mesh3d import build_slice_polydata, build_spline_polydata
import pyvisual.core.parsers as parsers
import astropy.units as u
import sunpy.sun.constants as sun_constants
from pyvisual.core._styling import (
    RANDOM_COLORING_DEFAULTS,
    FL_POLARITY_COLORING_DEFAULTS,
    FIELDLINE_KWARGS,
)

logger = logging.getLogger(__name__)


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


def fl_plot_kwargs(coloring: str | None, **kwargs) -> dict:
        """Translates a coloring mode into kwargs for pyvista.Plotter.add_mesh."""
        match coloring:
            case 'random':
                return RANDOM_COLORING_DEFAULTS | {
                    'scalars': 'line_index',
                    'clim': (0, 255),
                    'n_colors': 256,
                } | kwargs
            case 'polarity':
                return FL_POLARITY_COLORING_DEFAULTS | FIELDLINE_KWARGS | {
                    'scalars': 'polarity'
                } | kwargs
            case _:
                return kwargs

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

def parse_datetime(time_str: Optional[str], domain_label: str) -> dt.datetime:
    """Converts configuration time strings into standard datetime objects.

    Defaults to January 1st, 1990 if the input string is absent.

    Parameters
    ----------
    time_str : str | None
        Optional string representing the date and time in '%m/%d/%Y %H:%M:%S' format.
    domain_label : str
        String identifier used to clarify logging output if the fallback is triggered.

    Returns
    -------
    dt_obj : datetime
        A rounded datetime object representing the start epoch.
    """
    if time_str:
        dt_obj = dt.datetime.strptime(time_str, '%m/%d/%Y %H:%M:%S')
        return round_seconds(dt_obj)
    else:
        return dt.datetime.strptime('01/01/1990 00:00:00', '%m/%d/%Y %H:%M:%S')


def build_timeline_map(
    ut_datetimes_cor: np.ndarray,
    ut_datetimes_hel: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Constructs parallel arrays linking global simulation playback frames for the automatic coupled tracking mode.

    Pairs coronal steps with their nearest heliospheric counterpart by calculating minimum timedelta offsets, then 
    appends the remaining unique heliospheric steps chronologically.

    Parameters
    ----------
    ut_datetimes_cor : ndarray
        Calculated UT datetime objects for each coronal domain frame.
    ut_datetimes_hel : ndarray
        Calculated UT datetime objects for each heliospheric domain frame.

    Returns
    -------
    cor_idx : ndarray, shape (K,)
        Mapped coronal file indices per timeline frame; -1 indicates an unmapped frame.
    hel_idx : ndarray, shape (K,)
        Mapped heliospheric file indices per timeline frame; -1 indicates an unmapped frame.
    global_times : ndarray, shape (K,)
        Corresponding timeline datetimes matching the target frame array length K.
    """
    n_cor = len(ut_datetimes_cor)
    n_hel = len(ut_datetimes_hel)

    p1_cor = np.arange(n_cor)
    
    if n_hel > 0 and n_cor > 0:
        t0_ref = ut_datetimes_cor[0]
        cor_offsets = np.array([(t - t0_ref).total_seconds() for t in ut_datetimes_cor])
        hel_offsets = np.array([(t - t0_ref).total_seconds() for t in ut_datetimes_hel])
        
        p1_hel = np.array([
            int(np.argmin(np.abs(hel_offsets - t_cor)))
            for t_cor in cor_offsets
        ], dtype=int)
    else:
        p1_hel = np.zeros(n_cor, dtype=int)
        
    p1_times = ut_datetimes_cor

    last_matched_hel_idx = p1_hel[-1] if len(p1_hel) > 0 else -1
    p2_hel = np.arange(last_matched_hel_idx + 1, n_hel)
    
    if len(p2_hel) > 0:
        p2_cor = np.full(len(p2_hel), n_cor - 1, dtype=int)
        p2_times = ut_datetimes_hel[p2_hel]
        
        cor_idx = np.concatenate([p1_cor, p2_cor])
        hel_idx = np.concatenate([p1_hel, p2_hel])
        global_times = np.concatenate([p1_times, p2_times])
    else:
        cor_idx = p1_cor
        hel_idx = p1_hel
        global_times = p1_times

    logger.info(f"Timeline 'both_auto' mapping generated successfully. Total sequential frames: {len(cor_idx)}")
    return cor_idx, hel_idx, global_times


def compute_longitudinal_shifts(
    cor_indices: np.ndarray,
    hel_indices: np.ndarray,
    ut_datetimes_cor: np.ndarray,
    ut_datetimes_hel: np.ndarray,
    helio_shift: float = 0.0
) -> tuple[np.ndarray, np.ndarray]:
    """Calculates longitudinal alignment shifts and timedeltas between domains for every mapped frame.

    Computes the physical time difference between matched coronal and heliospheric frames,
    converting it into a rotational shift in radians based on the solar rotation rate.

    Parameters
    ----------
    cor_indices : ndarray, shape (K,)
        Mapped coronal file indices per timeline frame.
    hel_indices : ndarray, shape (K,)
        Mapped heliospheric file indices per timeline frame.
    ut_datetimes_cor : ndarray
        Parsed datetime objects for the coronal domain frames.
    ut_datetimes_hel : ndarray
        Parsed datetime objects for the heliospheric domain frames.
    static_shift : float
        Default fallback longitudinal shift in radians when dynamic tracking is missing.

    Returns
    -------
    shifts : ndarray, shape (K,)
        Computed rotational co-rotation shifts in radians per timeline frame.
    timedeltas : ndarray, shape (K,)
        Time differences in seconds (Helio - Coronal) per timeline frame; contains NaN if uncoupled.
    """
    total_len = len(cor_indices)
    shifts = np.full(total_len, helio_shift if helio_shift is not None else 0.0)
    timedeltas = np.full(total_len, np.nan)

    if len(ut_datetimes_cor) == 0 or len(ut_datetimes_hel) == 0:
        return shifts, timedeltas

    try:
        omega_sun = sun_constants.sidereal_rotation_rate.to(u.rad / u.h).value
        
        for i in range(total_len):
            c_idx = cor_indices[i]
            h_idx = hel_indices[i]
            
            if c_idx >= 0 and h_idx >= 0:
                t_cor = ut_datetimes_cor[c_idx]
                t_hel = ut_datetimes_hel[h_idx]
                
                dt_seconds = (t_hel - t_cor).total_seconds()
                timedeltas[i] = dt_seconds
                
                delta_t_hours = dt_seconds / 3600.0
                shifts[i] = delta_t_hours * omega_sun

        logger.info("Dynamic timeline alignment shifts and timedeltas successfully configured.")
    except Exception as e:
        logger.warning(f"Failed to calculate dynamic time-shifts: {e}. Defaulting to configuration defaults.")
        
    return shifts, timedeltas


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


def save_actor_mesh(self, actor: pv.Actor, path: Path):
        """Utility to save an actor's mesh to disk."""
        if actor and actor.mapper and actor.mapper.dataset:
            actor.mapper.dataset.save(path)

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