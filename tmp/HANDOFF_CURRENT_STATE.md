# Conductor — Handoff / Current State
> Resume from here after any session reset, context compaction, or agent handoff.
> Last updated: May 2026 — Build 7 (Creative Critic v1) complete. Pausing here.

---

## LOCKED / COMPLETE (do not re-audit or re-build)

| Slice | Sections | Test file | Result |
|---|---|---|---|
| D Slice 1 — ActionProof + Volume Readback | D01–D10 | `phase_d_slice1_eval.py` | ✅ LOCKED |
| D Slice 2 — Pan / Mute / Solo Readback | D11–D20 | `phase_d_slice2_eval.py` | ✅ LOCKED |
| D Slice 3 — `POST /feedback` | D21–D30 | `phase_d_slice3_eval.py` | ✅ LOCKED |
| D Slice 4 — Compensating Undo + Drift Detection | D31–D38 | `phase_d_slice4_eval.py` | ✅ LOCKED |
| D Slice 5 — Never-Do Preflight Gate | D41–D51 | `phase_d_slice5_eval.py` | ✅ LOCKED |
| Expanded Slice 1 — Track Management (Create/Delete/Duplicate/Color/Rename/Group) | D52–D73 | `phase_d_slice6_eval.py` | ✅ LOCKED |
| Expanded Slice 2 — Routing/Sends/Arm/Monitor/Transport | D74–D93 | `phase_d_slice7_eval.py` | ✅ LOCKED |
| Expanded Slice 3A — `POST /action/plugin_bypass` | D94–D102 | `phase_d_slice8_eval.py` | ✅ LOCKED — 9/9 PASS |
| D Slice 9 — Strict Confirm Parser | D103–D108 | `phase_d_slice9_eval.py` | ✅ LOCKED — 6/6 PASS |
| D Slice 10 — `GET /session/state` | D109–D114 | `phase_d_slice10_eval.py` | ✅ LOCKED — 6/6 PASS |
| D Slice 11 — Natural Replies + Premium UI | D115–D170 | `phase_d_slice11_eval.py` | ✅ LOCKED — 56/56 PASS |
| D Slice 12 — Knowledge Gateway v1 | D121–D127 | `phase_d_slice12_eval.py` | ✅ LOCKED — 7/7 PASS |
| D Slice 13 — `/session/state` v1.5 | D128–D134 | `phase_d_slice13_eval.py` | ✅ LOCKED — 7/7 PASS |
| D Slice 14 — Knowledge Explorer v1 (Build 6 hardening) | D135–D142 | `phase_d_slice14_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 15 — Creative Critic v1 (Build 7) | D143–D153 | `phase_d_slice15_eval.py` | ✅ LOCKED — 11/11 PASS |

**Phase C — RAG / retrieval:** ✅ LOCKED (28 sections, 410 checks — run as regression in every subsequent slice)
**test_vault_integrity.py:** ✅ PASS — 15 pass / 0 fail / 4 warnings (cosmetic — no frontmatter in operator cards)

---

## LAST CONFIRMED TEST RUN (this session)

```
phase_d_slice15_eval.py — 11/11 PASS  (D143–D153, Creative Critic v1 + filtering proof)
phase_d_slice14_eval.py — 8/8   PASS  (D135–D142, Knowledge Explorer v1)
phase_d_slice13_eval.py — 7/7   PASS
phase_d_slice12_eval.py — 7/7   PASS
phase_d_slice11_eval.py — 56/56 PASS
phase_d_slice10_eval.py — 6/6   PASS
phase_d_slice9_eval.py  — 6/6   PASS
test_vault_integrity.py — 15/15 PASS
node --check app/harness.js     PASS
python3 -m py_compile tools/harness_server.py  PASS
```

---

## CURRENT HANDOFF — BUILD 7 COMPLETE

```
Build:               Build 7 — Creative Critic v1

Last completed step: _compose_final_answer() added to harness_server.py.
                     _handle_orchestrate Explorer branch now calls
                     _compose_final_answer(answer_text, explorer_data, critic_data)
                     and sends final_text instead of raw answer_text.
                     phase_d_slice15_eval.py updated: D143–D148 revised,
                     D149 Sub-case C added (invalid index), D152 (filtering proof)
                     and D153 (real parser fallback) added. 11/11 passing.

