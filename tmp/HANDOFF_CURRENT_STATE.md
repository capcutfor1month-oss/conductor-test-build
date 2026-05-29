# Conductor — Handoff / Current State
> Resume from here after any session reset, context compaction, or agent handoff.
> Last updated: May 2026 — Builds 18 (9b63bac) + 19 (2e27de2) + 20 PASS/LOCKED.

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
| D Slice 16 — Card-aware Creative Critic v1 (Build 8) | D154–D161 | `phase_d_slice16_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 17 — Plugin Knowledge Routing v1 (Builds 9 + 10) | D162–D168 | `phase_d_slice17_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 18 — Plugin Knowledge Trust Signals (Build 11) | D169–D176 | `phase_d_slice18_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 19 — Knowledge Status Context to Critic (Build 12) | D177–D186 | `phase_d_slice19_eval.py` | ✅ LOCKED — 10/10 PASS |
| D Slice 20 — Critic Composer Polish (Build 13) | D187–D196 | `phase_d_slice20_eval.py` | ✅ LOCKED — 10/10 PASS |
| D Slice 21 — CLARIFY Mode Hardening (Build 14) | D197–D204 | `phase_d_slice21_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 22 — Knowledge Feedback Log v1 (Build 15) | D205–D212 | `phase_d_slice22_eval.py` | ✅ LOCKED — 8/8 PASS |
| D Slice 23 — Ambient Feedback UI / Feedback Wiring v1 (Build 16) | D213–D220 | `phase_d_slice23_eval.py` | ✅ LOCKED — 39/39 PASS |
| D Slice 24 — Feedback Signal Reader v1 (Build 17) | D221–D228 | `phase_d_slice24_eval.py` | ✅ LOCKED — 34/34 PASS |
| D Slice 25 — Memory Promotion v1 / Candidate Generator (Build 18) | D229–D248 | `phase_d_slice25_eval.py` | ✅ LOCKED — 59/59 PASS — commit 9b63bac |
| D Slice 26 — Session Reflection / Feedback Summary v1 (Build 19) | D249–D265 | `phase_d_slice26_eval.py` | ✅ LOCKED — 41/41 PASS |
| D Slice 27 — Controlled Memory Writer v1 (Build 20) | D266–D281 | `phase_d_slice27_eval.py` | ✅ PASS/LOCKED — 97/97 PASS |

**Phase C — RAG / retrieval:** ✅ LOCKED (28 sections, 410 checks — run as regression in every subsequent slice)
**test_vault_integrity.py:** ✅ PASS — 15 pass / 0 fail / 4 warnings (cosmetic — no frontmatter in operator cards)

---

## LAST CONFIRMED TEST RUN (this session)

```
[Build 20 — Controlled Memory Writer v1]
phase_d_slice27_eval.py — 97/97 PASS  (D266–D281, Controlled Memory Writer v1 — Build 20)
phase_d_slice26_eval.py — 41/41 PASS  (D249–D265, Session Reflection v1 — Build 19, regression)
phase_d_slice25_eval.py — 59/59 PASS  (D229–D248, Memory Promotion v1 — Build 18, regression)
test_vault_integrity.py — 15/15 PASS  (regression)
python3 -m py_compile rag/memory_writer.py  PASS

[Build 19 — Session Reflection v1]
phase_d_slice26_eval.py — 41/41 PASS  (D249–D265, Session Reflection v1 — Build 19)
phase_d_slice25_eval.py — 59/59 PASS  (D229–D248, Memory Promotion v1 — Build 18, regression)
test_vault_integrity.py — 15/15 PASS  (regression)
python3 -m py_compile rag/session_reflection.py  PASS

[post hygiene pass — Build 18]
phase_d_slice25_eval.py — 59/59 PASS  (D229–D248, Memory Promotion v1 — Build 18)
phase_d_slice24_eval.py — 34/34 PASS  (D221–D228, Feedback Signal Reader v1 — Build 17)
python3 -m py_compile rag/memory_promotion.py    PASS
test_vault_integrity.py — 15/15 PASS

phase_d_slice23_eval.py — 39/39 PASS  (D213–D220, Ambient Feedback UI — Build 16)
phase_d_slice22_eval.py — 8/8   PASS  (D205–D212, Knowledge Feedback Log v1 — Build 15)
phase_d_slice21_eval.py — 8/8   PASS  (D197–D204, CLARIFY Mode Hardening — Build 14)
phase_d_slice20_eval.py — 10/10 PASS  (D187–D196, Critic Composer Polish — Build 13)
phase_d_slice19_eval.py — 10/10 PASS  (D177–D186, Knowledge Status Context to Critic — Build 12)
phase_d_slice18_eval.py — 8/8   PASS  (D169–D176, Plugin Knowledge Trust Signals — Build 11)
phase_d_slice17_eval.py — 8/8   PASS  (D162–D168, Plugin Knowledge Routing v1)
phase_d_slice16_eval.py — 8/8   PASS  (D154–D161, Card-aware Creative Critic v1)
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

## BUILD 20 — PASS/LOCKED

```
Build:               Build 20 — Controlled Memory Writer v1

