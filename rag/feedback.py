"""
Conductor — Feedback Module (Phase D Slice 3)
─────────────────────────────────────────────
User feedback on completed Ableton write actions.

Slice 3 scope: store feedback linked to a proof or action. Nothing more.

This module does NOT:
  - Write to ChromaDB
  - Modify ActionProof records
  - Promote memories to Phase C retrieval
  - Trigger compensating undo
  - Touch Phase C context_pack_log.jsonl

All of that is deferred to Slice 4 (memory promotion from feedback).

Log: memory/feedback_log.jsonl  — append-only, separate from all other logs.

    context_pack_log.jsonl  →  Phase C retrieval debug  (never touched here)
    action_proof_log.jsonl  →  Phase D write proofs
    action_log.jsonl        →  Phase D execution timeline
    feedback_log.jsonl      →  Phase D user feedback      (this module)

Allowed feedback types:
    KEEP            — action was correct, result should stay
    UNDO            — action was wrong, should be reverted
    TOO_MUCH        — direction correct, magnitude too large
    NOT_ENOUGH      — direction correct, magnitude too small
    WRONG_DIRECTION — completely wrong direction

Validation contract:
    - At least one of proof_id or action_id must be non-empty
    - proof_id, if supplied, must exist in action_proof_log.jsonl
    - action_id, if supplied and no proof_id, must exist in
      action_log.jsonl or action_proof_log.jsonl
    - feedback_type must be one of FeedbackType values (case-insensitive)
    - promotion_eligible is always False in Slice 3

API:
    create_feedback(feedback_type, *, proof_id, action_id, ...) → FeedbackRecord
    read_last_feedback()  → dict | None
    read_all_feedback()   → list[dict]
    FeedbackType          — enum: KEEP | UNDO | TOO_MUCH | NOT_ENOUGH | WRONG_DIRECTION
    FeedbackValidationError — raised on bad input; carries .bridge_error_code

Thread-safe via module-level threading.Lock().
_append_feedback() never raises — write failures are silently swallowed.
"""

import dataclasses
import datetime
import json
import os
import threading
import uuid
from enum import Enum
from typing import Optional

from rag.action_proof import read_all_proofs, PROOF_LOG_PATH
from rag.black_box_log import read_all_events, BBL_LOG_PATH
from rag.bridge_errors import BridgeErrorCode

# ── CONFIG ────────────────────────────────────────────────────────────────────

_HERE             = os.path.dirname(os.path.abspath(__file__))
_ROOT             = os.path.dirname(_HERE)           # TEST-BUILD/
LOG_DIR           = os.path.join(_ROOT, "memory")
FEEDBACK_LOG_PATH = os.path.join(LOG_DIR, "feedback_log.jsonl")

# Guard constants — used in tests to verify log separation
_PROOF_LOG_NAME   = os.path.basename(PROOF_LOG_PATH)      # "action_proof_log.jsonl"
_BBL_LOG_NAME     = os.path.basename(BBL_LOG_PATH)        # "action_log.jsonl"
_PHASE_C_LOG_NAME = "context_pack_log.jsonl"

_write_lock = threading.Lock()


# ── FEEDBACK TYPE ENUM ────────────────────────────────────────────────────────

class FeedbackType(str, Enum):
    KEEP            = "KEEP"             # result is correct — keep it
    UNDO            = "UNDO"             # result is wrong — should be reverted
    TOO_MUCH        = "TOO_MUCH"         # direction right, magnitude too large
    NOT_ENOUGH      = "NOT_ENOUGH"       # direction right, magnitude too small
    WRONG_DIRECTION = "WRONG_DIRECTION"  # completely opposite of intended

ALLOWED_FEEDBACK_TYPES: frozenset = frozenset(ft.value for ft in FeedbackType)


# ── EXCEPTIONS ─────────────────────────────────────────────────────────────────

