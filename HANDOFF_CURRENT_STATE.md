# Conductor — Handoff: Current State
> Created: May 2026. Do not rewrite history — append updates below.
>
> **Source-of-truth note:** `tmp/HANDOFF_CURRENT_STATE.md` is the active operational handoff (latest slice state + key files). `tmp/BUILD_PHASES.md` is the active phase tracker. This root file is the durable summary — kept in sync but not the first-read doc.

---

## CURRENT PROJECT STATE

Phase D Slices 1–5 are complete and audited (PASS/LOCKED).
Expanded Actions Slice 1 is PASS/LOCKED (track_create, track_delete, track_duplicate, track_arm, track_monitor, track_rename, track_color, return_track_create, tracks_create_multiple).
Expanded Actions Slice 2 is PASS/LOCKED (track_send, track_route, transport_play, transport_stop, transport_record, transport_loop, transport_metronome).
Expanded Actions Slice 3A (`POST /action/plugin_bypass`) is PASS/LOCKED (9/9 tests).
Live Harness Slices 9–21 are PASS/LOCKED (Builds 6–14, Knowledge Explorer through CLARIFY Mode Hardening).
D Slice 22 (Build 15 — Knowledge Feedback Log v1) is PASS/LOCKED (8/8).
D Slice 23 (Build 16 — Ambient Feedback UI) is PASS/LOCKED (39/39).
All test suites pass. Phase C is stable.
Live Harness v1.5 is present (`app/harness.html`) — product-preview shell, not final shipped UI.
Product-layer re-alignment is pending (docs → harness UX → session-state → metadata hiding).

---

## COMPLETED PHASES / SLICES

| Phase | Status |
|---|---|
| A — Foundation (vault, operator cards, failure cases, plugin scanner) | ✅ Complete |
| B — Context pack builder, protection model, risk taxonomy, memory write contract | ✅ Complete |
| C — 5-collection RAG, BM25 rescue, corrective RAG, temporal scoring, token budget | ✅ Complete |
| D Slice 1 — ActionProof, black box logs, volume readback (6-step loop) | ✅ Complete |
| D Slice 2 — Pan / mute / solo readback + proof | ✅ Complete |
| D Slice 3 — `POST /feedback` (KEEP / UNDO / TOO_MUCH / NOT_ENOUGH / WRONG_DIRECTION) | ✅ Complete |
| D Slice 4 — Compensating undo engine, drift detection, three-gate validation | ✅ Complete |
| D Slice 5 — Never-do preflight gate | ✅ Complete |
| Expanded Actions Slice 1 — Create, Delete, Duplicate, Color, Rename, Group tracks | ✅ Complete (PASS/LOCKED) |
| Expanded Actions Slice 2 — Routing, Sends, Arm, Monitor | ✅ Complete (PASS/LOCKED) |
| Expanded Actions Slice 3A — `POST /action/plugin_bypass` | ✅ Complete (PASS/LOCKED) |
| D Slice 16 — Card-aware Creative Critic v1 (Build 8) | ✅ Complete (PASS/LOCKED — 8/8) |
| D Slice 17 — Plugin Knowledge Routing v1 (Builds 9 + 10) | ✅ Complete (PASS/LOCKED — 8/8) |
| D Slice 18 — Plugin Knowledge Trust Signals (Build 11) | ✅ Complete (PASS/LOCKED — 8/8) |
| D Slice 19 — Knowledge Status Context to Critic (Build 12) | ✅ Complete (PASS/LOCKED — 10/10) |
| D Slice 20 — Critic Composer Polish (Build 13) | ✅ Complete (PASS/LOCKED — 10/10) |
| D Slice 21 — CLARIFY Mode Hardening (Build 14) | ✅ Complete (PASS/LOCKED — 8/8) |
| D Slice 22 — Knowledge Feedback Log v1 (Build 15) | ✅ Complete (PASS/LOCKED — 8/8) |
| D Slice 23 — Ambient Feedback UI / Feedback Wiring v1 (Build 16) | ✅ Complete (PASS/LOCKED — 39/39) |

---

## LOCKED ARCHITECTURE DECISIONS

