#!/usr/bin/env python3
"""
rag/session_reflection.py — Build 19: Session Reflection / Feedback Summary v1

Reads Build 18 promotion candidates and feedback logs to produce a structured
session-level reflection. This is the first half of D7 (session-end hook) —
read-only analysis only. It does NOT act on candidates.

It does NOT:
  - write to ChromaDB
  - elevate memory levels
  - write to confirmed_preferences.md or never_do_rules.md
  - write to promotion_candidates.jsonl
  - trigger any runtime behavior change

─── Sources (read-only) ───────────────────────────────────────────────────────

  memory/promotion_candidates.jsonl   Build 18 output — candidates to reflect on
  memory/feedback_log.jsonl           action feedback — source of negative signals
  memory/knowledge_feedback_log.jsonl knowledge feedback — source of negative signals

─── Optional log written ──────────────────────────────────────────────────────

  memory/session_reflection_log.jsonl  one record per run, appended only when
                                        write_log=True and dry_run=False

─── Usage ─────────────────────────────────────────────────────────────────────

  python3 rag/session_reflection.py                    # output only
  python3 rag/session_reflection.py --write-log        # append to reflection log
  python3 rag/session_reflection.py --dry-run          # explicit no-write
  python3 rag/session_reflection.py --json             # machine-readable output

  from rag.session_reflection import run_reflection
  result = run_reflection(dry_run=True)

─── Output shape ──────────────────────────────────────────────────────────────

  {
      "reflection_id":      str,
      "generated_at":       str,
      "session_id":         str,    # shared session_id if all candidates agree, else ""
      "project_id":         str,    # shared project_id if all candidates agree, else ""
      "accepted_signals":   list,   # candidates from promotion_candidates.jsonl
      "rejected_signals":   list,   # UNDO / WRONG_DIRECTION / NOT_HELPFUL / WRONG / OUTDATED
      "repeated_patterns":  list,   # action_type appearing >= _REPEATED_PATTERN_MIN times
      "project_notes":      list,   # one note per distinct non-empty project_id
      "do_not_promote":     list,   # same as rejected_signals — explicit do-not-promote label
      "confidence_reasons": list,   # score + evidence per accepted signal
      "counts":             dict,
  }

─── Do-not-touch contract ─────────────────────────────────────────────────────

  This module NEVER writes to:
    memory/feedback_log.jsonl
    memory/action_log.jsonl
    memory/action_proof_log.jsonl
    memory/knowledge_feedback_log.jsonl
    memory/context_pack_log.jsonl
    memory/promotion_candidates.jsonl
    conductor-vault/producer/never_do_rules.md
    conductor-vault/producer/confirmed_preferences.md
    ChromaDB (any collection)
"""

import datetime
import hashlib
import json
import os
import sys
from collections import Counter
from typing import Any, Dict, List, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MEMORY_DIR = os.path.join(_ROOT, "memory")

# ── Source log paths (read-only) ──────────────────────────────────────────────
DEFAULT_CANDIDATES_PATH = os.path.join(_MEMORY_DIR, "promotion_candidates.jsonl")
DEFAULT_FEEDBACK_LOG    = os.path.join(_MEMORY_DIR, "feedback_log.jsonl")
DEFAULT_KNOWLEDGE_LOG   = os.path.join(_MEMORY_DIR, "knowledge_feedback_log.jsonl")

# ── Optional reflection log (written only when write_log=True and dry_run=False)
DEFAULT_REFLECTION_LOG  = os.path.join(_MEMORY_DIR, "session_reflection_log.jsonl")

# ── Guards — these paths are NEVER written to by this module ──────────────────
_NEVER_DO_PATH        = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")
_CONFIRMED_PREFS_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "confirmed_preferences.md")

# ── Pattern detection threshold ───────────────────────────────────────────────
# An action_type must appear at least this many times across accepted candidates
# to be considered a repeated pattern. Detection is metadata-driven — no
# hardcoded production category words, instruments, genres, or plugin names.
_REPEATED_PATTERN_MIN = 2

