#!/usr/bin/env python3
"""
rag/memory_promotion.py — Build 18: Memory Promotion v1 / Promotion Candidate Generator

Reads feedback logs and action proofs to generate structured promotion candidates.
This build: candidate generation + dry-run foundation only.
No ChromaDB writes. No hot-path retrieval changes. No session-end hook.

─── Learning rules ────────────────────────────────────────────────────────────

  KEEP / HELPFUL (explicit positive feedback) → promotion candidates.
  UNDO / WRONG_DIRECTION / NOT_HELPFUL / WRONG / OUTDATED → never promote.
  TOO_MUCH / NOT_ENOUGH / TOO_VAGUE → below threshold, not candidates.
  Missing feedback → no signal, no candidate. Absence never penalises.

  Music feedback is contextual: one accepted suggestion ≠ universal user taste.
  A vocal treatment can depend on song, vocal type, recording quality, genre,
  project goal, arrangement density, and personal taste.

  Scope defaults to session/project. Global user-taste candidates require
  repeated explicit evidence across multiple sessions — NOT built in this release.

  Feedback UI (Build 15/16) shows chips on knowledge answers only. Voice mode
  reactions require a separate future natural-reaction path (not built here).
  Absence of feedback has zero learning weight, especially when the feedback
  UI was not visible or available.

─── Sources (read-only) ───────────────────────────────────────────────────────

  memory/feedback_log.jsonl            action feedback (KEEP / UNDO / TOO_MUCH /
                                       NOT_ENOUGH / WRONG_DIRECTION)
  memory/action_proof_log.jsonl        action proofs — evidence enrichment
  memory/knowledge_feedback_log.jsonl  knowledge feedback (HELPFUL / NOT_HELPFUL /
                                       TOO_VAGUE / WRONG / OUTDATED)

─── Ledger written ────────────────────────────────────────────────────────────

  memory/promotion_candidates.jsonl    append-only, one record per new candidate
                                       used for idempotency across repeated runs

─── Usage ─────────────────────────────────────────────────────────────────────

  python3 rag/memory_promotion.py                    # live run
  python3 rag/memory_promotion.py --dry-run          # no ledger write
  python3 rag/memory_promotion.py --dry-run --json   # machine-readable output

  from rag.memory_promotion import run_promotion
  result = run_promotion(dry_run=True)

─── Output shape ──────────────────────────────────────────────────────────────

  {
      "candidates":             list[dict],   # new candidates this run
      "total_processed":        int,          # feedback records read
      "total_candidates":       int,          # new candidates generated
      "duplicates_skipped":     int,          # already in ledger
      "non_promoting_skipped":  int,          # negative or below threshold
  }

─── Do-not-touch contract ─────────────────────────────────────────────────────

  This module NEVER writes to:
    memory/feedback_log.jsonl
    memory/action_log.jsonl
    memory/action_proof_log.jsonl
    memory/knowledge_feedback_log.jsonl
    memory/context_pack_log.jsonl
    conductor-vault/producer/never_do_rules.md
    ChromaDB (any collection)

  Level 4 / Never-Do records are never generated or touched.
"""

import datetime
import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Optional, Set

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MEMORY_DIR = os.path.join(_ROOT, "memory")

# ── Source log paths (read-only) ──────────────────────────────────────────────
DEFAULT_FEEDBACK_LOG   = os.path.join(_MEMORY_DIR, "feedback_log.jsonl")
DEFAULT_PROOF_LOG      = os.path.join(_MEMORY_DIR, "action_proof_log.jsonl")
DEFAULT_KNOWLEDGE_LOG  = os.path.join(_MEMORY_DIR, "knowledge_feedback_log.jsonl")

# ── Ledger path (written by this module only) ─────────────────────────────────
DEFAULT_LEDGER_PATH    = os.path.join(_MEMORY_DIR, "promotion_candidates.jsonl")

# ── Never-Do guard — this path is NEVER written to by this module ─────────────
_NEVER_DO_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")

