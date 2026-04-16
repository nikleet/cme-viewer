# utils.py

import numpy as np
import datetime as dt
from glob import glob
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
    

# ========= IO UTILITIES =========

def get_mag_files(data_folder: str):
    br_files = glob(data_folder + '/br*')
    bt_files = glob(data_folder + '/bt*')
    bp_files = glob(data_folder + '/bp*')
    return list(zip(br_files, bt_files, bp_files))

