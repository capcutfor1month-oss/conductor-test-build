# Conductor — Handoff: Current State
> Created: May 2026. Do not rewrite history — append updates below.

---

## CURRENT PROJECT STATE

Phase D Slices 1–5 are complete and audited (PASS/LOCKED).
Expanded Actions Slice 1 is PASS/LOCKED (track_create, track_delete, track_duplicate, track_arm, track_monitor, track_rename, track_color, return_track_create, tracks_create_multiple).
Expanded Actions Slice 2 is PASS/LOCKED (track_send, track_route, transport_play, transport_stop, transport_record, transport_loop, transport_metronome).
All test suites pass. Phase C is stable.

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

- **UI Trust Behavior & Prototype Status:** `app/index.html` (phase 2 HTML) is prototype UI only. Prototype "Execute" buttons do not represent production trust behavior.
- **Strict Verification Path:** Before friend-test UI is deployed, every Execute path must call verified `/action/*` endpoints. UI must never show "Executed" unless the backend returns a verified action response.
- **Co-Producer Translation Layer:** A `CoProducerResponse` / translation layer is strictly required before deploying production UI.
- **Product Direction:** Conductor must feel like a premium studio assistant, not a bank approval app or dev endpoint.

---

## CURRENT LIMITATIONS

| Limitation | Deferred to |
|---|---|
| `frequency` score in C2 temporal scoring stubbed at `0.5` | Phase D Slice 5+ (needs `POST /feedback` access count tracking wired) |
| Memory promotion not built — Level 1 raw events never reach Level 2/3 | Phase D Slice 5+ (`rag/memory_promotion.py` not created yet) |
| Never-do preflight gate not wired to `POST /action/*` endpoints | Phase D Slice 5 (D5) — `never_do_rules.md` exists, enforcement absent |
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
- **New action types beyond volume/pan/mute/solo** — wait for Phase D Slice 5
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