Last completed step: rag/memory_writer.py created — bridge-only controlled write.
                     write_promoted_memories(reflection_path, bridge_url, dry_run,
                                             write_log, reflection) → dict.
                     Reads accepted_signals from Build 19 reflection.
                     Skips: do_not_promote, global_taste, suggested_level >= 3,
                            session_project with no project_id.
                     Routes session_project → "project" collection,
                            session_only → "producer" collection.
                     All writes via bridge POST /memory (mode=INTERN_WRITE_SAFE).
                     No direct ChromaDB. No Level 3/4 writes. No never-do writes.
                     dry_run=True (default) makes zero bridge calls.
                     Bridge failure on one candidate is non-fatal; others continue.
                     write_log=True + dry_run=False → idempotency via write_log.jsonl.
                     tests/phase_d_slice27_eval.py created: D266–D281, 97/97 PASS.

Files changed:
  rag/memory_writer.py (new)
    - write_promoted_memories(reflection_path, bridge_url, dry_run=True,
                               write_log=False, reflection=None) → dict
    - _load_latest_reflection(path) — reads last record from reflection log
    - _load_written_ids(write_log_path) — idempotency ledger reader
    - _append_write_log(write_log_path, record) — non-fatal appender
    - _post_memory(bridge_url, payload) → (ok, mem_id_or_error) — urllib only
    - _build_text(evidence, action_type, target, message, feedback_type) → str
    - _LEVEL_CAP = 2, _SKIP_SCOPES = {"global_taste"}, _MODE = "INTERN_WRITE_SAFE"
    - _SCOPE_TO_COLLECTION = {session_project: project, session_only: producer}
    - _NEVER_DO_PATH + _CONFIRMED_PREFS_PATH + _CHROMA_DIR guards documented
    - CLI: python3 rag/memory_writer.py [--no-dry-run] [--write-log] [--json]

  tests/phase_d_slice27_eval.py (new)
    - D266–D281, 97/97 PASS

  .gitignore
    - memory/write_log.jsonl added

  tmp/BUILD_PHASES.md + tmp/HANDOFF_CURRENT_STATE.md
    - Build 20 state recorded

Tests run:           phase_d_slice27_eval.py  97/97 PASS
                     phase_d_slice26_eval.py  41/41 PASS  (regression)
                     phase_d_slice25_eval.py  59/59 PASS  (regression)
                     test_vault_integrity.py  15/15 PASS  (regression)
                     python3 -m py_compile rag/memory_writer.py  PASS

Current failure:     none — all passing
Codex result:        PASS/LOCKED

