#!/usr/bin/env python3
"""
phase_d_slice29_eval.py — Build 22: Session-End Hook v1
Tests D298–D307.

All checks are static source analysis + unit-level functional tests.
No browser runtime, no live ChromaDB writes, no live bridge calls.
"""

import importlib.util
import json
import os
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_SESSION_END_PATH = os.path.join(_ROOT, "rag", "session_end.py")

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(id_, desc, ok, detail=""):
    status = PASS if ok else FAIL
    results.append((id_, status, desc, detail))
    suffix = f"\n         → {detail}" if (not ok and detail) else ""
    print(f"  [{status}] {id_}: {desc}{suffix}")
    return ok


def read_src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_session_end():
    spec = importlib.util.spec_from_file_location("session_end", _SESSION_END_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


# ── D298: importable + callable ───────────────────────────────────────────────

def run_d298():
    print("=== Section D298: importable + callable ===")
    try:
        check("D298a", "session_end.py file exists",
              os.path.exists(_SESSION_END_PATH))
        se = load_session_end()
        check("D298b", "run_session_end is callable",
              callable(getattr(se, "run_session_end", None)))
        check("D298c", "DEFAULT_BRIDGE_URL constant present",
              hasattr(se, "DEFAULT_BRIDGE_URL"))
        result = se.run_session_end(dry_run=True)
        check("D298d", "run_session_end(dry_run=True) returns dict",
              isinstance(result, dict))
    except Exception as exc:
        check("D298a", "importable + callable", False, str(exc))


# ── D299: missing/empty logs safe ────────────────────────────────────────────

def run_d299():
    print("=== Section D299: missing/empty logs safe ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        with tempfile.TemporaryDirectory() as td:
            # All log paths point to non-existent files
            result = fn(
                dry_run             = True,
                feedback_log_path   = os.path.join(td, "no_fb.jsonl"),
                knowledge_log_path  = os.path.join(td, "no_kfb.jsonl"),
                candidates_path     = os.path.join(td, "no_cand.jsonl"),
                reflection_log_path = os.path.join(td, "no_refl.jsonl"),
            )
            check("D299a", "nonexistent logs → returns dict without raising",
                  isinstance(result, dict))
            check("D299b", "nonexistent logs → steps_failed == 0",
                  result.get("steps_failed", 999) == 0)
            check("D299c", "nonexistent logs → errors list is empty",
                  result.get("errors") == [])

            # Empty log files
            empty = os.path.join(td, "empty.jsonl")
            _write_jsonl(empty, [])
            result2 = fn(
                dry_run             = True,
                feedback_log_path   = empty,
                knowledge_log_path  = empty,
                candidates_path     = empty,
                reflection_log_path = os.path.join(td, "empty_refl.jsonl"),
            )
            check("D299d", "empty logs → steps_failed == 0",
                  result2.get("steps_failed", 999) == 0)
    except Exception as exc:
        check("D299a", "missing/empty logs safe", False, str(exc))


# ── D300: correct pipeline order ─────────────────────────────────────────────

def run_d300():
    print("=== Section D300: correct pipeline order ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        # All three steps complete when logs are empty
        with tempfile.TemporaryDirectory() as td:
            result = fn(
                dry_run             = True,
                feedback_log_path   = os.path.join(td, "fb.jsonl"),
                knowledge_log_path  = os.path.join(td, "kfb.jsonl"),
                candidates_path     = os.path.join(td, "cand.jsonl"),
                reflection_log_path = os.path.join(td, "refl.jsonl"),
            )
            check("D300a", "all 3 steps attempted on empty logs",
                  result.get("steps_attempted") == 3)
            check("D300b", "all 3 steps completed on empty logs",
                  result.get("steps_completed") == 3)

        # Step 1 failure → Steps 2 and 3 not attempted
        orig_promo = se._run_promotion
        def _raise_promo(**kw): raise RuntimeError("forced step 1 failure")
        se._run_promotion = _raise_promo
        try:
            result2 = fn(dry_run=True)
            check("D300c", "step 1 failure → steps_attempted == 1",
                  result2.get("steps_attempted") == 1)
            check("D300d", "step 1 failure → steps_completed == 0",
                  result2.get("steps_completed") == 0)
        finally:
            se._run_promotion = orig_promo

        # Step 2 failure → Step 3 not attempted
        orig_refl = se._run_reflection
        def _raise_refl(**kw): raise RuntimeError("forced step 2 failure")
        se._run_reflection = _raise_refl
        try:
            result3 = fn(dry_run=True)
            check("D300e", "step 2 failure → steps_attempted == 2",
                  result3.get("steps_attempted") == 2)
            check("D300f", "step 2 failure → steps_completed == 1 (step 1 still done)",
                  result3.get("steps_completed") == 1)
        finally:
            se._run_reflection = orig_refl

    except Exception as exc:
        check("D300a", "pipeline order", False, str(exc))


# ── D301: dry_run=True blocks all writes ─────────────────────────────────────

def run_d301():
    print("=== Section D301: dry_run=True blocks all writes ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        with tempfile.TemporaryDirectory() as td:
            ledger   = os.path.join(td, "candidates.jsonl")
            refl_log = os.path.join(td, "reflection_log.jsonl")

            # Set all write flags True — dry_run=True should suppress them all
            result = fn(
                dry_run                = True,
                write_promotion_ledger = True,
                write_reflection_log   = True,
                write_memory           = True,
                candidates_path        = ledger,
                reflection_log_path    = refl_log,
            )
            check("D301a", "dry_run=True + write flags → ledger file not created",
                  not os.path.exists(ledger))
            check("D301b", "dry_run=True + write flags → reflection log not created",
                  not os.path.exists(refl_log))
            check("D301c", "result['dry_run'] is True",
                  result.get("dry_run") is True)
            mw = result.get("memory_write") or {}
            check("D301d", "memory_write result shows dry_run=True",
                  mw.get("dry_run") is True)
    except Exception as exc:
        check("D301a", "dry_run blocks writes", False, str(exc))


# ── D302: explicit write flag required ───────────────────────────────────────

def run_d302():
    print("=== Section D302: explicit write flag required ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        with tempfile.TemporaryDirectory() as td:
            ledger   = os.path.join(td, "candidates.jsonl")
            refl_log = os.path.join(td, "reflection_log.jsonl")
            fb_log   = os.path.join(td, "feedback.jsonl")
            _write_jsonl(fb_log, [
                {"feedback_type": "KEEP", "action_type": "eq", "target": "kick",
                 "project_id": "proj1", "session_id": "sess1", "message": "worked"}
            ])

            # dry_run=False but no write flags → still no files written
            result = fn(
                dry_run                = False,
                write_promotion_ledger = False,
                write_reflection_log   = False,
                write_memory           = False,
                feedback_log_path      = fb_log,
                candidates_path        = ledger,
                reflection_log_path    = refl_log,
            )
            check("D302a", "dry_run=False, no write flags → ledger not created",
                  not os.path.exists(ledger))
            check("D302b", "dry_run=False, no write flags → reflection log not created",
                  not os.path.exists(refl_log))
            check("D302c", "all 3 steps still complete with no writes",
                  result.get("steps_completed") == 3)
    except Exception as exc:
        check("D302a", "explicit write flags required", False, str(exc))


# ── D303: per-step failure captured, does not crash ──────────────────────────

def run_d303():
    print("=== Section D303: per-step failure captured ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        # Step 1 failure
        orig_promo = se._run_promotion
        def _raise_promo(**kw): raise RuntimeError("simulated promotion failure")
        se._run_promotion = _raise_promo
        try:
            result = fn(dry_run=True)
            check("D303a", "step 1 failure → steps_failed == 1",
                  result.get("steps_failed") == 1)
            check("D303b", "step 1 failure → errors list non-empty",
                  bool(result.get("errors")))
            check("D303c", "step 1 failure → error message references 'Step 1'",
                  "Step 1" in (result.get("errors") or [""])[0])
            check("D303d", "step 1 failure → promotion dict contains 'error' key",
                  "error" in (result.get("promotion") or {}))
        finally:
            se._run_promotion = orig_promo

        # Step 3 failure — steps 1 and 2 remain completed
        orig_write = se._write_memories
        def _raise_write(**kw): raise RuntimeError("simulated write failure")
        se._write_memories = _raise_write
        try:
            result2 = fn(dry_run=True)
            check("D303e", "step 3 failure → steps_failed == 1",
                  result2.get("steps_failed") == 1)
            check("D303f", "step 3 failure → steps 1 and 2 still completed (steps_completed == 2)",
                  result2.get("steps_completed") == 2)
            check("D303g", "step 3 failure → errors list non-empty",
                  bool(result2.get("errors")))
        finally:
            se._write_memories = orig_write

    except Exception as exc:
        check("D303a", "per-step failure captured", False, str(exc))


# ── D304: no forbidden imports/writes in source ──────────────────────────────

def run_d304():
    print("=== Section D304: no forbidden imports/writes in source ===")
    try:
        src = read_src(_SESSION_END_PATH)
        lines = src.splitlines()

        check("D304a", "no direct chromadb import",
              "import chromadb" not in src and "from chromadb" not in src)

        check("D304b", "no open(…, 'w') or open(…, 'a') file-write calls",
              all(
                  "'w'" not in line and '"w"' not in line and
                  "'a'" not in line and '"a"' not in line
                  for line in lines if "open(" in line
              ))

        check("D304c", "no PersistentClient / direct ChromaDB collection call",
              "PersistentClient" not in src and ".collection(" not in src)

        check("D304d", "no /action/ bridge endpoint calls",
              "/action/" not in src)

        check("D304e", "no global_taste scope generation",
              "global_taste" not in src)

        check("D304f", "no Level 3/4 writes (no suggested_level >= 3 emitted)",
              "suggested_level" not in src or
              all("suggested_level" in line and
                  ("= 3" not in line and "= 4" not in line and ">= 3" not in line)
                  for line in lines if "suggested_level" in line))

        check("D304g", "__main__ guard present",
              'if __name__ == "__main__"' in src or "if __name__ == '__main__'" in src)

        check("D304h", "run_session_end function defined",
              "def run_session_end(" in src)

    except Exception as exc:
        check("D304a", "forbidden imports/writes", False, str(exc))


# ── D305: idempotency ─────────────────────────────────────────────────────────

def run_d305():
    print("=== Section D305: idempotency ===")
    try:
        se = load_session_end()
        fn = se.run_session_end

        with tempfile.TemporaryDirectory() as td:
            kwargs = dict(
                dry_run             = True,
                feedback_log_path   = os.path.join(td, "fb.jsonl"),
                knowledge_log_path  = os.path.join(td, "kfb.jsonl"),
                candidates_path     = os.path.join(td, "cand.jsonl"),
                reflection_log_path = os.path.join(td, "refl.jsonl"),
            )
            result1 = fn(**kwargs)
            result2 = fn(**kwargs)

            check("D305a", "two dry-run calls → same steps_completed",
                  result1.get("steps_completed") == result2.get("steps_completed"))
            check("D305b", "two dry-run calls → both have 0 steps_failed",
                  result1.get("steps_failed") == 0 and result2.get("steps_failed") == 0)
            check("D305c", "two dry-run calls → no files created in temp dir",
                  not os.path.exists(os.path.join(td, "cand.jsonl")) and
                  not os.path.exists(os.path.join(td, "refl.jsonl")))
    except Exception as exc:
        check("D305a", "idempotency", False, str(exc))


# ── D306: structured result keys ──────────────────────────────────────────────

def run_d306():
    print("=== Section D306: structured result keys ===")
    try:
        se = load_session_end()
        result = se.run_session_end(dry_run=True)

        required_keys = {
            "steps_attempted", "steps_completed", "steps_failed",
            "dry_run", "promotion", "reflection", "memory_write", "errors",
        }
        for key in sorted(required_keys):
            check(f"D306-{key}", f"result has key '{key}'", key in result)

        check("D306-type-a", "steps_attempted is int",
              isinstance(result.get("steps_attempted"), int))
        check("D306-type-b", "steps_completed is int",
              isinstance(result.get("steps_completed"), int))
        check("D306-type-c", "dry_run is bool",
              isinstance(result.get("dry_run"), bool))
        check("D306-type-d", "errors is list",
              isinstance(result.get("errors"), list))
        check("D306-type-e", "promotion is dict",
              isinstance(result.get("promotion"), dict))
        check("D306-type-f", "reflection is dict",
              isinstance(result.get("reflection"), dict))
        check("D306-type-g", "memory_write is dict",
              isinstance(result.get("memory_write"), dict))

    except Exception as exc:
        check("D306-steps_attempted", "structured result keys", False, str(exc))


# ── D307: write_log flag preserved for Build 20 idempotency ──────────────────

def run_d307():
    print("=== Section D307: write_log flag preserved for Build 20 idempotency ===")
    import sys
    try:
        se = load_session_end()
        fn = se.run_session_end

        orig_promo = se._run_promotion
        orig_refl  = se._run_reflection
        orig_wm    = se._write_memories

        def _noop_promo(**kw):
            return {"total_candidates": 0, "duplicates_skipped": 0}

        def _noop_refl(**kw):
            return {"counts": {}, "accepted_signals": [], "do_not_promote": []}

        # ── D307a: write_log=True when dry_run=False + write_memory=True ──────
        captured_wl: list = []
        def _capture(**kw):
            captured_wl.append(kw.get("write_log"))
            return {"written": 0, "failed_bridge": 0, "dry_run": False, "skipped_duplicate": 0}

        se._run_promotion  = _noop_promo
        se._run_reflection = _noop_refl
        se._write_memories = _capture
        try:
            fn(dry_run=False, write_memory=True)
            check("D307a", "write_log=True when dry_run=False + write_memory=True",
                  bool(captured_wl) and captured_wl[0] is True)
        finally:
            se._run_promotion  = orig_promo
            se._run_reflection = orig_refl
            se._write_memories = orig_wm

        # ── D307b: write_log=False when dry_run=True ──────────────────────────
        captured_wl2: list = []
        def _capture2(**kw):
            captured_wl2.append(kw.get("write_log"))
            return {"written": 0, "failed_bridge": 0, "dry_run": True, "skipped_duplicate": 0}

        se._run_promotion  = _noop_promo
        se._run_reflection = _noop_refl
        se._write_memories = _capture2
        try:
            fn(dry_run=True, write_memory=True)
            check("D307b", "write_log=False when dry_run=True (even with write_memory=True)",
                  bool(captured_wl2) and captured_wl2[0] is False)
        finally:
            se._run_promotion  = orig_promo
            se._run_reflection = orig_refl
            se._write_memories = orig_wm

        # ── D307c-f: integration — mocked bridge, real write_log ledger ───────
        mw_mod = sys.modules.get("rag.memory_writer")
        if mw_mod is None:
            check("D307c", "rag.memory_writer in sys.modules for patching", False,
                  "module not loaded — run load_session_end() first")
            return

        orig_post    = mw_mod._post_memory
        orig_wl_path = mw_mod.DEFAULT_WRITE_LOG_PATH

        bridge_calls: list = []
        def _mock_post(bridge_url, payload):
            bridge_calls.append(payload.get("metadata", {}).get("candidate_id", "?"))
            return (True, "mock-mem-" + str(len(bridge_calls)))

        crafted_reflection = {
            "accepted_signals": [{
                "candidate_id":    "test-cand-001",
                "scope":           "session_only",
                "suggested_level": 1,
                "evidence":        "high-pass on kick worked",
                "action_type":     "eq",
                "target":          "kick",
                "session_id":      "sess-001",
                "project_id":      "",
                "message":         "",
                "feedback_type":   "KEEP",
            }],
            "do_not_promote": [],
            "counts": {"accepted": 1, "rejected": 0, "repeated_patterns": 0},
        }

        def _refl_with_signal(**kw):
            return crafted_reflection

        with tempfile.TemporaryDirectory() as td:
            tmp_wl = os.path.join(td, "write_log.jsonl")
            se._run_promotion  = _noop_promo
            se._run_reflection = _refl_with_signal
            mw_mod._post_memory            = _mock_post
            mw_mod.DEFAULT_WRITE_LOG_PATH  = tmp_wl
            try:
                r1 = fn(dry_run=False, write_memory=True)
                r2 = fn(dry_run=False, write_memory=True)
                mw1 = r1.get("memory_write") or {}
                mw2 = r2.get("memory_write") or {}
                check("D307c", "first live run: 1 candidate written",
                      mw1.get("written") == 1)
                check("D307d", "second live run: duplicate skipped, 0 written",
                      mw2.get("written") == 0 and mw2.get("skipped_duplicate", 0) >= 1)
                check("D307e", "write_log file created after first run",
                      os.path.exists(tmp_wl))
                check("D307f", "bridge called exactly once across both runs",
                      len(bridge_calls) == 1)
            finally:
                se._run_promotion          = orig_promo
                se._run_reflection         = orig_refl
                mw_mod._post_memory        = orig_post
                mw_mod.DEFAULT_WRITE_LOG_PATH = orig_wl_path

        # ── D307g: dry_run=True — write_log never created ────────────────────
        with tempfile.TemporaryDirectory() as td2:
            tmp_wl2 = os.path.join(td2, "write_log_dry.jsonl")
            se._run_promotion  = _noop_promo
            se._run_reflection = _refl_with_signal
            mw_mod._post_memory            = _mock_post
            mw_mod.DEFAULT_WRITE_LOG_PATH  = tmp_wl2
            try:
                fn(dry_run=True, write_memory=True)
                check("D307g", "dry_run=True never writes write_log file",
                      not os.path.exists(tmp_wl2))
            finally:
                se._run_promotion          = orig_promo
                se._run_reflection         = orig_refl
                mw_mod._post_memory        = orig_post
                mw_mod.DEFAULT_WRITE_LOG_PATH = orig_wl_path

    except Exception as exc:
        check("D307a", "write_log idempotency flag tests", False, str(exc))


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  phase_d_slice29_eval.py — Build 22: Session-End Hook v1 (D298–D307)")
    print("=" * 60)

    run_d298()
    run_d299()
    run_d300()
    run_d301()
    run_d302()
    run_d303()
    run_d304()
    run_d305()
    run_d306()
    run_d307()

    passed = sum(1 for _, s, _, _ in results if s == PASS)
    failed = sum(1 for _, s, _, _ in results if s == FAIL)
    total  = len(results)

    print()
    print("=" * 60)
    print(f"  TOTAL: {passed} PASS / {failed} FAIL  (of {total} checks)")
    print("=" * 60)

    if failed:
        print("\nFailed checks:")
        for id_, status, desc, detail in results:
            if status == FAIL:
                print(f"  {id_}: {desc}")
                if detail:
                    print(f"    → {detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
