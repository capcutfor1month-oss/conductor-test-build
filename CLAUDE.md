# Conductor — Session Context for Claude

> Read this at the start of every coding session.
> Source of truth: `project.md` (full audit log) + `tmp/BUILD_PHASES.md` (phase tracker).
> This file is operational shorthand — not a substitute for those.

---

## WHAT CONDUCTOR IS

A personal AI assistant, mentor, and assistant engineer for music producers.
It lives inside the producer's workflow: controls Ableton Live, queries a knowledge base, builds a memory profile of that specific producer over time, and enforces safe execution before writing anything to the DAW.

**It is NOT a generic dev tool, a music generator, or a chatbot with music knowledge.**
It is a product. Treat every decision — architecture, UX, safety, output — as product decisions.

**The core USP:** It grows with the user. Session 1 it is generic. Session 20 it knows their patterns, their taste, their past decisions. No other tool does this for music production.

---

## LOCKED DIRECTION

- Conductor is a **personal assistant + mentor + assistant engineer** for each user.
- **Preserve every useful old Conductor capability**, but rebuild it with public-grade architecture.
- **Limited scope is fine. Rough product behavior is not.** Every user-facing surface must feel intentional and premium.
- Do not treat this as a generic dev/test scaffold. It is a real product.
- Product behavior, setup, features, safety, and UI should feel considered — not bolted together.
- **Do not silently decide product scope.** If a feature from the old Conductor is difficult to implement safely, you must ASK the user how to proceed. Do not silently drop it.
- **Do not assume 'friend-test' means a rough engineering build.** All user-facing features must have premium product behavior. No raw JSON, no backend error enums in the UI.
- **Do not default to HARD_BLOCK for safety.** Ask the user if an action should be blocked, or if it simply requires a UI Confirmation step.
- Future direction: **Electron desktop app**, public release, per-user vault, hosted team knowledge server.

---

## ARCHITECTURE IN ONE VIEW

```
User message
    → Conductor UI (app/harness.html — Live Harness v1.5, active product-preview shell)
    → Anthropic API (Claude) — system_prompt.md injected every call
    → Conductor Bridge (localhost:4611) — HTTP, single gateway to all tools
         ├── Ableton Live (TCP 16619) — Python LOM execution
         ├── NotebookLM CLI — technique queries (5–15s, user's personal notebook)
         ├── Audio Analyzer (Rust MCP) — key, BPM, LUFS, stereo, sections
         ├── ChromaDB (local) — cross-session memory, 5 collections
         └── Conductor Vault (markdown) — producer DNA, never-do rules, operator cards
```

**Every user message gets 4 context layers before Claude answers:**
- Layer 1: `system_prompt.md` — static behavior rules
- Layer 2: Current project state — stage, BPM, key, tracks
- Layer 3: ChromaDB memory — top matches for this message, 5 routed collections
- Layer 4: Live Ableton state — what is connected right now

All 4 layers are wired (Phase B complete). Retrieval quality is Phase C (complete).

---

## PHASE / SLICE STATUS

| Phase | Status | What it covers |
|---|---|---|
| A | ✅ Complete | Plugin scanner, vault structure, operator cards, failure cases, schemas |
| B | ✅ Complete | Context pack builder, protection model, risk taxonomy, memory write contract |
| C | ✅ Complete | 5-collection RAG, temporal scoring, corrective RAG, BM25 rescue, token budget |
| D Slice 1 | ✅ Complete | ActionProof, black box logs, volume readback (6-step loop) |
| D Slice 2 | ✅ Complete | Pan / mute / solo readback + proof |
| D Slice 3 | ✅ Complete | `POST /feedback` — KEEP/UNDO/TOO_MUCH/NOT_ENOUGH/WRONG_DIRECTION |
| D Slice 4 | ✅ Complete | Compensating undo engine, drift detection, three-gate validation |
| D Slice 5 | ✅ Complete | Never-do preflight gate — deterministic enforcement on all write endpoints |
| Expanded Slice 1 | ✅ Complete | Create, Delete, Duplicate, Color, Rename, Group tracks |
| Expanded Slice 2 | ✅ Complete | Routing, Sends, Arm, Monitor, Transport controls |
| Expanded Slice 3A | ✅ Complete | `POST /action/plugin_bypass` — device bypass/activate with ActionProof, undo, never-do gate |
| Expanded Slice 3B | ❌ Roadmap | `POST /action/plugin_param` via PluginBridge |
| Expanded Slice 3C | ❌ Roadmap | PluginBridge placement on track |
| Expanded Slice 3D | ❌ Roadmap | `POST /action/plugin_load` |
| Expanded Slice 4 | ❌ Roadmap | Export / Bounce — pending user decision |
| Expanded Slice 5 | ❌ Roadmap | Clip / scene / session-view — pending user approval |
| D6 / CoProducer UI | ❌ Roadmap | Feedback buttons, CoProducerResponse layer, drift dialog, studio timeline — **required before friend-test** |
| D7 / D3 | ❌ Roadmap | Session-end hook + memory promotion ("dreaming") |
| E | ❌ Not started | Graph RAG, reference track DNA, Ragas evaluation |
| F | ❌ Not started | Hosted update server, team knowledge sync, public user model |