Files changed:
  tools/harness_server.py
    - Added _compose_final_answer() — deterministic composer, no LLM call.
      Reads critic_data["selected"], validates index, builds
      "{direction}. {rationale}." from selected candidate.
      Falls back to explorer_answer if critic_data empty, index invalid,
      direction missing, or _STRUCTURAL_RE fires on composed text.
    - Added call_creative_critic() — single LLM call, evaluates candidates
      on 6 criteria (genericity / session_grounding / session_contradiction /
      goal_fit / practicality / unsupported_assumptions).
      Returns ({}, tokens) on parse failure or invalid index. Never raises to caller.
    - Added _build_critic_prompt() and _CRITIC_JSON_SCHEMA.
    - _handle_orchestrate Explorer branch: calls call_creative_critic after
      call_knowledge_explorer, then calls _compose_final_answer, sends
      "text": final_text (not answer_text).

  tests/phase_d_slice15_eval.py
    - D143/D144: assert text ≠ explorer_answer; assert selected direction in text.
    - D145–D147: added text content assertions per section.
    - D148: removed old text==explorer_answer assert; added composed-text checks.
    - D149: added Sub-case C — invalid selected index mock → fallback.
    - D151: added _compose_final_answer + final_text to static symbol checks.
    - D152 (new): core filtering proof — 5 assertions proving rejected candidate
      cannot control the final answer.
    - D153 (new): real call_creative_critic() parser — 7 sub-cases (malformed,
      missing key, out-of-range, valid, _compose_final_answer edge cases).

Tests run:           phase_d_slice15_eval.py 11/11 PASS
                     phase_d_slice14_eval.py  8/8  PASS
                     phase_d_slice13_eval.py  7/7  PASS
                     phase_d_slice12_eval.py  7/7  PASS
                     phase_d_slice11_eval.py 56/56 PASS
                     phase_d_slice10_eval.py  6/6  PASS
                     phase_d_slice9_eval.py   6/6  PASS
                     test_vault_integrity.py 15/15 PASS
                     node --check app/harness.js    PASS
                     python3 -m py_compile harness_server.py  PASS

Current failure:     none — all passing

Next intended edit:  Mark Build 7 PASS/LOCKED in tmp/BUILD_PHASES.md and project.md
                     (doc update only — no code changes needed)

Known limitation:    _compose_final_answer() produces a safe but simple answer:
                     "{direction}. {rationale}." — no LLM rewrite, no polish.
                     Build 7 contract is satisfied. Marked for future polish:
                     premium co-producer phrasing, smoother sentence flow,
                     optional session-fact weaving. Do NOT reopen Build 7 for this.
                     Track as: "Critic composer polish — post Build 7".