- **Single HTTP gateway** — all tools go through `conductor_bridge.py` on port 4611. No direct Ableton access from Claude.
- **ActionProof required on every write** — before_state → write → readback → VerificationStatus. `ok=True` only on `VERIFIED` or `ALREADY_CORRECT`.
- **Append-only logs** — `action_log.jsonl` and `action_proof_log.jsonl` are never modified. Every undo creates a new `UNDO_{type}` proof.
- **Compensating undo only** — restore `before_state` via LOM. Never call Ableton's native `Cmd+Z`.
- **Three-gate undo** — Gate 1 (missing after_state) and Gate 2 (unreadable live state) are hard blocks. `confirm=True` does NOT bypass either. Gate 3 (drift) is bypassable with `confirm=True`.
- **5 ChromaDB collections** — `producer_memory_index`, `project_session_index`, `plugin_operator_index`, `failure_cases_index`, `audio_analysis_index`. Names are locked. Do not add collections without explicit decision.
- **Never-do rules are deterministic** — no LLM judgment. Any matching action + target = `HARD_BLOCK`.
- **`memory_schema.py` is single source of truth** — collection names, thresholds, mode map. Never hardcode collection names elsewhere.
- **Bridge error passthrough** — every undo response path must include `"error_code": result.get("error_code", "")`.
- **`STATE_DRIFT_COLLISION`** — hardcoded in the drift-blocked 409 path in `conductor_bridge.py`. Correct. Do not change.
- **BM25 graceful degradation** — retrieval works without `rank_bm25`. BM25 sections soft-skip. Non-fatal.
- **Test suites must run sequentially** — D2 and D13 fail when Slice 1 and Slice 2 run in parallel (shared JSONL log files).

---

## CURRENT BLOCKERS

- **Active Harness:** `app/harness.html` is the current product-preview shell (Live Harness v1.5). `app/index.html` is the legacy Phase 2 prototype — not the active harness.
- **UI Trust Behavior & Prototype Status:** Live Harness is a developer-facing testing shell. Prototype "Execute" buttons do not represent production trust behavior.
- **Strict Verification Path:** Before friend-test UI is deployed, every Execute path must call verified `/action/*` endpoints. UI must never show "Executed" unless the backend returns a verified action response.
- **Co-Producer Translation Layer:** A `CoProducerResponse` / translation layer is strictly required before deploying production UI.
- **Product Direction:** Conductor must feel like a premium studio assistant — safe actions should feel effortless, with backend safety under the hood. Not a bank approval system or dev endpoint.

---

## CURRENT LIMITATIONS

| Limitation | Deferred to |
|---|---|
| `frequency` score in C2 temporal scoring stubbed at `0.5` | Phase D Slice 5+ (needs `POST /feedback` access count tracking wired) |
| Memory promotion not built — Level 1 raw events never reach Level 2/3 | Phase D Slice 5+ (`rag/memory_promotion.py` not created yet) |
| ~~Never-do preflight gate~~ | ✅ Wired — D5 complete. Deterministic enforcement on all write endpoints. |
| Plugin parameter verification (PluginBridge readback) not wired | Phase D Slice 5+ |
| Bridge not auto-launched | Manual: `bash tools/start_bridge.sh` |
| UI Tutorials panel not built | Users cannot connect NotebookLM or Ableton from within the app |
| Batch undo, undo chain, undo list | Explicitly rejected for Phase D (see below) |

---

## FILES CURRENTLY AUTHORITATIVE

| File | Authority |
|---|---|
| `CLAUDE.md` | Operational session context — read first every session |
| `tmp/BUILD_PHASES.md` | Phase/slice tracker — source of truth for what's built |
| `project.md` | Full audit log — do not rewrite |
| `rag/routed_retriever.py` | RAG mode routing, BM25 rescue, corrective RAG, token budget |
| `rag/memory_schema.py` | Collection names, thresholds, mode map |
| `tools/conductor_bridge.py` | All HTTP endpoints (v1.9) |
| `rag/action_proof.py` | ActionProof, VerificationStatus |
| `rag/readback.py` | Volume/pan/mute/solo 6-step readback loop |
| `rag/undo_engine.py` | Three-gate undo model |
| `rag/corrective_check.py` | Contradiction suppression (`CONTRADICTION_OVERLAP_THRESHOLD = 0.40`) |
| `rag/black_box_log.py` | Writes to `memory/action_log.jsonl` + `memory/action_proof_log.jsonl` |
| `conductor-vault/producer/never_do_rules.md` | Hard block rules — deterministic |
| `app/system_prompt.md` | Injected into every API call |
| `requirements.txt` | Python dependency documentation for bridge/test venv |
| `tools/run_tests.sh` | Test runner — uses chromadb venv Python |

---

## THINGS EXPLICITLY REJECTED