**Status:** Paused after Expanded Slice 3A. Ask user which slice to build next. See `tmp/HANDOFF_CURRENT_STATE.md` for full locked state + roadmap. `app/harness.html` is the active product-preview shell (Live Harness v1.5). `app/index.html` is the legacy Phase 2 prototype — not the active harness. `CoProducerResponse` translation required before any friend-test UI.

---

## KEY FILES — WHERE THINGS LIVE

| What | Path |
|---|---|
| Bridge (HTTP server, all endpoints) | `tools/conductor_bridge.py` |
| RAG retriever (mode routing, BM25, C3) | `rag/routed_retriever.py` |
| Memory schema (collections, thresholds, mode map) | `rag/memory_schema.py` |
| ActionProof (before/after state, VerificationStatus) | `rag/action_proof.py` |
| Readback (volume/pan/mute/solo 6-step loop) | `rag/readback.py` |
| Undo engine (drift detection, three-gate) | `rag/undo_engine.py` |
| Corrective RAG (contradiction suppression) | `rag/corrective_check.py` |
| Black box logs | `rag/black_box_log.py` → `memory/action_log.jsonl` + `memory/action_proof_log.jsonl` |
| Feedback log | `memory/feedback_log.jsonl` |
| Bridge error codes | `rag/bridge_errors.py` |
| Token budget / drop policy | `rag/token_budget.py` |
| Protection model (6 levels) | `rag/protection_model.py` |
| Risk taxonomy (action categories, plugin aliases) | `rag/risk_taxonomy.py` |
| Context pack builder | `rag/context_pack_builder.py` |
| Memory scoring (temporal decay, C2) | `rag/memory_scoring.py` |
| Vault failure cases | `conductor-vault/failure-cases/` |
| Producer DNA + never-do rules | `conductor-vault/producer/` |
| Operator cards (Pro-Q 4, Ozone 12, Serum 2, stock) | `conductor-vault/plugins/` |
| System prompt (injected every API call) | `app/system_prompt.md` |
| UI (active harness) | `app/harness.html` — Live Harness v1.5 |
| UI (legacy prototype) | `app/index.html` — Phase 2 prototype, not active |
| ChromaDB storage | `memory/chromadb/` |

---

## SAFETY RULES — NON-NEGOTIABLE

**ActionProof:**
Every write action (volume, pan, mute, solo, undo) must:
1. Capture `before_state` before writing
2. Write via Ableton LOM
3. Read back after write
4. Return `VerificationStatus`: `VERIFIED` / `ALREADY_CORRECT` / `FAILED` / `UNVERIFIED`
5. Log to `action_proof_log.jsonl` (append-only — original proof never modified)

**Never say done without readback.** `ok=True` in bridge responses only when `vstat` is `VERIFIED` or `ALREADY_CORRECT`. `FAILED` and `UNVERIFIED` return `ok=False`.

**Never-Do rules:**
`conductor-vault/producer/never_do_rules.md` defines hard blocks. Enforcement is deterministic — no LLM judgment on whether a never-do applies. Always `HARD_BLOCK` on matching action + target.

