#!/usr/bin/env python3
"""
rag/memory_writer.py — Build 20: Controlled Memory Writer v1

Reads a Build 19 session reflection and writes accepted promotion candidates
to ChromaDB via the bridge POST /memory endpoint.

This build: controlled write step — reads reflection, filters candidates,
writes only safe scoped signals. Dry-run default. No direct ChromaDB.

─── Promotion rules ───────────────────────────────────────────────────────────

  Accepted signals only (from accepted_signals in the reflection).
  Skip if feedback_type is negative (UNDO/WRONG_DIRECTION/NOT_HELPFUL/WRONG/OUTDATED)
    — hard gate independent of do_not_promote, guards against malformed reflections.
  Skip if candidate_id is in do_not_promote.
  Skip if scope == "global_taste" (global scope not built in this release).
  Skip if suggested_level >= 3 (hard cap: Level 1–2 only).
  session_project → "project" collection; requires non-empty project_id.
  session_only    → "producer" collection.
  Unknown scope   → skip conservatively (counted under skipped_global_taste).

─── Bridge contract ───────────────────────────────────────────────────────────

  All writes are via bridge POST /memory — no direct ChromaDB calls.
  mode:       "INTERN_WRITE_SAFE"
  collection: "project" or "producer"
  metadata:   source_type="memory_promotion", memory_level, project_id,
              session_id, candidate_id

─── Idempotency ──────────────────────────────────────────────────────────────

  When write_log=True and dry_run=False:
    Each successfully written candidate_id is appended to write_log.jsonl.
    On subsequent runs the same candidate_id is skipped as "skipped_duplicate".
  When write_log=False (default):
    No idempotency ledger is maintained. Repeated runs may re-write the same
    candidate. The bridge's C3 corrective check deduplicates at read time.

─── Usage ─────────────────────────────────────────────────────────────────────

  python3 rag/memory_writer.py                            # dry-run preview
  python3 rag/memory_writer.py --no-dry-run               # live run (no log)
  python3 rag/memory_writer.py --no-dry-run --write-log   # live run + log
  python3 rag/memory_writer.py --json                     # JSON output

  from rag.memory_writer import write_promoted_memories
  result = write_promoted_memories(dry_run=True)
  result = write_promoted_memories(reflection=my_dict, dry_run=True)

─── Do-not-touch contract ────────────────────────────────────────────────────

  This module NEVER writes to:
    memory/feedback_log.jsonl
    memory/action_log.jsonl
    memory/action_proof_log.jsonl
    memory/knowledge_feedback_log.jsonl
    memory/context_pack_log.jsonl
    memory/promotion_candidates.jsonl
    memory/session_reflection_log.jsonl
    conductor-vault/producer/never_do_rules.md
    conductor-vault/producer/confirmed_preferences.md
    memory/chromadb/  (no direct ChromaDB — bridge only)
"""

import datetime
import json
import os
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Set

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MEMORY_DIR = os.path.join(_ROOT, "memory")

# ── Source: reflection log (read-only) ───────────────────────────────────────
DEFAULT_REFLECTION_PATH = os.path.join(_MEMORY_DIR, "session_reflection_log.jsonl")

# ── Optional write log (idempotency ledger when write_log=True) ───────────────
DEFAULT_WRITE_LOG_PATH = os.path.join(_MEMORY_DIR, "write_log.jsonl")

# ── Bridge defaults ───────────────────────────────────────────────────────────
DEFAULT_BRIDGE_URL = "http://localhost:4611"

# ── Hard caps — enforced unconditionally, never overrideable at call time ─────
_LEVEL_CAP   = 2
_SKIP_SCOPES = frozenset({"global_taste"})
_MODE        = "INTERN_WRITE_SAFE"

# ── Negative feedback types — never written, even if in accepted_signals ──────
# Hard gate independent of do_not_promote. Guards against malformed reflections
# where a negative signal was incorrectly placed in accepted_signals.
_NEGATIVE_FEEDBACK_TYPES = frozenset({
    "UNDO", "WRONG_DIRECTION", "NOT_HELPFUL", "WRONG", "OUTDATED",
})

