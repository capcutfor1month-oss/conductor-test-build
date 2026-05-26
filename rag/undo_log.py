"""
Conductor — Undo Log Skeleton (C5)
────────────────────────────────────
Append-only JSONL undo log for risky action tracking.

Scope (what this IS):
    - Infrastructure for logging pre-execution state before risky Ableton writes.
    - Blocking guard: raises UndoLogRequiredError if a UNDO_LOG_REQUIRED action
      is attempted without capturing prior_state first.
    - Status markers: mark_executed() and mark_failed() append outcome records.

Scope (what this IS NOT):
    - Full rollback engine — re-applying prior_state to Ableton (not built here).
    - Automatic undo on failure — that requires Ableton LOM integration.
    - Claim: do not claim full rollback is implemented.

Log location: memory/undo_log.jsonl  (relative to TEST-BUILD root)
Each line: one JSON object, newline-terminated (append-only — never modified).

API:
    create_undo_record(action_type, prior_state, **kwargs) → record_id : str
    mark_executed(record_id)  → None
    mark_failed(record_id, error) → None
    read_last_record()        → dict | None
    read_all_records()        → list[dict]
    UndoLogRequiredError      — raised when prior_state is missing for UNDO_LOG_REQUIRED

Thread-safe: module-level threading.Lock() wraps all file writes.
Never raises (except UndoLogRequiredError from create_undo_record).
"""

import datetime
import json
import os
import threading
import uuid

# ── CONFIG ────────────────────────────────────────────────────────────────────

_HERE    = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_HERE)           # TEST-BUILD/
LOG_DIR  = os.path.join(_ROOT, "memory")
LOG_PATH = os.path.join(LOG_DIR, "undo_log.jsonl")

_write_lock = threading.Lock()

# Protection levels that REQUIRE prior_state before any action is logged
_UNDO_REQUIRED_LEVELS = frozenset({"UNDO_LOG_REQUIRED"})


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class UndoLogRequiredError(ValueError):
    """
    Raised by create_undo_record() when:
        protection_level == "UNDO_LOG_REQUIRED"  AND  prior_state is None/empty.

    The calling code MUST capture current Ableton state (track list, routing,
    param values) and pass it as prior_state before calling create_undo_record().
    """
    pass


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def create_undo_record(
    action_type: str,
    prior_state: dict | None = None,
    **kwargs,
) -> str:
    """
    Write a pre-execution undo record (executed=False) before the action runs.

    Args:
        action_type:       e.g. "DELETE_TRACK", "ROUTE_BUS", "SET_PARAM"
        prior_state:       Snapshot of Ableton state captured BEFORE execution.
                           Required when protection_level="UNDO_LOG_REQUIRED".
                           Pass {} or None for non-UNDO_LOG_REQUIRED actions.
        **kwargs:          Optional metadata:
                           protection_level (str) — e.g. "UNDO_LOG_REQUIRED"
                           track_name (str), plugin_id (str), param_id (str), etc.

    Returns:
        record_id: short UUID string. Pass to mark_executed() or mark_failed().

    Raises:
        UndoLogRequiredError — if protection_level="UNDO_LOG_REQUIRED" and
                               prior_state is missing or empty.
    """
    protection = str(kwargs.pop("protection_level", "") or "")

    if protection in _UNDO_REQUIRED_LEVELS and not prior_state:
        raise UndoLogRequiredError(
            f"Action '{action_type}' has protection_level='{protection}'. "
            "prior_state is required — capture current Ableton state before "
            "calling create_undo_record()."
        )

    record_id = uuid.uuid4().hex[:12]
    record = {
        "_type":           "pre_action",
        "record_id":       record_id,
        "timestamp":       _now_iso(),
        "action_type":     str(action_type),
        "protection_level": protection,
        "prior_state":     prior_state or {},
        "executed":        False,
        "failed":          False,
        "error":           "",
    }
    # Merge any extra kwargs (track_name, plugin_id, etc.)
    for k, v in kwargs.items():
        record[k] = v

    _append_record(record)
    return record_id


def mark_executed(record_id: str) -> None:
    """
    Append an execution-confirmed outcome record.
    Append-only — does NOT modify the original pre_action record.
    Never raises.
    """
    try:
        _append_record({
            "_type":     "executed",
            "record_id": str(record_id),
            "timestamp": _now_iso(),
            "executed":  True,
            "failed":    False,
        })
    except Exception:
        pass


def mark_failed(record_id: str, error: str) -> None:
    """
    Append a failure outcome record.
    Append-only — does NOT modify the original pre_action record.
    Never raises.
    """
    try:
        _append_record({
            "_type":     "failed",
            "record_id": str(record_id),
            "timestamp": _now_iso(),
            "executed":  False,
            "failed":    True,
            "error":     str(error)[:400],
        })
    except Exception:
        pass


# ── READER HELPERS (tests / CLI) ──────────────────────────────────────────────

def read_last_record() -> dict | None:
    """Return the last JSONL record, or None if log is empty or missing."""
    try:
        if not os.path.exists(LOG_PATH):
            return None
        last = None
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        last = json.loads(line)
                    except Exception:
                        pass
        return last
    except Exception:
        return None


def read_all_records() -> list:
    """Return all JSONL records as a list. Used by tests."""
    try:
        if not os.path.exists(LOG_PATH):
            return []
        records = []
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        return records
    except Exception:
        return []


# ── INTERNALS ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_record(record: dict) -> None:
    """Append one JSON line. Thread-safe."""
    os.makedirs(LOG_DIR, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _write_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
