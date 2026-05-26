#!/bin/bash
# ─────────────────────────────────────────────────────────
#  Conductor Bridge — Start Script (TEST-BUILD)
#  Double-click this file (or run in Terminal) to start
#  the local server that connects Conductor UI to Ableton,
#  NotebookLM, and the audio analyzer.
#
#  Port : 4611  (TEST-BUILD — do NOT change to 4601)
#  DB   : TEST-BUILD/memory/chromadb  (isolated, not shared with personal build)
# ─────────────────────────────────────────────────────────

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# ── Python selection ──────────────────────────────────────────────────────────
# ChromaDB is installed in the pipx chromadb venv. Use it so memory is always
# available. Falls back to system python3 so the bridge still starts (without
# memory) if the venv was removed.
CHROMA_PY="/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3"
# T7 Shield portable path (resolves if running from an external drive)
CHROMA_PY_T7="/Volumes/T7 Shield/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3"

if [ -x "$CHROMA_PY_T7" ]; then
    PYTHON="$CHROMA_PY_T7"
elif [ -x "$CHROMA_PY" ]; then
    PYTHON="$CHROMA_PY"
else
    PYTHON="python3"
    echo "  ⚠  ChromaDB venv not found — bridge will start without memory."
    echo "     Run: pipx install chromadb   (then restart bridge)"
fi

echo ""
echo "  Starting Conductor Bridge (TEST-BUILD)..."
echo "  Python  : $PYTHON"
echo "  Port    : 4611"
echo "  Keep this window open while using Conductor."
echo ""

exec "$PYTHON" "$SCRIPT_DIR/conductor_bridge.py"
