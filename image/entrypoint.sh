#!/bin/bash
set -e

# Start noVNC with token-based routing (routes browser VNC to session containers)
$HOME/novnc_startup.sh

echo "Computer Use Agent is ready!"
echo "Open http://localhost:8000 in your browser to begin"

# Run the app from /opt/.cua/ so child processes inherit $HOME as cwd
exec python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 --app-dir /opt/.cua/
