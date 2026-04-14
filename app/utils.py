import numpy as np
import datetime as dt
from glob import glob
import pyvista as pv
import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib import cm

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



def round_seconds(obj: dt.datetime) -> dt.datetime:
    if obj.microsecond >= 500_000:
        obj += dt.timedelta(seconds=1)
    return obj.replace(microsecond=0)



def mastime_to_ut(mas_times: str, t0: dt.datetime = None) -> list[dt.datetime]:
    """
    Converts mastimes dict to a list of UT datetimes.
    
    fname: dict   dict of sequence and mastimes from dumps or masTime .txt file  
    t0: datetime    initial time at start of run
    
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


def extract_mesh_and_metadata(actor: pv.Actor):
    """
    Extracts the underlying mesh and visualization metadata from a PyVista Actor.
    
    Parameters:
        actor (pyvista.Actor): The actor to extract data from.
        
    Returns:
        tuple: (pyvista.DataSet, dict) The underlying mesh and a dictionary of metadata.
    """
    if not isinstance(actor, pv.Actor):
        raise TypeError(f"Expected pyvista.Actor, got {type(actor)}.")

    # 1. Extract the Mesh via the Mapper
    mapper = actor.mapper
    mesh = mapper.dataset if mapper is not None else None

    # 2. Extract Metadata
    metadata = {
        "actor": {
            "visibility": actor.visibility,
            "pickable": actor.pickable,
            "position": actor.position,
            "orientation": actor.orientation,
            "scale": actor.scale,
            "user_matrix": actor.user_matrix.tolist() if actor.user_matrix is not None else None,
        },
        "property": {},
        "mapper": {},
        "has_texture": actor.texture is not None
    }

    # Extract Visual Properties (Color, Opacity, Shading)
    prop = actor.prop
    if prop is not None:
        metadata["property"] = {
            "color": prop.color.name if hasattr(prop.color, 'name') else prop.color,
            "opacity": prop.opacity,
            "show_edges": prop.show_edges,
            "edge_color": prop.edge_color.name if hasattr(prop.edge_color, 'name') else prop.edge_color,
            "representation": prop.representation, # 'surface', 'wireframe', or 'points'
            "line_width": prop.line_width,
            "point_size": prop.point_size,
            "ambient": prop.ambient,
            "diffuse": prop.diffuse,
            "specular": prop.specular,
            "specular_power": prop.specular_power,
        }

    # Extract Mapping details (Scalars, Colormaps, Data bounds)
    if mapper is not None:
        metadata["mapper"] = {
            "scalar_visibility": mapper.scalar_visibility,
            "array_name": mapper.array_name,
            "scalar_range": mapper.scalar_range,
            "interpolate_scalars_before_mapping": mapper.interpolate_scalars_before_mapping,
            "cmap": mapper.cmap,
            "color_mode": mapper.color_mode,
        }

    return mesh, metadata


# ========= IO UTILITIES =========

def get_mag_files(data_folder):
    br_files = glob(data_folder + '/br*')
    bt_files = glob(data_folder + '/bt*')
    bp_files = glob(data_folder + '/bp*')
    return list(zip(br_files, bt_files, bp_files))