# ── Scope → bridge collection short key ──────────────────────────────────────
_SCOPE_TO_COLLECTION: Dict[str, str] = {
    "session_project": "project",   # → project_session_index
    "session_only":    "producer",  # → producer_memory_index
}

# ── Guards — these paths are NEVER written to by this module ─────────────────
_NEVER_DO_PATH        = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")
_CONFIRMED_PREFS_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "confirmed_preferences.md")
_CHROMA_DIR           = os.path.join(_MEMORY_DIR, "chromadb")


# ── Public API ────────────────────────────────────────────────────────────────

def write_promoted_memories(
    reflection_path: Optional[str] = None,
    bridge_url: str = DEFAULT_BRIDGE_URL,
    dry_run: bool = True,
    write_log: bool = False,
    reflection: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Write accepted promotion candidates from a Build 19 reflection to ChromaDB
    via the bridge POST /memory endpoint.

    Args:
        reflection_path:  Path to session_reflection_log.jsonl. The last valid
                          record in the file is used. Ignored when `reflection`
                          is provided directly.
        bridge_url:       Bridge base URL. Default: http://localhost:4611.
        dry_run:          If True (default), no bridge calls and no log writes.
        write_log:        If True and not dry_run, append per-candidate records to
                          write_log.jsonl for idempotency across repeated runs.
        reflection:       Pass a reflection dict directly (overrides reflection_path).
                          Intended for testing and session-end hook use.

    Returns:
        {
            "written":                    int,   # candidates successfully sent to bridge
            "skipped_negative_feedback":  int,   # UNDO/WRONG_DIRECTION/NOT_HELPFUL/WRONG/OUTDATED
            "skipped_do_not_promote":     int,
            "skipped_global_taste":       int,   # includes unknown scope
            "skipped_level_cap":          int,
            "skipped_no_project_id":      int,   # session_project + empty project_id
            "skipped_duplicate":          int,   # already in write_log
            "failed_bridge":              int,   # bridge error (non-fatal)
            "dry_run":                    bool,
            "write_details":              list,  # per-candidate outcome
        }
    """
    rfl_path = reflection_path or DEFAULT_REFLECTION_PATH
    wl_path  = DEFAULT_WRITE_LOG_PATH

    # ── Load reflection ───────────────────────────────────────────────────────
    if reflection is None:
        reflection = _load_latest_reflection(rfl_path)
    if not reflection:
        return _empty_result(dry_run)

    accepted = reflection.get("accepted_signals", []) or []
    dnp_set: Set[str] = {
        (entry.get("candidate_id") or "")
        for entry in (reflection.get("do_not_promote", []) or [])
        if entry.get("candidate_id")
    }

    # ── Load already-written IDs for idempotency (only when write_log=True) ──
    already_written: Set[str] = _load_written_ids(wl_path) if write_log else set()

    # ── Counters ──────────────────────────────────────────────────────────────
    written                    = 0
    skipped_negative_feedback  = 0
    skipped_do_not_promote     = 0
    skipped_global_taste       = 0
    skipped_level_cap          = 0
    skipped_no_project_id      = 0
    skipped_duplicate          = 0
    failed_bridge              = 0
    write_details: List[Dict[str, Any]] = []

    # ── Process each accepted signal ──────────────────────────────────────────
    for sig in accepted:
        if not isinstance(sig, dict):
            continue

        candidate_id    = sig.get("candidate_id",    "") or ""
        scope           = sig.get("scope",           "") or ""
        suggested_level = int(sig.get("suggested_level", 1) or 1)
        project_id      = sig.get("project_id",      "") or ""
        session_id      = sig.get("session_id",      "") or ""
        evidence        = sig.get("evidence",        "") or ""
        action_type     = sig.get("action_type",     "") or ""
        target          = sig.get("target",          "") or ""
        message         = sig.get("message",         "") or ""
        feedback_type   = sig.get("feedback_type",   "") or ""

        detail: Dict[str, Any] = {
            "candidate_id": candidate_id,
            "scope":        scope,
        }

        # Gate 0 — negative feedback_type (hard guard, independent of do_not_promote)
        if feedback_type in _NEGATIVE_FEEDBACK_TYPES:
            skipped_negative_feedback += 1
            detail["outcome"] = "skipped_negative_feedback"
            write_details.append(detail)
            continue

        # Gate 1 — do_not_promote
        if candidate_id in dnp_set:
            skipped_do_not_promote += 1
            detail["outcome"] = "skipped_do_not_promote"
            write_details.append(detail)
            continue

        # Gate 2 — global_taste (never written in this build)
        if scope in _SKIP_SCOPES:
            skipped_global_taste += 1
            detail["outcome"] = "skipped_global_taste"
            write_details.append(detail)
            continue

        # Gate 3 — level cap (hard: Level 1–2 only)
        if suggested_level >= 3:
            skipped_level_cap += 1
            detail["outcome"] = "skipped_level_cap"
            write_details.append(detail)
            continue

        # Gate 4 — determine collection; unknown scope → skip conservatively
        collection = _SCOPE_TO_COLLECTION.get(scope)
        if collection is None:
            skipped_global_taste += 1
            detail["outcome"] = "skipped_unknown_scope"
            write_details.append(detail)
            continue

        # Gate 5 — session_project requires a non-empty project_id
        if scope == "session_project" and not project_id:
            skipped_no_project_id += 1
            detail["outcome"] = "skipped_no_project_id"
            write_details.append(detail)
            continue

        # Gate 6 — idempotency (only active when write_log=True)
        if candidate_id and candidate_id in already_written:
            skipped_duplicate += 1
            detail["outcome"] = "skipped_duplicate"
            write_details.append(detail)
            continue

        # ── Build bridge payload ──────────────────────────────────────────────
        safe_level = min(max(suggested_level, 1), _LEVEL_CAP)
        text       = _build_text(evidence, action_type, target, message, feedback_type)
        metadata: Dict[str, Any] = {
            "source_type":  "memory_promotion",
            "memory_level": safe_level,
        }
        if project_id:
            metadata["project_id"] = project_id
        if session_id:
            metadata["session_id"] = session_id
        if candidate_id:
            metadata["candidate_id"] = candidate_id

        payload = {
            "text":       text,
            "collection": collection,
            "mode":       _MODE,
            "metadata":   metadata,
        }

        detail["collection"] = collection
        detail["level"]      = safe_level
        detail["payload"]    = payload

        # ── dry_run guard ─────────────────────────────────────────────────────
        if dry_run:
            detail["outcome"] = "dry_run"
            write_details.append(detail)
            continue

        # ── Call bridge (non-fatal on failure) ────────────────────────────────
        ok, mem_id_or_err = _post_memory(bridge_url, payload)

        if ok:
            written += 1
            detail["outcome"] = "written"
            detail["mem_id"]  = mem_id_or_err
            if write_log and candidate_id:
                already_written.add(candidate_id)
                _append_write_log(wl_path, {
                    "candidate_id": candidate_id,
                    "mem_id":       mem_id_or_err,
                    "collection":   collection,
                    "scope":        scope,
                    "written_at":   _now_iso(),
                })
        else:
            failed_bridge += 1
            detail["outcome"] = "failed_bridge"
            detail["error"]   = mem_id_or_err

        write_details.append(detail)

    return {
        "written":                   written,
        "skipped_negative_feedback": skipped_negative_feedback,
        "skipped_do_not_promote":    skipped_do_not_promote,
        "skipped_global_taste":      skipped_global_taste,
        "skipped_level_cap":         skipped_level_cap,
        "skipped_no_project_id":     skipped_no_project_id,
        "skipped_duplicate":         skipped_duplicate,
        "failed_bridge":             failed_bridge,
        "dry_run":                   dry_run,
        "write_details":             write_details,
    }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _load_latest_reflection(path: str) -> Optional[Dict[str, Any]]:
    """Return the last valid JSON record from the reflection log, or None."""
    if not os.path.exists(path):
        return None
    last: Optional[Dict[str, Any]] = None
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        last = obj
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return last


def _load_written_ids(write_log_path: str) -> Set[str]:
    """Return set of candidate_ids already recorded in write_log.jsonl."""
    seen: Set[str] = set()
    if not os.path.exists(write_log_path):
        return seen
    try:
        with open(write_log_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        cid = obj.get("candidate_id") or ""
                        if cid:
                            seen.add(cid)
                except json.JSONDecodeError:
                    pass
    except OSError:
        pass
    return seen


def _append_write_log(write_log_path: str, record: dict) -> None:
    """Append a record to the write log. Never raises."""
    try:
        os.makedirs(os.path.dirname(write_log_path), exist_ok=True)
        with open(write_log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except Exception:
        pass


def _post_memory(bridge_url: str, payload: dict) -> tuple:
    """
    POST payload to bridge /memory.
    Returns (ok: bool, mem_id_or_error: str). Never raises.
    """
    url  = bridge_url.rstrip("/") + "/memory"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req  = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return bool(body.get("ok", False)), str(body.get("id", ""))
    except urllib.error.HTTPError as exc:
        try:
            err_body = exc.read().decode("utf-8")[:120]
        except Exception:
            err_body = ""
        return False, f"http_{exc.code}: {err_body}"
    except Exception as exc:
        return False, str(exc)[:120]


def _build_text(
    evidence: str,
    action_type: str,
    target: str,
    message: str,
    feedback_type: str,
) -> str:
    """Build the memory text from candidate fields."""
    if evidence:
        if message and message not in evidence:
            return evidence + " | note:" + message
        return evidence
    parts = []
    if action_type:
        parts.append("action:" + action_type)
    if target:
        parts.append("target:" + target)
    if message:
        parts.append("note:" + message)
    return " | ".join(parts) or ("feedback:" + feedback_type)


def _empty_result(dry_run: bool) -> Dict[str, Any]:
    return {
        "written":                   0,
        "skipped_negative_feedback": 0,
        "skipped_do_not_promote":    0,
        "skipped_global_taste":      0,
        "skipped_level_cap":         0,
        "skipped_no_project_id":     0,
        "skipped_duplicate":         0,
        "failed_bridge":             0,
        "dry_run":                   dry_run,
        "write_details":             [],
    }


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


# ── CLI output ────────────────────────────────────────────────────────────────

def _print_summary(result: Dict[str, Any]) -> None:
    mode = " [DRY RUN — no bridge calls]" if result["dry_run"] else ""
    print("=" * 56)
    print(f"Memory Writer v1{mode}")
    print("=" * 56)
    print(f"  Written                : {result['written']}")
    print(f"  Skipped (neg feedback) : {result['skipped_negative_feedback']}")
    print(f"  Skipped (do_not)       : {result['skipped_do_not_promote']}")
    print(f"  Skipped (global_taste) : {result['skipped_global_taste']}")
    print(f"  Skipped (level_cap)    : {result['skipped_level_cap']}")
    print(f"  Skipped (no project)   : {result['skipped_no_project_id']}")
    print(f"  Skipped (duplicate)    : {result['skipped_duplicate']}")
    print(f"  Bridge failures        : {result['failed_bridge']}")
    print("=" * 56)


# ── CLI entry ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Memory Writer v1 — write accepted promotion candidates to ChromaDB via bridge."
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Disable dry-run and make live bridge calls",
    )
    parser.add_argument(
        "--write-log",
        action="store_true",
        help="Append per-candidate records to write_log.jsonl for idempotency",
    )
    parser.add_argument(
        "--bridge-url",
        default=DEFAULT_BRIDGE_URL,
        help=f"Bridge base URL (default: {DEFAULT_BRIDGE_URL})",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    args = parser.parse_args()

    result = write_promoted_memories(
        bridge_url=args.bridge_url,
        dry_run=not args.no_dry_run,
        write_log=args.write_log,
    )

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _print_summary(result)
