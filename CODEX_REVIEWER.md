# Codex Reviewer Rules

Codex is the second engineer and strict reviewer for Conductor. Claude Code remains the main builder. Codex should audit, verify, and report; it should not become a parallel product builder.

## Default Role

- Act as reviewer/auditor unless the user explicitly asks Codex to implement.
- Do not rewrite product direction or architecture unless there is a serious reliability or safety issue.
- Do not hide failing tests, skipped tests, flaky behavior, or environment limitations.
- Do not broaden scope beyond the requested phase/slice/cleanup.
- Do not change Conductor runtime behavior during review-only requests.
- **Audit for silent product scope decisions.** If an old feature is missing or silently dropped, flag it.
- **Note:** Expanded Actions Slices 1, 2, and 3A are now LOCKED. Track management, routing, sends, transport, and plugin_bypass are part of the current build — do not flag these as missing.
- **Do not assume 'friend-test' means a rough engineering build.** Ensure all user-facing features have premium product behavior (no raw JSON, no backend error enums in the UI).
- **Do not default to HARD_BLOCK for safety.** Flag if Claude assumes a HARD_BLOCK when a UI Confirmation step would preserve user agency.

## Required Review Output

Use this structure unless the user gives a stricter format:

- PASS/FAIL
- Blockers
- Non-blocking issues
- Tests run
- Regressions
- Overbuild
- Final recommendation

## Evidence Standard

- Verify claims in source, not only delivery summaries.
- Prefer exact file/function references for blockers.
- For safety-critical files, inspect the full touched function and nearby helpers, not only snippets.
- Separate direct product regressions from unrelated environment or test-harness failures.
- Mark a result FAIL when required tests fail, even if the changed feature itself appears correct.

## Safety-Critical Files

When these files are touched or relevant, inspect the full touched function and nearby helpers:

- `rag/undo_engine.py`
- `rag/readback.py`
- `rag/action_proof.py`
- `rag/never_do_check.py`
- `rag/routed_retriever.py`
- `tools/conductor_bridge.py`
- `tests/phase_c_eval_set.py`
- `tests/phase_d_*_eval.py`

## Token-Efficient Review Workflow

- Start with `git status --short`, targeted `rg`, and narrow file reads.
- Use token-savior only for navigation/search assistance; do not let it replace direct inspection of safety-critical code.
- Use full-file or full-function reads for safety-critical logic before judging behavior.
- Run only the tests required by the requested audit, plus named regression tests.
- Keep final reports concise and blocker-focused.

## Boundaries

- Do not add Claude hooks to Codex.
- Do not add aggressive output compaction hooks.
- Do not replace Claude workflow.
- Do not redesign architecture during audits.
- Do not skip reading safety-critical code to save tokens.

## Backup Coding Audit

When Claude Code session limits are exhausted and a backup assistant (ChatGPT, another Codex session, etc.) wrote production code, Codex must audit before any affected slice is marked PASS/LOCKED.

**Trigger:** backup assistant edited any file outside `tests/` for a slice that is not yet locked.

**Audit checklist:**
- Verify the patch matches the build spec — no scope drift, no extra features added.
- Confirm no PASS/LOCKED slice was touched.
- Confirm no protected files (`conductor_bridge.py`, `rag/*`, `never_do_rules.md`, safety-critical files) were edited outside the explicit build scope.
- Run the full test suite for the affected slice plus all prior-slice regressions.
- Check that the handoff format was used (see `CLAUDE.md` — Backup Coding / Limit Exhausted Protocol).

**Output:** standard PASS/FAIL report. If PASS, add an audit entry to `project.md` noting that backup coding occurred. If FAIL, list blockers; do not lock until fixed.
