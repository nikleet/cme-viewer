# scene_manager.py

from __future__ import annotations
from typing import Optional
from pyvisual.core.plot3d import Plot3d
import pyvista as pv
import numpy as np
from pathlib import Path
import datetime as dt

# PSI imports
from mapflpy.scripts import run_forward_tracing
from mapflpy.utils import fetch_default_launch_points
from psi_io import read_hdf_by_index

# Local imports
from config import SimulationConfig
import utils

class SceneManager:
    def __init__(self, cfg: SimulationConfig, cache_dir: str = ".cache", **kwargs):
        self.cfg: SimulationConfig = cfg
        self.data_dir: Path = cfg.data_dir
        mtime = int(self.data_dir.stat().st_mtime)
        self.run_id = f"{self.data_dir.name}_{mtime}"
        
        print(self.data_dir)
        self.mag_files_list = utils.get_mag_files(self.data_dir)
        
        self.t0 = None
        if cfg.t0:
            dt_obj = dt.strptime(cfg.t0, '%m/%d/%y %H:%M:%S')
            self.t0 = utils.round_seconds(dt_obj)
        
        self.ut_datetimes = None
        time_path = self.data_dir / cfg.time_file
        if time_path.exists():
            raw_times = utils.get_hdf_times(time_path)
            self.ut_datetimes = utils.mastime_to_ut(raw_times, t0=self.t0)

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.plotter = Plot3d(**kwargs)
        
        self.actors = {}
        self.total_frames = len(self.mag_files_list)
        
        
    def initialize(self, initial_frame=0):
        """Creates the initial actors and saves them to the cache."""
        # Create field line and magnetogram actors
        fl_actor, mgram_actor = self._make_sun_actors(self.plotter, self.mag_files_list[initial_frame])

        if fl_actor:
            self.actors["fl"] = fl_actor
        if mgram_actor:
            self.actors["mgram"] = mgram_actor
            
        # Cache actors for the initial frame
        for key, actor in self.actors.items():
            path = self.cache_dir / f"frame_{initial_frame:04d}_{key}_{self.run_id}.vtp"
            self._save_actor_mesh(actor, path)
        

    def preload_all_frames(self):
        """
        Precomputes meshes and saves them to disk.
        Skips frames that have already been cached.
        """
        print(f"Checking cache for {self.total_frames} frames...")

        for frame_idx, mag_files in enumerate(self.mag_files_list):
            
            fl_path = self.cache_dir / f"frame_{frame_idx:04d}_fl_{self.run_id}.vtp"
            mgram_path = self.cache_dir / f"frame_{frame_idx:04d}_mgram_{self.run_id}.vtp"

            if fl_path.exists() and mgram_path.exists():
                continue

            print(f"Processing and caching frame {frame_idx}...")
            
            # Read hdf data
            values, r, t, p = read_hdf_by_index(mag_files[0], 0, None, None)
            # Make magnetogram mesh
            mgram_mesh = utils.create_mgram_mesh(r, t, p, values, frame='rtp')
            
            # Make fieldline mesh
            # TODO: Improve launch points generation with functions to make launch points and traces
            lps = fetch_default_launch_points(30)
            traces = run_forward_tracing(*mag_files, launch_points=lps)
            trace_geometry = traces.geometry
            mask = trace_geometry[:, 0, :] > 100
            a = np.where(mask[:, None, :], np.nan, trace_geometry)
            trace_r, trace_t, trace_p = (a[:, i, :] for i in range(3))
            fl_mesh = utils.create_fieldline_mesh(trace_r, trace_t, trace_p, frame='rtp')
            
            mgram_mesh.save(mgram_path)
            fl_mesh.save(fl_path)
            
            # LAZY ACTOR-BASED IMPLEMENTATION
            # # Note: Ideally, we bypass creating actors here entirely and just generate the pyvisual.DataSet directly. 
            # print(f"Processing and caching frame {frame_idx}...")
            # temp_plotter = Plot3d(off_screen=True)
            # temp_fl, temp_mgram = self._make_sun_actors(temp_plotter, mag_files)
            # # Extract and save the meshes to disk
            # self._save_actor_mesh(temp_fl, fl_path)
            # self._save_actor_mesh(temp_mgram, mgram_path)
            # temp_plotter.close()

        print("Caching complete.")

    
    def set_frame(self, frame_idx: int):
        """
        Generically updates all registered actors by reading from disk.
        """
        if not (0 <= frame_idx < self.total_frames):
            return

        for key, actor in self.actors.items():
            path = self.cache_dir / f"frame_{frame_idx:04d}_{key}_{self.run_id}.vtp"
            
            if path.exists():
                # Read the new geometry from disk
                new_mesh = pv.read(path)
                
                # Update the existing actor's dataset in-place.
                actor.mapper.dataset.copy_from(new_mesh)
                
                # Notify the mapper that the data has changed
                actor.mapper.dataset.Modified()
            else:
                print(f"Warning: Cache missing for frame {frame_idx}, component '{key}'")

        # Re-render the scene once after all actors are updated
        self.plotter.render()

    
    def get_frame_time(self, frame_idx: int) -> Optional[dt.datetime]:
        """
            Utility to get the simulation time corresponding to the given frame index. 
            Returns a datetime object or None if unavailable.
        """
        if frame_idx < 0 or frame_idx >= self.total_frames:
            return None
        if self.t0 is None:
            return None
        return self.ut_datetimes[frame_idx]
    
    def clear_cache(self, all_runs: bool = False):
        """Deletes cached files."""
        if all_runs:
            # Delete everything in .cache
            for f in self.cache_dir.glob("*.vtp"):
                f.unlink()
        else:
            # Delete only files matching the current run_id
            for f in self.cache_dir.glob(f"*{self.run_id}*"):
                f.unlink()
    
    def _save_actor_mesh(self, actor: pv.Actor, path: Path):
        """Utility to save an actor's mesh to disk."""
        if actor and actor.mapper and actor.mapper.dataset:
            actor.mapper.dataset.save(path)

    
    def _make_sun_actors(self, plotter: Plot3d, mag_files: list[str]):
        """Internal helper to generate actors from raw data."""
        values, r, t, p = read_hdf_by_index(mag_files[0], 0, None, None)
        # TODO: Add appearance settings to config and pass here instead of hardcoding
        mgram_actor = plotter.add_2d_slice(r, t, p, values, 
                                           dataid="Magnetogram", 
                                           clim=(-1e1, 1e1), 
                                           cmap="seismic")

        # TODO: Improve launch points generation with functions to make launch points and traces
        # TODO: Add launch point settings to config and pass here instead of hardcoding
        lps = fetch_default_launch_points(30)
        traces = run_forward_tracing(*mag_files, launch_points=lps)
        trace_geometry = traces.geometry
        mask = trace_geometry[:, 0, :] > 100
        a = np.where(mask[:, None, :], np.nan, trace_geometry)
        trace_r, trace_t, trace_p = (a[:, i, :] for i in range(3))

        fl_actor = plotter.add_fieldlines(
            trace_r,
            trace_t,
            trace_p,
            coloring="random",
            cmap="hsv",
            n_colors=256,
            line_width=1,
        )

        return fl_actor, mgram_actor

    