**Undo three-gate model:**
- Gate 1: `after_state[state_key]` must exist — checked before any LOM call. `confirm=True` does NOT bypass.
- Gate 2: Current live state must be readable — checked before write. `confirm=True` does NOT bypass.
- Gate 3: Drift detection (value changed since action) — blocks unless `confirm=True`.
- `UNDO_NO_AFTER_STATE` and `UNDO_DRIFT_READ_UNAVAILABLE` are hard errors.

**Append-only log invariant:**
`action_log.jsonl` and `action_proof_log.jsonl` are never modified. Every undo creates a new `UNDO_{original_type}` proof. No rewriting history.

**No native Ableton undo.**
Conductor's undo is compensating (restore before_state via LOM). Never call Ableton's own `Cmd+Z`.

**UI Trust & Prototype Limits:**
The `app/index.html` (phase 2 HTML) is prototype UI only. Prototype "Execute" buttons do not represent production trust behavior. Before friend-test UI is deployed, every Execute path must call verified `/action/*` endpoints. UI must never show "Executed" unless the backend returns a verified action response. A `CoProducerResponse` translation layer is required before production UI.

---

## NO-OVERBUILD POLICY

These are permanently out of scope until explicitly asked for:
- Batch undo / undo list / undo debugger
- Memory promotion (Slice 5+ only)
- Graph RAG / reference track DNA (Phase E)
- Hosted server / public user model (Phase F)
- ~~New action types beyond volume/pan/mute/solo~~ — **resolved.** Expanded Actions Slices 1, 2, and 3A are locked. Do not add future action types unless explicitly scoped, but locked expanded actions are now part of current build.

If a task description implies building one of these — stop and confirm. Do not gold-plate.

---

## TESTING & REVIEW WORKFLOW

**Claude builds. Codex audits.**

Every slice follows this cycle:
1. Claude builds: code + eval suite (new `run_dNN()` functions in the relevant slice eval file)
2. Run all 6 suites locally: `bash tools/run_tests.sh` (uses chromadb venv Python — has `rank-bm25` and `chromadb`)
3. Codex receives the slice for independent audit
4. If Codex returns FAIL: fix only the named blockers. Do not touch Phase D behavior to fix Phase C. Do not refactor broadly.
5. Log to `project.md` Audit section + update `tmp/BUILD_PHASES.md`

**Test suites (run sequentially — shared log files break on parallel runs):**
```
tests/phase_c_eval_set.py       ← 28 sections, all Phase C retrieval behavior
tests/test_vault_integrity.py   ← 15 checks, vault schema + seeder idempotency
tests/phase_d_slice1_eval.py    ← D01–D11
tests/phase_d_slice2_eval.py    ← D12–D22 (includes Slice 1 + Phase C regression)
tests/phase_d_slice3_eval.py    ← D23–D30
tests/phase_d_slice4_eval.py    ← D31–D40 (includes all prior regressions)
tests/phase_d_slice5_eval.py    ← D41–D50 (never-do; includes Slice 4 + Phase C regressions)
```

**Nested regression structure:** Each Slice N eval calls the previous slices and Phase C as regression checks. If Phase C fails, all D11/D19/D20/D29/D30/D37/D38 cascade-fail. Fix Phase C first.

**Phase C stability rules:**
- Section 18 (`c4_test_*` records) and Section 21 (`mt21_*` records) pre-clean stale DB state before seeding. If the test crashes and records persist, the next run cleans them.
- `run_failure_code_dedup_check()` also pre-cleans `mt21_` records from `failure_cases_index` before asserting stale IDs.
- Run Phase C **at least 3 consecutive times** to confirm stability before Codex submission.

---

## BACKUP CODING / LIMIT EXHAUSTED PROTOCOL

Use this when Claude Code session limits are exhausted and ChatGPT, Codex, or another assistant must continue the current build.

### Required context before backup coding begins

Paste ALL of the following into the backup session — do not skip items:

1. **Current build name** — e.g. `"Build 7 — Creative Critic v1"`
2. **Locked builds** — full locked-slice table from `tmp/BUILD_PHASES.md`
3. **Claude's last output** — exact final message before the session ended
4. **`git status --short`** — which files are modified / untracked
5. **`git diff`** — exact diff of all uncommitted changes
6. **Failing test output** — full `python3 tests/phase_d_sliceNN_eval.py` stdout if tests were failing (or "no failures")
7. **Relevant file sections** — paste the specific function(s) being edited if the diff alone is ambiguous
8. **Graphify report** *(optional)* — `graphify-out/GRAPH_REPORT.md` if the task requires tracing call paths across multiple files

