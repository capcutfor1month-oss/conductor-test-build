"""
Conductor — Compensating Undo Engine (Phase D Slice 4)
───────────────────────────────────────────────────────
Compensating undo for the four supported scalar/boolean track actions.

Slice 4 scope — supported action types only:
    SET_TRACK_VOLUME   → restore before_state["volume"]  (scalar, normalized)
    SET_TRACK_PAN      → restore before_state["pan"]     (scalar, normalized)
    SET_TRACK_MUTE     → restore before_state["mute"]    (bool)
    SET_TRACK_SOLO     → restore before_state["solo"]    (bool)

Not supported (deferred):
    Batch undo, routing undo, master bus, plugin params, preset restore,
    native Ableton undo (Song.undo()), VST3 gestures, Phase C changes,
    undo-of-undo.

Drift detection (three gates, in order):

    Gate 1 — UNDO_NO_AFTER_STATE (step 1, UndoValidationError):
        after_state[state_key] must be present in the original proof.
        Without it there is no baseline for drift comparison.
        confirm=True does NOT bypass this gate.

    Gate 2 — UNDO_DRIFT_READ_UNAVAILABLE (step 3, return dict):
        Current live state must be readable before any write is attempted.
        If the executor returns None, undo is blocked immediately.
        confirm=True does NOT bypass this gate.

    Gate 3 — STATE_DRIFT_COLLISION (step 4, return dict):
        Current live value differs from the original after_state beyond
        tolerance. Undo is blocked unless confirm=True is passed.
        confirm=True bypasses ONLY this gate.

New ActionProof:
    Each undo creates a NEW proof:
        action_type = "UNDO_{original_type}"  (e.g. "UNDO_SET_TRACK_VOLUME")
        undo_eligible = False                 (no undo-of-undo)
    The original proof is NEVER modified — append-only log invariant.

Tolerances:
    Scalars (volume, pan): DEFAULT_VOLUME_TOLERANCE = 0.005 normalized
    Booleans (mute, solo): exact match, no tolerance

Executor protocol (same as readback.py — DI-friendly, mock-able in tests):
    executor(code: str) → {"ok": bool, "data": dict, "error": str|None}

API:
    execute_undo(proof, executor, *, confirm, ...) → dict
    UndoValidationError  — raised on ineligible proof; carries .bridge_error_code
    UNDOABLE_ACTION_TYPES — frozenset of supported action_type strings
"""

from typing import Callable, Optional

from rag.action_proof  import create_proof, VerificationStatus
from rag.black_box_log import log_event, ACTION_VERIFIED, ACTION_FAILED
from rag.bridge_errors import BridgeErrorCode
from rag.readback      import (
    verify_track_volume,
    verify_track_pan,
    verify_track_mute,
    verify_track_solo,
    verify_track_arm,
    verify_track_monitor,
    verify_track_color,
    verify_track_send,
    verify_track_route,
    verify_transport_loop,
    verify_transport_metronome,
    verify_plugin_bypass,
    _read_volume,
    _read_pan,
    _read_bool_property,
    _read_integer_property,
    _read_send_value,
    _read_route_name,
    _read_song_bool,
    _read_plugin_bypass,
    DEFAULT_STABILIZATION_DELAY,
    DEFAULT_VOLUME_TOLERANCE,
)


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

UNDOABLE_ACTION_TYPES: frozenset = frozenset({
    "SET_TRACK_VOLUME",
    "SET_TRACK_PAN",
    "SET_TRACK_MUTE",
    "SET_TRACK_SOLO",
    # Action Expansion Slice 1:
    "ARM_TRACK",          # boolean — restore before arm state
    "SET_TRACK_MONITOR",  # integer (0/1/2) — restore before monitor mode
    "SET_TRACK_COLOR",    # integer (0xRRGGBB) — restore before color
    # Action Expansion Slice 2:
    "SET_TRACK_SEND",     # float (0.0–1.0) — restore before send level
    "SET_TRACK_ROUTE",    # string (display name) — restore before output routing
    "TRANSPORT_LOOP",     # song bool — restore before loop state
    "TRANSPORT_METRONOME", # song bool — restore before metronome state
    # Action Expansion Slice 3A:
    "PLUGIN_BYPASS",      # device bool — restore before is_active state
})