class FeedbackValidationError(Exception):
    """
    Raised when feedback cannot be stored due to a validation failure.

    Callers should catch this, use .bridge_error_code to form a structured
    error_response(), and return HTTP 400.

    Covers:
        FEEDBACK_NO_REFERENCE     — neither proof_id nor action_id supplied
        FEEDBACK_INVALID_TYPE     — feedback_type not in ALLOWED_FEEDBACK_TYPES
        FEEDBACK_PROOF_NOT_FOUND  — supplied proof_id not in action_proof_log
        FEEDBACK_ACTION_NOT_FOUND — supplied action_id not found in any log
    """
    def __init__(self, message: str, bridge_error_code: "BridgeErrorCode"):
        super().__init__(message)
        self.bridge_error_code = bridge_error_code


# ── DATACLASS ─────────────────────────────────────────────────────────────────

@dataclasses.dataclass
class FeedbackRecord:
    """
    One user feedback event linked to a prior write action.

    All fields serialise to JSONL as plain strings/bools.

    feedback_id                   — unique 16-char hex
    proof_id                      — ActionProof ID (resolved from log)
    action_id                     — action ID (from proof or action_log)
    request_id                    — caller request correlation ID (or "")
    session_id                    — bridge session ID (or "")
    project_id                    — project name (or "")
    feedback_type                 — FeedbackType value string
    timestamp                     — ISO 8601 UTC
    verification_status_at_feedback — vstat from the referenced proof (or "")
    promotion_eligible            — False in Slice 3; set True by Slice 4
    message                       — optional human note (or "")
    """
    feedback_id:                    str
    proof_id:                       str
    action_id:                      str
    request_id:                     str
    session_id:                     str
    project_id:                     str
    feedback_type:                  str
    timestamp:                      str
    verification_status_at_feedback: str
    promotion_eligible:             bool
    message:                        str

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def create_feedback(
    feedback_type: str,
    *,
    proof_id:   str = "",
    action_id:  str = "",
    request_id: str = "",
    session_id: str = "",
    project_id: str = "",
    message:    str = "",
) -> FeedbackRecord:
    """
    Validate input and persist one FeedbackRecord to feedback_log.jsonl.

    Args:
        feedback_type:  One of KEEP | UNDO | TOO_MUCH | NOT_ENOUGH | WRONG_DIRECTION.
                        Case-insensitive.
        proof_id:       ActionProof ID from action_proof_log.jsonl.  At least one
                        of proof_id or action_id must be non-empty.
        action_id:      Action ID from action_log.jsonl or action_proof_log.jsonl.
        request_id:     Bridge request correlation ID (optional).
        session_id:     Bridge session ID (optional).
        project_id:     Project name (optional).
        message:        Human-readable note (optional).

    Returns:
        FeedbackRecord written to feedback_log.jsonl.

    Raises:
        FeedbackValidationError if:
            - Neither proof_id nor action_id is non-empty
            - feedback_type is not in ALLOWED_FEEDBACK_TYPES
            - proof_id supplied but not found in action_proof_log.jsonl
            - action_id supplied (no proof_id) but not found in any log
    """
    # ── 1. Validate feedback_type ─────────────────────────────────────────────
    ft_norm = str(feedback_type).upper().strip()
    if ft_norm not in ALLOWED_FEEDBACK_TYPES:
        raise FeedbackValidationError(
            f"Invalid feedback_type {feedback_type!r}. "
            f"Allowed values: {sorted(ALLOWED_FEEDBACK_TYPES)}",
            bridge_error_code=BridgeErrorCode.FEEDBACK_INVALID_TYPE,
        )

    # ── 2. Require at least one reference ────────────────────────────────────
    proof_id  = str(proof_id  or "").strip()
    action_id = str(action_id or "").strip()

    if not proof_id and not action_id:
        raise FeedbackValidationError(
            "At least one of proof_id or action_id must be provided. "
            "Both were empty or missing.",
            bridge_error_code=BridgeErrorCode.FEEDBACK_NO_REFERENCE,
        )

    # ── 3. Look up reference — extract verification_status ───────────────────
    vstat_at_feedback    = ""
    resolved_proof_id    = proof_id
    resolved_action_id   = action_id

    if proof_id:
        matched_proof = _find_proof_by_id(proof_id)
        if matched_proof is None:
            raise FeedbackValidationError(
                f"proof_id {proof_id!r} not found in action_proof_log.jsonl. "
                "Cannot attach feedback to a non-existent proof. "
                "Check that the action completed before submitting feedback.",
                bridge_error_code=BridgeErrorCode.FEEDBACK_PROOF_NOT_FOUND,
            )
        vstat_at_feedback = matched_proof.get("verification_status", "")
        # Pull action_id from proof record if caller didn't supply one
        if not resolved_action_id:
            resolved_action_id = matched_proof.get("action_id", "")

    else:
        # action_id only — search action_log first, then proof log
        matched_event = _find_event_by_action_id(action_id)
        if matched_event is not None:
            vstat_at_feedback = matched_event.get("verification_status", "")
            # Try to also link to a proof if one exists for this action
            matched_proof = _find_proof_by_action_id(action_id)
            if matched_proof:
                resolved_proof_id = matched_proof.get("proof_id", "")
                if not vstat_at_feedback:
                    vstat_at_feedback = matched_proof.get("verification_status", "")
        else:
            # Not in action_log — try proof log by action_id
            matched_proof = _find_proof_by_action_id(action_id)
            if matched_proof is None:
                raise FeedbackValidationError(
                    f"action_id {action_id!r} not found in action_log.jsonl "
                    "or action_proof_log.jsonl. "
                    "Cannot attach feedback to an unknown action.",
                    bridge_error_code=BridgeErrorCode.FEEDBACK_ACTION_NOT_FOUND,
                )
            vstat_at_feedback  = matched_proof.get("verification_status", "")
            resolved_proof_id  = matched_proof.get("proof_id", "")

    # ── 4. Build and persist ──────────────────────────────────────────────────
    record = FeedbackRecord(
        feedback_id                     = uuid.uuid4().hex[:16],
        proof_id                        = resolved_proof_id,
        action_id                       = resolved_action_id,
        request_id                      = str(request_id  or ""),
        session_id                      = str(session_id  or ""),
        project_id                      = str(project_id  or ""),
        feedback_type                   = ft_norm,
        timestamp                       = _now_iso(),
        verification_status_at_feedback = vstat_at_feedback,
        promotion_eligible              = False,   # always False in Slice 3
        message                         = str(message or ""),
    )
    _append_feedback(record)
    return record