- **Batch undo / undo list / undo debugger** — out of scope, Slice 5+
- **Graph RAG / LightRAG / reference track DNA** — Phase E, not started
- **Hosted server / public user model** — Phase F, not started
- ~~New action types beyond volume/pan/mute/solo~~ — **resolved.** Expanded Actions Slices 1, 2, and 3A are locked. Do not add future action types unless explicitly scoped, but locked expanded actions are now part of current build.
- **Memory promotion ("dreaming")** — Slice 5+ only
- **Loosening `CONTRADICTION_OVERLAP_THRESHOLD`** — do not change without running Phase C Section 26
- **`confirm=True` bypass for Gates 1 or 2 in undo** — permanently rejected
- **Native Ableton undo (`Cmd+Z`)** — permanently rejected; compensating undo only
- **Electron app / auto-launch bridge / API key UI** — directional anchor, do not build yet
- **LLM judgment on never-do rule matching** — deterministic enforcement only

---

## NEXT RECOMMENDED TASK

**Phase D / Expanded Actions Follow-up** — in this order:

1. **Hygiene Alignment for Slice 2**: Clean up unnecessary future scaffolding in expanded actions.
2. **D3 / D7 — Memory promotion ("dreaming") & Session-end hook**: `rag/memory_promotion.py` — session-end hook that scores Level 1 raw events and promotes to Level 2/3 confirmed patterns.

Per `CLAUDE.md` no-overbuild policy: do not build batch undo, undo chain, or undo list.

---

## TESTING STATUS

| Suite | Status | Notes |
|---|---|---|
| `tests/phase_c_eval_set.py` (28 sections) | ✅ Pass | Stable — 3 consecutive runs confirmed May 2026 |
| `tests/test_vault_integrity.py` (15 checks) | ✅ Pass | Vault schema + seeder idempotency |
| `tests/phase_d_slice1_eval.py` (D01–D11) | ✅ Pass | |
| `tests/phase_d_slice2_eval.py` (D12–D22) | ✅ Pass | Includes Slice 1 + Phase C regression |
| `tests/phase_d_slice3_eval.py` (D23–D30) | ✅ Pass | |
| `tests/phase_d_slice4_eval.py` (D31–D40) | ✅ Pass | Includes all prior regressions |
| `tests/phase_d_slice21_eval.py` (D197–D204) | ✅ Pass | Build 14 — CLARIFY Mode Hardening |
| `tests/phase_d_slice22_eval.py` (D205–D212) | ✅ Pass | Build 15 — Knowledge Feedback Log v1 |
| `tests/phase_d_slice23_eval.py` (D213–D220) | ✅ Pass | Build 16 — Ambient Feedback UI |
| `tests/phase_d_slice20_eval.py` (D187–D196) | ✅ Pass | Build 13 — Critic Composer Polish |
| `tests/phase_d_slice19_eval.py` (D177–D186) | ✅ Pass | Build 12 — Knowledge Status Context to Critic |
| `tests/phase_d_slice18_eval.py` (D169–D176) | ✅ Pass | Build 11 — Plugin Knowledge Trust Signals |
| `tests/phase_d_slice17_eval.py` (D162–D168) | ✅ Pass | Builds 9+10 — Plugin Knowledge Routing |
| `tests/phase_d_slice16_eval.py` (D154–D161) | ✅ Pass | Build 8 — Card-aware Creative Critic |
| `tests/phase_d_slice15_eval.py` (D143–D153) | ✅ Pass | Build 7 — Creative Critic v1 |

**Run with:** `bash tools/run_tests.sh` — uses chromadb venv Python automatically.
**Must be sequential** — parallel runs collide on shared JSONL log files.

---

## KNOWN FLAKY TESTS (now fixed — context for next engineer)

All three were fixed May 2026. Pre-cleans are in place. These can recur if a test process is killed before `finally` cleanup runs.

| Section | Issue | Fix location |
|---|---|---|
| Phase C Section 21 — `producer_memory_index` NOT FOUND | Stale `mt21_` records + weak BM25 token overlap (1 token) | `run_failure_code_dedup_check()` pre-cleans `mt21_` from `failure_cases_index`; Section 21 pre-clean + seed text expanded to include "Vocals / last / session" |
| Phase C Section 18 — superseded item wrong metadata | Stale `c4_test_*` records from prior killed runs | Pre-clean of `c4_test_` records added before Section 18 seeding |
| Phase C dedup check — stale `mt21_failure_*` IDs | `run_failure_code_dedup_check()` runs BEFORE Section 21 pre-clean in `__main__` order | Pre-clean added directly inside `run_failure_code_dedup_check()` |