### Backup assistant rules

- Do not invent repo structure. Work only from actual files, diffs, and test output provided.
- Ask for any missing context before writing a patch.
- Do not change scope. Build only what was already in progress.
- Do not touch protected files (see list below) unless they are explicitly named in the current build spec.
- Preserve all locked builds. Do not modify any PASS/LOCKED slice's code or tests.
- Write minimal patches only — targeted edits, not broad rewrites.
- Add or update tests only for the current slice.
- Do not mix in any of the following unless it is the explicitly approved current build:
  - Conductor Bridge / `conductor_bridge.py`
  - Knowledge Brain / RAG (`rag/*`)
  - Premium UI or CoProducer translation layer
  - Auto Execute path
  - Web search / current info features
  - PluginBridge
  - Operator Cards v2

### Graphify usage

- Graphify is allowed as a **build/research helper** to understand call paths, file relationships, and which tests cover a given module.
- Graphify is **not** a Conductor runtime dependency. Do not add any Graphify import or reference to production code.
- Use `graphify-out/GRAPH_REPORT.md` to trace which files are used by a module before editing it.

### Handoff format — fill this in when Claude stops

```
Build:               [e.g. Build 7 — Creative Critic v1]
Last completed step: [e.g. "Added call_creative_critic(); edited _handle_orchestrate explorer branch"]
Files changed:       [each file + one-line summary of what changed]
Tests run:           [suite name + section count + PASS/FAIL for each]
Current failure:     [exact test output, or "none — all passing"]
Next intended edit:  [exact function / file / line Claude would have touched next]
Do-not-touch list:   [files explicitly out of scope for this build]
```

### Recovery rule

If a backup assistant edits any production code (not tests only), Codex must perform a full slice audit before that slice is marked PASS/LOCKED. Log the audit result in `project.md` under a new Audit section.

---

## FILES/AREAS TO BE CAREFUL WITH

**`rag/routed_retriever.py`**
Most complex file. Handles: mode routing, semantic query, BM25 rescue, corrective RAG call, token budget, C1 Step 1 normalization. Do not change retrieval ranking logic without running all 6 suites. BM25 rescue must gracefully degrade if `rank_bm25` not installed.

**`rag/memory_schema.py`**
Single source of truth for collection names, thresholds, mode map, metadata schema. Never hardcode collection names elsewhere. Any change here cascades to all retrieval paths.

**`tools/conductor_bridge.py`**
All HTTP endpoints live here. v1.9 (POST /action/undo). Bridge error passthrough: every undo response path must include `"error_code": result.get("error_code", "")`. The drift-blocked 409 path has `STATE_DRIFT_COLLISION` hardcoded — that is correct.

**`rag/undo_engine.py`**
Three-gate model. `_fail_unreadable()` helper handles Gate 2. UndoValidationError with `.bridge_error_code` handles Gate 1. Do not add `confirm=True` bypass to Gates 1 or 2. Do not add batch undo here.

**`rag/corrective_check.py`**
Contradiction suppression. `CONTRADICTION_OVERLAP_THRESHOLD = 0.40`. The C4 scope guards (project_id / plugin_id) prevent over-suppression. Do not loosen without running Phase C Section 26.

**`tests/phase_c_eval_set.py`**
28 sections. Sections that seed ChromaDB data (18, 19, 20, 21, 26, 27, 28) all have pre-clean + `finally` cleanup. If adding new ChromaDB-seeding sections, follow the same pattern.

---

## TOKEN DISCIPLINE

### Response rules
- Do not restate the prompt. Acknowledge only if something is ambiguous.
- Avoid long explanations unless explicitly requested.
- When a task is done: files changed + root cause + exact fix + tests run + blockers/limitations. Nothing else.
- Never say "I'll now..." or "Let me...". Act, then report.
- Error messages should be exact (copy from output). Do not paraphrase test failures.