# ── Negative feedback types (source of rejected_signals / do_not_promote) ─────
_ACTION_NEGATIVE    = frozenset({"UNDO", "WRONG_DIRECTION"})
_KNOWLEDGE_NEGATIVE = frozenset({"NOT_HELPFUL", "WRONG", "OUTDATED"})


# ── Public API ────────────────────────────────────────────────────────────────

def run_reflection(
    candidates_path:     Optional[str] = None,
    feedback_log_path:   Optional[str] = None,
    knowledge_log_path:  Optional[str] = None,
    reflection_log_path: Optional[str] = None,
    dry_run:             bool = False,
    write_log:           bool = False,
) -> Dict[str, Any]:
    """
    Read promotion candidates and feedback logs; return a structured session reflection.

    All source logs are opened read-only. The reflection log is appended only when
    write_log=True and dry_run=False. No ChromaDB reads or writes. No memory level
    elevation. No writes to never_do_rules.md or confirmed_preferences.md.

    Args:
        candidates_path:     Override for memory/promotion_candidates.jsonl
        feedback_log_path:   Override for memory/feedback_log.jsonl
        knowledge_log_path:  Override for memory/knowledge_feedback_log.jsonl
        reflection_log_path: Override for memory/session_reflection_log.jsonl
        dry_run:             If True, produce reflection in memory only — no log write
        write_log:           If True (and not dry_run), append to reflection log

    Returns a reflection dict. Never raises.
    """
    cand_path = candidates_path     or DEFAULT_CANDIDATES_PATH
    fb_path   = feedback_log_path   or DEFAULT_FEEDBACK_LOG
    kfb_path  = knowledge_log_path  or DEFAULT_KNOWLEDGE_LOG
    ref_path  = reflection_log_path or DEFAULT_REFLECTION_LOG

    # ── Read promotion candidates (read-only) ─────────────────────────────────
    raw_candidates = _read_jsonl(cand_path)

    # ── Read feedback logs for negative signals (read-only) ───────────────────
    feedback_records  = _read_jsonl(fb_path)
    knowledge_records = _read_jsonl(kfb_path)

    # ── Build accepted_signals from candidates ────────────────────────────────
    accepted_signals: List[Dict] = []
    for rec in raw_candidates:
        if not isinstance(rec, dict):
            continue
        accepted_signals.append({
            "candidate_id":    rec.get("candidate_id",    "") or "",
            "source":          rec.get("source",          "") or "",
            "feedback_type":   rec.get("feedback_type",   "") or "",
            "scope":           rec.get("scope",           "") or "",
            "suggested_level": rec.get("suggested_level", 1),
            "score":           rec.get("score",           0.0),
            "evidence":        rec.get("evidence",        "") or "",
            "action_type":     rec.get("action_type",     "") or "",
            "target":          rec.get("target",          "") or "",
            "project_id":      rec.get("project_id",      "") or "",
            "session_id":      rec.get("session_id",      "") or "",
            "message":         rec.get("message",         "") or "",
        })

    # ── Build rejected_signals + do_not_promote from feedback logs ────────────
    #
    # Only explicit negative feedback types are collected here.
    # Absence of a feedback record has zero signal in either direction.
    # TOO_MUCH / NOT_ENOUGH / TOO_VAGUE are calibration signals, not rejections —
    # they do not appear in rejected_signals or do_not_promote.
    #
    rejected_signals: List[Dict] = []
    do_not_promote:   List[Dict] = []

    for rec in feedback_records:
        if not isinstance(rec, dict):
            continue
        ftype = rec.get("feedback_type", "") or ""
        if ftype not in _ACTION_NEGATIVE:
            continue
        entry = {
            "feedback_id":   rec.get("feedback_id",  "") or "",
            "feedback_type": ftype,
            "source":        "action_feedback",
            "action_type":   rec.get("action_type",  "") or "",
            "target":        rec.get("target",        "") or "",
            "session_id":    rec.get("session_id",    "") or "",
            "project_id":    rec.get("project_id",    "") or "",
            "timestamp":     rec.get("timestamp",     "") or "",
        }
        rejected_signals.append(entry)
        do_not_promote.append(entry)

    for rec in knowledge_records:
        if not isinstance(rec, dict):
            continue
        ftype = rec.get("feedback_type", "") or ""
        if ftype not in _KNOWLEDGE_NEGATIVE:
            continue
        entry = {
            "feedback_id":   rec.get("feedback_id",  "") or "",
            "feedback_type": ftype,
            "source":        "knowledge_feedback",
            "action_type":   "",
            "target":        "",
            "session_id":    rec.get("session_id",   "") or "",
            "project_id":    rec.get("project_id",   "") or "",
            "timestamp":     rec.get("timestamp",    "") or "",
        }
        rejected_signals.append(entry)
        do_not_promote.append(entry)

    # ── Repeated pattern detection ────────────────────────────────────────────
    #
    # Looks for action_type values that appear across multiple accepted candidates.
    # Entirely metadata-driven — no hardcoded production categories, instruments,
    # genres, plugin names, or example words. The pattern key is whatever
    # action_type string appears in the candidate records from the logs.
    #
    action_type_counter: Counter = Counter()
    action_type_data: Dict[str, Dict] = {}

    for sig in accepted_signals:
        atype = sig.get("action_type", "") or ""
        if not atype:
            continue
        action_type_counter[atype] += 1
        if atype not in action_type_data:
            action_type_data[atype] = {
                "project_ids":   set(),
                "session_ids":   set(),
                "candidate_ids": [],
            }
        pid = sig["project_id"]
        sid = sig["session_id"]
        if pid:
            action_type_data[atype]["project_ids"].add(pid)
        if sid:
            action_type_data[atype]["session_ids"].add(sid)
        cid = sig["candidate_id"]
        if cid:
            action_type_data[atype]["candidate_ids"].append(cid)

    repeated_patterns: List[Dict] = []
    for atype, count in action_type_counter.items():
        if count >= _REPEATED_PATTERN_MIN:
            data = action_type_data[atype]
            repeated_patterns.append({
                "pattern_key":   atype,
                "pattern_type":  "action_type",
                "count":         count,
                "project_ids":   sorted(data["project_ids"]),
                "session_ids":   sorted(data["session_ids"]),
                "candidate_ids": list(data["candidate_ids"]),
            })

    # Sort by count descending
    repeated_patterns.sort(key=lambda x: x["count"], reverse=True)

    # ── Project notes ─────────────────────────────────────────────────────────
    #
    # One note per distinct non-empty project_id found across accepted and
    # rejected signals. Sessions with no project_id do not generate project notes.
    #
    project_map: Dict[str, Dict] = {}

    for sig in accepted_signals:
        pid = sig.get("project_id", "") or ""
        if not pid:
            continue
        if pid not in project_map:
            project_map[pid] = {"accepted_count": 0, "rejected_count": 0, "candidate_ids": []}
        project_map[pid]["accepted_count"] += 1
        cid = sig["candidate_id"]
        if cid:
            project_map[pid]["candidate_ids"].append(cid)

    for entry in rejected_signals:
        pid = entry.get("project_id", "") or ""
        if not pid:
            continue
        if pid not in project_map:
            project_map[pid] = {"accepted_count": 0, "rejected_count": 0, "candidate_ids": []}
        project_map[pid]["rejected_count"] += 1

    project_notes: List[Dict] = [
        {
            "project_id":     pid,
            "accepted_count": data["accepted_count"],
            "rejected_count": data["rejected_count"],
            "candidate_ids":  data["candidate_ids"],
        }
        for pid, data in sorted(project_map.items())
    ]

    # ── Confidence reasons ────────────────────────────────────────────────────
    confidence_reasons: List[Dict] = [
        {
            "candidate_id":    sig["candidate_id"],
            "feedback_type":   sig["feedback_type"],
            "score":           sig["score"],
            "suggested_level": sig["suggested_level"],
            "evidence":        sig["evidence"],
        }
        for sig in accepted_signals
    ]

    # ── Shared session_id / project_id ────────────────────────────────────────
    all_session_ids = {s["session_id"] for s in accepted_signals if s["session_id"]}
    all_project_ids = {s["project_id"] for s in accepted_signals if s["project_id"]}
    shared_session_id = list(all_session_ids)[0] if len(all_session_ids) == 1 else ""
    shared_project_id = list(all_project_ids)[0] if len(all_project_ids) == 1 else ""

    # ── Reflection ID ─────────────────────────────────────────────────────────
    now_str = _now_iso()
    id_raw = f"{now_str}:{len(accepted_signals)}:{len(rejected_signals)}"
    reflection_id = "refl_" + hashlib.md5(id_raw.encode("utf-8")).hexdigest()[:12]

    # ── Assemble reflection ───────────────────────────────────────────────────
    reflection: Dict[str, Any] = {
        "reflection_id":      reflection_id,
        "generated_at":       now_str,
        "session_id":         shared_session_id,
        "project_id":         shared_project_id,
        "accepted_signals":   accepted_signals,
        "rejected_signals":   rejected_signals,
        "repeated_patterns":  repeated_patterns,
        "project_notes":      project_notes,
        "do_not_promote":     do_not_promote,
        "confidence_reasons": confidence_reasons,
        "counts": {
            "total_candidates_read": len(raw_candidates),
            "accepted":              len(accepted_signals),
            "rejected":              len(rejected_signals),
            "repeated_patterns":     len(repeated_patterns),
            "project_notes":         len(project_notes),
            "do_not_promote":        len(do_not_promote),
        },
    }

    # ── Optional log write ────────────────────────────────────────────────────
    if write_log and not dry_run:
        _append_to_reflection_log(reflection, ref_path)

    return reflection


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_jsonl(path: str) -> List[dict]:
    """Read all valid JSON lines from a JSONL file. Returns [] if missing or unreadable."""
    if not os.path.exists(path):
        return []
    records: List[dict] = []
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return records


