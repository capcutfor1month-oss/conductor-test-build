# Conductor — Full Product-Direction Audit

> **Target Audience:** Aditya (Product Owner) & Advanced Agentic Coding Team
> **Context:** Conductor must retain its soul as a personal assistant, mentor, and assistant engineer. The new build brings public-grade safety, but we must ensure it does not regress into a sterile, limited developer utility.

---

## A. Verdict Against Product Philosophy
**PASS WITH WARNINGS**
* **The Good:** The mathematical and backend safety (Phase A-D) is flawless. The foundation is rock solid.
* **The Warning:** The AI agents (Claude, Codex, Antigravity) have made silent assumptions that "friend-test" means "rough engineering demo." Conductor is drifting toward a restricted, 4-action developer endpoint rather than a premium co-producer.

---

## B. Top Silent Assumptions Found
The AI build process has silently made the following assumptions that violate the product direction. **These must be reversed or explicitly decided by you (the user):**

1. **Friend-Test = Rough UI:** Assumed that raw JSONL logs, terminal scripts, and database enum errors (`UNDO_DRIFT_READ_UNAVAILABLE`) are acceptable for friend-testing. *(Correction: Friend-test requires premium, real-product behavior).*
2. **Action Scope Reduction:** Assumed that verifying only 4 endpoints (volume, pan, mute, solo) was enough for now, silently deferring core producer tools (track creation, routing, plugins) indefinitely without asking.
3. **Overly Restrictive Hard-Blocks:** Assumed that dangerous actions should be strictly hard-blocked by the LLM/safety-gate, rather than triggering a premium "Confirmation/Are you sure?" UI dialog. This removes user agency.
4. **Deferring the Debugger:** Assumed the visual timeline/debugger could wait for a future public release because JSONL exists.
5. **Memory Promotion:** Assumed that turning session feedback into long-term memory (Producer DNA) can wait, ignoring the "mentor/assistant" soul of the project.
6. **Old Features Can Wait:** Assumed Notch UI, PluginBridge UI, and AgentAudioTap integrations could be deferred without user approval.

---

## C. What is Aligned
* **Safety & Trust Architecture:** The deterministic readback, drift detection, and ActionProof systems are genuinely public-safe. They fail closed and prevent hallucinated DAW destruction.
* **Component Modularity:** PluginBridge, NotebookLM research, AgentAudioTap, and audio-analyzer rust binaries are perfectly decoupled.
* **Context Protection:** Phase B/C token budgeting and corrective RAG ensure the LLM stays focused and doesn't get poisoned by stale memory.

---

## D. What is Drifting
* **The "Co-Producer" Soul:** The system is responding like an API (`"ok": true, "verification_status": "VERIFIED"`) rather than an assistant engineer (`"I pulled the kick down 2dB, let me know if it needs more."`).
* **UX & Failure States:** Failures currently look like crashes or developer exceptions to the user. They need to fail gracefully with actionable, human-readable advice.
* **User Agency:** The safety system is acting like a dictator (blocking) instead of an assistant (asking for confirmation).

---

## E. Old Feature Preservation Map

| Capability | Current Status | Recommendation / Audit Status |
| :--- | :--- | :--- |
| **Ableton basic control (vol/pan)** | Preserved | Current friend-test scope. |
| **Track basics (create/del/dup/color)** | Missing / Risk of loss | **Must be current friend-test scope.** |
| **Routing / Sends / Returns** | Missing / Risk of loss | **Must be current friend-test scope.** |
| **Arm / Record / Monitor** | Missing / Risk of loss | **Must be current friend-test scope.** |
| **PluginBridge / Param Changes** | Partially preserved (backend) | **Must be current friend-test scope.** Needs UI. |
| **Export / Bounce** | Missing | Needs explicit user decision (Current or Future?). |
| **NotebookLM / Research** | Preserved (backend) | Needs UI surface. |
| **ChromaDB / Routed Memory** | Preserved (backend) | Needs "Mentor" UI tone injection. |
| **Audio Analyzer / AgentAudioTap** | Preserved (backend) | Needs premium Notch UI integration. |
| **Notch / Floating Mac UI** | Missing / Risk of loss | **Must fix before friend-test.** |
| **Task / Activity Timeline Debugger** | Missing / Risk of loss | **Must fix before friend-test.** |
| **Integrations / Settings** | Missing / Rough | Must fix before friend-test (Premium Onboarding). |
| **Producer DNA / Personal Memory** | Partially preserved | Needs explicit user decision on promotion loop. |
| **Mentor Mode** | Partially preserved | Needs UI tone adjustment. |
| **Voice Shortcut** | Missing | Should fix before friend test if time allows. |
| **Never-Do Rules** | Preserved | Needs user review of Hard-Block vs Confirmation. |