# ── Scoring constants ──────────────────────────────────────────────────────────
#
# Only KEEP and HELPFUL clear the CANDIDATE_THRESHOLD (0.50).
#
# TOO_MUCH / NOT_ENOUGH say "direction was right, magnitude was wrong" — useful
# signal for future calibration, but NOT a "promote this decision" signal.
# They are intentionally kept below threshold.
#
# TOO_VAGUE — weak signal, no specific action to promote.

_ACTION_BASE_SCORES: Dict[str, float] = {
    "KEEP":             0.65,   # strong positive — candidate
    "TOO_MUCH":         0.25,   # direction right, magnitude wrong — below threshold
    "NOT_ENOUGH":       0.25,   # direction right, magnitude wrong — below threshold
    # UNDO, WRONG_DIRECTION: absent from map — never promote
}

_KNOWLEDGE_BASE_SCORES: Dict[str, float] = {
    "HELPFUL":          0.55,   # positive knowledge signal — candidate
    "TOO_VAGUE":        0.20,   # weak signal — below threshold
    # NOT_HELPFUL, WRONG, OUTDATED: absent from map — never promote
}

_MESSAGE_BONUS       = 0.10   # non-empty user message adds confidence
_CANDIDATE_THRESHOLD = 0.50   # minimum score to become a candidate

# Suggested memory level bounds (never suggest Level 3 or 4 in this build)
_LEVEL_SESSION_ONLY    = 1    # no project context — raw event
_LEVEL_SESSION_PROJECT = 2    # project_id known — session decision
_LEVEL_MAX_THIS_BUILD  = 2    # hard cap: no Level 3/4 candidates in Build 18

# Negative feedback types — explicitly skipped, never become candidates
_ACTION_NEGATIVE     = frozenset({"UNDO", "WRONG_DIRECTION"})
_KNOWLEDGE_NEGATIVE  = frozenset({"NOT_HELPFUL", "WRONG", "OUTDATED"})


# ── Public API ────────────────────────────────────────────────────────────────

