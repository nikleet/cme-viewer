#!/usr/bin/env bash
# connect.sh — establish an SSH tunnel to the CME Viewer and open a browser.
# Usage: ./connect.sh user@host [remote_port] [local_port]

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
MAX_WAIT_SECS=30

# helpers

port_open() {
    # Try nc first; fall back to bash /dev/tcp for systems without nc.
    if command -v nc &>/dev/null; then
        nc -z localhost "$1" 2>/dev/null
    else
        (echo >/dev/tcp/localhost/"$1") 2>/dev/null
    fi
}

open_browser() {
    open "$1" 2>/dev/null \
        || xdg-open "$1" 2>/dev/null \
        || echo "  → Open $1 in your browser."
}

cleanup() {
    echo ""
    echo "Disconnecting tunnel (PID ${SSH_PID})..."
    kill "${SSH_PID}" 2>/dev/null && echo "Tunnel closed." || echo "Tunnel already gone."
    exit 0
}

# main

echo ""
echo "  CME Viewer — SSH Tunnel"
echo "  ════════════════════════════════════"
echo "  Target : ${SSH_TARGET}"
echo "  Tunnel : localhost:${LOCAL_PORT} → remote:${REMOTE_PORT}"
echo ""
echo "  Connecting..."
echo ""

# Start the tunnel in the background. Stdin is inherited so the password
# prompt appears on this terminal. The tunnel is NOT yet established at
# this point — authentication may still be in progress.
ssh -N \
    -L "${LOCAL_PORT}:localhost:${REMOTE_PORT}" \
    -o ExitOnForwardFailure=yes \
    -o ConnectTimeout=15 \
    -o ServerAliveInterval=30 \
    "${SSH_TARGET}" &
SSH_PID=$!

trap cleanup INT TERM

# Poll until the local port accepts connections, which only happens after
# authentication succeeds AND the port forward is active.
elapsed=0
while ! port_open "${LOCAL_PORT}"; do
    if ! kill -0 "${SSH_PID}" 2>/dev/null; then
        echo "  ERROR: SSH exited before the tunnel was established."
        echo "  Check your credentials and confirm the app is running on port ${REMOTE_PORT}."
        exit 1
    fi
    if (( elapsed >= MAX_WAIT_SECS )); then
        echo "  ERROR: Timed out after ${MAX_WAIT_SECS}s waiting for the tunnel."
        kill "${SSH_PID}" 2>/dev/null
        exit 1
    fi
    sleep 0.5
    (( elapsed++ )) || true
done

echo "  Connected successfully!"
echo ""
echo "  Opening ${URL}..."
open_browser "${URL}"
echo ""
echo "  Press Ctrl+C to close the tunnel when you're done."
echo ""

# Block until the user hits Ctrl+C or SSH dies on its own.
wait "${SSH_PID}" || true
echo ""
echo "  Tunnel closed."