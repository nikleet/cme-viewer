# CME Viewer

An interactive 3D visualization tool for solar coronal mass ejection (CME) simulations. Built on [PyVista](https://pyvista.org) / Pyvisual, [Trame](https://kitware.github.io/trame/), and PSI's solar physics libraries (`mapflpy`, `psi_io`).

The viewer streams a live 3D scene to a web browser, allowing navigation through simulation time steps, toggling of scene components, and control over magnetic field line rendering — either locally or from a remote headless server over an SSH tunnel.


## Table of Contents

- [Architecture](#architecture)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [Accessing Remotely via SSH Tunnel](#accessing-remotely-via-ssh-tunnel)
- [CLI Reference](#cli-reference)
- [UI Guide](#ui-guide)
- [Caching](#caching)
- [Project Structure](#project-structure)


## Architecture

The application is split into three layers:

| File | Role |
|---|---|
| `server.py` | Entry point. Parses arguments, wires up Trame layout and server. |
| `scene_manager.py` | All data I/O, fieldline tracing, actor management, and cache logic. |
| `ui.py` | Declarative Trame/Vuetify3 UI: toolbar, sidebar, state callbacks. |
| `config.py` | Dataclass-based config with YAML file + CLI override resolution. |

In **local mode**, rendering is done client-side by vtk.js running in the browser. In **remote mode**, PyVista renders server-side and streams images over a WebSocket — better for large datasets on powerful remote hardware.


## Requirements

- Python 3.10+
- PyVista / Pyvisual
- Trame + `trame-vuetify`
- `mapflpy`
- `psi_io`
- `numpy`, `matplotlib`, `pyyaml`

> PSI libraries (`mapflpy`, `psi_io`) are proprietary. Contact PSI for access.


## Installation

```bash
git clone <repo-url>
cd cme-viewer
pip install -r requirements.txt
```


## Configuration

Configuration is resolved in priority order: **CLI arguments > `config.yaml` > built-in defaults**.

On first run with no `config.yaml`, defaults are used. To persist settings, create a `config.yaml` at the project root. The structure mirrors the two config dataclasses:

```yaml
runtime_cfg:
  mode: remote
  host: 127.0.0.1
  port: 8080
  verbose: false

scene_cfg:
  data_dir: /data/cme_run_01
  t0: "01/15/2024 00:00:00"
  time_file: mas_dumps_3d.txt
  tracer_header: tracer_header.dat
  tracer_prefix: tracers_pos
  max_traces: 50
  max_steps: 500
  label_select: "apex,axis,arcade,background"
```

Any value set here can still be overridden at the command line.


## Running the Application

### Local mode

Renders client-side via vtk.js. Opens a browser automatically. Best for development on a workstation with a display.

```bash
python server.py --mode local --data-dir /path/to/data
```

### Remote mode

Renders server-side and streams frames to the browser. Designed for headless servers. Binds to `127.0.0.1` by default (SSH tunnel access — see below).

```bash
python server.py --mode remote --data-dir /path/to/data --port 8080
```

To expose on all interfaces instead (e.g. within a trusted network):

```bash
python server.py --mode remote --data-dir /path/to/data --host 0.0.0.0
```


## Accessing Remotely via SSH Tunnel

The recommended way to access a remote instance securely — no open ports, no domain, no TLS certificate required. All traffic, including the WebSocket stream, is carried over the encrypted SSH connection.

### How it works

The server binds to `127.0.0.1:8080` (localhost only), making it unreachable from the network. An SSH local port forward creates an encrypted tunnel from your machine's `localhost:8080` to the server's `localhost:8080`. You then access the app at `http://localhost:8080` in your browser as if it were running locally.

### One-command connection (recommended)

A helper script is provided. Run it on your **local machine**:

```bash
./connect.sh user@yourserver.example.com
```

Optional arguments:

```bash
./connect.sh user@yourserver.example.com [remote_port] [local_port]
# e.g.: ./connect.sh alice@hpc.uni.edu 8080 8080
```

The script opens the SSH tunnel and launches your browser automatically. Press `Ctrl+C` to close the tunnel when done.

> Make the script executable once with: `chmod +x connect.sh`

### Manual tunnel command

If you prefer to manage the tunnel yourself:

```bash
ssh -N -L 8080:localhost:8080 user@yourserver.example.com
```

Then open `http://localhost:8080` in your browser. The `-N` flag suppresses a remote shell — the command just holds the tunnel open.

### Connecting with an interactive SSH session

If you want a terminal open at the same time (e.g. to monitor server logs), omit `-N`:

```bash
ssh -L 8080:localhost:8080 user@yourserver.example.com
```

The tunnel stays open for the duration of your SSH session.


## CLI Reference

```
usage: server.py [--mode {local,remote}] [--data-dir PATH] [options]

required arguments:
  --mode {local,remote}     Runtime mode
  --data-dir PATH           Directory containing .hdf simulation files

server & render settings:
  --host HOST               Bind address (default: 127.0.0.1)
  --port PORT               Port to listen on (default: 8080)
  --still-ratio FLOAT       Render quality for still frames
  --interactive-ratio FLOAT Render quality during interaction
  --aa {ssaa,fxaa,msaa}     Anti-aliasing method
  --multi-samples INT        Samples for MSAA

scene metadata:
  --t0 "MM/DD/YYYY HH:MM:SS"   Simulation start time
  --time-file FILENAME          File containing simulation time steps

tracer & fieldline settings:
  --tracer-header FILENAME   Tracer label header file
  --tracer-prefix PREFIX     Prefix of tracer position files
  --lp-prefix PREFIX         Prefix of output launch point files
  --max-traces INT           Max fieldlines per group (default: 50)
  --max-steps INT            Max tracing steps (default: 500)
  --label-select LABELS      Comma-separated label filter
  --bg-lp FILEPATH           Fixed launch points for background fieldlines

debug:
  --verbose                  Enable debug logging
```

Example:
```
python server.py --mode remote --data-dir /home/niklas/PSI/cmecme/cmecme_poly_part1_run1a_cme/cor_mhd --t0 "01/01/1990 00:00:00"
```

## UI Guide

### Toolbar

| Control | Description |
|---|---|
| Play / Pause | Animates through all simulation frames in sequence |
| Frame slider | Scrub to any frame manually |
| Frame counter | Shows the current frame number |

### Sidebar — Magnetogram

| Control | Description |
|---|---|
| Visible | Toggle magnetogram surface on/off |
| Colormap | Choose colormap for magnetogram |
| Color Range (Min/Max) | Set the scalar clipping range for the colormap |

### Sidebar — Field Lines

| Control | Description |
|---|---|
| Coloring Mode | **Random**: each line gets a unique hue. **Polarity**: colored by magnetic polarity (open/closed, inner/outer boundary). **Custom**: per-group color picker. |
| All Line Widths | Global slider that sets line width across all groups simultaneously |
| Group rows | Per-group visibility toggle, color picker (Custom mode only), and a cog menu for individual opacity and line width |


## Caching

On first run, the viewer traces fieldlines and renders magnetogram meshes for every frame, saving them as `.vtp` files in `.cache/`. This is the most time-consuming step and only happens once per dataset.

On subsequent runs, cached meshes are loaded from disk directly into RAM at startup for smooth frame playback.

Cache validity is checked via a manifest file (`.cache/manifest.json`) that records the data directory path and a modification-time-based run ID. If the data directory changes, the cache is automatically invalidated and rebuilt.

To manually clear the cache for the current dataset:

```python
scene.clear_cache()
```

To wipe the entire cache directory (all runs):

```python
scene.clear_cache(all_runs=True)
```


## Project Structure

```
cme-viewer/
├── server.py            # Application entry point
├── scene_manager.py     # Data loading, tracing, actor management
├── ui.py                # Trame/Vuetify3 UI definition and callbacks
├── config.py            # Configuration dataclasses and resolution logic
├── utils.py             # I/O helpers (HDF reading, tracer parsing, etc.)
├── config.yaml          # (optional) Persistent configuration
├── connect.sh           # SSH tunnel helper for remote access
└── .cache/              # Auto-generated mesh cache (gitignored)
```