Do-not-touch list:   rag/memory_promotion.py (locked Build 18)
                     rag/session_reflection.py (locked Build 19)
                     tools/harness_server.py
                     tools/conductor_bridge.py
                     app/*
                     memory/chromadb/
                     memory/feedback_log.jsonl (read-only)
                     memory/knowledge_feedback_log.jsonl (read-only)
                     memory/promotion_candidates.jsonl (read-only)
                     memory/session_reflection_log.jsonl (read-only)
                     conductor-vault/producer/never_do_rules.md
                     conductor-vault/producer/confirmed_preferences.md
                     phase_d_slice1–26_eval.py (all locked)
```

---

## PREVIOUS HANDOFF — BUILD 19 (PASS/LOCKED — commit 2e27de2)

```
Build:               Build 19 — Session Reflection / Feedback Summary v1

Last completed step: rag/session_reflection.py created — read-only reflection generator.
                     run_reflection(candidates_path, feedback_log_path, knowledge_log_path,
                                    reflection_log_path, dry_run, write_log) → dict.
                     Reads promotion_candidates.jsonl (accepted signals) and
                     feedback_log.jsonl + knowledge_feedback_log.jsonl (negative signals).
                     Detects repeated action_type patterns from metadata (no hardcoded words).
                     Project notes only when project_id present. Scope field preserved from
                     candidate record. Negative types (UNDO/WRONG_DIRECTION/NOT_HELPFUL/
                     WRONG/OUTDATED) → rejected_signals + do_not_promote.
                     TOO_MUCH/KEEP/etc. → not in do_not_promote (calibration, not rejection).
                     write_log=True + dry_run=False → appends to session_reflection_log.jsonl.
                     dry_run always overrides write_log. No ChromaDB. No level elevation.
                     tests/phase_d_slice26_eval.py created: D249–D265, 41/41 PASS.

Files changed:
  rag/session_reflection.py (new)
    - run_reflection(candidates_path, feedback_log_path, knowledge_log_path,
                     reflection_log_path, dry_run=False, write_log=False) → dict
    - accepted_signals: all records from promotion_candidates.jsonl
    - rejected_signals / do_not_promote: UNDO/WRONG_DIRECTION from action log;
      NOT_HELPFUL/WRONG/OUTDATED from knowledge log
    - repeated_patterns: action_type appearing >= 2 times in accepted_signals
    - project_notes: one per distinct non-empty project_id across accepted + rejected
    - confidence_reasons: candidate_id, score, evidence, suggested_level per accepted
    - counts: total_candidates_read, accepted, rejected, repeated_patterns,
              project_notes, do_not_promote
    - _REPEATED_PATTERN_MIN = 2
    - _NEVER_DO_PATH + _CONFIRMED_PREFS_PATH guards documented (never written to)
    - CLI: python3 rag/session_reflection.py [--dry-run] [--write-log] [--json]

  tests/phase_d_slice26_eval.py (new)
    - D249–D265, 41/41 PASS

  .gitignore
    - memory/session_reflection_log.jsonl added

Tests run:           phase_d_slice26_eval.py  41/41 PASS
                     phase_d_slice25_eval.py  59/59 PASS  (regression)
                     test_vault_integrity.py  15/15 PASS  (regression)
                     python3 -m py_compile rag/session_reflection.py  PASS

Current failure:     none — all passing
Next intended edit:  none — awaiting Codex audit

Staged files:        .gitignore
                     rag/session_reflection.py
                     tests/phase_d_slice26_eval.py
                     tmp/HANDOFF_CURRENT_STATE.md
                     tmp/BUILD_PHASES.md

Do-not-touch list:   rag/memory_promotion.py (locked Build 18)
                     tools/harness_server.py
                     tools/conductor_bridge.py
                     app/*
                     memory/chromadb/
                     memory/feedback_log.jsonl (read-only)
                     memory/knowledge_feedback_log.jsonl (read-only)
                     memory/promotion_candidates.jsonl (read-only)
                     conductor-vault/producer/never_do_rules.md
                     conductor-vault/producer/confirmed_preferences.md
                     phase_d_slice1–25_eval.py (all locked)
```

---

## PREVIOUS HANDOFF — BUILD 18 (PASS/LOCKED — commit 9b63bac)

```
Build:               Build 18 — Memory Promotion v1 / Promotion Candidate Generator

Last completed step: rag/memory_promotion.py created — read-only candidate generator.
                     run_promotion(dry_run, ...) returns structured promotion candidates
                     from both feedback_log.jsonl (action) and knowledge_feedback_log.jsonl.
                     Idempotency via MD5 candidate_id + ledger (promotion_candidates.jsonl).
                     Level 4 / Never-Do hard cap: suggested_level never >= 3.
                     Scope: session_project when project_id set; session_only otherwise.
                     Global taste scope NOT generated in this build.
                     tests/phase_d_slice25_eval.py created: D229–D248, 59/59 PASS.
                     Future-builds note added to conductor_future_vision_roadmap.md.

Files changed:
  rag/memory_promotion.py (new)
    - run_promotion(feedback_log_path, proof_log_path, knowledge_log_path,
                    ledger_path, dry_run=False) → dict
    - Reads action feedback + knowledge feedback, read-only
    - KEEP / HELPFUL → candidates (score >= 0.50)
    - UNDO / WRONG_DIRECTION / NOT_HELPFUL / WRONG / OUTDATED → never promote
    - TOO_MUCH / NOT_ENOUGH / TOO_VAGUE → below threshold (0.25/0.20)
    - Message bonus +0.10
    - Idempotency: _make_candidate_id(source, fb_id, type) → MD5 hash
    - Ledger: memory/promotion_candidates.jsonl (append-only, new log)
    - Level cap: _LEVEL_MAX_THIS_BUILD = 2 (never 3 or 4)
    - _NEVER_DO_PATH guard documented (never written to)
    - CLI: python3 rag/memory_promotion.py [--dry-run] [--json]

  tests/phase_d_slice25_eval.py (new)
    - D229: importable, run_promotion callable
    - D230: missing logs → safe zero result
    - D231: empty logs → safe zero result
    - D232: KEEP/HELPFUL → candidates generated with correct source/score
    - D233: UNDO/WRONG_DIRECTION/NOT_HELPFUL/WRONG/OUTDATED → no candidates
    - D234: TOO_MUCH/NOT_ENOUGH/TOO_VAGUE below threshold → no candidates
    - D235: message bonus — exact scores 0.65/0.75/0.55/0.65
    - D236: scope session_project (project_id set) vs session_only (not set)
    - D237: knowledge feedback always session_only, project_id == ""
    - D238: single KEEP → no global_taste scope; suggested_level <= 2
    - D239: idempotency — second run with same log: 0 new, N duplicates_skipped
    - D240: dry_run=True → ledger not created
    - D241: no suggested_level >= 3 in any candidate
    - D242: live log mtimes unchanged (feedback, knowledge, proof)
    - D243: never_do_rules.md mtime unchanged
    - D244: static source analysis — no forbidden imports, CLI guard, default paths

  Future Builds/conductor_future_vision_roadmap.md
    - Build 18 feedback learning caveats added under Phase D section

Live CLI run (dry-run):
  1543 records processed (test data from prior suites + live feedback)
  459 candidates generated (all test-data KEEP/HELPFUL)
  1084 non-promoting skipped (UNDO/WRONG_DIRECTION/etc.)
  Ledger not written (dry-run)

Note:
  datetime.utcnow() deprecation warning on Python 3.12+ is cosmetic.
  Behavior unaffected. Future: replace with datetime.now(UTC) if desired.

Tests run:           phase_d_slice25_eval.py  59/59 PASS
                     phase_d_slice24_eval.py  34/34 PASS  (regression)
                     test_vault_integrity.py  15/15 PASS  (regression)
                     python3 -m py_compile rag/memory_promotion.py  PASS

Hygiene pass:        Codex failed initial lock due to out-of-scope staged files.
                     Unstaged: memory/knowledge_feedback_log.jsonl,
                               CHAT GPT SESSION HANDCOFFS/ (2 files),
                               tmp/old_project_reference/ (8 files).
                     Added to .gitignore:
                               memory/knowledge_feedback_log.jsonl
                               memory/promotion_candidates.jsonl
                               CHAT GPT SESSION HANDCOFFS/
                               tmp/old_project_reference/
                     Re-confirmed all 4 suites after hygiene. All PASS.

Current failure:     none — all passing

Next intended edit:  none — awaiting Codex re-audit after hygiene pass

Staged files:        .gitignore  (hygiene addition)
                     rag/memory_promotion.py
                     tests/phase_d_slice25_eval.py
                     Future Builds/conductor_future_vision_roadmap.md
                     tmp/HANDOFF_CURRENT_STATE.md

Do-not-touch list:   tools/harness_server.py
                     tools/conductor_bridge.py
                     rag/feedback.py
                     rag/routed_retriever.py
                     rag/context_pack_builder.py
                     rag/* (all other existing files)
                     memory/feedback_log.jsonl (read-only)
                     memory/action_log.jsonl (read-only)
                     memory/action_proof_log.jsonl (read-only)
                     memory/knowledge_feedback_log.jsonl (read-only, gitignored)
                     conductor-vault/producer/never_do_rules.md
                     app/* (UI not in scope)
                     phase_d_slice1–25_eval.py (locked once Codex passes)
```

---

## PREVIOUS HANDOFF — BUILD 17 LOCKED

```
Build:               Build 17 — Feedback Signal Reader v1
Commit:              1697c80

Last completed step: tools/read_feedback.py created — standalone CLI + importable
                     summarize_feedback(path=None) -> dict.
                     Reads memory/knowledge_feedback_log.jsonl read-only.
                     All 6 type keys always present; unknown types → OTHER;
                     sample_messages capped at 5; period_start/end from timestamps.
                     phase_d_slice24_eval.py created: D221–D228, 34/34 PASS.
                     D228 promotion-regex false-positive fixed during build
                     (bare \bpromotion\b → specific function/module names only).

Files changed (committed):
  tools/read_feedback.py (new)
    - summarize_feedback(path=None) → dict
    - _build_result() helper
    - _print_summary() CLI formatter
    - if __name__ == '__main__' guard; default path = knowledge_feedback_log.jsonl
    - Read-only: no open(w/a), no chromadb, no rag imports, no promotion calls

  tests/phase_d_slice24_eval.py (new)
    - D221: importable, summarize_feedback callable
    - D222: missing/empty file → total=0, all keys zeroed, period_start None
    - D223: malformed lines skipped; valid lines counted
    - D224: all type buckets correct; unknown → OTHER
    - D225: all 6 type keys always present (empty + missing file)
    - D226: period_start/end correctness; messages_with_content; sample cap ≤5
    - D227: live log mtime unchanged after call (read-only proof)
    - D228: no forbidden imports/writes in source; no build refs in harness_server;
            __main__ guard present; default path references correct filename

Live log at commit:  64 records — HELPFUL:16 NOT_HELPFUL:16 TOO_VAGUE:8
                     WRONG:8 OUTDATED:16 OTHER:0 messages_with_content:24

Tests run:           phase_d_slice24_eval.py  34/34 PASS
                     phase_d_slice23_eval.py  39/39 PASS
                     node --check app/harness.js    PASS
                     python3 -m py_compile tools/harness_server.py  PASS

Current failure:     none — all passing

Next intended edit:  none — Build 17.5 deferred (see below)

Do-not-touch list:   tools/harness_server.py (untouched)
                     tools/conductor_bridge.py (untouched)
                     rag/* (all files untouched)
                     memory/* (untouched)
                     phase_d_slice1–24_eval.py (all locked)
                     action endpoints (/action/*)
                     /session/state implementation
                     Auto Execute path
                     PluginBridge
                     Operator Cards
```

---

## BUILD 17.5 — SCOPE-CHECKED, DEFERRED

> Scope check completed May 2026 (two iterations — sandbox boundary correction applied).
> Decision: defer. Do NOT build without explicit user instruction.

### What was scoped

Two isolated client-side wiring additions to `app/harness.js`:

**Addition A — `#studioLastResponse` preview**
- The div exists in `app/harness.html` below the Ask Conductor input.
- It is never written to in the current `harness.js`.
- Proposed: when `type:"answer"` arrives in `handleSandboxChat()`, write ≤120 char
  preview of `data.text` to `#studioLastResponse`; clear on new message submission;
  leave blank on clarify/action/error paths.

**Addition B — Studio action stub buttons**
- Three buttons exist in HTML: "Analyze selected" / "Check gain" / "Explain chain".
- They have `data-tooltip` attributes but zero click handlers.
- Proposed: each calls `handleSandboxChat()` with a pre-defined knowledge query text;
  sandbox gate (`currentMode !== "sandbox"`) remains intact.

### Why deferred

- Both are small UI polish — not worth a standalone backend-style audit cycle right now.
- The locked Knowledge Brain v1 is already testable through AI Sandbox mode as-is.
- Better bundled later with CoProducer Translation Layer (Build 19) or production UI
  cleanup when developer controls are removed from harness.html/js.

### Constraints preserved

- `currentMode = "live"` default: KEEP as-is. Do not change.
- Sandbox gate in `handleSandboxChat()`: KEEP. It is an intentional dev boundary.
- No backend, rag, bridge, memory, PluginBridge, Auto Execute, Web, new cards, or
  `app/index.html` changes.

### Test plan (when eventually built)

- Static source analysis only (same pattern as slices 22–24)
- D229: `#studioLastResponse` written on type:"answer"
- D230: `#studioLastResponse` cleared on new submission
- D231: `#studioLastResponse` untouched on clarify/action/error
- D232–D234: each Studio stub button wired and calls handleSandboxChat with correct text
- D235: sandbox gate still blocks stubs when currentMode !== "sandbox"
- D236: no backend files touched

### Scope label for future build prompt

> "Claude, Build 17.5 only: UI Integration Pass.
>  Wire #studioLastResponse and three Studio action stubs in harness.js.
>  Do not change currentMode default or sandbox gate.
>  Do not touch backend, rag, bridge, memory, PluginBridge, or app/index.html."

---

## PREVIOUS HANDOFF — BUILD 16 COMPLETE

```
Build:               Build 16 — Ambient Feedback UI / Feedback Wiring v1

Last completed step: Added type:"clarify" guard in handleSandboxChat().
                     addChatMessage() now returns wrap.
                     Added _sendKnowledgeFeedback() and addFeedbackChips() to harness.js.
                     Answer branch calls addFeedbackChips(wrap, data.response_id) when eligible.
                     CSS for .fb-chips / .fb-chip / .fb-sub added to harness.html.
                     phase_d_slice23_eval.py created: D213–D220, 39/39 PASS.

Files changed:
  app/harness.js
    - type:"clarify" guard added before answer branch (explicit, no chips)
    - addChatMessage() returns wrap element
    - _sendKnowledgeFeedback(responseId, feedbackType) — fire-and-forget POST
    - addFeedbackChips(wrap, responseId) — Helpful + Not this + sub-row chips
    - Answer branch wires chips via if (wrap && data.response_id)

  app/harness.html
    - CSS: .fb-chips, .fb-chip, .fb-chip:hover, .fb-chip[data-sent], .fb-sub
    - Matches .btn-copy / .msg-actions muted design language

  tests/phase_d_slice23_eval.py (new file)
    - D213–D220 (39 checks)

  docs/HARNESS_GUIDE.md — Build 16 section added

Tests run:           phase_d_slice23_eval.py  39/39 PASS
                     phase_d_slice22_eval.py  8/8   PASS
                     phase_d_slice21_eval.py  8/8   PASS
                     node --check app/harness.js    PASS

Current failure:     none — all passing
```

---

## PREVIOUS HANDOFF — BUILD 14 COMPLETE

```
Build:               Build 14 — CLARIFY Mode Hardening

Last completed step: _compose_clarify_question() + _clarify_safe() added to
                     harness_server.py. CLARIFY fast-path inserted in
                     _handle_orchestrate() before context assembly.
                     risk_reason and risk_category now extracted from pack_data.
                     phase_d_slice21_eval.py created: D197–D204, 8/8 PASS.

Files changed:
  tools/harness_server.py
    - _CLARIFY_LABEL_RE (module-level, re.IGNORECASE) — guards internal
      category/label names from leaking into composed clarify questions.
    - _CLARIFY_VERB_RE (module-level) — extracts action verbs from ambiguous
      pronoun messages for grounded question generation.
    - _clarify_safe(question) — final safety guard; rejects non-questions
      and outputs containing internal labels.
    - _compose_clarify_question(original_text, risk_reason, risk_category) —
      deterministic composer, no LLM call. Templates: unclear* → verb-grounded
      question; too_short → natural re-ask; *scope* → track/bus/plugin question;
      generic fallback from risk_reason; BLOCK/unknown → ''.
    - _handle_orchestrate() — extracts risk_reason + risk_category from
      pack_data. CLARIFY fast-path returns type:"clarify" with zero LLM tokens
      when composer succeeds; falls through to call_knowledge_answer() (type:
      "answer") when composer returns ''.

  tests/phase_d_slice21_eval.py (new file)
    - D197: composer unit tests — all template branches (7 sub-cases)
    - D198: label guard — no internal labels in any template output
    - D199: integration — pronoun "Lower it" → type:"clarify", verb reflected
    - D200: integration — too_short "ok" → type:"clarify", no LLM call
    - D201: integration — BLOCK/unsupported → composer returns '', fallback fires
    - D202: regression — MENTOR mode unaffected
    - D203: risk_reason/risk_category extraction correctness
    - D204: symbol importability + output shape contracts

Tests run:           phase_d_slice21_eval.py  8/8  PASS
                     phase_d_slice20_eval.py 10/10 PASS
                     phase_d_slice19_eval.py 10/10 PASS
                     phase_d_slice18_eval.py  8/8  PASS
                     phase_d_slice17_eval.py  8/8  PASS
                     phase_d_slice16_eval.py  8/8  PASS
                     phase_d_slice15_eval.py 11/11 PASS
                     node --check app/harness.js    PASS
                     python3 -m py_compile tools/harness_server.py  PASS

Current failure:     none — all passing

Next intended edit:  paused — awaiting user direction for next slice

Do-not-touch list:   conductor_bridge.py
                     rag/* (all files)
                     phase_d_slice1–21_eval.py (all locked)
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

### Premium Notch UI v1 — Harness-Only State

> Added May 29, 2026 after Codex Premium Notch UI cleanup. This is UI surface/state work only; do not mark it as a backend PASS/LOCKED slice.

Active UI file remains `app/harness.html`; chat/sandbox wiring remains `app/harness.js`. `app/index.html` is still reference/prototype only.

Current harness UI state:
- Notch preview now separates grey menu-bar/screen area from black hardware notch and black/glass software notch surface.
- Harness context control: Ableton Open = Studio surface; Ableton Closed = Freeform surface. Do not expose Studio/Freeform as product tabs.
- Studio tabs: Session, Tasks, Meters, Assistants. Freeform tabs: Ask, Learn, Notes, Assistants.
- Collapsed Studio notch shows mock stereo meter only when Audio = Playing. Silent and Freeform collapsed states stay quiet/no text.
- Voice states: Listening, Thinking, Applying, Done, Can't verify. These avoid the hardware notch dead zone and expand horizontally.
- Studio Session is premium overview plus small Ask Conductor input. Attached chat opens from that input and can take over the panel.
- Attached chat preserves history through hide/show, collapses on outside click, keeps message scrolling, and has developer-only mock response preview controls.
- Floating chat is detachable, directly resizable by corner, hideable, and re-attachable. Auto Exec label toggles Auto Exec / Auto On. Analyze and Auto Exec only show short timed glows.
- Studio Tasks/Meters/Assistants have cleaned premium mock layouts. Meter Strip is mock Compact/Hidden only.
- Debug/dev/test controls live under Advanced/Harness. Keep raw parser output, token/cost, proof IDs, mock controls, and technical toggles out of the main premium surface.

Do not regress:
- No backend behavior changes for this UI work.
- No real meter engine.
- No production assistant routing.
- No screen agents / Surface OS.
- Preserve detached/freeflow chat code unless explicitly scoped.
- Preserve Studio/Freeform contextual tab logic.

Verification performed for this UI work: static checks only (`node --check app/harness.js` and inline script syntax check on `app/harness.html`). No browser/Playwright/manual visual tests were run by Codex.

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