### Read rules
- Inspect only touched paths first — start from the specific function or class, not the whole file.
- Expand to full-file reads only when the file contains safety-critical logic (see ALWAYS FULL READ below).
- Do not read source files speculatively. Read only what you need for the specific change.
- Do not re-read an unchanged file you already read this session.
- Prefer `grep -n` + targeted `Read` with `offset` / `limit` over reading entire large files.
- When debugging a test failure: grep for the specific assertion first, read the surrounding block (~40 lines), then the relevant production code path.

### Log + diff rules
- Summarize logs before analysis: count, first/last N lines, unique error messages only.
- Use narrow diffs — show only changed lines + 3 lines of context.
- Prefer additive changes over rewrites. Do not restructure code while fixing a bug.

### What NOT to skip
- Do not skip tests to save tokens.
- Do not compress reasoning about safety-critical decisions.
- Preserve all audit, readback, and ActionProof behavior — no shortcuts.

### SAFE TO SKIM — token-savior symbol lookup / narrow Read acceptable
- `rag/memory_schema.py` — look up collection names, thresholds, mode map only
- `rag/memory_scoring.py` — scoring formula constants
- `rag/risk_taxonomy.py` — action category lists
- `rag/bridge_errors.py` — error code enum
- `rag/token_budget.py` — budget constant
- `rag/context_pack_builder.py` — field names, layer structure
- `rag/context_pack_logger.py` — log schema
- `tools/conductor_router.py` — route list
- `tests/` — individual `run_dNN()` function lookup
- `conductor-vault/plugins/` — operator card param lookup
- `data/known_plugins.json` — plugin alias lookup

### ALWAYS FULL READ — never skim, never substitute token-savior
- `rag/action_proof.py` — ActionProof, VerificationStatus, create_proof()
- `rag/readback.py` — 6-step readback loop for volume/pan/mute/solo
- `rag/undo_engine.py` — three-gate undo model, drift detection
- `rag/corrective_check.py` — contradiction suppression thresholds
- `rag/routed_retriever.py` — full retrieval pipeline (BM25, C3, token budget)
- `rag/black_box_log.py` — append-only log invariants
- `tools/conductor_bridge.py` — all HTTP endpoints, error passthrough paths
- `conductor-vault/producer/never_do_rules.md` — hard block rules
- Any file where you are about to write a RISKY or CONFIRM-level action

### token-savior MCP tools — use for
- Symbol lookup: `mcp__token-savior__get_function_source`, `mcp__token-savior__get_class_source`
- Repo navigation: `mcp__token-savior__search_codebase`, `mcp__token-savior__files`
- Lightweight search: grep-style queries across TEST-BUILD only (WORKSPACE_ROOTS scoped)
- Do NOT use token-savior to substitute a full read on any ALWAYS FULL READ file above.

---

## OUTPUT STYLE FOR THIS PROJECT

- Short responses. Specifics over prose.
- When a task is done: list files changed (path + what changed), tests run (suite name + pass/fail), and any limitations. Nothing else.
- Never say "I'll now..." or "Let me...". Act, then report.
- If a constraint prevents the task (e.g., scope boundary), say what it is in one sentence and stop.
- Error messages should be exact (copy from output). Do not paraphrase test failures.

---

## KNOWN LIMITATIONS CARRIED FORWARD

- `frequency` score in C2 temporal scoring is stubbed at `0.5` — actual access count tracking deferred to Phase D Slice 5+ (requires `POST /feedback` tracking to be wired).
- Memory promotion not built — Level 1 raw events never promoted to Level 2/3 confirmed patterns. Phase D Slice 5+.
- Plugin parameter verification (PluginBridge readback) not wired — Phase D Slice 6+.
- Bridge not auto-launched — must be started manually via `bash tools/start_bridge.sh`.
- UI Tutorials panel not built — users cannot connect NotebookLM or Ableton from within the app.

---

## FUTURE DIRECTION (do not build yet)

- **Electron desktop app** — `.app` bundling with auto-launch bridge, API key UI, onboarding
- **Public user model** — each user gets their own vault, producer DNA, memory profile
- **Hosted team knowledge server** — anonymous error collection, operator card submissions, vault sync
- **Phase E** — Graph RAG (LightRAG), reference track DNA, Ragas evaluation suite

These are directional anchors, not active tasks. Build Phase D Slice 5 first.
