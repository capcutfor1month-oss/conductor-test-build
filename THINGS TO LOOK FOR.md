# Things To Look For
> Edge cases, alternatives, and known issues for specific user setups.
> Update this as new cases are discovered during testing.

---

## What is `.env.template`?

The `.env.template` file is a placeholder that shows you what API keys Conductor needs.

**What to do:**
1. Find `.env.template` in the Conductor folder
2. Make a copy of it — rename the copy to `.env` (just remove `.template`)
3. Open `.env` in any text editor
4. Replace `your_google_api_key_here` with your actual key

**What it looks like after filling it in:**
```
GOOGLE_API_KEY=AIzaSyAbCdEfGhIjKlMnOpQrStUvWxYz123456
```

**Why is this needed?**
Conductor's memory system (Mem0) runs on Google's Gemini AI. It needs your Google API key to remember things you tell it across sessions — like your mixing preferences, what worked, what didn't.

**How to get a Google API key (free):**
1. Go to `https://aistudio.google.com/apikey`
2. Sign in with your Google account
3. Click `Create API Key`
4. Copy the key → paste it into `.env`

Free tier gives you 1,500 requests/day — more than enough for daily use.

---

## Intel Mac (Non-Apple Silicon)

**The problem:**
The `audio-analyzer` binary included in `tools/audio-analyzer` is compiled for **Apple Silicon only** (M1/M2/M3/M4). It will not run on Intel Macs.

**How to check which Mac you have:**
Click Apple menu → `About This Mac`
- Shows `Apple M1 / M2 / M3 / M4` → you're fine, binary works
- Shows `Intel Core i5 / i7 / i9` → you need to build from source

**If you're on Intel Mac — build from source:**
```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"

# Clone and build the audio analyzer
git clone https://github.com/capcutfor1month-oss/ai-music-production.git
cd ai-music-production/audio-analyzer-rs
cargo build --release

# Copy the built binary to Conductor tools
cp target/release/cli /path/to/TEST-BUILD/tools/audio-analyzer
```

**What breaks without it:**
- The `Analyze` button in Conductor chat won't return results
- Bridge will show `audio_analyzer: not_installed` in status
- Everything else works fine

---

## Older macOS Versions

**Minimum required: macOS 12 Monterey**

| macOS | Status |
|---|---|
| macOS 15 Sequoia | ✅ Fully tested |
| macOS 14 Sonoma | ✅ Works |
| macOS 13 Ventura | ✅ Works |
| macOS 12 Monterey | ✅ Should work |
| macOS 11 Big Sur | ⚠️ Not tested — Homebrew may have issues |
| macOS 10.x | ❌ Not supported |

**Fix for older macOS:** Update to at least macOS 12. Apple menu → System Preferences → Software Update.

---

## Homebrew Already Installed But Not Found

**Symptom:** `install.command` says "Installing Homebrew" even though you already have it.

**Why:** Homebrew may be installed at a different path on Intel Macs (`/usr/local/`) vs Apple Silicon (`/opt/homebrew/`).

**Fix:** The installer handles both paths automatically. If it still fails:
```bash
# Run this in Terminal, then re-run install.command
eval "$(/opt/homebrew/bin/brew shellenv)"   # Apple Silicon
# OR
eval "$(/usr/local/bin/brew shellenv)"       # Intel
```

---

## pipx Tools Not Found After Install

**Symptom:** `ableton-live-mcp` or `notebooklm` installed fine but Terminal says "command not found".

**Why:** `pipx ensurepath` adds `~/.local/bin` to your PATH but the current Terminal session doesn't know about it yet.

**Fix:** Close Terminal completely and reopen it. Or run:
```bash
source ~/.zshrc
```

---

## NotebookLM Login Fails or Browser Doesn't Open

**Symptom:** `notebooklm login` command hangs or gives an error.

**Why:** The `notebooklm-py` package uses browser-based OAuth. If your default browser is blocked or the Google account has 2FA issues it can fail.

**Fix options:**
1. Make sure Chrome or Safari is set as your default browser
2. Run login manually after install: `notebooklm login`
3. If still failing, check your Google account isn't using Advanced Protection Program

---

## Ableton User Library Not Found

**Symptom:** Installer says `Ableton User Library not found` and skips copying remote scripts.

**Why:** Ableton creates its User Library only after you open it for the first time.

**Fix:**
1. Open Ableton Live once
2. Let it finish loading (it creates the folder on first launch)
3. Re-run `install.command` — it will find the folder this time

**Default location:** `~/Music/Ableton/User Library`
If yours is in a different location (e.g. on an external drive), the installer will miss it.

**Manual fix for custom location:**
```bash
ABLETON_USER_LIBRARY="/Volumes/YourDrive/Ableton/User Library" \
  /path/to/TEST-BUILD/install.command
```

---

## Mem0 Memory Not Working

**Symptom:** Conductor doesn't remember anything between sessions. Memory source shows disconnected.

**Checklist:**
1. `.env` file exists (not just `.env.template`) — check the Conductor folder
2. `GOOGLE_API_KEY` in `.env` is filled in correctly — no spaces, no quotes
3. `start_mem0_mcp.sh` is running — double-click it before opening Conductor
4. Google API key has not hit its free tier limit — check `https://aistudio.google.com/`

---

## Ableton Connects Then Disconnects

**Symptom:** Ableton shows as connected in Conductor but drops after a few seconds.

**Most common cause:** Another app (Logic Pro, another DAW) is using the same MIDI port.

**Fix:**
1. Close Logic Pro or any other DAW
2. In Ableton Preferences → MIDI — make sure no other Control Surfaces are set to conflicting ports
3. Restart Ableton

---

## NotebookLM Returns Empty Responses

**Symptom:** You send a question with NotebookLM source selected, the N badge appears, but the response is blank or says "no results".

**Why:** Your notebook may have no sources added yet, or the notebook ID is wrong.

**Fix:**
1. Go to `notebooklm.google.com` — check your notebook has sources added
2. Run `notebooklm list` in Terminal — verify the right notebook is selected
3. Re-run `notebooklm use <your-notebook-id>` with the correct ID

---

## Windows / Linux

Conductor currently only supports **macOS**.

The bridge server (`conductor_bridge.py`) is Python and will run on any OS, but:
- `install.command` is a bash script — won't run on Windows
- Ableton remote scripts assume macOS paths
- `notebooklm-py` has macOS-specific auth flow

**Windows/Linux support:** planned for a future version. Not in current scope.

---
*Update this file whenever a new edge case is found during testing.*
