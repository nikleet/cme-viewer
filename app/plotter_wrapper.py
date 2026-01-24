# app/plotter_wrapper.py
import pyvista as pv


def make_plotter(data_dir: str):
    """
    Create the plotter and initial cone mesh.

    Returns
    -------
    plotter, resources
        plotter : pv.Plotter
        resources : dict with keys 'plotter' and 'actor'
    """
    pl = pv.Plotter()

    # initial mesh (resolution 10)
    mesh = pv.ConeSource(resolution=10)
    actor = pl.add_mesh(mesh)

    return pl, {"plotter": pl, "actor": actor}