def run_promotion(
    feedback_log_path:  Optional[str] = None,
    proof_log_path:     Optional[str] = None,
    knowledge_log_path: Optional[str] = None,
    ledger_path:        Optional[str] = None,
    dry_run:            bool = False,
) -> Dict[str, Any]:
    """
    Read feedback logs and generate promotion candidates.

    Reads action feedback (feedback_log.jsonl), action proofs (action_proof_log.jsonl),
    and knowledge feedback (knowledge_feedback_log.jsonl). Returns a result dict with
    new promotion candidates, counters, and scope metadata.

    All source logs are opened read-only. The ledger (promotion_candidates.jsonl) is
    written unless dry_run=True. Repeated runs with the same inputs produce zero new
    candidates after the first run (idempotency via candidate_id hash).

    Args:
        feedback_log_path:   Override for memory/feedback_log.jsonl
        proof_log_path:      Override for memory/action_proof_log.jsonl
        knowledge_log_path:  Override for memory/knowledge_feedback_log.jsonl
        ledger_path:         Override for memory/promotion_candidates.jsonl
        dry_run:             If True, generate candidates but do not write to ledger

    Returns:
        {
            "candidates":             list[dict],
            "total_processed":        int,
            "total_candidates":       int,
            "duplicates_skipped":     int,
            "non_promoting_skipped":  int,
        }
    """
    fb_path  = feedback_log_path  or DEFAULT_FEEDBACK_LOG
    prf_path = proof_log_path     or DEFAULT_PROOF_LOG
    kfb_path = knowledge_log_path or DEFAULT_KNOWLEDGE_LOG
    led_path = ledger_path        or DEFAULT_LEDGER_PATH

    # Load existing candidate IDs for idempotency
    seen_ids: Set[str] = _load_seen_candidate_ids(led_path)

    # Load action proofs for evidence enrichment (proof_id → dict)
    proof_index = _load_proof_index(prf_path)

    candidates: List[Dict] = []
    duplicates_skipped    = 0
    non_promoting_skipped = 0
    total_processed       = 0

    # ── Process action feedback ───────────────────────────────────────────────
    for record in _read_jsonl(fb_path):
        if not isinstance(record, dict):
            continue
        total_processed += 1

        ftype      = record.get("feedback_type", "") or ""
        fb_id      = record.get("feedback_id",   "") or ""
        proof_id   = record.get("proof_id",       "") or ""
        action_id  = record.get("action_id",      "") or ""
        session_id = record.get("session_id",     "") or ""
        project_id = record.get("project_id",     "") or ""
        message    = record.get("message",        "") or ""
        timestamp  = record.get("timestamp",      "") or ""

        # Explicitly negative — skip
        if ftype in _ACTION_NEGATIVE:
            non_promoting_skipped += 1
            continue

        # Get base score; unknown type → skip
        base = _ACTION_BASE_SCORES.get(ftype)
        if base is None:
            non_promoting_skipped += 1
            continue

        score = base + (_MESSAGE_BONUS if message.strip() else 0.0)

        # Below candidate threshold
        if score < _CANDIDATE_THRESHOLD:
            non_promoting_skipped += 1
            continue

        # Enrich from matching proof
        proof        = proof_index.get(proof_id, {})
        action_type  = proof.get("action_type", "")           or ""
        target       = proof.get("target", "")                or ""
        summary      = proof.get("user_facing_summary", "")   or ""
        before_state = proof.get("before_state", {})          or {}
        after_state  = proof.get("after_state", {})           or {}

        # Scope: session_project if we know the project; session_only otherwise
        scope           = "session_project" if project_id else "session_only"
        suggested_level = min(
            _LEVEL_SESSION_PROJECT if project_id else _LEVEL_SESSION_ONLY,
            _LEVEL_MAX_THIS_BUILD,
        )

        # Build evidence string
        parts = []
        if action_type:
            parts.append(f"action:{action_type}")
        if target:
            parts.append(f"target:{target}")
        if summary:
            parts.append(summary)
        if message:
            parts.append(f"user_note:{message}")
        evidence = " | ".join(parts) or f"action_feedback:{ftype}"

        # Stable candidate ID for idempotency (hash of source + feedback_id + type)
        candidate_id = _make_candidate_id("action", fb_id, ftype)

        if candidate_id in seen_ids:
            duplicates_skipped += 1
            continue

        candidate: Dict[str, Any] = {
            "candidate_id":       candidate_id,
            "source":             "action_feedback",
            "feedback_id":        fb_id,
            "feedback_type":      ftype,
            "action_type":        action_type,
            "action_id":          action_id,
            "proof_id":           proof_id,
            "target":             target,
            "session_id":         session_id,
            "project_id":         project_id,
            "scope":              scope,
            "suggested_level":    suggested_level,
            "score":              round(score, 4),
            "evidence":           evidence,
            "message":            message,
            "before_state":       before_state,
            "after_state":        after_state,
            "generated_at":       _now_iso(),
            "timestamp_original": timestamp,
        }
        candidates.append(candidate)
        seen_ids.add(candidate_id)

    # ── Process knowledge feedback ────────────────────────────────────────────
    #
    # Knowledge feedback (Build 15/16) is explicit UI feedback from chips shown
    # below knowledge answers. Absence of chips — or their non-interaction — has
    # zero learning weight. Voice mode reactions require a separate future path.
    #
    for record in _read_jsonl(kfb_path):
        if not isinstance(record, dict):
            continue
        total_processed += 1

        ftype       = record.get("feedback_type", "") or ""
        fb_id       = record.get("feedback_id",   "") or ""
        response_id = record.get("response_id",   "") or ""
        message     = record.get("message",       "") or ""
        timestamp   = record.get("timestamp",     "") or ""

        # Explicitly negative — skip
        if ftype in _KNOWLEDGE_NEGATIVE:
            non_promoting_skipped += 1
            continue

        base = _KNOWLEDGE_BASE_SCORES.get(ftype)
        if base is None:
            non_promoting_skipped += 1
            continue

        score = base + (_MESSAGE_BONUS if message.strip() else 0.0)

        if score < _CANDIDATE_THRESHOLD:
            non_promoting_skipped += 1
            continue

        # Knowledge feedback carries no project_id — always session_only scope
        scope           = "session_only"
        suggested_level = _LEVEL_SESSION_ONLY

        candidate_id = _make_candidate_id("knowledge", fb_id, ftype)

        if candidate_id in seen_ids:
            duplicates_skipped += 1
            continue

        evidence = f"knowledge_feedback:{ftype}"
        if message:
            evidence += f" | user_note:{message}"

        candidate = {
            "candidate_id":       candidate_id,
            "source":             "knowledge_feedback",
            "feedback_id":        fb_id,
            "feedback_type":      ftype,
            "response_id":        response_id,
            "session_id":         "",
            "project_id":         "",
            "scope":              scope,
            "suggested_level":    suggested_level,
            "score":              round(score, 4),
            "evidence":           evidence,
            "message":            message,
            "generated_at":       _now_iso(),
            "timestamp_original": timestamp,
        }
        candidates.append(candidate)
        seen_ids.add(candidate_id)

    # ── Write to ledger ───────────────────────────────────────────────────────
    if not dry_run and candidates:
        _append_to_ledger(candidates, led_path)

    return {
        "candidates":            candidates,
        "total_processed":       total_processed,
        "total_candidates":      len(candidates),
        "duplicates_skipped":    duplicates_skipped,
        "non_promoting_skipped": non_promoting_skipped,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_candidate_id(source: str, feedback_id: str, feedback_type: str) -> str:
    """Stable 16-char hex ID from source + feedback_id + feedback_type."""
    raw = f"{source}:{feedback_id}:{feedback_type}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]


def _load_seen_candidate_ids(ledger_path: str) -> Set[str]:
    """Return set of candidate_ids already written to the ledger."""
    seen: Set[str] = set()
    if not os.path.exists(ledger_path):
        return seen
    try:
        for record in _read_jsonl(ledger_path):
            if isinstance(record, dict):
                cid = record.get("candidate_id")
                if cid:
                    seen.add(str(cid))
    except Exception:
        pass
    return seen


def _load_proof_index(proof_log_path: str) -> Dict[str, dict]:
    """Build a proof_id → proof_record index from action_proof_log.jsonl."""
    index: Dict[str, dict] = {}
    for record in _read_jsonl(proof_log_path):
        if isinstance(record, dict):
            pid = record.get("proof_id")
            if pid:
                index[str(pid)] = record
    return index


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


def _append_to_ledger(candidates: List[dict], ledger_path: str) -> None:
    """Append new candidates to the promotion ledger. Never raises."""
    try:
        os.makedirs(os.path.dirname(ledger_path), exist_ok=True)
        with open(ledger_path, "a", encoding="utf-8") as fh:
            for c in candidates:
                fh.write(json.dumps(c, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CLI output ────────────────────────────────────────────────────────────────

def _print_summary(result: Dict[str, Any], dry_run: bool = False) -> None:
    mode = " [DRY RUN — ledger not written]" if dry_run else ""
    print("=" * 56)
    print(f"Memory Promotion v1 — Candidate Generator{mode}")
    print("=" * 56)
    print(f"  Records processed    : {result['total_processed']}")
    print(f"  New candidates       : {result['total_candidates']}")
    print(f"  Duplicates skipped   : {result['duplicates_skipped']}")
    print(f"  Non-promoting skipped: {result['non_promoting_skipped']}")
    if result["candidates"]:
        print()
        print("  Candidates:")
        for c in result["candidates"]:
            scope_tag = f"[{c['scope']}]"
            level_tag = f"L{c['suggested_level']}"
            print(
                f"    • {c['feedback_type']:<20}  score={c['score']:.2f}  "
                f"{level_tag}  {scope_tag}"
            )
            evidence = c.get("evidence", "")
            if evidence:
                print(f"      {evidence[:80]}")
    else:
        print()
        print("  No new candidates this run.")
    print("=" * 56)


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Memory Promotion v1 — generate promotion candidates from feedback logs."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate candidates without writing to ledger",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    result = run_promotion(dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_summary(result, dry_run=args.dry_run)