**If Phase C fails:** run 3 more times first. If still failing, check for stale `mt21_` or `c4_test_` records in ChromaDB before debugging retrieval.

---

## RULES THAT MUST NEVER BE VIOLATED

1. **Never say `ok=True` without readback.** `FAILED` and `UNVERIFIED` always return `ok=False`.
2. **Never modify `action_log.jsonl` or `action_proof_log.jsonl`.** Append only. Every undo creates a new proof.
3. **Never call Ableton's native undo.** Compensating only.
4. **Never bypass Gate 1 or Gate 2 in the undo engine.** Not even with `confirm=True`.
5. **Never use LLM judgment on never-do rule matching.** Deterministic string match only.
6. **Never hardcode collection names outside `rag/memory_schema.py`.**
7. **Never run test suites in parallel.** Always sequential.
8. **Never touch Phase D behavior to fix a Phase C test failure.** Fix Phase C first.
9. **Never refactor broadly when Codex returns a FAIL.** Fix only named blockers.
10. **Never start a scope-boundary item (batch undo, graph RAG, hosted server, Electron) without explicit user request.**

---

## BACKUP CODING / LIMIT EXHAUSTED — HANDOFF TEMPLATE

When Claude Code session limits are exhausted mid-build, fill in this template and paste it into the backup session (ChatGPT, Codex, etc.) along with the full context listed below.

**Context to include (do not skip):**
- This file (`HANDOFF_CURRENT_STATE.md`) and `tmp/HANDOFF_CURRENT_STATE.md`
- `tmp/BUILD_PHASES.md` — so the backup assistant can see all locked slices
- `git status --short` output
- `git diff` output (all uncommitted changes)
- Full test output for the current slice (even if passing)
- The specific function(s) being edited, if the diff alone is ambiguous

**Template — fill in before handing off:**

```
Build:               [e.g. Build 7 — Creative Critic v1]
Last completed step: [e.g. "Added call_creative_critic(); edited _handle_orchestrate explorer branch"]
Files changed:       [each file + one-line summary of what changed]
Tests run:           [suite name + section count + PASS/FAIL for each]
Current failure:     [exact test output, or "none — all passing"]
Next intended edit:  [exact function / file / line Claude would have touched next]
Do-not-touch list:   [files explicitly out of scope for this build]
```

**Backup assistant rules (pass these along):**
- Work only from actual files, diffs, and test output — do not invent repo structure.
- Ask for missing context before writing any patch.
- Do not change scope; build only what was in progress.
- Preserve all PASS/LOCKED slices — do not modify their code or tests.
- Minimal patches only.
- Do not mix in RAG, Premium UI, Auto Execute, Web/current info, PluginBridge, or Operator Cards unless that is the approved build.
- If any production code is edited, Codex must audit the slice before it is marked PASS/LOCKED.

Full protocol: `CLAUDE.md` → **Backup Coding / Limit Exhausted Protocol**
Codex audit rules: `CODEX_REVIEWER.md` → **Backup Coding Audit**

---

## CURRENT RE-ALIGNMENT STATUS

> Added May 2026 after Codex re-alignment audit.

| Area | Status | Notes |
|---|---|---|
| Backend trust (ActionProof, readback, never-do, undo, drift, logs, feedback) | ✅ Preserve | Strong foundation — do not regress. |
| Product feel | ❌ FAIL — needs correction | Safe actions feel like bank approvals. Must feel effortless; backend safety stays under the hood. |
| Live Harness v1.5 (`app/harness.html`) | ⚠️ Useful but needs UX cleanup | Developer-preview shell. AI Sandbox works but product UX needs re-alignment. |
| Docs | ⚠️ Stale / conflicting | This realignment pass corrects known stale claims. |
| Next fixes (in order) | — | Docs cleanup → harness UX → session-state context → metadata hiding / risky-action cleanup |
| `track_delete` and `transport_record` | 🔒 Disabled in harness | Pending proper confirmation UI. |
| `route_track` / routing actions | ⚠️ Careful | Routing can require confirmation — policy TBD. |
| ChromaDB memory | ⚠️ May be missing locally | Do not describe as fully available unless installed and seeded. |

---

## BUILD 16 — AMBIENT FEEDBACK UI (PASS/LOCKED)

> Added May 2026 after Codex Build 16 audit.

**Files touched:** `app/harness.js`, `app/harness.html`, `tests/phase_d_slice23_eval.py`, `docs/HARNESS_GUIDE.md`.

