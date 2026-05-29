#!/usr/bin/env bash
# connect.sh: sets up an SSH tunnel and opens the CME Viewer in the browser.

# Usage: ./connect.sh user@yourserver.example.com [remote_port] [local_port]

# Typical server startup command:
# python server.py --mode remote --data-dir /path/to/data --port 8080
# --host defaults to 127.0.0.1, so no further flags needed for SSH-only access

# Typical client connection command:
# ./connect.sh user@yourserver.example.com
# Then open http://localhost:8080

set -euo pipefail

SSH_TARGET="${1:?Usage: $0 user@host [remote_port] [local_port]}"
REMOTE_PORT="${2:-8080}"
LOCAL_PORT="${3:-8080}"
URL="http://localhost:${LOCAL_PORT}"

echo "Opening SSH tunnel: localhost:${LOCAL_PORT} -> ${SSH_TARGET}:${REMOTE_PORT}"
echo "Press Ctrl+C to close the tunnel."

# Open the browser after a short delay to let the tunnel establish
(sleep 1.5 && (open "${URL}" 2>/dev/null || xdg-open "${URL}" 2>/dev/null || echo "Open ${URL} in your browser")) &

# -N: no remote command  -L: local port forward
ssh -N -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" "${SSH_TARGET}"