# State dict key per action type
_ACTION_STATE_KEY: dict = {
    "SET_TRACK_VOLUME":    "volume",
    "SET_TRACK_PAN":       "pan",
    "SET_TRACK_MUTE":      "mute",
    "SET_TRACK_SOLO":      "solo",
    "ARM_TRACK":           "arm",
    "SET_TRACK_MONITOR":   "monitor",
    "SET_TRACK_COLOR":     "color",
    # Slice 2:
    "SET_TRACK_SEND":      "send_value",
    "SET_TRACK_ROUTE":     "routing",
    "TRANSPORT_LOOP":      "loop",
    "TRANSPORT_METRONOME": "metronome",
    # Slice 3A:
    "PLUGIN_BYPASS":       "is_active",
}

# Action types where the state is an integer (not float scalar, not boolean)
# Drift detection for these uses exact integer comparison
_INTEGER_ACTION_TYPES: frozenset = frozenset({
    "SET_TRACK_MONITOR",
    "SET_TRACK_COLOR",
})

# LOM property name for each integer action type — used in drift detection
_INTEGER_LOM_PROP: dict = {
    "SET_TRACK_MONITOR": "current_monitoring_state",
    "SET_TRACK_COLOR":   "color",
}

# Action Expansion Slice 2 — new undo categories

# String comparison (output routing display name)
_STRING_ACTION_TYPES: frozenset = frozenset({
    "SET_TRACK_ROUTE",
})

# Song-level boolean (no track_id needed)
_SONG_BOOL_ACTION_TYPES: frozenset = frozenset({
    "TRANSPORT_LOOP",
    "TRANSPORT_METRONOME",
})

# LOM property name for song-bool types — used in drift detection
_SONG_BOOL_LOM_PROP: dict = {
    "TRANSPORT_LOOP":      "loop",
    "TRANSPORT_METRONOME": "metronome",
}

# Float send (track_id + send_idx encoded in target)
_FLOAT_SEND_ACTION_TYPES: frozenset = frozenset({
    "SET_TRACK_SEND",
})

# Plugin bypass (track_id + device_name encoded in target)
_PLUGIN_BYPASS_ACTION_TYPES: frozenset = frozenset({
    "PLUGIN_BYPASS",
})

# Drift tolerance for scalars — matches readback default
_SCALAR_TOLERANCE: float = DEFAULT_VOLUME_TOLERANCE   # 0.005


# ── EXCEPTIONS ────────────────────────────────────────────────────────────────

