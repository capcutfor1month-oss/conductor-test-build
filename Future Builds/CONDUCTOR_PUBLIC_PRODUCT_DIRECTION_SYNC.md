# Conductor Public Product Direction Sync

> Purpose: keep the old-project → new public Conductor direction clear so we do not lose the product architecture while building phases.

## Core Direction

Conductor is not a new project that replaces the old one.

Conductor is the old project’s useful feature set rebuilt into a public-grade, testable, safe, structured product.

Old project = feature inventory and proof of possibility.  
New project = public product architecture.

The target product is:

> A trusted AI assistant engineer for Ableton that knows the producer, knows the project, hears/analyzes audio, understands plugins/manuals/operator cards, safely operates existing tools, proves what changed, and learns only from confirmed outcomes.

## Same Direction Confirmation

The new build is still in the same direction as the old project. It is not becoming a generic engineering shell or a soulless automation tool.

The direction is:

> Old Conductor for Adi → public Conductor for every producer.

The old project supplied the soul: a personal assistant, mentor, and assistant engineer that knows the producer, knows the studio, understands the project, and helps inside Ableton.

The new build supplies the public-grade structure: phases, tests, scoped memory, deterministic safety, ActionProof, black box logs, feedback records, debugger data, and Electron/public onboarding.

The goal is to preserve every useful old feature, but rebuild it through proper scalable contracts so Conductor can be personal for each user, not only for Adi.

## Product Identity Lock

Conductor is three things at once:

1. **Assistant engineer** — it can inspect, prepare, and safely act inside Ableton.
2. **Mentor** — it explains decisions, teaches production/mixing/mastering concepts, and helps the user improve.
3. **Personal memory companion** — it learns each user’s taste, workflow, plugins, recurring mistakes, project goals, and never-do rules over time.

This is the product identity that must be protected during every future slice.

Conductor is not just:

- Ableton automation
- a chatbot
- a plugin controller
- a RAG demo
- a UI wrapper

Conductor is each producer’s personal assistant + mentor + assistant engineer.

## Product Standard

Conductor should feel like:

> A trusted assistant engineer who knows my studio.

Not:

> A chatbot that gives music tips.

The product moat is not generic Ableton chat. The moat is:

- producer memory
- project/session context
- Ableton control
- audio capture/analysis
- plugin inventory
- third-party plugin parameter control
- plugin/manual/operator knowledge
- risk-aware execution
- before/after verification
- confirmed learning

## Rule For Migrating Old Features

Every useful old feature comes forward, but only through the new architecture.

Do not bring old features back as random endpoints or personal scripts.

For every old feature, ask:

1. Which phase owns it?
2. What is the public-safe version?
3. What is the backend contract?
4. What is the UI state?
5. What test proves it works?
6. What failure state does the user see?
7. Does it preserve Phase A/B/C/D contracts?

## What Is Already Covered

### Phase A — Foundation / Vault / Plugin Knowledge

Covered:

- conductor-vault structure
- producer DNA
- never-do rules
- studio/plugin inventory
- known_plugins.json
- operator cards
- failure cases
- schemas and vault integrity tests

Public product meaning:

- user knowledge is structured
- plugin knowledge is versionable
- markdown is human-readable source
- JSON/YAML is machine-readable metadata
- ChromaDB is derived retrieval index, not source of truth

### Phase B — Context Delivery / Mode Awareness

Covered:

- context pack builder
- mode classifier
- protection levels
- session-start hook
- prompt-submit hook
- pre-risky-action hook
- context/debug view

Public product meaning:

- Conductor does not rely on the user manually pasting context
- mode/risk/protection state travels with the request
- the app can show why a response/action was allowed or blocked

### Phase C — Retrieval Quality / Memory Routing

Covered:

- five Phase C collections:
  - producer_memory_index
  - project_session_index
  - plugin_operator_index
  - failure_cases_index
  - audio_analysis_index
- routed retriever
- evidence labels
- temporal scoring
- corrective RAG
- BM25 exact rescue
- token budget
- context-pack logging
- vault integrity tests

Public product meaning:

- memory is routed by meaning
- plugin facts do not pollute producer DNA
- project decisions stay project-specific
- retrieval is inspectable and testable

### Phase D — Trust Layer / Safe Execution

