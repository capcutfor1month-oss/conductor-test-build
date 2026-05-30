#!/usr/bin/env python3
"""
rag/session_end.py — Build 22: Session-End Hook v1

Orchestrates the full learning pipeline at session end:

  Step 1 — Memory Promotion  (Build 18): generate promotion candidates from feedback
  Step 2 — Session Reflection (Build 19): reflect on candidates, detect patterns
  Step 3 — Memory Writer      (Build 20): write safe signals to bridge POST /memory

This module is a thin orchestrator. All business logic stays in the three
locked modules. run_session_end() returns a structured result with per-step
outcomes and errors. Per-step failure is non-fatal where possible:
  • Step 1 failure → Steps 2 and 3 are skipped (no candidates to reflect on).
  • Step 2 failure → Step 3 is skipped (no reflection to write from).
  • Step 3 failure → captured in result; Steps 1 and 2 remain completed.

─── Write control ─────────────────────────────────────────────────────────────

  dry_run=True (default) suppresses ALL writes across all three steps,
  regardless of the individual write flags.

  To write, BOTH conditions must be true:
    • dry_run=False  (explicit)
    • the per-step write flag is True

  Per-step write flags:
    write_promotion_ledger   Step 1: write promotion_candidates.jsonl
    write_reflection_log     Step 2: append to session_reflection_log.jsonl
    write_memory             Step 3: send candidates to bridge POST /memory

─── Pipeline ──────────────────────────────────────────────────────────────────

  Step 1  run_promotion()                    → promotion result dict
  Step 2  run_reflection()                   → reflection result dict
  Step 3  write_promoted_memories(reflection=…) → write result dict

─── Usage ─────────────────────────────────────────────────────────────────────

  python3 rag/session_end.py                       # dry-run summary
  python3 rag/session_end.py --no-dry-run          # live run, no file writes
  python3 rag/session_end.py --no-dry-run --write-all   # live + all writes
  python3 rag/session_end.py --json                # machine-readable output

  from rag.session_end import run_session_end
  result = run_session_end(dry_run=True)

─── Output shape ──────────────────────────────────────────────────────────────

  {
      "steps_attempted":   int,    # 1–3
      "steps_completed":   int,    # 0–3
      "steps_failed":      int,    # 0–3
      "dry_run":           bool,
      "promotion":         dict,   # run_promotion() result, or {"error": str}
      "reflection":        dict,   # run_reflection() result, or {"error": str}
      "memory_write":      dict,   # write_promoted_memories() result, or {"error": str}
      "errors":            list,   # human-readable error strings (one per failed step)
  }

─── Do-not-touch contract ─────────────────────────────────────────────────────

  This module NEVER directly writes to:
    memory/feedback_log.jsonl
    memory/action_log.jsonl
    memory/action_proof_log.jsonl
    memory/knowledge_feedback_log.jsonl
    memory/context_pack_log.jsonl
    conductor-vault/producer/never_do_rules.md
    conductor-vault/producer/confirmed_preferences.md
    memory/chromadb/  (no direct ChromaDB — bridge only via memory_writer)

  All writes are delegated to the three locked modules under their own contracts.
"""

import json
import os
import sys
from typing import Any, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MEMORY_DIR = os.path.join(_ROOT, "memory")

DEFAULT_BRIDGE_URL = "http://localhost:4611"

# Never-Do guard — this path is NEVER written to by this module.
_NEVER_DO_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")

# Ensure the project root is importable when this script is run directly
# from the rag/ subdirectory.
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from rag.memory_promotion   import run_promotion           as _run_promotion
from rag.session_reflection import run_reflection          as _run_reflection
from rag.memory_writer      import write_promoted_memories as _write_memories


# ── Public API ─────────────────────────────────────────────────────────────────

