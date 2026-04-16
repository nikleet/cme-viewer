import pyvista as pv
import numpy as np

from pyvisual.core._mesh_parser import (
    parse_mesh_params, parse_stack_params, 
    mesh_grid_scales, stack_grid_scales, unravel_values
)

# TODO: Double check that this works and implement in scene_manager

def create_mgram_mesh(*args, 
                      iframe='rtp', 
                      oframe='xyz', 
                      forder=True, 
                      v_name="Data"):
    """Explicit builder for 2D slices (Magnetograms) as StructuredGrids."""
    # Parse arguments
    parsed = parse_mesh_params(*args)
    if len(parsed) not in (3, 4):
        raise ValueError(f"Expected 3 or 4 arguments, got {len(parsed)}")

    # Build 3D meshgrid and transform coordinates
    scales = mesh_grid_scales(*parsed[:3], iframe=iframe, oframe=oframe, forder=forder)

    # Strict Validation
    if scales[0].shape.count(1) != 1:
        raise ValueError(f"2D slices should have one fixed dimension, got {scales[0].shape}")

    # Build Geometry
    grid = pv.StructuredGrid(*scales)

    # Attach unraveled point data if provided
    if len(parsed) == 4:
        grid[v_name] = unravel_values(parsed[3], scales[0].shape, forder=forder)

    return grid


def create_fieldline_mesh(*args, 
                          iframe='rtp', 
                          oframe='xyz', 
                          forder=True, 
                          v_name="Data"):
    """Explicit builder for multi-splines (Fieldlines) as PolyData."""
    # Parse arguments
    parsed = parse_stack_params(*args)
    if len(parsed) not in (3, 4):
        raise ValueError(f"Expected 3 or 4 arguments, got {len(parsed)}")

    # Transform coordinates (maintains stack shape)
    scales = stack_grid_scales(*parsed[:3], iframe=iframe, oframe=oframe, forder=forder)

    # Strict Validation
    if scales[0].ndim != 2:
        raise ValueError(f"Multi-spline arrays should be 2D, got {scales[0].ndim}D")

    # Geometry Math
    splines = np.stack(scales, axis=1).transpose((2, 0, 1)).reshape(-1, 3)
    spline_len, num_splines = scales[0].shape
    cells = np.column_stack(
        (np.repeat(spline_len, num_splines), 
         np.arange(spline_len * num_splines).reshape(num_splines, spline_len))
    ).ravel()

    # Build Geometry
    grid = pv.PolyData()
    grid.points = splines
    grid.lines = cells

    # Attach unraveled point data if provided
    if len(parsed) == 4:
        grid[v_name] = unravel_values(parsed[3], scales[0].shape, forder=forder)

    return grid