---

## F. Friend-Test Readiness Gaps
To treat the friend-test as a **premium controlled release** (Perplexity Mac style), the following gaps exist:
1. **No Premium UI:** We lack the floating Mac Notch UI.
2. **Raw Error Codes:** Users will see JSON and enums instead of co-producer dialogue.
3. **No Visual Debugger:** Users cannot see *why* Conductor made a decision without opening terminal logs.
4. **Restricted Actions:** A 4-action demo will not impress a producer; they need routing, track management, and plugins.
5. **No Visual Diff for Undo:** When drift blocks an undo, there is no UI asking the user what to do.

---

## G. Action Expansion Recommendation
We must immediately expand beyond the 4-action demo.
**Action Slices for Friend-Test:**
* **Slice 1 (Session Management):** Create Track, Delete Track, Duplicate Track, Rename Track, Color Track, Group Tracks.
* **Slice 2 (Signal Flow):** Route Tracks, Set Send Levels, Create Return Track, Arm Record, Set Monitor Mode.
* **Slice 3 (Plugins):** Load Plugin, Bypass Plugin, Change Plugin Parameter (via LOM & PluginBridge).
* **Slice 4 (Export):** Export/Bounce (Pending User Decision).

**Safety Mapping:**
* **Hard Block:** Only explicitly destructive actions (e.g., `OVERWRITE_SESSION`). User must curate this exact list.
* **Confirmation Required (`Are you sure?`):** Delete Track, Route Master, Replace Plugin, Export.
* **Auto-Execute (with Readback/Undo):** Create, Duplicate, Route, Sends, Params, Volume, Pan, Color, Rename.

---

## H. Product-Quality Requirements Before Friend Test
**Must Fix Before Friend Test:**
1. **The Floating Notch UI:** Implement the premium Mac glassmorphism UI for all interactions.
2. **Co-Producer Translation Layer:** Wrap all ActionProofs, drift blocks, and backend errors in human-readable, assistant-style dialogue.
3. **Visual Studio Timeline:** Build a clean UI view of `action_log.jsonl` so users can audit what the AI is thinking/doing.
4. **Drift Diff Dialog:** If an undo drifts, show a premium modal: *"You manually changed the volume to -3dB. Do you want me to restore it to -8dB or keep your changes?"*
5. **Action Expansion:** Implement Slices 1, 2, and 3 (Tracks, Routing, Plugins).
6. **Premium Onboarding:** A "Studio Discovery Tour" instead of a raw API key terminal script.

**Acceptable Known Limitations:**
1. Multi-track complex arrangement parsing.
2. Background memory promotion (if we decide to defer the "dreaming" loop to Phase E).

---

## I. Updates Recommended for Agent Hand-off Docs
Update `CLAUDE.md`, `CODEX_REVIEWER.md`, and project context with these strict rules:
1. **"Do not silently decide product scope. If a feature from the old Conductor is difficult to implement safely, you must ASK the user how to proceed. Do not silently drop it."**
2. **"Do not assume 'friend-test' means a rough engineering build. All user-facing features must have premium product behavior. No raw JSON, no backend error enums in the UI."**
3. **"Do not default to HARD_BLOCK for safety. Ask the user if an action should be blocked, or if it simply requires a UI Confirmation step."**

---

## J. Concrete Next-Step Prompts for Claude/Codex

**Prompt 1 (Action Expansion):**
> "Claude, we need to expand Conductor's verified actions beyond the initial 4. Implement Track Management (Create, Delete, Duplicate, Rename, Color, Group). For 'Delete Track', implement it as CONFIRMATION_REQUIRED, not a hard block. Ensure all actions generate full ActionProofs and support Undo."

**Prompt 2 (Premium Translation Layer):**
> "Claude, build a Co-Producer Translation utility. It must take raw ActionProofs, Undo Validation Errors, and Bridge Error Codes and convert them into human-readable, premium assistant dialogue for the frontend UI. No raw JSON should reach the user."

**Prompt 3 (The Notch UI & Timeline):**
> "Claude, begin implementing the floating Mac Notch UI for Conductor. It must include a 'Studio Timeline' tab that parses the JSONL logs into a beautiful, visual history of what the assistant has done, why it made decisions, and what was blocked."

---

## K. North Star Statement

> **"Conductor is an elite co-producer living in your Mac's notch—a second pair of ears that deeply knows your studio, executes your tedious routing and mixing tasks with absolute precision, asks for confirmation before doing anything destructive, and protects your DAW session with bulletproof, silent safety."**