def read_last_feedback() -> "Optional[dict]":
    """Return the last feedback record as a dict, or None if log is empty/missing."""
    try:
        if not os.path.exists(FEEDBACK_LOG_PATH):
            return None
        last = None
        with open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as f:
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


def read_all_feedback() -> list:
    """Return all feedback records as a list of dicts. Used by tests."""
    try:
        if not os.path.exists(FEEDBACK_LOG_PATH):
            return []
        records = []
        with open(FEEDBACK_LOG_PATH, "r", encoding="utf-8") as f:
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

def _find_proof_by_id(proof_id: str) -> "Optional[dict]":
    """Search action_proof_log.jsonl for a matching proof_id. Returns dict or None."""
    try:
        for p in read_all_proofs():
            if p.get("proof_id") == proof_id:
                return p
    except Exception:
        pass
    return None


def _find_proof_by_action_id(action_id: str) -> "Optional[dict]":
    """Search action_proof_log.jsonl for a record whose action_id matches."""
    try:
        for p in read_all_proofs():
            if p.get("action_id") == action_id:
                return p
    except Exception:
        pass
    return None


def _find_event_by_action_id(action_id: str) -> "Optional[dict]":
    """Search action_log.jsonl for a matching action_id. Returns dict or None."""
    try:
        for e in read_all_events():
            if e.get("action_id") == action_id:
                return e
    except Exception:
        pass
    return None


def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _append_feedback(record: FeedbackRecord) -> None:
    """Append one JSON line to FEEDBACK_LOG_PATH. Thread-safe. Never raises."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        line = json.dumps(record.to_dict(), ensure_ascii=False, default=str) + "\n"
        with _write_lock:
            with open(FEEDBACK_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(line)
    except Exception:
        pass