Current progress:

- Slice 1: PASS / LOCKED
  - ActionProof
  - black box JSONL
  - structured bridge errors
  - never-do preflight
  - track volume readback verification

- Slice 2: PASS / LOCKED
  - track pan
  - track mute
  - track solo
  - better blocked-event correlation
  - safe boolean parsing

- Slice 3: PASS / LOCKED
  - POST /feedback
  - feedback JSONL
  - valid proof/action required
  - no memory promotion
  - no undo triggered

Public product meaning:

- Conductor must never say “done” unless readback verifies the action
- every real action must have a proof/log trail
- feedback attaches to a real ActionProof/action_id
- never-do rules are enforced outside the LLM

## Old Feature Preservation Rule

No useful feature from the old project should be silently dropped. Every old feature must be classified as one of:

- **Build now** — needed for the current friend-testable product.
- **Build later** — important, but belongs to a later phase.
- **Keep as optional connector** — useful for advanced users, but not required for the core product.
- **Replace with safer architecture** — keep the user-facing value, but not the old implementation style.
- **Reject only with reason** — remove only if it is unsafe, redundant, or not aligned with the product identity.

For every old feature, the migration question is not “copy or delete?”

The correct question is:

> What was the user value of this feature, and what is the public-safe version of that value?

Examples:

- Old raw Ableton execution → verified typed action endpoints with ActionProof.
- Old memory dump → routed scoped memory with promotion rules.
- Old error logs → debugger timeline and exportable debug bundle.
- Old UI/notch concept → Electron Mac presence with real backend state.
- Old personal behavior for Adi → onboarding + memory + feedback so every user gets their own personal Conductor.

## Old Project Feature Migration Map

| Old feature | New public architecture home | Public-grade version |
|---|---|---|
| Raw Ableton bridge / MCP | Phase D execution layer | Typed safe action endpoints with ActionProof/readback |
| ChromaDB memory | Phase C + Phase H | Routed memory, scoped collections, promotion rules |
| NotebookLM | Optional research connector | Deep research mode, not core product memory |
| Audio analyzer | Phase F/G audio intelligence | file picker, live capture, audio_analysis_index, before/after proof |
| AgentAudioTap | Phase F/G audio capture | guided setup, capture orchestration, health checks |
| PluginBridge | Phase D/G plugin execution | readback-verified parameter control, operator-card linked |
| ableton.md / failure docs | Phase A/C failure knowledge | failure_cases_index and public troubleshooting UI |
| Old chat/notch UI | Phase E Electron UI | public app shell with chat, status, proof receipts |
| Settings/tutorials | Phase E onboarding | guided setup wizard and health dashboard |
| /errors logging | Phase I reliability | real failure dataset, regression tests, diagnostics |
| Project/session memory | Phase B/C/H session management | stable project IDs, freeform isolation, session summaries |

## Public Product Phases After Brain Foundation

### Phase E — Product UX / Electron App Readiness

Goal: turn the working local system into a real public desktop app.

Build:

- Electron shell
- bridge auto-launch
- bridge health check
- Ableton connection state
- setup wizard
- API key entry
- plugin/bridge detection
- tutorials/setup panels
- project/session dashboard
- safe error-state UI
- action proof receipt UI
- feedback buttons
- recent actions panel
- context/debug panel for developer mode
- crash recovery prompt
- installer packaging and update checks

Important: Electron is the desktop shell, not the brain rewrite.

Backend stays Python/local bridge. Electron launches it, monitors it, and displays state.

### UI Phase 1 — Installation / Setup

Purpose: help a public user get Conductor working without knowing the developer setup.

Should include:

- welcome screen
- choose/install location
- API key setup
- Python/backend check
- Ableton connection guide
- PluginBridge setup/check
- optional NotebookLM connector
- optional AgentAudioTap/audio analyzer setup
- permissions check
- health dashboard
- first demo/test project flow

### UI Phase 2 — How Conductor Sits On The Mac

Purpose: define how Conductor lives in the user’s daily workflow.

Possible surfaces:

- main desktop app window
- menu bar helper
- compact floating/notch-style assistant
- Ableton connection indicator
- bridge status indicator
- quick action/recent action panel
- proof receipt panel
- settings and diagnostics
- project/session switcher

Key design rule:

Safe actions should feel smooth. Risky/failed actions should be visibly protected.

### Phase F/G — Audio + Plugin Intelligence Expansion

Build later:

- AgentAudioTap orchestration
- file picker for audio analyzer
- reference track DNA
- LUFS/true peak/stereo/phase/spectrum analysis
- before/after audio comparison
- audio_analysis_index memory
- plugin parameter maps from PluginBridge scans
- operator card expansion
- plugin reliability tracking

### Phase H — Memory / Personalization Scale

Build later:

- session/project/global memory UI
- “should this be remembered?” confirmation
- Level 1 → Level 2 → Level 3 promotion
- never-do rule proposal only with explicit confirmation
- memory conflict review
- memory decay/confidence
- export/import/reset
- long-session compaction

### Phase I — Debugger / Reliability / Evaluation

Build as a required friend-test/public-readiness layer, not as a luxury dashboard.

Purpose: rely on actual recorded behavior, not only verbal tester feedback.

Build:

- local session debugger
- test recorder for real sessions
- session timeline from context logs + ActionProof + action log + feedback log + undo results
- debug bundle export for friends/testers
- convert real failures into regression tests
- context-pack replay
- plugin/action reliability metrics
- bridge diagnostics
- “why did Conductor do this?” view
- golden dataset from actual producer workflows

Privacy rule: local-only by default, manual export only, redact secrets/API keys/file paths before public sharing.

### Phase J — Multi-Agent Build Workflow

Keep using:

- Claude = implementation
- Codex = audit/test
- Gemini/Perplexity/NotebookLM = research
- ChatGPT = synthesis, prompts, direction memory

Lock a slice only after Codex PASS.

## Current Build Discipline

For every slice:

1. Define small scope.
2. Claude builds only that scope.
3. Codex tests/audits.
4. If FAIL, Claude fixes blockers only.
5. If PASS, lock the slice.
6. Move future ideas to the future build file.

Current status:

- Phase A: PASS / locked
- Phase B: PASS / locked
- Phase C: PASS / locked
- Phase D Slice 1: PASS / locked
- Phase D Slice 2: PASS / locked
- Phase D Slice 3: PASS / locked

## Direction Guardrails

Do not do:

- Do not rewrite working A/B/C.
- Do not rebuild Python backend in Electron.
- Do not let UI enforce safety alone.
- Do not merge Phase D action logs into Phase C context logs.
- Do not make NotebookLM core memory.
- Do not auto-promote feedback into producer memory.
- Do not promise full Ableton rollback.
- Do not use native Ableton undo stack as trust foundation.
- Do not build public UI before backend state/error/proof contracts are stable.

Do:

- Keep backend local-first.
- Keep Electron as shell/orchestrator/UI.
- Keep ActionProof as execution truth.
- Keep black box logs on-demand only.
- Keep ChromaDB as derived/scoped retrieval.
- Keep never-do enforcement deterministic.
- Keep public user onboarding guided.
- Keep all old useful features, but migrate through phase-owned contracts.

## UI Placeholder Review Request

The user has already built placeholder UI in two phases:

1. Installation/setup flow.
2. How Conductor sits on the user’s Mac.

Before finalizing Phase E UI, review those placeholders and map them into:

- setup wizard
- app shell
- menu bar/floating assistant behavior
- bridge/Ableton health states
- proof receipt UX
- settings/tutorials
- diagnostics panel

Do not discard the placeholder UI. Treat it as early product direction and upgrade it into the public Electron UX plan.

## Slice Acceptance Question

Before locking any future slice, ask:

> Does this make Conductor more personal, useful, trustworthy, and mentor-like for the producer?

If yes, it belongs in the direction.

If it only makes the system more complicated without improving the producer’s trust, learning, workflow, or personal assistant experience, delay it.

This question prevents two failure modes:

1. Losing the old project’s personal/mentor soul.
2. Shipping powerful but unsafe automation without public-product trust.

## Final Product Direction

The new Conductor should include every useful feature from the old project, but upgraded into a product that is:

- public-safe
- local-first
- testable
- auditable
- phase-owned
- memory-safe
- UI-visible
- recoverable
- friendly for non-technical producers

The old project proved Conductor could be powerful.

The new project must prove Conductor can be trusted.