Do-not-touch list:   conductor_bridge.py
                     rag/* (all files)
                     phase_d_slice1–14_eval.py (all locked)
                     conductor-vault/producer/never_do_rules.md
                     rag/action_proof.py, rag/undo_engine.py, rag/readback.py
                     action endpoints (/action/*)
                     /session/state implementation
                     Premium UI / CoProducer translation layer
                     Auto Execute path
                     PluginBridge
                     Operator Cards v2
                     model/provider integration
                     /harness/parse_intent behavior
```

---

## PAUSED HERE — DO NOT BUILD NEXT WITHOUT USER INSTRUCTION

### ROADMAP — Expanded Actions (not built, not started)

| Slice | What | Notes |
|---|---|---|
| **Expanded Slice 3B** | `POST /action/plugin_param` | Parameter changes via PluginBridge. Requires PluginBridge MCP to be stable. |
| **Expanded Slice 3C** | PluginBridge placement on track | Load PluginBridge VST3 on a track, select plugin from within Conductor. |
| **Expanded Slice 3D** | `POST /action/plugin_load` | Load a plugin onto a track via LOM (stock only) or PluginBridge. |
| **Expanded Slice 4** | Export / Bounce | Pending explicit user decision — CONFIRM_REQUIRED action. |
| **Expanded Slice 5** | Clip / scene / session-view actions | Pending user approval of scope. |

### ROADMAP — Critic Composer Polish (future, low priority)

| Item | What | Notes |
|---|---|---|
| **Critic composer polish** | Improve `_compose_final_answer()` phrasing | Currently outputs `"{direction}. {rationale}."` — safe and correct but plain. Future: smoother sentence flow, session-fact weaving, optional co-producer voice. No extra LLM call needed — still deterministic. Do not reopen Build 7. New slice only. |

---

### ROADMAP — Phase D Product Layer (not built)

| Item | What | Priority |
|---|---|---|
| **D6** | Feedback UI buttons | Keep / Undo / Too much / Not enough / Wrong direction in `app/index.html` wired to `POST /feedback`. Endpoint already built. |
| **D7** | Session-end hook | Triggers `memory_promotion.py` on session close; summarises session, extracts decisions. |
| **D3** | Memory promotion / "dreaming" | `rag/memory_promotion.py` — promotes Level 1 → 2 → 3 → 4 silently at session end. |
| **UI** | CoProducer Translation layer | **Required before friend-test.** Wraps all ActionProofs, drift errors, and bridge errors in human-readable assistant dialogue. No raw JSON / no error enums reach the user. |
| **UI** | Drift diff dialog | Premium modal: "You changed X to Y. Restore to Z or keep?" |
| **UI** | Studio timeline / debugger | Visual view of `action_log.jsonl`. |

---

## UI / PRODUCTION RULES (locked product direction)

- `app/index.html` is **prototype-only**. Not production UI.
- Every production Execute path must call verified `/action/*` endpoints.
- UI must never show "Executed" unless backend returns a verified `ActionProof` response.
- **`CoProducerResponse` translation layer is required before any friend-test UI deployment.**
- Conductor must feel like a premium studio assistant — not a bank approval app. No raw JSON, no error code enums, no terminal-style output in the UI.
- HARD_BLOCK is for truly destructive actions only. All other risky actions → `REQUIRE_CONFIRMATION` (ask, don't block).

---

## SAFETY INVARIANTS — NON-NEGOTIABLE

- Gate 1 (undo: after_state must exist) — never bypassable, including `confirm=True`
- Gate 2 (undo: current state readable) — never bypassable
- Gate 3 (undo: drift check) — bypassable with `confirm=True` only
- `action_log.jsonl` + `action_proof_log.jsonl` — append-only, never modified
- `ok=True` only when `vstat` is `VERIFIED` or `ALREADY_CORRECT`
- Never-do check before every write, before any LOM call
- Availability precheck (track_route) and range validation (track_send) before any LOM call
- `bypass` field on `/action/plugin_bypass` — strict bool parsing only (no truthy-string bugs)

---

## BACKUP CODING / LIMIT EXHAUSTED — HANDOFF TEMPLATE

Fill this in and paste into the backup session (ChatGPT, Codex, etc.) along with the required context.

**Required context to attach:**
- This file + `HANDOFF_CURRENT_STATE.md` (root)
- `tmp/BUILD_PHASES.md` — locked slice table
- `git status --short` output
- `git diff` output
- Full test output for the current slice
- Relevant function(s) being edited if diff is ambiguous

**Fill in before handing off:**

```
Build:               [e.g. Build 7 — Creative Critic v1]
Last completed step: [e.g. "Added call_creative_critic(); edited _handle_orchestrate"]
Files changed:       [each file + one-line summary]
Tests run:           [suite + count + PASS/FAIL]
Current failure:     [exact output, or "none"]
Next intended edit:  [exact function / file / line]
Do-not-touch list:   [files out of scope for this build]
```

**Backup assistant must not:**
- Invent repo structure — work from actual files and diffs only
- Touch any PASS/LOCKED slice
- Change scope or mix in unrelated work (RAG, Premium UI, Auto Execute, Web/current info, PluginBridge, Operator Cards) unless explicitly in the current build spec
- Skip Codex audit if production code was changed

Full protocol: `CLAUDE.md` → **Backup Coding / Limit Exhausted Protocol**
Recovery rule: if backup edits production code, Codex must audit before the slice is marked PASS/LOCKED.

---

## KEY FILES

| File | Role |
|---|---|
| `rag/readback.py` | All readback loops (volume/pan/mute/solo/arm/monitor/send/route/transport/plugin_bypass) |
| `rag/undo_engine.py` | Three-gate undo, drift detection, PLUGIN_BYPASS undo, `_parse_plugin_target` |
| `rag/never_do_check.py` | Static never-do table — ALLOW / REQUIRE_CONFIRMATION / HARD_BLOCK / UNDO_LOG_REQUIRED |
| `rag/action_proof.py` | ActionProof dataclass, create_proof(), VerificationStatus |
| `rag/black_box_log.py` | Append-only log writers |
| `tools/conductor_bridge.py` | All HTTP endpoints — single gateway |
| `tests/phase_d_slice8_eval.py` | Slice 3A eval — D94–D102 |
| `tools/run_tests.sh` | Full suite runner (10 suites including slice 8) |