**What changed:**
- Added explicit `type:"clarify"` guard in `handleSandboxChat()` before the answer branch. Clarifying questions now display correctly and never receive feedback chips.
- `addChatMessage()` returns the created `wrap` element so callers can attach UI to it.
- Added `_sendKnowledgeFeedback(responseId, feedbackType)` — fire-and-forget `POST /harness/feedback`.
- Added `addFeedbackChips(wrap, responseId)` — attaches chip row below assistant bubble.
- Answer branch now calls `addFeedbackChips(wrap, data.response_id)` when both values are present.
- CSS added to `harness.html`: `.fb-chips`, `.fb-chip`, `.fb-chip:hover`, `.fb-chip[data-sent]`, `.fb-sub` — styled to match existing `.btn-copy` / `.msg-actions` muted design language.

**Eligibility rule (enforced in harness.js):**
- Chips appear only on `data.type === "answer"` with `data.response_id` present
- No chips on `type:"clarify"`, `type:"action"`, `!data.ok`, `needs_confirmation` path
- In clarify → answer flow: chips appear only on the final answer

**Chip UX:**
- `Helpful` → sends `HELPFUL`, collapses all chips
- `Not this ▾` → opens sub-row only, sends nothing
- `Too vague` → sends `TOO_VAGUE`, collapses all chips
- `Wrong` → sends `WRONG`, collapses all chips
- `Outdated` → sends `OUTDATED`, collapses all chips
- `data-sent="true"` set on `msg-wrap` after any send — prevents duplicate sends
- No toast, popup, survey, or "training data" wording

**What this does NOT do:**
- No memory promotion, ranking, or retrieval influence
- No ChromaDB writes
- No frequency score changes
- No changes to `tools/harness_server.py` or any rag/memory files

**Test suite:** `tests/phase_d_slice23_eval.py` — D213–D220, 39/39 PASS

**Next likely slice:** Build 17 — Memory Promotion v1 (`rag/memory_promotion.py`).
Only after Build 16 is audited and locked.

---

## PREMIUM NOTCH UI v1 — HARNESS UPDATE

> Added May 29, 2026 after Codex Premium Notch UI cleanup. UI-only harness work; no backend behavior changed.

**Files touched:** `app/harness.html`, `app/harness.js`.

**What changed:**
- Premium notch preview environment was cleaned up: lighter wallpaper, grey menu-bar area, black hardware notch, and black/glass software notch surface.
- Studio vs Freeform surface logic is harness-controlled by Ableton Open / Ableton Closed. These are internal context states, not user-facing product tabs.
- Collapsed Studio notch shows a mock compact stereo meter only when Audio = Playing. Silent state hides meter/text. Freeform collapsed state stays quiet with no "Ask Conductor" text.
- Voice states are Listening, Thinking, Applying, Done, and Can't verify. Voice state content avoids the hardware notch dead zone and expands horizontally from the notch surface.
- Studio panel tabs: Session, Tasks, Meters, Assistants. Freeform panel tabs: Ask, Learn, Notes, Assistants. Studio/Freeform are not shown as user-facing tabs.
- Session tab was cleaned into a premium studio overview with Selected, Session, Level, Actions, and a small Ask Conductor input.
- Tasks tab was cleaned into Now / Recent / Can't verify rows with Cancel, Undo, Auto Execute controls.
- Meters tab now has compact mock Master Out values and a mock optional top Meter Strip preview. No real meter engine was added.
- Studio Assistants tab now shows four static studio cards: Mix Assistant, Mastering Assistant, Arrangement Assistant, Plugin Expert.
- Settings remain behind the gear panel. Debug/developer/test controls were moved into Advanced/Harness.
- Attached Session chat now opens from the small Ask Conductor input, uses the existing attached chat wiring, preserves conversation during hide/show, and can collapse when clicking outside.
- Developer-only Mock Chat Responses controls were added under Advanced/Harness: Off/On and Small/Medium/Long. When On, attached chat can preview response sizes without calling backend or saving history.
- Floating chat remains detachable, resizable from the corner, hideable, and re-attachable. Visual polish was applied, but behavior was preserved.
- Floating chat Auto Exec label toggles between Auto Exec and Auto On. Auto Exec and Analyze show short timed window glows only; the glow is not permanent.

**Explicitly not changed:**
- No backend behavior changed.
- No real meter engine added.
- No screen agents / Surface OS / new production features added.
- Existing detached/freeflow chat code preserved.
- Existing Studio/Freeform tab logic preserved.

**Verification performed:** static/code-level checks only (`node --check app/harness.js` and inline script syntax checks on `app/harness.html`). No browser/Playwright/manual visual tests were run by Codex for these UI passes.
