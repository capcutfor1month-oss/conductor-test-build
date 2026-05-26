#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  Conductor — Start Mem0 Memory Server
#  Loads your API key from .env then starts the memory server.
#  Run this alongside start_bridge.sh when using Conductor.
# ─────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="$SCRIPT_DIR/../.env"

# Load .env
if [[ -f "$ENV_FILE" ]]; then
  set -a
  source "$ENV_FILE"
  set +a
else
  echo ""
  echo "  ✗  .env file not found at: $ENV_FILE"
  echo "     Copy .env.template → .env and add your GOOGLE_API_KEY"
  echo "     See THINGS TO LOOK FOR.md for instructions."
  echo ""
  exit 1
fi

# Find agent-mem0 binary
MEM0_BIN=""
for candidate in \
  "$(command -v agent-mem0 2>/dev/null)" \
  "$(command -v mcp-mem0 2>/dev/null)" \
  "$HOME/.local/bin/agent-mem0" \
  "/opt/homebrew/bin/agent-mem0"
do
  if [[ -x "$candidate" ]]; then
    MEM0_BIN="$candidate"
    break
  fi
done

if [[ -z "$MEM0_BIN" ]]; then
  echo ""
  echo "  ✗  agent-mem0 not found."
  echo "     Install it: pipx install mcp-mem0"
  echo ""
  exit 1
fi

echo ""
echo "  Starting Conductor Memory Server..."
echo "  Keep this window open while using Conductor."
echo ""

exec "$MEM0_BIN" serve --project CONDUCTOR
