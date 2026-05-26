#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Conductor — One-Click Installer
#  Double-click this file from Finder to set up everything.
#  Keep this window open until you see "Setup complete."
# ═══════════════════════════════════════════════════════════════

cd "$(dirname "$0")"
ROOT="$(pwd)"

# ── Colours ───────────────────────────────────────────────────
GREEN="\033[0;32m"; YELLOW="\033[0;33m"; RED="\033[0;31m"
BLUE="\033[0;34m"; BOLD="\033[1m"; RESET="\033[0m"

ok()    { echo -e "  ${GREEN}✓${RESET}  $1"; }
warn()  { echo -e "  ${YELLOW}⚠${RESET}  $1"; }
fail()  { echo -e "  ${RED}✗${RESET}  $1"; }
step()  { echo; echo -e "${BOLD}${BLUE}▸  $1${RESET}"; }
have()  { command -v "$1" >/dev/null 2>&1; }

ERRORS=()
log_error() { ERRORS+=("$1"); fail "$1"; }

# ── Header ────────────────────────────────────────────────────
clear
echo
echo -e "${BOLD}  ╔══════════════════════════════════════════╗${RESET}"
echo -e "${BOLD}  ║         Conductor Installer              ║${RESET}"
echo -e "${BOLD}  ║   Your AI music production assistant     ║${RESET}"
echo -e "${BOLD}  ╚══════════════════════════════════════════╝${RESET}"
echo
echo "  Installing everything Conductor needs."
echo "  Takes about 3–5 minutes on a fresh Mac."
echo
read -p "  Press Enter to start, or Ctrl+C to cancel... "
echo

# ── 1. macOS check ────────────────────────────────────────────
step "Checking system"
if [[ "$(uname)" != "Darwin" ]]; then
  fail "Conductor requires macOS. Exiting."; exit 1
fi
ok "macOS $(sw_vers -productVersion)"

# ── 2. Homebrew ───────────────────────────────────────────────
step "Homebrew"
if ! have brew; then
  echo "  Installing Homebrew (you may be asked for your password)..."
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  [[ -x /opt/homebrew/bin/brew ]] && eval "$(/opt/homebrew/bin/brew shellenv)"
  [[ -x /usr/local/bin/brew   ]] && eval "$(/usr/local/bin/brew shellenv)"
fi
have brew && ok "Homebrew $(brew --version | head -1)" \
           || log_error "Homebrew not available — restart Terminal and re-run"

# ── 3. Python 3 ───────────────────────────────────────────────
step "Python 3"
have python3 || brew install python
have python3 && ok "$(python3 --version)" || log_error "Python 3 install failed"

# ── 4. pipx ───────────────────────────────────────────────────
step "pipx"
have pipx || brew install pipx
pipx ensurepath --force >/dev/null 2>&1 || true
export PATH="$PATH:$HOME/.local/bin:/opt/homebrew/bin"
have pipx && ok "pipx ready" || log_error "pipx install failed"

# ── 5. Ableton MCP server ─────────────────────────────────────
step "Ableton MCP server (ableton-live-mcp)"
if have ableton-live-mcp; then
  ok "Already installed → $(command -v ableton-live-mcp)"
else
  pipx install ableton-live-mcp
  have ableton-live-mcp \
    && ok "Installed → $(command -v ableton-live-mcp)" \
    || log_error "ableton-live-mcp install failed"
fi

# ── 6. NotebookLM CLI ─────────────────────────────────────────
step "NotebookLM CLI (notebooklm-py)"
if have notebooklm; then
  ok "Already installed → $(command -v notebooklm)"
else
  pipx install notebooklm-py
  have notebooklm \
    && ok "Installed → $(command -v notebooklm)" \
    || log_error "notebooklm-py install failed"
fi

# ── 7. ChromaDB memory ────────────────────────────────────────
step "ChromaDB memory (local, no API key)"
if pipx list 2>/dev/null | grep -q "chromadb"; then
  ok "chromadb already installed"
else
  pipx install chromadb 2>/dev/null \
    && ok "chromadb installed — local memory ready" \
    || warn "chromadb install failed — memory features will be unavailable"
fi

# ── 7b. BM25 search — inject into chromadb venv ──────────────
step "BM25 search (rank-bm25 → chromadb venv)"
# rank-bm25 must live in the same venv as chromadb so the bridge and
# test runner (tools/run_tests.sh) can import it together.
if pipx list 2>/dev/null | grep -q "chromadb"; then
  pipx inject chromadb rank-bm25 2>/dev/null \
    && ok "rank-bm25 injected into chromadb venv" \
    || warn "rank-bm25 inject failed — BM25 rescue will soft-skip (non-fatal)"
else
  warn "chromadb venv not found — skipping rank-bm25 inject"
fi

# ── 8. Ableton remote scripts ─────────────────────────────────
step "Ableton remote scripts → User Library"

ABLETON_LIB="$HOME/Music/Ableton/User Library"
REMOTE_DIR="$ABLETON_LIB/Remote Scripts"
M4L_DIR="$ABLETON_LIB/Presets/Audio Effects/Max Audio Effect"
ASSETS="$ROOT/machine-assets"
STAMP="$(date +%Y%m%d-%H%M%S)"

install_asset() {
  local src="$1" dest_dir="$2"
  local name; name="$(basename "$src")"
  mkdir -p "$dest_dir"
  if [[ -e "$dest_dir/$name" ]]; then
    mv "$dest_dir/$name" "$dest_dir/$name.backup-$STAMP" 2>/dev/null || true
  fi
  cp -R "$src" "$dest_dir/"
}

