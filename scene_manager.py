# scene_manager.py

from __future__ import annotations
from pyvisual.core.plot3d import Plot3d
import pyvista as pv
import numpy as np
from pathlib import Path

from typing import Optional

from mapflpy.scripts import run_forward_tracing
from mapflpy.utils import fetch_default_launch_points
from psi_io import read_hdf_by_index

from utils import make_splines


class SceneManager:
    def __init__(self, data_dir: str, cache_dir: str = ".cache", **kwargs):
        self.data_dir = data_dir

        # Setup caching directory
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.total_frames = 0

        self.plotter = Plot3d(**kwargs)
        self.actors = {}
        
        
    def initialize_scene(self, mag_files: list[str]):
        """Creates the initial actors for Frame 0."""
        fl_actor, mgram_actor = self._make_sun_actors(self.plotter, mag_files)
        if fl_actor:
            self.actors["fl"] = fl_actor
            self.active_fl_mesh = fl_actor.mapper.dataset
        if mgram_actor:
            self.actors["mgram"] = mgram_actor
            self.active_mgram_mesh = mgram_actor.mapper.dataset

    def preload_all_frames(self, mag_files_list: list[list[str]]):
        """
        Precomputes meshes and saves them to disk.
        Skips frames that have already been cached.
        """
        self.total_frames = len(mag_files_list)
        print(f"Checking cache for {self.total_frames} frames...")

        for idx, mag_files in enumerate(mag_files_list):
            fl_path = self.cache_dir / f"frame_{idx:06d}_fl.vtp"
            mgram_path = self.cache_dir / f"frame_{idx:06d}_mgram.vts"

            # If both files already exist on disk, skip the heavy processing!
            if fl_path.exists() and mgram_path.exists():
                continue

            print(f"Processing and caching frame {idx}...")
            temp_plotter = Plot3d()
            # Note: Ideally, we bypass creating actors here entirely and just generate the pyvisual.DataSet directly. 
            # If your _make_sun_actors relies heavily on the plotter, we use a hidden temp plotter, but extract ONLY the mesh.

            temp_fl, temp_mgram = self._make_sun_actors(temp_plotter, mag_files)

            # Extract and save the meshes to disk
            if temp_mgram and temp_mgram.mapper.dataset:
                temp_mgram.mapper.dataset.save(mgram_path)

            if temp_fl and temp_fl.mapper.dataset:
                temp_fl.mapper.dataset.save(fl_path)

            temp_plotter.close()

        print("Caching complete.")

    def set_frame(self, frame_index: int):
        """
        Reads the mesh directly from the disk cache and updates the actors.
        """
        if frame_index < 0 or frame_index >= self.total_frames:
            return

        fl_path = self.cache_dir / f"frame_{frame_index:06d}_fl.vtp"
        mgram_path = self.cache_dir / f"frame_{frame_index:06d}_mgram.vts"

        if not fl_path.exists() or not mgram_path.exists():
            print(f"Warning: Cache missing for frame {frame_index}")
            return

        # TODO: Instead of discretely updating the meshes for the fieldlines and magnetogram, it would be better to just
        # go through all actors and update them to support more types of actors in the future.
         
        # Read new meshes into temperory variables
        if "fl" in self.actors:
            new_fl = pv.read(fl_path)

        if "mgram" in self.actors:
            new_mgram = pv.read(mgram_path)

        # Overwrite the active meshes in-place and flag as modified to trigger the rendering update
        if hasattr(self, "active_fl_mesh") and self.active_fl_mesh:
            self.active_fl_mesh.copy_from(new_fl)
            self.active_fl_mesh.Modified()

        if hasattr(self, "active_mgram_mesh") and self.active_mgram_mesh:
            self.active_mgram_mesh.copy_from(new_mgram)
            self.active_mgram_mesh.Modified()

        # Trigger a re-render after updating meshes
        self.plotter.render()

    def _make_sun_actors(self, plotter: Plot3d, mag_files: list[str]):
        """Internal helper to generate actors from raw data."""
        print(mag_files)
        values, r, t, p = read_hdf_by_index(mag_files[0], 0, None, None)
        mgram_actor = plotter.add_2d_slice(
            r, t, p, values, clim=(-1e1, 1e1), cmap="seismic", v_name="Radial Boundary"
        )

        # TODO: improve launch points generation
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
    
