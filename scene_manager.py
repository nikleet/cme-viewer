# scene_manager.py

from __future__ import annotations
import asyncio
from typing import Optional
from pyvisual.core.plot3d import Plot3d
import pyvista as pv
import numpy as np
from pathlib import Path
import datetime as dt
import json
import matplotlib.colors as mcolors
import logging
from contextlib import contextmanager


# Solar imports
import astropy.units as u
import sunpy.sun.constants as sun_constants
from mapflpy.globals import DEFAULT_BUFFER_SIZE
from mapflpy.tracer import TracerMP
from mapflpy.utils import get_fieldline_polarity, fetch_default_launch_points, combine_and_pad_fieldlines
from mapflpy.scripts import _inter_domain_tracing
from psi_io import read_hdf_by_index

# Local imports
from config import SceneConfig
import utils
from pyvisual.core._styling import (
    RANDOM_COLORING_DEFAULTS,
    FL_POLARITY_COLORING_DEFAULTS,
    FIELDLINE_KWARGS,
)

logger = logging.getLogger(__name__)

# Radial inner boundary of the coronal domain (solar surface, always 1 R_sun).
R_INNER = 1.0


class SceneManager:
    def __init__(self, cfg: SceneConfig, cache_dir: str = ".cache", mode: str = "local", **kwargs):
        self.mode = mode    # 'local' or 'remote'
        self.cfg = cfg
        # Coronal & Heliospheric Directories
        self.cor_dir = Path(getattr(cfg, 'cor_dir', cfg.cor_dir))
        self.hel_dir = Path(cfg.hel_dir) if getattr(cfg, 'hel_dir', None) else None

        mtime = int(self.cor_dir.stat().st_mtime)
        self.run_id = f"{self.cor_dir.name}_{mtime}"

        logger.info(f"Coronal data directory: {self.cor_dir}")
        if self.hel_dir:
            logger.info(f"Heliospheric data directory: {self.hel_dir}")

        self.cor_files = utils.get_mag_files(self.cor_dir)
        self.hel_files = utils.get_mag_files(self.hel_dir) if self.hel_dir else []
        self.mag_files_list = self.cor_files   # single-domain fallback alias

        self.t0 = None
        if cfg.t0:
            dt_obj = dt.datetime.strptime(cfg.t0, '%m/%d/%Y %H:%M:%S')
            self.t0 = utils.round_seconds(dt_obj)

        # Parse Multi-Domain Time Files & Compute Time Shift Array
        self.ut_datetimes = None
        self.cor_times = np.array([])
        self.hel_times = np.array([])

        static_shift = getattr(cfg, 'helio_shift', 0.0)
        self.helio_shifts = np.full(len(self.cor_files), static_shift if static_shift is not None else 0.0)

        cor_time_path = self.cor_dir / cfg.time_file
        if cor_time_path.exists():
            cor_time_dict = utils.get_hdf_times(cor_time_path)
            self.cor_times = np.array(list(cor_time_dict.values()), dtype=float)
            self.ut_datetimes = utils.mastime_to_ut(cor_time_dict, t0=self.t0)

        if self.hel_dir and self.hel_dir.exists():
            hel_time_path = self.hel_dir / cfg.time_file
            if hel_time_path.exists():
                try:
                    self.hel_times = np.array(list(utils.get_hdf_times(hel_time_path).values()), dtype=float)
                    min_len = min(len(self.cor_times), len(self.hel_times))
                    if min_len > 0:
                        delta_t = self.hel_times[:min_len] - self.cor_times[:min_len]
                        omega_sun = sun_constants.sidereal_rotation_rate.to(u.rad / u.h).value
                        computed_shifts = delta_t * omega_sun
                        self.helio_shifts[:min_len] = computed_shifts
                        logger.info(
                            f"Successfully computed dynamic helio_shifts from time files. "
                            f"Sample shift (Frame 0): {computed_shifts[0]:.4f} rad"
                        )
                except Exception as e:
                    logger.warning(
                        f"Could not compute dynamic helio_shift from time file: {e}. "
                        f"Falling back to static values."
                    )
            else:
                logger.info(
                    f"No heliospheric time file found at {hel_time_path}. "
                    f"Using static configuration shift: {cfg.helio_shift}"
                )

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._check_manifest()
        self.plotter = Plot3d(**kwargs)

        self.actors = {}
        self.ram_cache = {}  # Holds {frame_idx: {actor_key: pv.PolyData}}

        self.start_frame = cfg.start_frame if cfg.start_frame is not None else 0
        self.end_frame = cfg.end_frame if cfg.end_frame is not None else len(self.cor_files) - 1
        self.total_frames = self.end_frame - self.start_frame + 1

        self.fl_coloring_config: dict = {
            'coloring': getattr(cfg, 'fl_coloring', 'random'),
            'kwargs': getattr(cfg, 'fl_coloring_kwargs', {}),
            'per_group': {},
        }

        self._view_update_fn = None


    # ------------------------------------------------------------------ #
    # Properties                                                         #
    # ------------------------------------------------------------------ #

    @property
    def is_dual_domain(self) -> bool:
        """True when a heliospheric directory is configured and has data files."""
        return bool(self.hel_files)

    @property
    def fl_group_labels(self) -> list[str]:
        """Returns fieldline group labels derived from actor keys (e.g. 'fl_cme' --> 'cme')."""
        return [key[3:] for key in self.actors if key.startswith('fl_')]


    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    def initialize(self):
        """Creates the initial actors and saves their meshes to the cache."""
        logger.info("Setting up initial scene...")
        initial_frame = self.start_frame
        mgram_actor = self._make_mgram_actor(self.cor_files[initial_frame])
        logger.info("Creating magnetogram actor...")
        if mgram_actor:
            self.actors['mgram'] = mgram_actor
            mgram_path = self.cache_dir / f'frame_{(initial_frame+1):04d}_mgram_{self.run_id}.vtp'
            self._save_actor_mesh(mgram_actor, mgram_path)

        logger.info("Creating field line actors...")
        for group_label, actor in self._make_fl_actors(initial_frame).items():
            self.actors[f'fl_{group_label}'] = actor


    def preload_all_frames(self):
        """Precomputes and caches per-group fieldline and magnetogram meshes, then loads them into RAM."""
        logger.info(f"Preloading frames. Checking cache for {self.total_frames} frames ({self.start_frame} to {self.end_frame})...")
        from contextlib import ExitStack

        for frame_idx in range(self.start_frame, self.end_frame + 1):
            r_groups, t_groups, p_groups, group_labels = self._get_lps_for_frame(frame_idx)

            fl_paths = {
                label: self.cache_dir / f'frame_{(frame_idx+1):04d}_fl_{label}_{self.run_id}.vtp'
                for label in group_labels
            }
            mgram_path = self.cache_dir / f'frame_{(frame_idx+1):04d}_mgram_{self.run_id}.vtp'

            groups_to_process = [
                (label, r, t, p)
                for label, r, t, p in zip(group_labels, r_groups, t_groups, p_groups)
                if not fl_paths[label].exists()
            ]
            needs_mgram = not mgram_path.exists()

            if not groups_to_process and not needs_mgram:
                continue

            logger.info(f"Processing frame {frame_idx + 1}...")

            if needs_mgram:
                values, r, t, p = read_hdf_by_index(self.cor_files[frame_idx][0], 0, None, None)
                utils.create_mgram_mesh(r, t, p, values, frame='rtp').save(mgram_path)

            if groups_to_process:
                with ExitStack() as stack:
                    if self.is_dual_domain:
                        tracer, br_filepath = stack.enter_context(self._open_tracer(frame_idx, domain='cor'))
                        hel_tracer, _       = stack.enter_context(self._open_tracer(frame_idx, domain='hel'))
                    else:
                        tracer, br_filepath = stack.enter_context(self._open_tracer(frame_idx))
                        hel_tracer = None

                    for label, r_lp, t_lp, p_lp in groups_to_process:
                        logger.info(f"Tracing group '{label}' for frame {frame_idx + 1}...")

                        r_tr, t_tr, p_tr, polarity = self._trace_fieldlines(
                            tracer, br_filepath, (r_lp, t_lp, p_lp),
                            hel_tracer=hel_tracer,
                            helio_shift=self.helio_shifts[frame_idx],
                        )
                        temp_plotter = Plot3d(off_screen=True)
                        try:
                            temp_actor = temp_plotter.add_fieldlines(
                                r_tr, t_tr, p_tr,
                                coloring='random',
                                dataid='line_index',
                            )
                            temp_actor.mapper.dataset.cell_data['polarity'] = polarity.astype(np.int8)
                            self._save_actor_mesh(temp_actor, fl_paths[label])
                            logger.info(f"Saved mesh for group '{label}'.")
                        finally:
                            temp_plotter.close()

        logger.info("Caching complete.")
        logger.info("Loading meshes into RAM for playback...")
        for frame_idx in range(self.start_frame, self.end_frame + 1):
            self.ram_cache[frame_idx] = {}
            for key in self.actors.keys():
                path = self.cache_dir / f"frame_{(frame_idx+1):04d}_{key}_{self.run_id}.vtp"
                if path.exists():
                    self.ram_cache[frame_idx][key] = pv.read(path)
                else:
                    logger.warning(f"Missing cache file for RAM load: {path}")


    def set_view_update(self, fn):
        """Register the Trame view.update callback."""
        self._view_update_fn = fn


    def set_frame(self, frame_idx: int):
        if not (0 <= frame_idx < self.total_frames):
            return

        for key, actor in self.actors.items():
            new_mesh = self.ram_cache.get(frame_idx, {}).get(key)
            if new_mesh is None:
                logger.warning(f"Cache missing for frame {frame_idx}, component '{key}'")
                continue
            actor.GetMapper().SetInputData(new_mesh)
            actor.GetMapper().Modified()

        per_group = self.fl_coloring_config.get('per_group', {})
        for key, actor in self.actors.items():
            if key.startswith('fl_'):
                label = key[3:]
                cfg = per_group.get(label, self.fl_coloring_config)
                self._apply_coloring_to_actor(actor, cfg['coloring'], **cfg['kwargs'])


    def set_actor_property(self, actor_key: str, **props):
        """Set visual properties on a named actor."""
        actor = self.actors.get(actor_key)
        if actor is None:
            logger.warning(f"Warning: no actor found with key '{actor_key}'.")
            return

        for prop, value in props.items():
            match prop:
                case 'visibility':
                    actor.visibility = value
                case 'opacity':
                    actor.prop.opacity = value
                case 'line_width':
                    actor.prop.line_width = value
                case 'color':
                    actor.prop.color = value
                case _:
                    logger.warning(f"Warning: unknown actor property '{prop}'.")

        self._push_update()


    def apply_fl_coloring(self, coloring: str | None,
                           group_label: str | None = None, **kwargs):
        """Update fieldline coloring for one or all groups."""
        if group_label is not None:
            self.fl_coloring_config['per_group'][group_label] = {
                'coloring': coloring,
                'kwargs': kwargs,
            }
            key = f'fl_{group_label}'
            fl_actors = {key: self.actors[key]} if key in self.actors else {}
        else:
            self.fl_coloring_config['coloring'] = coloring
            self.fl_coloring_config['kwargs'] = kwargs
            self.fl_coloring_config['per_group'] = {}
            fl_actors = {k: v for k, v in self.actors.items() if k.startswith('fl_')}

        for actor in fl_actors.values():
            self._apply_coloring_to_actor(actor, coloring, **kwargs)

        self._push_update()


    def set_mgram_style(self, cmap: str | None = None, clim: tuple | None = None) -> None:
        """Updates the magnetogram actor's colormap and/or scalar range."""
        actor = self.actors.get('mgram')
        if actor is None:
            return
        if cmap is not None:
            lut = pv.LookupTable(cmap=cmap)
            actor.mapper.lookup_table = lut
        if clim is not None:
            actor.mapper.scalar_range = clim
        self._push_update()


    def get_frame_time(self, frame_idx: int) -> Optional[dt.datetime]:
        """Returns the simulation UT datetime for the given frame, or None if unavailable."""
        if frame_idx < 0 or frame_idx >= self.total_frames:
            return None
        if self.t0 is None or self.ut_datetimes is None:
            return None
        return self.ut_datetimes[frame_idx]


    def clear_cache(self, all_runs: bool = False):
        """Deletes cached files."""
        if all_runs:
            logger.info("Clearing entire cache...")
            for f in self.cache_dir.glob("*.vtp"):
                f.unlink()
            for f in self.cache_dir.glob("*.dat"):
                f.unlink()
            manifest_path = self.cache_dir / 'manifest.json'
            if manifest_path.exists():
                manifest_path.unlink()
        else:
            logger.info(f"Clearing cache for run {self.run_id}...")
            for f in self.cache_dir.glob(f"*{self.run_id}*"):
                f.unlink()


    # ------------------------------------------------------------------ #
    # Private helpers                                                    #
    # ------------------------------------------------------------------ #

    def _push_update(self):
        """Push the current scene state to the browser."""
        if self._view_update_fn is not None:
            self._view_update_fn()
        else:
            self.plotter.render()


    def _check_manifest(self):
        """Checks the cache manifest against the current run. Clears the cache if stale."""
        manifest_path = self.cache_dir / 'manifest.json'

        manifest = {
            'cor_dir': str(self.cor_dir),
            'hel_dir': str(self.hel_dir) if self.hel_dir else None,
            'run_id': self.run_id
        }

        if manifest_path.exists():
            with open(manifest_path, 'r') as f:
                cached_manifest = json.load(f)
            if cached_manifest == manifest:
                return
            logger.info("Cache manifest mismatch. Clearing stale cache...")
            self.clear_cache(all_runs=True)

        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)


    def _save_actor_mesh(self, actor: pv.Actor, path: Path):
        """Utility to save an actor's mesh to disk."""
        if actor and actor.mapper and actor.mapper.dataset:
            actor.mapper.dataset.save(path)


    def _make_mgram_actor(self, mag_files: list[str]) -> pv.Actor:
        """Creates and returns the magnetogram actor."""
        values, r, t, p = read_hdf_by_index(mag_files[0], 0, None, None)
        return self.plotter.add_2d_slice(r, t, p, values,
                                          dataid='Magnetogram',
                                          clim=(-1e1, 1e1),
                                          cmap='seismic')


    def _get_lps_for_frame(self, frame_idx: int
                            ) -> tuple[list, list, list, list[str]]:
        """Returns grouped launch points for the given frame."""
        tracers, labels = self._get_tracers(frame_idx)
        if tracers[0] is None:
            logger.warning(f"No tracer data found for frame {frame_idx}. Falling back to default launch points.")
            r_default, theta_default, phi_default = fetch_default_launch_points()
            return r_default, theta_default, phi_default, ['default']
        logger.info(f"Making launch points for frame {frame_idx}...")
        return self._make_lps_from_tracers(tracers, labels, return_groups=True)


    def _make_fl_actors(self, frame_idx: int) -> dict[str, pv.Actor]:
        """Creates one fieldline actor per launch point group."""
        r_groups, t_groups, p_groups, group_labels = self._get_lps_for_frame(frame_idx)
        coloring = self.fl_coloring_config['coloring']
        coloring_kwargs = self.fl_coloring_config['kwargs']

        fl_actors = {}
        from contextlib import ExitStack

        cached, to_trace = {}, {}
        for label, r, t, p in zip(group_labels, r_groups, t_groups, p_groups):
            fl_path = self.cache_dir / f'frame_{(frame_idx+1):04d}_fl_{label}_{self.run_id}.vtp'
            if fl_path.exists():
                cached[label] = fl_path
            else:
                to_trace[label] = (r, t, p, fl_path)

        for label, fl_path in cached.items():
            mesh = pv.read(fl_path)
            fl_actors[label] = self.plotter.add_mesh(
                mesh, **self._fl_plot_kwargs(coloring, **coloring_kwargs)
            )

        if to_trace:
            with ExitStack() as stack:
                if self.is_dual_domain:
                    tracer, br_filepath = stack.enter_context(self._open_tracer(frame_idx, domain='cor'))
                    hel_tracer, _       = stack.enter_context(self._open_tracer(frame_idx, domain='hel'))
                else:
                    tracer, br_filepath = stack.enter_context(self._open_tracer(frame_idx))
                    hel_tracer = None

                for label, (r_lp, t_lp, p_lp, fl_path) in to_trace.items():
                    logger.info("Tracing field lines for group '{}', frame {}...".format(label, frame_idx))
                    r_tr, t_tr, p_tr, polarity = self._trace_fieldlines(
                        tracer, br_filepath, (r_lp, t_lp, p_lp),
                        hel_tracer=hel_tracer,
                        helio_shift=self.helio_shifts[frame_idx],
                    )
                    actor = self.plotter.add_fieldlines(
                        r_tr, t_tr, p_tr,
                        coloring='random',
                        dataid='line_index',
                    )
                    actor.mapper.dataset.cell_data['polarity'] = polarity.astype(np.int8)
                    self._save_actor_mesh(actor, fl_path)

                    if coloring != 'random':
                        self._apply_coloring_to_actor(actor, coloring, **coloring_kwargs)
                    fl_actors[label] = actor

        return fl_actors


    @contextmanager
    def _open_tracer(self, frame_idx: int, domain: Optional[str] = None, timeout: int = 600, **kwargs):
        """Context manager yielding a ready-to-use TracerMP for the given frame.

        Supports optional domain selection ('cor' or 'hel') for dual-domain setups.
        """
        if domain == 'cor':
            mag_files = self.cor_files[frame_idx]
        elif domain == 'hel':
            mag_files = self.hel_files[frame_idx]
        else:
            # Single-domain default: use coronal files
            mag_files = self.cor_files[frame_idx]

        with TracerMP(*mag_files, timeout=timeout, context='fork', **kwargs) as tracer:
            yield tracer, mag_files[0]


    def _trace_fieldlines(self,
                          tracer: TracerMP,
                          br_filepath: Path,
                          lps: tuple[np.ndarray, np.ndarray, np.ndarray],
                          hel_tracer: Optional[TracerMP] = None,
                          helio_shift: float = 0.0,
                          buffer_size: int = DEFAULT_BUFFER_SIZE,
                          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Traces field lines from launch points and computes polarity.

        Handles both single-domain and coupled dual-domain tracers.

        Parameters
        ----------
        tracer : TracerMP
            Coronal (or single-domain) tracer context.
        br_filepath : Path
            Path to the Br field file used by ``get_fieldline_polarity``.
        lps : tuple of ndarray
            Launch point coordinates ``(r, theta, phi)``.
        hel_tracer : TracerMP | None
            When provided, inter-domain tracing is performed between ``tracer``
            (coronal) and this heliospheric tracer.
        helio_shift : float
            Longitudinal co-rotation shift between domains in radians.
            Pass ``self.helio_shifts[frame_idx]`` from the caller.
        buffer_size : int
            Per-fieldline point buffer passed to the tracer.

        Returns
        -------
        r, theta, phi : ndarray, shape (M, N)
            Traced coordinates; NaN-padded to a uniform length M.
        polarity : ndarray, shape (N,)
            Boundary polarity classification per fieldline.
        """
        r_outer = self.cfg.r_interface

        if hel_tracer is not None:
            inter_domain_traces, *_ = _inter_domain_tracing(
                tracer, hel_tracer,
                launch_points=lps,
                r_interface=r_outer,
                helio_shift=helio_shift,
                buffer_size=buffer_size,
            )
            # Pad the heterogeneous list of (3, M_i) arrays into a uniform
            # (M_max, 3, N) array matching the single-domain geometry format.
            padded = combine_and_pad_fieldlines(inter_domain_traces)
            geometry = padded.geometry if hasattr(padded, 'geometry') else padded
            polarity = get_fieldline_polarity(R_INNER, r_outer, br_filepath, padded)

        else:
            traces = tracer.trace_fbwd(lps, buffer_size)
            polarity = get_fieldline_polarity(R_INNER, r_outer, br_filepath, traces)
            geometry = traces.geometry.copy()

        # geometry shape: (M, 3, N)
        # Mask escaped field lines (r > 100 R_sun) by setting coordinates to NaN
        mask = geometry[:, 0, :] > 100
        geometry = np.where(mask[:, None, :], np.nan, geometry)

        return geometry[:, 0, :], geometry[:, 1, :], geometry[:, 2, :], polarity


    def _fl_plot_kwargs(self, coloring: str | None, **kwargs) -> dict:
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


    def _apply_coloring_to_actor(self, actor: pv.Actor,
                                  coloring: str | None, **kwargs):
        """Apply a coloring mode to an actor's mapper and render properties."""
        match coloring:
            case 'random':
                actor.mapper.scalar_visibility = True
                actor.mapper.array_name = 'line_index'
                actor.mapper.scalar_range = (0, 255)
                actor.mapper.lookup_table = pv.LookupTable(
                    cmap=kwargs.get('cmap', 'hsv'), n_values=256
                )

            case 'polarity':
                if 'polarity' not in actor.mapper.dataset.cell_data.keys():
                    logger.error(
                        "No 'polarity' array found in the fieldline mesh. "
                        "Call clear_cache() and re-run preload_all_frames()."
                    )
                    return

                polarity_cmap = mcolors.ListedColormap(
                    ['blue', 'grey', 'black', 'green', 'red']
                )
                lut = pv.LookupTable(cmap=polarity_cmap, n_values=5, scalar_range=(-2, 2))
                actor.mapper.scalar_visibility = True
                actor.mapper.array_name = 'polarity'
                actor.mapper.scalar_range = (-2, 2)
                actor.mapper.lookup_table = lut

            case _:
                actor.mapper.scalar_visibility = False
                if 'color' in kwargs:
                    actor.prop.color = kwargs['color']

        if 'opacity' in kwargs:
            actor.prop.opacity = kwargs['opacity']
        if 'line_width' in kwargs:
            actor.prop.line_width = kwargs['line_width']


    def _get_tracers(self, frame_idx: int):
        hdf_filename = f'{self.cor_dir}/{self.cfg.tracer_prefix}{(frame_idx+1):06d}.hdf'

        try:
            r, theta, phi = utils.read_tracers(hdf_filename)
        except Exception as e:
            logger.error(f'Could not find tracers in {hdf_filename}: {e}')
            return (None, None, None), None

        labels_path = f'{self.cor_dir}/{self.cfg.tracer_header}'
        labels = utils.read_labels(labels_path)

        logger.info(f'Successfully loaded {len(labels)} labels for frame {frame_idx}.')

        return (r, theta, phi), labels


    def _make_lps_from_tracers(self, tracers, labels, return_groups=False):
        """Select and downsample tracer launch points by label group."""
        r_tr, theta_tr, phi_tr = tracers

        if self.cfg.bg_lp is not None:
            r_bg, theta_bg, phi_bg = utils.read_lps(self.cfg.bg_lp)
            r_tr = np.hstack((r_tr, r_bg))
            theta_tr = np.hstack((theta_tr, theta_bg))
            phi_tr = np.hstack((phi_tr, phi_bg))
            labels.extend(len(phi_bg) * ['background'])
            logger.info('After adding background, number of labels:{}'.format(len(labels)))

        labels, label_ids, label_orig = np.unique(
            np.array(labels),
            return_index=True,
            return_inverse=True,
        )

        r_group, theta_group, phi_group, label_group = [], [], [], []
        for label_id, label in enumerate(labels):
            group_ids = np.where(label_orig == label_id)[0]
            if label not in ['background']:
                group_ids = group_ids[::utils.get_cadence(group_ids, self.cfg.max_traces)]
            if any(keyword in label for keyword in self.cfg.label_select):
                r_group.append(r_tr[group_ids])
                theta_group.append(theta_tr[group_ids])
                phi_group.append(phi_tr[group_ids])
                label_group.append(len(group_ids) * [label])

        if return_groups:
            group_labels = [labels_of_group[0] for labels_of_group in label_group]
            return r_group, theta_group, phi_group, group_labels

        r_select = np.hstack(r_group)
        theta_select = np.hstack(theta_group)
        phi_select = np.hstack(phi_group)
        label_select = np.hstack(label_group)

        return r_select, theta_select, phi_select, label_select


    def _cache_lps(self, frame_idx: int):
        tracers, labels = self._get_tracers(frame_idx)
        r_groups, theta_groups, phi_groups, group_labels = self._make_lps_from_tracers(
            tracers, labels, return_groups=True
        )
        lp_fpath = self.cache_dir / f'lp_select_{(frame_idx+1):04d}_{self.run_id}.dat'
        utils.write_lps(
            lp_fpath,
            np.hstack(r_groups),
            np.hstack(theta_groups),
            np.hstack(phi_groups),
        )
        label_fpath = self.cache_dir / 'tracer_header_select.dat'
        if not label_fpath.exists():
            utils.write_labels(label_fpath, group_labels)


    async def _warm_up_vtk_cache(self, on_progress=None):
        """Pre-push all frame geometries to the vtk.js client-side array cache."""
        if self._view_update_fn is None:
            logger.warning("Warmup called before view_update_fn was registered.")
            return

        logger.info(f"Local mode: pre-loading {self.total_frames} frames into vtk.js cache...")

        for frame_idx in range(self.start_frame, self.end_frame + 1):
            frame_cache = self.ram_cache.get(frame_idx, {})
            for key, actor in self.actors.items():
                new_mesh = frame_cache.get(key)
                if new_mesh is not None:
                    actor.GetMapper().SetInputData(new_mesh)
                    actor.GetMapper().Modified()

            self._view_update_fn()

            if on_progress:
                on_progress(frame_idx + 1 - self.start_frame, self.total_frames)

            for _ in range(10):
                await asyncio.sleep(0.1)

        self.set_frame(self.start_frame)
        self._view_update_fn()
        logger.info("vtk.js cache warmup complete — playback ready.")