# Check Ableton User Library exists (Ableton must have been launched at least once)
if [[ ! -d "$ABLETON_LIB" ]]; then
  warn "Ableton User Library not found at $ABLETON_LIB"
  warn "Open Ableton Live once, then re-run this installer to copy the scripts."
else
  install_asset "$ASSETS/ableton-remote-scripts/Ableton_Live_MCP" "$REMOTE_DIR"
  ok "Ableton_Live_MCP → $REMOTE_DIR"

  install_asset "$ASSETS/ableton-remote-scripts/AbletonOSC" "$REMOTE_DIR"
  ok "AbletonOSC → $REMOTE_DIR"

  install_asset "$ASSETS/max-for-live/AgentAudioTap.amxd" "$M4L_DIR"
  install_asset "$ASSETS/max-for-live/agent_audio_tap.js"  "$M4L_DIR"
  ok "AgentAudioTap → $M4L_DIR"
fi

# ── 9. NotebookLM login ───────────────────────────────────────
step "NotebookLM — log in with your Google account"
if have notebooklm; then
  echo
  echo "  A browser window will open. Log in with the Google account"
  echo "  where your NotebookLM notebooks live."
  echo
  read -p "  Press Enter to open the login page... "
  notebooklm login 2>/dev/null || warn "Login skipped — run 'notebooklm login' later"
  echo
  echo "  Your notebooks:"
  notebooklm list 2>/dev/null || warn "No notebooks found yet"
  echo
  echo "  After login, connect a notebook by running:"
  echo "  notebooklm use <notebook-id>"
fi

# ── 10. Write conductor_bridge_config.json ───────────────────
step "Linking tools → bridge config"

NLM_BIN="$(command -v notebooklm 2>/dev/null || true)"
AA_BIN="$ROOT/tools/audio-analyzer"
CHROMA_PATH="$ROOT/memory/chromadb"

python3 - <<PYEOF
import json, os

config_path = "$ROOT/tools/conductor_bridge_config.json"

# Load existing config if present
cfg = {}
if os.path.exists(config_path):
    try:
        with open(config_path) as f:
            cfg = json.load(f)
    except Exception:
        cfg = {}

# Write resolved paths
cfg["conductor_root"]      = "$ROOT"
cfg["notebooklm_bin"]      = "$NLM_BIN"
cfg["audio_analyzer_bin"]  = "$AA_BIN" if os.path.exists("$AA_BIN") else ""
cfg["chromadb_path"]       = "$CHROMA_PATH"
cfg["start_bridge"]        = "$ROOT/tools/start_bridge.sh"
cfg["app"]                 = "$ROOT/app/index.html"

# Ensure chromadb storage folder exists
os.makedirs("$CHROMA_PATH", exist_ok=True)

with open(config_path, "w") as f:
    json.dump(cfg, f, indent=2)

print("  Config written to: " + config_path)
PYEOF

ok "conductor_bridge_config.json — all paths locked in"

# ── 11. Test the bridge ───────────────────────────────────────
step "Testing Conductor Bridge"
python3 "$ROOT/tools/conductor_bridge.py" &
BRIDGE_PID=$!
sleep 3
if curl -s --max-time 2 http://localhost:4611/ping 2>/dev/null | grep -q '"ok"'; then
  ok "Bridge is running on port 4611"
else
  warn "Bridge didn't respond — check Python installed correctly"
fi
kill $BRIDGE_PID 2>/dev/null; wait $BRIDGE_PID 2>/dev/null

# ── 13. Save environment ──────────────────────────────────────
step "Saving environment to ~/.zshrc"
ZSHRC="$HOME/.zshrc"
MARKER="# >>> CONDUCTOR >>>"
if ! grep -q "$MARKER" "$ZSHRC" 2>/dev/null; then
  {
    echo; echo "$MARKER"
    echo "export CONDUCTOR_ROOT=\"$ROOT\""
    echo "export NOTEBOOKLM_BIN=\"\$(command -v notebooklm 2>/dev/null || true)\""
    echo "export ABLETON_MCP_BIN=\"\$(command -v ableton-live-mcp 2>/dev/null || true)\""
    echo "# <<< CONDUCTOR <<<"
  } >> "$ZSHRC"
  ok "Saved to ~/.zshrc"
else
  ok "Already in ~/.zshrc"
fi

# ── Summary ───────────────────────────────────────────────────
echo
if [[ ${#ERRORS[@]} -eq 0 ]]; then
  echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════${RESET}"
  echo -e "${GREEN}${BOLD}  ✓  Setup complete — no errors.${RESET}"
  echo -e "${GREEN}${BOLD}  ══════════════════════════════════════════${RESET}"
else
  echo -e "${YELLOW}${BOLD}  ══════════════════════════════════════════${RESET}"
  echo -e "${YELLOW}${BOLD}  Setup finished with warnings:${RESET}"
  for e in "${ERRORS[@]}"; do echo -e "  ${RED}•${RESET} $e"; done
  echo -e "${YELLOW}${BOLD}  ══════════════════════════════════════════${RESET}"
fi

echo
echo -e "${BOLD}  Two manual steps left (can't be automated):${RESET}"
echo
echo "  1. Open Ableton Live"
echo "     Preferences → MIDI → Control Surface 1 = Ableton_Live_MCP"
echo "                          Control Surface 2 = AbletonOSC"
echo "     Then restart Ableton."
echo
echo "  2. Start Conductor"
echo "     Double-click  tools/start_bridge.sh"
echo "     Open          app/index.html  in Chrome"
echo
read -p "  Press Enter to close... "