class UndoValidationError(Exception):
    """
    Raised when a proof is not eligible for undo (before any write is attempted).

    .bridge_error_code carries the specific BridgeErrorCode for a structured
    error_response() call.

    Covers:
        UNDO_NOT_ELIGIBLE       — proof is FAILED/UNVERIFIED; undoing unconfirmed
                                  state would restore something that was never reliably set.
        UNDO_UNSUPPORTED_ACTION — action_type not in UNDOABLE_ACTION_TYPES.
        UNDO_NO_BEFORE_STATE    — before_state is empty or missing the required key;
                                  cannot restore without a captured before-value.
    """
    def __init__(self, message: str, bridge_error_code: "BridgeErrorCode"):
        super().__init__(message)
        self.bridge_error_code = bridge_error_code


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def execute_undo(
    proof: dict,
    executor: Callable,
    *,
    confirm:             bool  = False,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
    request_id:          str   = "",
    session_id:          str   = "",
    project_id:          str   = "",
    action_id:           str   = "",
) -> dict:
    """
    Execute a compensating undo for a single verified track action.

    Args:
        proof:               Original ActionProof dict (from read_all_proofs()).
                             Must have verification_status VERIFIED or ALREADY_CORRECT,
                             a recognised action_type, and a populated before_state.
        executor:            ableton_execute-compatible callable.
                             Protocol: executor(code: str) → {"ok": bool, "data": dict, ...}
        confirm:             If True, proceed with the undo write even when drift
                             is detected.  Defaults to False (drift blocks undo).
        stabilization_delay: Seconds to wait after the undo write before readback.
                             Pass 0 in tests.
        request_id:          Correlation ID for the undo request.
        session_id:          Bridge session ID for the new undo proof.
        project_id:          Project name for the new undo proof.
        action_id:           Action ID for the new undo proof.

    Returns dict:
        ok                   — bool: True when undo vstat is VERIFIED or ALREADY_CORRECT
        undo_proof           — ActionProof: new proof created for this undo
        drift_detected       — bool
        drift_state          — dict: current live state when drift was found (or {})
        verification_status  — str: undo readback result
        original_proof_id    — str: the proof_id of the proof that was undone
        message              — str: human-readable summary

    Raises:
        UndoValidationError  — proof is not eligible (before any write).
                               Caller should catch and return HTTP 400.
    """
    original_proof_id = str(proof.get("proof_id",            ""))
    action_type       = str(proof.get("action_type",         ""))
    target            = str(proof.get("target",              ""))
    vstat             = str(proof.get("verification_status", ""))
    before_state      = proof.get("before_state") or {}
    after_state       = proof.get("after_state")  or {}

    # ── 1. Validate eligibility ───────────────────────────────────────────────
    if vstat not in ("VERIFIED", "ALREADY_CORRECT"):
        raise UndoValidationError(
            f"Cannot undo proof {original_proof_id!r}: verification_status is "
            f"{vstat!r}. Only VERIFIED or ALREADY_CORRECT proofs can be undone — "
            "undoing an unconfirmed action would restore a state that was never "
            "reliably set.",
            bridge_error_code=BridgeErrorCode.UNDO_NOT_ELIGIBLE,
        )

    if action_type not in UNDOABLE_ACTION_TYPES:
        raise UndoValidationError(
            f"Unsupported action type {action_type!r} for undo. "
            f"Supported: {sorted(UNDOABLE_ACTION_TYPES)}.",
            bridge_error_code=BridgeErrorCode.UNDO_UNSUPPORTED_ACTION,
        )

    state_key = _ACTION_STATE_KEY[action_type]
    if not before_state or state_key not in before_state:
        raise UndoValidationError(
            f"Proof {original_proof_id!r} has no before_state[{state_key!r}]. "
            "Cannot restore without a captured before-value. "
            "The original action may have had before-state capture disabled.",
            bridge_error_code=BridgeErrorCode.UNDO_NO_BEFORE_STATE,
        )

    # Blocker 2 — Gate 1: after_state[state_key] must exist.
    # Without it there is no baseline for drift detection and we cannot verify
    # what the live state should be before writing before_state back.
    # confirm=True does NOT bypass this gate: an absent after_state means the
    # original action never recorded its verified result, making drift comparison
    # impossible regardless of caller intent.
    if not after_state or state_key not in after_state:
        raise UndoValidationError(
            f"Proof {original_proof_id!r} has no after_state[{state_key!r}]. "
            "Cannot run drift preflight without a verified after-value to compare against. "
            "The original action may not have recorded its after_state correctly. "
            "confirm=True does not override this gate.",
            bridge_error_code=BridgeErrorCode.UNDO_NO_AFTER_STATE,
        )

    # ── 2. Parse track identifier from proof target ───────────────────────────
    track_id   = _parse_target(target)
    undo_target = f"undo:{target}"

    before_value = before_state[state_key]
    after_value  = after_state[state_key]        # guaranteed non-None: validated in step 1
    is_scalar        = action_type in ("SET_TRACK_VOLUME", "SET_TRACK_PAN")
    is_integer       = action_type in _INTEGER_ACTION_TYPES
    # Slice 2 categories
    is_string        = action_type in _STRING_ACTION_TYPES
    is_song_bool     = action_type in _SONG_BOOL_ACTION_TYPES
    is_float_send    = action_type in _FLOAT_SEND_ACTION_TYPES
    # Slice 3A
    is_plugin_bypass = action_type in _PLUGIN_BYPASS_ACTION_TYPES

    # For SET_TRACK_SEND: override track_id and extract send_idx from target
    # Target format: "track:{name}:send:{idx}"
    send_idx = None
    if is_float_send:
        parsed_t, parsed_s = _parse_send_target(target)
        if parsed_t is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        track_id = parsed_t
        send_idx = parsed_s

    # For PLUGIN_BYPASS: override track_id and extract device_name from target
    # Target format: "track:{track_id}:device:{matched_device_name}"
    plugin_device_name = None
    if is_plugin_bypass:
        parsed_t, parsed_d = _parse_plugin_target(target)
        if parsed_t is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        track_id           = parsed_t
        plugin_device_name = parsed_d

    # ── 3. Drift detection — read current live state ──────────────────────────
    #       Gate 2 (Blocker 1): if the live-state read returns None (Ableton
    #       unreachable, track absent, parse failure), undo is blocked immediately
    #       with UNDO_DRIFT_READ_UNAVAILABLE.  confirm=True cannot override this:
    #       we need the current value to perform the drift comparison and to
    #       populate before_state of the undo proof.  The caller never reaches
    #       step 4 (the drift gate), so confirm is irrelevant here.
    drift_detected = False
    drift_state    = {}
    current_value  = None

    if is_plugin_bypass:
        # Device bypass — bool exact match; find device by name query in readback
        current_raw = _read_plugin_bypass(track_id, plugin_device_name, executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = bool(current_raw)
        expected_after = bool(after_value)
        if current_value != expected_after:
            drift_detected = True
            drift_state    = {state_key: current_value}
    elif is_float_send:
        # Float send — same tolerance as volume/pan
        current_raw = _read_send_value(track_id, send_idx, executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = round(float(current_raw), 6)
        expected_after = round(float(after_value), 6)
        if abs(current_value - expected_after) > _SCALAR_TOLERANCE:
            drift_detected = True
            drift_state    = {state_key: current_value}
    elif is_string:
        # String property (output routing display name) — exact match
        current_raw = _read_route_name(track_id, executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = str(current_raw)
        expected_after = str(after_value)
        if current_value != expected_after:
            drift_detected = True
            drift_state    = {state_key: current_value}
    elif is_song_bool:
        # Song-level boolean (loop / metronome) — exact match, no track_id
        song_prop   = _SONG_BOOL_LOM_PROP[action_type]
        current_raw = _read_song_bool(song_prop, executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = bool(current_raw)
        expected_after = bool(after_value)
        if current_value != expected_after:
            drift_detected = True
            drift_state    = {state_key: current_value}
    elif is_scalar:
        current_raw = (
            _read_volume(track_id, executor)
            if action_type == "SET_TRACK_VOLUME"
            else _read_pan(track_id, executor)
        )
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = round(float(current_raw), 6)
        expected_after = round(float(after_value), 6)
        if abs(current_value - expected_after) > _SCALAR_TOLERANCE:
            drift_detected = True
            drift_state    = {state_key: current_value}
    elif is_integer:
        # Integer property (e.g. monitor mode 0/1/2) — exact comparison
        current_raw = _read_integer_property(track_id, _INTEGER_LOM_PROP[action_type], executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = int(current_raw)
        expected_after = int(after_value)
        if current_value != expected_after:
            drift_detected = True
            drift_state    = {state_key: current_value}
    else:
        # Boolean: mute / solo / arm
        prop        = state_key
        current_raw = _read_bool_property(track_id, prop, executor)
        if current_raw is None:
            return _fail_unreadable(
                action_type, undo_target, before_value, state_key,
                original_proof_id, action_id, request_id, session_id, project_id,
            )
        current_value  = bool(current_raw)
        expected_after = bool(after_value)
        if current_value != expected_after:
            drift_detected = True
            drift_state    = {state_key: current_value}

    # ── 4. Drift gate — block unless confirm=True ─────────────────────────────
    #       Scope of confirm=True: bypasses Gate 3 (actual value drift) ONLY.
    #       Gate 1 (UNDO_NO_AFTER_STATE) and Gate 2 (UNDO_DRIFT_READ_UNAVAILABLE)
    #       both return/raise before this point and are never reached here.
    if drift_detected and not confirm:
        stub_proof = create_proof(
            action_type         = f"UNDO_{action_type}",
            target              = undo_target,
            intended_value      = before_value,
            before_state        = drift_state,   # what we found (current live)
            after_state         = {},            # no write attempted
            verification_status = VerificationStatus.FAILED.value,
            undo_eligible       = False,
            user_facing_summary = (
                f"Undo blocked: current {state_key}={current_value!r} drifted "
                f"from original after_state ({after_value!r}). "
                "Pass confirm=true to override."
            ),
            action_id   = action_id,
            request_id  = request_id,
            session_id  = session_id,
            project_id  = project_id,
        )
        log_event(
            ACTION_FAILED,
            action_type         = f"UNDO_{action_type}",
            target              = undo_target,
            proof_id            = stub_proof.proof_id,
            action_id           = action_id,
            request_id          = request_id,
            session_id          = session_id,
            verification_status = VerificationStatus.FAILED.value,
            error_code          = BridgeErrorCode.STATE_DRIFT_COLLISION.value,
            message             = (
                f"Undo drift: current {state_key}={current_value!r}, "
                f"expected after_state={after_value!r}. confirm=False → blocked."
            ),
            original_proof_id   = original_proof_id,
        )
        return {
            "ok":                  False,
            "undo_proof":          stub_proof,
            "drift_detected":      True,
            "drift_state":         drift_state,
            "verification_status": VerificationStatus.FAILED.value,
            "original_proof_id":   original_proof_id,
            "message":             stub_proof.user_facing_summary,
        }

    # ── 5. Execute undo write via verify_* ───────────────────────────────────
    #       Reuse the same readback loop, setting the value to before_value.
    try:
        if action_type == "SET_TRACK_VOLUME":
            rb = verify_track_volume(
                track_id, float(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_PAN":
            rb = verify_track_pan(
                track_id, float(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_MUTE":
            rb = verify_track_mute(
                track_id, bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_SOLO":
            rb = verify_track_solo(
                track_id, bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "ARM_TRACK":
            rb = verify_track_arm(
                track_id, bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_MONITOR":
            rb = verify_track_monitor(
                track_id, int(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_COLOR":
            rb = verify_track_color(
                track_id, int(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_SEND":
            rb = verify_track_send(
                track_id, send_idx, float(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "SET_TRACK_ROUTE":
            rb = verify_track_route(
                track_id, str(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "TRANSPORT_LOOP":
            rb = verify_transport_loop(
                bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "TRANSPORT_METRONOME":
            rb = verify_transport_metronome(
                bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        elif action_type == "PLUGIN_BYPASS":
            rb = verify_plugin_bypass(
                track_id, plugin_device_name, bool(before_value), executor,
                stabilization_delay=stabilization_delay,
            )
        else:  # fallback — should not reach here given UNDOABLE_ACTION_TYPES gate
            rb = {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state": {}, "after_state": {},
                "error_code": BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                "intended_value": before_value,
                "message": f"No verify function for action type {action_type!r}.",
            }
    except Exception as exc:
        rb = {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        {},
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      before_value,
            "message":             f"Undo write raised: {exc}",
        }

    undo_vstat    = rb["verification_status"]
    undo_confirmed = undo_vstat in (
        VerificationStatus.VERIFIED.value,
        VerificationStatus.ALREADY_CORRECT.value,
    )

    drift_note = " (drift was present; confirm=True used)" if drift_detected else ""
    summary = (
        f"Undo {action_type} on {target}: "
        f"restored {state_key} to {before_value!r}. "
        f"Result: {undo_vstat}.{drift_note}"
    )

    # ── 6. Create new ActionProof for this undo ───────────────────────────────
    undo_proof = create_proof(
        action_type         = f"UNDO_{action_type}",
        target              = undo_target,
        intended_value      = before_value,
        before_state        = rb["before_state"],   # live state just before the undo write
        after_state         = rb["after_state"],    # state after the undo write
        verification_status = undo_vstat,
        undo_eligible       = False,                # no undo-of-undo
        user_facing_summary = summary,
        action_id           = action_id,
        request_id          = request_id,
        session_id          = session_id,
        project_id          = project_id,
    )

    # ── 7. Log BBL event ──────────────────────────────────────────────────────
    bbl_type = ACTION_VERIFIED if undo_confirmed else ACTION_FAILED
    log_event(
        bbl_type,
        action_type         = f"UNDO_{action_type}",
        target              = undo_target,
        proof_id            = undo_proof.proof_id,
        action_id           = action_id,
        request_id          = request_id,
        session_id          = session_id,
        verification_status = undo_vstat,
        error_code          = rb.get("error_code", ""),
        message             = summary,
        original_proof_id   = original_proof_id,
        drift_detected      = drift_detected,
        confirm_used        = (confirm and drift_detected),
    )

    return {
        "ok":                  undo_confirmed,
        "undo_proof":          undo_proof,
        "drift_detected":      drift_detected,
        "drift_state":         drift_state if drift_detected else {},
        "verification_status": undo_vstat,
        "original_proof_id":   original_proof_id,
        "message":             summary,
    }


# ── INTERNALS ─────────────────────────────────────────────────────────────────

def _fail_unreadable(
    action_type:       str,
    undo_target:       str,
    before_value:      object,
    state_key:         str,
    original_proof_id: str,
    action_id:         str,
    request_id:        str,
    session_id:        str,
    project_id:        str,
) -> dict:
    """
    Gate 2 — UNDO_DRIFT_READ_UNAVAILABLE.

    Called when the drift-preflight live-state read returns None (executor
    error, Ableton disconnected, track absent, or float/bool parse failure).

    No write is ever attempted from this path.
    confirm=True does NOT bypass this: the caller returns from step 3 before
    ever reaching the step-4 drift gate where confirm is evaluated.

    Returns a structured failure dict with:
        ok=False
        verification_status=FAILED
        drift_detected=False   (we could not read — drift status is unknown)
        error_code=UNDO_DRIFT_READ_UNAVAILABLE
    A stub ActionProof is created and logged to the black box log.
    """
    msg = (
        f"Undo could not read current live {state_key} before writing. "
        "No changes were made. "
        "Check that Ableton is connected and the track exists. "
        "confirm=True does not override an unreadable live state."
    )
    stub_proof = create_proof(
        action_type         = f"UNDO_{action_type}",
        target              = undo_target,
        intended_value      = before_value,
        before_state        = {},   # unknown — could not read live state
        after_state         = {},   # no write attempted
        verification_status = VerificationStatus.FAILED.value,
        undo_eligible       = False,
        user_facing_summary = msg,
        action_id           = action_id,
        request_id          = request_id,
        session_id          = session_id,
        project_id          = project_id,
    )
    log_event(
        ACTION_FAILED,
        action_type         = f"UNDO_{action_type}",
        target              = undo_target,
        proof_id            = stub_proof.proof_id,
        action_id           = action_id,
        request_id          = request_id,
        session_id          = session_id,
        verification_status = VerificationStatus.FAILED.value,
        error_code          = BridgeErrorCode.UNDO_DRIFT_READ_UNAVAILABLE.value,
        message             = msg,
        original_proof_id   = original_proof_id,
    )
    return {
        "ok":                  False,
        "undo_proof":          stub_proof,
        "drift_detected":      False,
        "drift_state":         {},
        "verification_status": VerificationStatus.FAILED.value,
        "error_code":          BridgeErrorCode.UNDO_DRIFT_READ_UNAVAILABLE.value,
        "original_proof_id":   original_proof_id,
        "message":             msg,
    }


def _parse_target(target: str) -> "str | int":
    """
    Parse a proof target string back to a track identifier.

    Bridge sets target as "track:TrackName" or "track:3" (0-based index).
    Returns int for numeric identifiers, str for named tracks.

    Examples:
        "track:Kick Drum"   → "Kick Drum"
        "track:0"           → 0
        "track:3"           → 3
        "track:"            → ""        (degenerate — will fail at Ableton level)
    """
    prefix = "track:"
    if target.startswith(prefix):
        ident = target[len(prefix):]
        try:
            return int(ident)
        except ValueError:
            return ident
    # Non-standard target format — return as-is
    return target


def _parse_send_target(target: str) -> "tuple":
    """
    Parse a send proof target back to (track_id, send_idx).

    Bridge sets target as "track:{name}:send:{idx}" for SET_TRACK_SEND.
    Returns (track_id, send_idx) on success, (None, None) on parse failure.

    Examples:
        "track:Kick Drum:send:2"  → ("Kick Drum", 2)
        "track:0:send:0"          → (0, 0)
    """
    if ":send:" not in target:
        return (None, None)
    # Split on last ":send:" occurrence to handle track names with colons
    idx_of_send = target.rfind(":send:")
    if idx_of_send == -1:
        return (None, None)
    track_part = target[:idx_of_send]
    send_part  = target[idx_of_send + len(":send:"):]
    try:
        send_idx = int(send_part)
    except ValueError:
        return (None, None)
    # Parse track part ("track:Name" or "track:3")
    prefix = "track:"
    if track_part.startswith(prefix):
        ident = track_part[len(prefix):]
        try:
            return (int(ident), send_idx)
        except ValueError:
            return (ident, send_idx)
    return (None, None)


def _parse_plugin_target(target: str) -> "tuple":
    """
    Parse a plugin bypass proof target back to (track_id, device_name).

    Bridge sets target as "track:{track_id}:device:{matched_device_name}".
    Uses rfind to handle colons in track/device names.
    Returns (track_id, device_name) on success, (None, None) on parse failure.

    Examples:
        "track:Vocal Bus:device:Pro-Q 4"  → ("Vocal Bus", "Pro-Q 4")
        "track:0:device:Compressor"       → (0, "Compressor")
    """
    marker    = ":device:"
    idx       = target.rfind(marker)
    if idx == -1:
        return (None, None)
    track_part  = target[:idx]
    device_name = target[idx + len(marker):]
    if not device_name:
        return (None, None)
    track_id = _parse_target(track_part)
    return (track_id, device_name)
