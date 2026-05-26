"""
Conductor — Structured Bridge Error Codes (Phase D Slice 1 + Slice 3)
──────────────────────────────────────────────────────────────────────
Canonical error code constants for the bridge and Phase D execution pipeline.

Structured errors replace generic {"error": "string"} responses on action
endpoints so the UI and logs can handle each failure type distinctly.

Usage in bridge:
    from rag.bridge_errors import BridgeErrorCode, error_response, ok_response

    return self._send_json(
        error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                       f"Track '{name}' not found",
                       request_id=request_id),
        404,
    )

    return self._send_json(
        ok_response(proof.proof_id, str(vstat),
                    before_state=..., after_state=...,
                    request_id=request_id),
    )
"""

from enum import Enum


# ── ERROR CODE ENUM ───────────────────────────────────────────────────────────

class BridgeErrorCode(str, Enum):
    # Transport / connectivity
    BRIDGE_TIMEOUT              = "BRIDGE_TIMEOUT"

    # Readback
    BRIDGE_READBACK_UNAVAILABLE = "BRIDGE_READBACK_UNAVAILABLE"

    # Parameter validation
    BRIDGE_PARAM_OUT_OF_RANGE   = "BRIDGE_PARAM_OUT_OF_RANGE"

    # Object not found in Ableton session
    BRIDGE_TRACK_ABSENT         = "BRIDGE_TRACK_ABSENT"
    BRIDGE_PLUGIN_ABSENT        = "BRIDGE_PLUGIN_ABSENT"

    # State verification
    STATE_VERIFICATION_FAILED   = "STATE_VERIFICATION_FAILED"
    STATE_CAPTURE_FAILED        = "STATE_CAPTURE_FAILED"
    STATE_DRIFT_COLLISION       = "STATE_DRIFT_COLLISION"   # reserved for Slice 2 undo

    # Security / never-do
    SECURITY_NEVER_DO_BLOCK          = "SECURITY_NEVER_DO_BLOCK"
    SECURITY_CONFIRMATION_REQUIRED   = "SECURITY_CONFIRMATION_REQUIRED"
    SECURITY_CLARIFY_REQUIRED        = "SECURITY_CLARIFY_REQUIRED"

    # Feedback (Phase D Slice 3)
    FEEDBACK_INVALID_TYPE       = "FEEDBACK_INVALID_TYPE"
    FEEDBACK_NO_REFERENCE       = "FEEDBACK_NO_REFERENCE"
    FEEDBACK_PROOF_NOT_FOUND    = "FEEDBACK_PROOF_NOT_FOUND"
    FEEDBACK_ACTION_NOT_FOUND   = "FEEDBACK_ACTION_NOT_FOUND"

    # Undo (Phase D Slice 4)
    UNDO_PROOF_NOT_FOUND        = "UNDO_PROOF_NOT_FOUND"        # proof/action_id not in log
    UNDO_NOT_ELIGIBLE           = "UNDO_NOT_ELIGIBLE"           # vstat is FAILED/UNVERIFIED
    UNDO_UNSUPPORTED_ACTION     = "UNDO_UNSUPPORTED_ACTION"     # action_type not undoable
    UNDO_NO_BEFORE_STATE        = "UNDO_NO_BEFORE_STATE"        # before_state empty/missing key
    UNDO_NO_AFTER_STATE         = "UNDO_NO_AFTER_STATE"         # after_state empty/missing key — no drift baseline
    UNDO_DRIFT_READ_UNAVAILABLE = "UNDO_DRIFT_READ_UNAVAILABLE" # live state unreadable before undo write
    # Drift uses STATE_DRIFT_COLLISION (already defined above)


# ── RESPONSE HELPERS ──────────────────────────────────────────────────────────

def error_response(code: "BridgeErrorCode | str", message: str, **extra) -> dict:
    """
    Return a structured error dict for passing to _send_json().

    Always sets ok=False, error_code (canonical string), error (human message).
    Caller may pass request_id, action_id, proof_id, verification_status, etc.
    as extra kwargs — they are merged into the top-level response dict.

    Example:
        error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                       "Track 'Kick' not found",
                       request_id="req_abc")
        →  {"ok": False, "error_code": "BRIDGE_TRACK_ABSENT",
            "error": "Track 'Kick' not found", "request_id": "req_abc"}
    """
    return {
        "ok":         False,
        "error_code": code.value if hasattr(code, "value") else str(code),
        "error":      message,
        **extra,
    }


def ok_response(proof_id: str, verification_status: str, **extra) -> dict:
    """
    Return a structured success dict for a completed action.

    ok=True ONLY when verification_status is VERIFIED or ALREADY_CORRECT.
    For FAILED, UNVERIFIED, PARTIAL — ok=False so the caller never tells the
    user "done" unless the action is actually confirmed.

    Caller should pass before_state, after_state, undo_eligible,
    user_facing_summary, request_id, action_id, etc. as extra kwargs.
    """
    is_confirmed = verification_status in ("VERIFIED", "ALREADY_CORRECT")
    return {
        "ok":                  is_confirmed,
        "proof_id":            proof_id,
        "verification_status": verification_status,
        **extra,
    }
