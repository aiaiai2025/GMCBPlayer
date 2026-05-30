#!/bin/bash
# Double-click this file to start the GMCB Player locally.
# It starts a small web server and opens the player in your browser.

cd "$(dirname "$0")"

PORT=8765

# Kill any previous instance on that port
lsof -ti tcp:$PORT | xargs kill -9 2>/dev/null

echo "Starting GMCB Player at http://localhost:$PORT"
echo "Press Ctrl-C to stop."

# Open browser after a short delay so the server is ready
(sleep 1 && open "http://localhost:$PORT") &

python3 -m http.server $PORT