def run_session_end(
    dry_run:                bool = True,
    write_promotion_ledger: bool = False,
    write_reflection_log:   bool = False,
    write_memory:           bool = False,
    bridge_url:             str  = DEFAULT_BRIDGE_URL,
    # Path overrides — primarily for testing and CLI use.
    feedback_log_path:      Optional[str] = None,
    proof_log_path:         Optional[str] = None,
    knowledge_log_path:     Optional[str] = None,
    candidates_path:        Optional[str] = None,
    reflection_log_path:    Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run the full session-end learning pipeline.

    Orchestrates memory_promotion (Step 1), session_reflection (Step 2), and
    memory_writer (Step 3) in order. Each step's outcome is captured in the
    returned dict. An exception in Step 1 or Step 2 causes dependent later
    steps to be skipped to avoid running on bad data.

    Args:
        dry_run:                If True (default), ALL writes suppressed regardless
                                of individual write flags.
        write_promotion_ledger: Write promotion_candidates.jsonl (Step 1).
                                Only effective when dry_run=False.
        write_reflection_log:   Append to session_reflection_log.jsonl (Step 2).
                                Only effective when dry_run=False.
        write_memory:           Send signals to bridge POST /memory (Step 3).
                                Only effective when dry_run=False.
        bridge_url:             Bridge base URL. Default: http://localhost:4611.
        feedback_log_path:      Override for memory/feedback_log.jsonl.
        proof_log_path:         Override for memory/action_proof_log.jsonl.
        knowledge_log_path:     Override for memory/knowledge_feedback_log.jsonl.
        candidates_path:        Override for memory/promotion_candidates.jsonl.
        reflection_log_path:    Override for memory/session_reflection_log.jsonl.

    Returns:
        Structured result dict. Never raises.
    """
    result: Dict[str, Any] = {
        "steps_attempted": 0,
        "steps_completed": 0,
        "steps_failed":    0,
        "dry_run":         dry_run,
        "promotion":       {},
        "reflection":      {},
        "memory_write":    {},
        "errors":          [],
    }

    # ── Step 1: Memory Promotion ──────────────────────────────────────────────
    result["steps_attempted"] += 1
    try:
        promo = _run_promotion(
            feedback_log_path  = feedback_log_path,
            proof_log_path     = proof_log_path,
            knowledge_log_path = knowledge_log_path,
            ledger_path        = candidates_path,
            dry_run            = dry_run or not write_promotion_ledger,
        )
        result["promotion"] = promo
        result["steps_completed"] += 1
    except Exception as exc:
        result["promotion"] = {"error": str(exc)}
        result["errors"].append(f"Step 1 (promotion) failed: {exc}")
        result["steps_failed"] += 1
        return result  # Steps 2 and 3 depend on Step 1 output — abort.

    # ── Step 2: Session Reflection ────────────────────────────────────────────
    result["steps_attempted"] += 1
    try:
        refl = _run_reflection(
            candidates_path     = candidates_path,
            feedback_log_path   = feedback_log_path,
            knowledge_log_path  = knowledge_log_path,
            reflection_log_path = reflection_log_path,
            dry_run             = dry_run or not write_reflection_log,
            write_log           = write_reflection_log and not dry_run,
        )
        result["reflection"] = refl
        result["steps_completed"] += 1
    except Exception as exc:
        result["reflection"] = {"error": str(exc)}
        result["errors"].append(f"Step 2 (reflection) failed: {exc}")
        result["steps_failed"] += 1
        return result  # Step 3 requires a valid reflection — abort.

    # ── Step 3: Controlled Memory Write ──────────────────────────────────────
    result["steps_attempted"] += 1
    try:
        mw = _write_memories(
            reflection = refl,
            bridge_url = bridge_url,
            dry_run    = dry_run or not write_memory,
            write_log  = write_memory and not dry_run,
        )
        result["memory_write"] = mw
        result["steps_completed"] += 1
    except Exception as exc:
        result["memory_write"] = {"error": str(exc)}
        result["errors"].append(f"Step 3 (memory_write) failed: {exc}")
        result["steps_failed"] += 1

    return result


# ── CLI ───────────────────────────────────────────────────────────────────────

def _main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Conductor session-end learning pipeline")
    parser.add_argument("--no-dry-run",       dest="no_dry_run",   action="store_true",
                        help="Disable dry-run (required to enable any writes)")
    parser.add_argument("--write-all",        dest="write_all",    action="store_true",
                        help="Enable all write flags (requires --no-dry-run)")
    parser.add_argument("--write-promotion",  dest="write_promo",  action="store_true")
    parser.add_argument("--write-reflection", dest="write_refl",   action="store_true")
    parser.add_argument("--write-memory",     dest="write_mem",    action="store_true")
    parser.add_argument("--json",             dest="as_json",      action="store_true")
    args = parser.parse_args()

    dry_run = not args.no_dry_run
    result  = run_session_end(
        dry_run                = dry_run,
        write_promotion_ledger = args.write_all or args.write_promo,
        write_reflection_log   = args.write_all or args.write_refl,
        write_memory           = args.write_all or args.write_mem,
    )

    if args.as_json:
        print(json.dumps(result, indent=2, default=str))
        return 1 if result["steps_failed"] else 0

    dr = " [DRY RUN]" if dry_run else ""
    print(f"\nSession-End Hook v1{dr}")
    print(f"  Steps: {result['steps_completed']}/{result['steps_attempted']} completed,"
          f" {result['steps_failed']} failed")

    promo = result.get("promotion") or {}
    if "error" in promo:
        print(f"  Promotion:  ERROR — {promo['error']}")
    else:
        print(f"  Promotion:  {promo.get('total_candidates', 0)} new candidates,"
              f" {promo.get('duplicates_skipped', 0)} duplicates skipped")

    refl = result.get("reflection") or {}
    if "error" in refl:
        print(f"  Reflection: ERROR — {refl['error']}")
    else:
        c = refl.get("counts") or {}
        print(f"  Reflection: {c.get('accepted', 0)} accepted,"
              f" {c.get('rejected', 0)} rejected,"
              f" {c.get('repeated_patterns', 0)} patterns")

    mw = result.get("memory_write") or {}
    if "error" in mw:
        print(f"  Memory:     ERROR — {mw['error']}")
    else:
        print(f"  Memory:     {mw.get('written', 0)} written,"
              f" {mw.get('failed_bridge', 0)} bridge failures"
              f" (dry_run={mw.get('dry_run', True)})")

    for err in result.get("errors") or []:
        print(f"  [!] {err}")

    return 1 if result["steps_failed"] else 0


if __name__ == "__main__":
    sys.exit(_main())
