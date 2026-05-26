"""
Conductor — Phase D Black Box Execution Log
────────────────────────────────────────────
Append-only JSONL audit log for every real Ableton write action.

CRITICAL SEPARATION:
    This log is SEPARATE from Phase C's context_pack_log.jsonl.
    - context_pack_log.jsonl  →  retrieval / inference debug trace (Phase C)
    - action_log.jsonl        →  action execution timeline         (Phase D)
    These two files MUST never be merged.  Phase D code must never write to
    context_pack_log.jsonl and Phase C code must never write to action_log.jsonl.

This log answers:
    - What did Conductor change in this session?
    - Did the change succeed / fail / get blocked?
    - Why does this track sound different?
    - What actions happened today?
    - Was any never-do rule triggered?

Raw events are NOT injected into Claude context by default.  They are an
offline audit trail for debugging, undo support (Phase D Slice 2), and user
trust ("what did you change?").

Log location: memory/action_log.jsonl  (relative to TEST-BUILD root)
Each line: one JSON object, newline-terminated (append-only).

Event types:
    ACTION_REQUESTED   — intent logged before preflight (may still be blocked)
    ACTION_VERIFIED    — completed with VERIFIED or ALREADY_CORRECT status
    ACTION_FAILED      — completed with FAILED status
    ACTION_UNVERIFIED  — completed with UNVERIFIED status
    NEVER_DO_BLOCKED   — action refused by never-do preflight

Thread-safe via module-level threading.Lock().
Best-effort: never raises.  Logging failure never breaks the execution path.
"""

import datetime
import json
import os
import threading

# ── CONFIG ────────────────────────────────────────────────────────────────────

_HERE        = os.path.dirname(os.path.abspath(__file__))
_ROOT        = os.path.dirname(_HERE)          # TEST-BUILD/
LOG_DIR      = os.path.join(_ROOT, "memory")
BBL_LOG_PATH = os.path.join(LOG_DIR, "action_log.jsonl")  # Phase D black box log

# Guard constant — used in tests to verify we never write here
_PHASE_C_LOG_NAME = "context_pack_log.jsonl"

_write_lock = threading.Lock()


# ── EVENT TYPE CONSTANTS ──────────────────────────────────────────────────────

ACTION_REQUESTED  = "ACTION_REQUESTED"
ACTION_VERIFIED   = "ACTION_VERIFIED"
ACTION_FAILED     = "ACTION_FAILED"
ACTION_UNVERIFIED = "ACTION_UNVERIFIED"
NEVER_DO_BLOCKED  = "NEVER_DO_BLOCKED"

ALL_EVENT_TYPES = frozenset({
    ACTION_REQUESTED, ACTION_VERIFIED, ACTION_FAILED,
    ACTION_UNVERIFIED, NEVER_DO_BLOCKED,
})


# ── PUBLIC API — low-level ────────────────────────────────────────────────────

def log_event(
    event_type: str,
    *,
    action_type:          str = "",
    target:               str = "",
    proof_id:             str = "",
    action_id:            str = "",
    request_id:           str = "",
    session_id:           str = "",
    verification_status:  str = "",
    error_code:           str = "",
    message:              str = "",
    **extra,
) -> None:
    """
    Append one event record to the Phase D black box log.
    Thread-safe.  Never raises.

    All keyword arguments are optional — include what you have.
    extra kwargs are merged into the record at the top level.
    """
    try:
        record = {
            "_type":               event_type,
            "timestamp":           _now_iso(),
            "action_type":         action_type,
            "target":              target,
            "proof_id":            proof_id,
            "action_id":           action_id,
            "request_id":          request_id,
            "session_id":          session_id,
            "verification_status": verification_status,
            "error_code":          error_code,
            "message":             message,
        }
        record.update(extra)
        _append(record)
    except Exception:
        pass


# ── PUBLIC API — convenience wrappers ────────────────────────────────────────

def log_requested(
    action_type: str,
    target: str,
    *,
    request_id: str = "",
    session_id: str = "",
    action_id:  str = "",
    **kw,
) -> None:
    """Log intent to execute an action (before preflight checks)."""
    log_event(
        ACTION_REQUESTED,
        action_type=action_type,
        target=target,
        request_id=request_id,
        session_id=session_id,
        action_id=action_id,
        **kw,
    )


def log_verified(
    action_type: str,
    target: str,
    proof_id: str,
    verification_status: str,
    *,
    request_id: str = "",
    **kw,
) -> None:
    """Log a completed action with VERIFIED or ALREADY_CORRECT status."""
    log_event(
        ACTION_VERIFIED,
        action_type=action_type,
        target=target,
        proof_id=proof_id,
        verification_status=verification_status,
        request_id=request_id,
        **kw,
    )


def log_failed(
    action_type: str,
    target: str,
    error_code: str,
    *,
    proof_id:   str = "",
    request_id: str = "",
    message:    str = "",
    **kw,
) -> None:
    """Log a completed action with FAILED status or an execution error."""
    log_event(
        ACTION_FAILED,
        action_type=action_type,
        target=target,
        error_code=error_code,
        proof_id=proof_id,
        request_id=request_id,
        message=message,
        **kw,
    )


def log_unverified(
    action_type: str,
    target: str,
    proof_id: str,
    *,
    request_id: str = "",
    **kw,
) -> None:
    """Log a completed action where readback was unavailable (UNVERIFIED)."""
    log_event(
        ACTION_UNVERIFIED,
        action_type=action_type,
        target=target,
        proof_id=proof_id,
        verification_status="UNVERIFIED",
        request_id=request_id,
        **kw,
    )


def log_never_do_blocked(
    action_type: str,
    target: str,
    decision: str,
    *,
    request_id: str = "",
    action_id:  str = "",
    session_id: str = "",
    rule_text:  str = "",
    **kw,
) -> None:
    """Log an action that was refused by never-do preflight.

    proof_id is intentionally absent — blocked actions never reach ActionProof.
    action_id and session_id are included for correlation with the request log.
    """
    log_event(
        NEVER_DO_BLOCKED,
        action_type=action_type,
        target=target,
        request_id=request_id,
        action_id=action_id,
        session_id=session_id,
        error_code="SECURITY_NEVER_DO_BLOCK",
        message=f"Blocked by never-do: {decision}. Rule: {rule_text}",
        **kw,
    )


# ── READER HELPERS ────────────────────────────────────────────────────────────

def read_last_event() -> "dict | None":
    """Return the last event record as a dict, or None if log is empty/missing."""
    try:
        if not os.path.exists(BBL_LOG_PATH):
            return None
        last = None
        with open(BBL_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    try:
                        last = json.loads(stripped)
                    except Exception:
                        pass
        return last
    except Exception:
        return None


def read_all_events() -> list:
    """Return all event records as a list of dicts.  Used by tests."""
    try:
        if not os.path.exists(BBL_LOG_PATH):
            return []
        records = []
        with open(BBL_LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                stripped = line.strip()
                if stripped:
                    try:
                        records.append(json.loads(stripped))
                    except Exception:
                        pass
        return records
    except Exception:
        return []


# ── INTERNALS ─────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(record: dict) -> None:
    """Append one JSON line to BBL_LOG_PATH.  Thread-safe.  Never raises."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
        with _write_lock:
            with open(BBL_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
