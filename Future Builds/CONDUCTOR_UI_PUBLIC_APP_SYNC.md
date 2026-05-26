# Conductor Public App UI Sync

> Purpose: keep the old UI placeholder direction aligned with the new public-grade Conductor architecture.  
> This file prevents losing the product/UI direction while backend Phase D trust slices continue.

---

## 1. Core Direction

The old project/UI placeholders are not being thrown away.

They become the **public Conductor app experience**, but rebuilt on top of the new phased architecture:

```text
Old UI prototype
→ Electron public app shell
→ backed by Phase A/B/C/D brain + trust layer
→ safe for public users, not just personal use
```

The target is:

```text
Conductor = a local-first AI assistant engineer for Ableton
that sits on the user's Mac, understands the current session,
proves what it changes, and stays out of the creative flow.
```

---

## 2. Uploaded UI Assets Reviewed

### Phase 1 — Installation / Setup UI

File:

```text
Conductor_Setup_Phase1.html
```

Strong ideas to preserve:

- cinematic first-run onboarding
- “Start studio tasks from anywhere on your Mac”
- Control + Command shortcut trainer
- Conductor notch introduction
- permission education
- Accessibility / Screen Recording / Plugin Bridge setup
- Plugin Bridge explained as safe session/plugin context
- approval-first framing before edits happen

Main product role:

```text
Phase 1 = first-run setup and trust onboarding
```

This should become part of Phase E / Electron onboarding.

---

### Phase 2 — How Conductor Sits on User’s Mac

File:

```text
Gpt version phase 2.html
```

Strong ideas to preserve:

- macOS menu-bar/notch style presence
- compact notch states: Listening / Thinking
- floating Conductor panel
- Session and Tasks tabs
- chat with Execute in Ableton action
- Live / Analyze / Voice / Auto Exec toolbar
- source selector:
  - Auto
  - Source files
  - NotebookLM
  - Memory only
  - No sources
- activity timeline:
  - Now
  - Recent
- integrations/settings pages
- Ableton MCP / NotebookLM / Mem0 / PluginBridge rows
- customization controls for glow, size, transparency
- shortcut settings
- detached/floating chat idea

Main product role:

```text
Phase 2 = always-available Mac workspace UI
```

This should become the main Electron shell direction.

---

### Planning Docs

Files:

```text
WIRING.md
WHAT TO FIX.md
```

These are important because they show what is wired, what is placeholder, and what must be fixed before public release.

Key points to preserve:

- current stage is browser prototype
- bridge is local
- Ableton MCP stays
- NotebookLM stays as optional/power-user connector
- PluginBridge stays
- Mem0/memory concept stays, but must map into new Phase C/H memory architecture
- fLive must fetch real Ableton session state
- Analyze must run through bridge/audio-analyzer and show results in chat
- Auto source routing must become real
- source modes must be defined
- connection setup page must be turned into real public onboarding
- browser-only pieces should be replaced by Electron/macOS equivalents

---

## 3. UI Product Principles

### Keep

```text
notch presence
floating compact chat
global shortcut
Live / Analyze / Voice / Auto Exec toolbar
source selector
task/activity timeline
setup wizard
integration status panel
customization
approval-first UX
```

### Upgrade

```text
placeholder UI → real bridge-backed state
fake messages → real AI/bridge responses
manual setup → guided setup wizard
raw execution → ActionProof/verification receipts
source dropdown → real routing into Phase B/C context system
activity list → real black box action log
settings toggles → persisted app settings
```

### Reject

```text
frontend-only safety
fake connected states
execute button without Phase D proof
Auto Exec without protection model
NotebookLM as required core memory
black box logs injected into prompts by default
user-facing raw debug traces
```

---

## 4. Phase Ownership

### Phase A — Foundation/Vault

UI surfaces:

- plugin inventory
- producer DNA
- never-do rules
- studio setup
- onboarding preferences
- operator cards
- project folders

Electron UI should eventually expose:

```text
Settings → Studio Setup
Settings → Plugin Inventory
Settings → Never-Do Rules
Settings → Producer Profile
```

---

### Phase B — Context Pack

UI surfaces:

- current mode
- current risk
- protection level
- session freshness
- source status

Electron UI should show:

```text
Mode: SESSION / MENTOR / READ / WRITE_SAFE / WRITE_RISKY
Protection: AUTO_EXECUTE / CONFIRM_REQUIRED / BLOCKED
Context: Fresh / Stale / Refreshing
```

Do not show this to normal users as scary debug text by default. Make it collapsible.

---

### Phase C — Retrieval

UI surfaces:

- source selector:
  - Auto
  - Source files
  - NotebookLM
  - Memory only
  - No sources
- evidence/debug panel
- context preview
- retrieved operator card snippets
- project memory results

Important mapping:

```text
Auto → use classifier + routed retrieval
Source files → local references/manuals/project files
NotebookLM → optional deep research connector
Memory only → Phase C memory collections
No sources → freeform chat only
```

The current source selector idea is good, but it must wire into the real Phase C router.

---

### Phase D — Trust Layer

UI surfaces:

- ActionProof receipts
- verified / failed / unverified status
- before/after values
- feedback buttons
- undo button later
- recent actions timeline
- “what did you change?” panel

The Phase 2 “Tasks / Recent” panel should become the visual surface for Phase D black box logs.

Mapping:

```text
Now → currently executing action
Recent → black box log summaries
Execute in Ableton → protected action proposal + Phase D proof
Auto Exec → only allowed when protection model says safe
```

---

### Phase E — Electron/Public App

UI surfaces:

- bridge auto-launch
- first-run setup
- permissions
- Ableton connection check
- PluginBridge detection
- NotebookLM optional connector
- audio analyzer file picker
- update/support
- app state handling:
  - Bridge not running
  - Ableton disconnected
  - PluginBridge missing
  - Permissions missing
  - Ready

Phase E is where the two HTML placeholders become a real Electron product.

---

### Phase G/H/I/F — Future Public Scale

Later UI areas:

```text
Phase G — audio analysis / reference track DNA
Phase H — memory review / promotion / export-import-reset
Phase I — trust debugger / reliability dashboard
Phase F — hosted knowledge sync / community vault updates
```

---

## 5. Setup Flow Recommendation

The setup flow should become:

```text
1. Welcome / brand reveal
2. Shortcut trainer
3. macOS permissions
4. Bridge check
5. Ableton connection check
6. PluginBridge check
7. Optional connectors:
   - NotebookLM
   - Audio Analyzer
   - Basic Pitch
8. Plugin scan
9. Producer setup:
   - primary EQ
   - compressor
   - reverb
   - saturator
10. Ready screen
```

Important: setup must distinguish required vs optional.

Required:

```text
Conductor app
local bridge
Ableton connection
basic permissions
```

Optional:

```text
NotebookLM
audio analyzer
Basic Pitch
advanced PluginBridge maps
hosted sync
```

---

## 6. Phase 2 Mac Presence Recommendation

The Phase 2 notch/floating UI should become the main product surface.

Primary states:

```text
Idle
Listening
Thinking
Inspecting
Executing
Verified
Failed
Blocked
Needs confirmation
```

Main tabs:

```text
Session
Tasks / Recent Actions
Settings
```

Toolbar:

```text
Live
Analyze
Voice
Auto Exec
Source
```

Recommended behavior:

- Live pulls real Ableton state through the bridge.
- Analyze opens file picker or captures audio, then routes to audio analyzer.
- Voice uses macOS/Electron voice capture.
- Auto Exec is disabled unless protection model allows it.
- Source selector controls Phase C retrieval routing.
- Tasks tab reads Phase D black box summaries.
- Recent verified actions show ActionProof summaries.

---

## 7. Current UI Fix Backlog From Old Prototype

### Must fix before public UI

```text
NotebookLM response formatting
fLive button pulling real Ableton data
Analyze button showing analysis result in chat
Auto source routing
Memory-only source routing
Source files source definition
Session tab content
connection status truthfulness
fake responses replaced by real AI/backend flow
```

### UX polish

```text
Auto Exec inactive state
NLM bubble copy button
NLM loading state color
source label reset
chat placeholder changes by source
notch/panel hover/dropdown stability
```

### Public app states to add

```text
Bridge starting
Bridge failed
Ableton disconnected
PluginBridge missing
Permission missing
Readback failed
Action blocked by never-do
Action verified
Action unverified
Feedback stored
Undo unavailable
```

---

## 8. Backend ↔ UI Contract

Electron UI should not decide safety. Backend decides.

UI calls local bridge endpoints:

```text
GET  /ping
GET  /status
GET  /context/session
GET  /context/pack
POST /action/track_volume
POST /action/track_pan
POST /action/track_mute
POST /action/track_solo
POST /feedback
```

Future endpoints:

```text
POST /action/undo
GET  /actions/recent
GET  /actions/summary
POST /audio/analyze
GET  /studio/inventory
GET  /vault/status
POST /setup/plugin-scan
```

UI displays:

```text
mode
risk
protection_level
verification_status
ActionProof summary
feedback status
connection status
```

Backend enforces:

```text
never-do rules
protection model
readback verification
ActionProof writing
black box logging
feedback validation
undo eligibility
```

---

## 9. Electron Migration Rule

Do not rewrite the backend into Electron.

Correct architecture:

```text
Electron main process
→ launches Python bridge
→ waits for /ping
→ renders UI
→ calls localhost bridge endpoints
→ shows state/proof/results
```

Keep Python brain independent:

```text
rag/
tools/conductor_bridge.py
conductor-vault/
memory/
tests/
```

Electron is the shell/dashboard, not the brain.

---

## 10. Acceptance Criteria For Public UI

The public UI is not ready until:

```text
1. First-run setup can guide a non-technical user.
2. Bridge starts automatically.
3. Ableton connection state is truthful.
4. PluginBridge state is truthful.
5. Live button returns real session state.
6. Analyze button returns real analysis results.
7. Source selector actually routes context.
8. Execute button never bypasses protection model.
9. Verified actions show proof receipts.
10. Failed/unverified actions never say done.
11. Feedback writes to feedback log.
12. Recent tasks are real black box events.
13. No fake connected/ready states remain.
14. App has clear error states.
15. Phase A/B/C/D tests still pass after Electron integration.
```

---

## 11. Product Direction Lock

The direction is:

```text
Phase 1 UI = onboarding and permissions
Phase 2 UI = notch/floating Mac presence
Phase D backend = trust/proof/action logs
Phase E = Electron migration and public app readiness
```

Do not lose the old placeholder ideas.

Do not ship them as fake demo UI either.

They become real when wired to:

```text
Phase A vault
Phase B context pack
Phase C retrieval
Phase D ActionProof / black box / feedback
Electron app shell
```

---

## 12. Next Step

After Phase D Slice 3 is audited by Codex:

```text
1. Continue Phase D backend slices:
   - feedback lock
   - undo
   - UI receipts
2. In parallel, keep this UI sync file as the Phase E input.
3. When Phase D trust layer is stable, ask Claude/Codex to convert the HTML placeholders into an Electron UI architecture plan.
4. Only then start implementing the Electron shell.
```

