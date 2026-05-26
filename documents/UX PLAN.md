# Conductor — UX Plan
> The full user experience from first launch to daily use.
> Update this as decisions are made.

---

## Core Principles

- **Nothing blocks the user.** Setup happens when they need it, not upfront.
- **Everything is bundled.** No internet required at install time. Nothing can break mid-install.
- **Updates are controlled.** Tested by Adi + Claude/AI before pushed to users via update server.

---

## The Full Flow

### 1. First Launch
- User double-clicks **Conductor.app**
- Cinematic intro plays (Phase 1 HTML)
- Same launch silently unpacks and installs all bundled dependencies in the background
- No Terminal. No separate install step. No internet.

### 2. Cinematic Ends → Notch Appears
- Notch animates into top of screen
- **Quick tour begins** — each notch feature highlighted, ~4 seconds each
- Tour ends with a **pre-recorded AI chat demo** — realistic fake session showing what Conductor looks like in real use

### 3. App is Ready
- User lands on the notch / float chat
- No forced setup. No wizard. No gates.
- They can explore immediately.

### 4. Settings (when user is ready)
- Accessed via **gear icon** in the notch
- This is where API keys live:
  - Anthropic API key (required for chat)
- User adds them when they decide to, not before.

### 5. Tutorials Panel
- A dedicated panel inside the notch
- Contains setup guides for things that need manual steps:
  - **Ableton MCP setup** — short video clip (~45 sec)
  - **NotebookLM connection** — short video clip (~60 sec)
  - Future guides added here as needed
- User goes here when they're ready to connect those tools.

---

## What Exists Now

| Part | File | Status |
|---|---|---|
| Cinematic intro | `NEW/Conductor_Setup_Phase1.html` | 80% done |
| Notch + chat UI | `NEW/Claude version phase 2.html` | Working |
| Install script | `TEST-BUILD/install.command` | Done (bash, not bundled yet) |
| Bridge server | `TEST-BUILD/tools/conductor_bridge.py` | Done |
| Tutorial scripts | `TEST-BUILD/SETUP TUTORIAL SCRIPT.md` | Written, not recorded |

---

## What to Build Next

### Immediately buildable (HTML only)
1. **Tour sequence** in Phase 1 HTML — 4-sec feature highlights after cinematic, ends with pre-recorded fake chat
2. **Tutorials panel** in Phase 2 HTML — panel tab with embedded video clips
3. **API key fields in Settings** — Anthropic + Google keys, save to bridge config

### Needs more infrastructure
- **Bundled .app installer** — requires Tauri or Electron packaging (not just HTML)
- **Update server** — requires backend, hosting, versioning pipeline (maintained by Adi + AI)

---

## Update Pipeline (planned)

- Updates tested by Adi + Claude (or other CLI AI) first
- Only pushed to users after passing test
- Delivered via maintenance/update server window
- Users get updates silently or with a small notch indicator

---

*Last updated: May 2026*
