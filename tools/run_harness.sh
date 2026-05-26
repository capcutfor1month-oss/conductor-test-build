#!/usr/bin/env bash
# tools/run_harness.sh
# Starts the Live Harness UI server

# Get the directory of this script, then go up one level to TEST-BUILD
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT_DIR="$(dirname "$DIR")"

echo "Starting Live Harness UI on port 4620..."
echo "Opening http://localhost:4620/harness.html"

# Run the harness proxy server (static files + AI parse endpoint)
cd "$ROOT_DIR"
python3 tools/harness_server.py