def _append_to_reflection_log(reflection: dict, log_path: str) -> None:
    """Append a reflection record to the reflection log. Never raises."""
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(reflection, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CLI output ────────────────────────────────────────────────────────────────

def _print_summary(
    reflection: Dict[str, Any],
    dry_run: bool = False,
    write_log: bool = False,
) -> None:
    if dry_run:
        mode = " [DRY RUN — no log write]"
    elif write_log:
        mode = " [log written]"
    else:
        mode = " [output only]"
    counts = reflection["counts"]
    print("=" * 56)
    print(f"Session Reflection v1{mode}")
    print("=" * 56)
    print(f"  Candidates read      : {counts['total_candidates_read']}")
    print(f"  Accepted signals     : {counts['accepted']}")
    print(f"  Rejected signals     : {counts['rejected']}")
    print(f"  Repeated patterns    : {counts['repeated_patterns']}")
    print(f"  Project notes        : {counts['project_notes']}")
    print(f"  Do-not-promote       : {counts['do_not_promote']}")
    if reflection["repeated_patterns"]:
        print()
        print("  Repeated patterns:")
        for p in reflection["repeated_patterns"]:
            print(f"    • {p['pattern_key']}  ×{p['count']}")
    if reflection["project_notes"]:
        print()
        print("  Project notes:")
        for n in reflection["project_notes"]:
            print(
                f"    • {n['project_id']}  "
                f"accepted={n['accepted_count']}  rejected={n['rejected_count']}"
            )
    print("=" * 56)


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Session Reflection v1 — summarise promotion candidates and feedback signals."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Output only — do not write to reflection log",
    )
    parser.add_argument(
        "--write-log",
        action="store_true",
        help="Append reflection to session_reflection_log.jsonl",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    if args.dry_run and args.write_log:
        print(
            "Warning: --dry-run overrides --write-log. No log will be written.",
            file=sys.stderr,
        )

    result = run_reflection(dry_run=args.dry_run, write_log=args.write_log)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_summary(result, dry_run=args.dry_run, write_log=args.write_log)
