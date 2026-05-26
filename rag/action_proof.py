"""
Conductor — ActionProof v1 (Phase D Slice 1)
────────────────────────────────────────────
ActionProof is the execution truth record for every Ableton write action.

Design rules:
  - One proof per write action, written AFTER verification_status is determined.
  - Append-only JSONL. No record modification after write.
  - Never say "done" to the user unless verification_status is VERIFIED or
    ALREADY_CORRECT.  The caller is responsible for checking the status before
    forming the user-facing response.
  - undo_eligible is True only when before_state was captured successfully AND
    the action type supports compensating undo.  Set by the caller.
  - This file contains NO Ableton LOM code and NO bridge logic.  Pure data +
    storage only.

Log location: memory/action_proof_log.jsonl  (relative to TEST-BUILD root)
Each line: one JSON object, newline-terminated (append-only — never modified).

Separate from Phase C context_pack_log.jsonl:
  - context_pack_log.jsonl  → retrieval / inference debug trace  (Phase C)
  - action_proof_log.jsonl  → execution truth record             (Phase D)

API:
    create_proof(action_type, target, ...) → ActionProof
    read_last_proof()  → dict | None
    read_all_proofs()  → list[dict]
    VerificationStatus — enum: VERIFIED | ALREADY_CORRECT | FAILED |
                               UNVERIFIED | PARTIAL

Thread-safe via module-level threading.Lock().
_append_proof() never raises — if the write fails, the proof object is still
returned so the caller can respond to the user.
"""

import dataclasses
import datetime
import json
import os
import threading
import uuid
from enum import Enum

# ── CONFIG ────────────────────────────────────────────────────────────────────

_HERE         = os.path.dirname(os.path.abspath(__file__))
_ROOT         = os.path.dirname(_HERE)          # TEST-BUILD/
LOG_DIR       = os.path.join(_ROOT, "memory")
PROOF_LOG_PATH = os.path.join(LOG_DIR, "action_proof_log.jsonl")

_write_lock = threading.Lock()


# ── ENUMS ─────────────────────────────────────────────────────────────────────

class VerificationStatus(str, Enum):
    VERIFIED        = "VERIFIED"         # readback matches intended value
    ALREADY_CORRECT = "ALREADY_CORRECT"  # value was already at intended — no write needed
    FAILED          = "FAILED"           # readback differs from intended, or write errored
    UNVERIFIED      = "UNVERIFIED"       # readback not supported for this target type
    PARTIAL         = "PARTIAL"          # some targets verified, some not (future: batch)


# ── DATACLASS ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class ActionProof:
    """
    Execution truth record for one Ableton write action.

    All 14 fields are required by the Phase D spec.  Every field is populated
    at proof-creation time — no nullable/optional fields in the serialised record.

    proof_id            — unique ID for this proof record (16-char hex UUID)
    action_id           — caller-assigned or auto-generated action ID
    request_id          — bridge request ID for correlation with Phase C audit log
    session_id          — bridge session UUID (set once at bridge startup)
    project_id          — Ableton project name / ID (empty string if unknown)
    timestamp           — ISO 8601 UTC (YYYY-MM-DDTHH:MM:SSZ)
    action_type         — canonical action name, e.g. "SET_TRACK_VOLUME"
    target              — what was targeted, e.g. "track:Kick" or "track:0"
    intended_value      — the value the caller wanted to set
    before_state        — dict snapshot captured BEFORE execution;
                          {} if capture failed (undo_eligible will be False)
    after_state         — dict snapshot captured AFTER execution;
                          {} if UNVERIFIED or write failed before readback
    verification_status — VerificationStatus value string
    undo_eligible       — True if before_state was captured and action is reversible
    user_facing_summary — plain English: what happened and whether it succeeded
    """
    proof_id:            str
    action_id:           str
    request_id:          str
    session_id:          str
    project_id:          str
    timestamp:           str
    action_type:         str
    target:              str
    intended_value:      object   # float / str / dict — serialised via default=str
    before_state:        dict
    after_state:         dict
    verification_status: str      # VerificationStatus string value
    undo_eligible:       bool
    user_facing_summary: str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def create_proof(
    action_type: str,
    target: str,
    intended_value,
    before_state: dict,
    after_state: dict,
    verification_status: str,
    undo_eligible: bool,
    user_facing_summary: str,
    *,
    action_id:  str = "",
    request_id: str = "",
    session_id: str = "",
    project_id: str = "",
) -> ActionProof:
    """
    Create and persist one ActionProof.

    Assigns a new proof_id (random 16-char hex).
    Writes to PROOF_LOG_PATH (append-only JSONL).  Thread-safe.
    Never raises — write failures are silently swallowed so the caller
    can still return a response to the user.

    Returns the ActionProof object regardless of whether the write succeeded.
    """
    proof = ActionProof(
        proof_id            = uuid.uuid4().hex[:16],
        action_id           = action_id  or uuid.uuid4().hex[:12],
        request_id          = request_id or "",
        session_id          = session_id or "",
        project_id          = project_id or "",
        timestamp           = _now_iso(),
        action_type         = str(action_type),
        target              = str(target),
        intended_value      = intended_value,
        before_state        = before_state  if isinstance(before_state,  dict) else {},
        after_state         = after_state   if isinstance(after_state,   dict) else {},
        verification_status = _coerce_str(verification_status),
        undo_eligible       = bool(undo_eligible),
        user_facing_summary = str(user_facing_summary),
    )
    _append_proof(proof)
    return proof


def read_last_proof() -> "dict | None":
    """Return the last proof record as a dict, or None if log is empty/missing."""
    try:
        if not os.path.exists(PROOF_LOG_PATH):
            return None
        last = None
        with open(PROOF_LOG_PATH, "r", encoding="utf-8") as f:
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


def read_all_proofs() -> list:
    """Return all proof records as a list of dicts.  Used by tests and diagnostics."""
    try:
        if not os.path.exists(PROOF_LOG_PATH):
            return []
        records = []
        with open(PROOF_LOG_PATH, "r", encoding="utf-8") as f:
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

def _coerce_str(v) -> str:
    """
    Extract the plain string value from an Enum or str.
    Works on Python 3.10 where str(SomeStrEnum.X) returns 'SomeStrEnum.X'
    instead of just 'X'.  Using .value is safe across all Python 3.x versions.
    """
    return v.value if hasattr(v, "value") else str(v)


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_proof(proof: ActionProof) -> None:
    """Append one JSON line to PROOF_LOG_PATH.  Thread-safe.  Never raises."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = json.dumps(proof.to_dict(), ensure_ascii=False, default=str) + "\n"
        with _write_lock:
            with open(PROOF_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
