"""
Conductor — Readback Verification (Phase D Slice 1 + Slice 2)
──────────────────────────────────────────────────────────────
Before/after readback loop for track-level scalar and boolean writes.

Slice 1 scope: track volume only.
Slice 2 adds:  track pan (scalar), track mute (boolean), track solo (boolean).
Each new action type follows the same six-step pattern defined here.

The six steps:
    1. Read before_state via executor  →  raises BeforeStateCaptureError on failure
    2. ALREADY_CORRECT check            →  short-circuit if value is already right
    3. Execute the write via executor   →  returns FAILED if write call errors
    4. Wait stabilization_delay         →  configurable, default 0.25 s
    5. Read after_state via executor    →  returns UNVERIFIED if readback fails
    6. Compare within tolerance         →  VERIFIED or FAILED
       (booleans: exact match; scalars: within tolerance)

Rule: if before_state capture fails, BeforeStateCaptureError is raised and the
caller MUST NOT execute the write.  Execution without a captured before_state
would leave the action un-undoable.

Executor protocol (dependency injection — no direct Ableton import here):
    executor(code: str) → {
        "ok":    bool,
        "data":  dict,      # raw Ableton MCP response; value at data["result"]
        "error": str | None
    }
    For mocking in tests:
        def mock_exec(code): return {"ok": True, "data": {"result": 0.85}, "error": None}

Volume scale:
    Ableton LOM mixer_device.volume.value is normalized 0.0–1.0.
    0.0 = -inf dB (silence), ~0.85 = 0 dB (unity), 1.0 ≈ +6 dB.

Pan scale:
    Ableton LOM mixer_device.panning.value is normalized 0.0–1.0.
    0.0 = full left, 0.5 = center (default), 1.0 = full right.

Mute / Solo:
    track.mute  — Python bool: True = muted,  False = unmuted.
    track.solo  — Python bool: True = soloed, False = unsoloed.
    Boolean exact-match — no tolerance parameter.

Return value note:
    verification_status in the returned dict is always a plain string
    (e.g. "VERIFIED"), not an Enum object.  This avoids Python-version
    differences in str(Enum) behaviour.  Callers compare against the
    VerificationStatus enum's .value or against plain strings directly.
"""

import time
from typing import Callable, Optional

from rag.action_proof import VerificationStatus
from rag.bridge_errors import BridgeErrorCode

# ── CONSTANTS ──────────────────────────────────────────────────────────────────

DEFAULT_STABILIZATION_DELAY: float = 0.25   # seconds — conservative for LOM async lag
DEFAULT_VOLUME_TOLERANCE:    float = 0.005  # normalized — ≈ 0.1 dB at unity gain
DEFAULT_PAN_TOLERANCE:       float = 0.005  # normalized — same granularity as volume


# ── EXCEPTIONS ─────────────────────────────────────────────────────────────────

class BeforeStateCaptureError(Exception):
    """
    Raised when before_state cannot be read from Ableton.

    The caller MUST NOT proceed with the write when this is raised.
    Without a captured before_state:
      - undo_eligible must be False
      - The action cannot be reversed without manual inspection
      - ActionProof.before_state would be empty, which is misleading

    Catchable by the bridge endpoint: log the error, return STATE_CAPTURE_FAILED.
    """
    pass


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def verify_track_volume(
    track_identifier: "str | int",
    intended_value: float,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
    tolerance: float           = DEFAULT_VOLUME_TOLERANCE,
) -> dict:
    """
    Write track volume with before/after readback verification.

    Args:
        track_identifier:    Track name (str) or index (int, 0-based).
        intended_value:      Target volume, normalized 0.0–1.0.
                             Clamped silently to [0.0, 1.0].
        executor:            ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write before readback.
        tolerance:           Allowed absolute delta (normalized) between intended
                             and actual after_state before FAILED is returned.

    Returns:
        dict with keys:
            verification_status  (str)   — plain string: "VERIFIED" | "ALREADY_CORRECT" |
                                           "FAILED" | "UNVERIFIED" | "PARTIAL"
            before_state         (dict)  — {"volume": float}
            after_state          (dict)  — {"volume": float} or {}
            error_code           (str)   — BridgeErrorCode .value string, or ""
            intended_value       (float) — clamped value we tried to set
            message              (str)   — human detail, "" if clean

    Raises:
        BeforeStateCaptureError  — if before_state cannot be read.
                                   Caller must NOT execute the write.
        ValueError               — if intended_value cannot be coerced to float.
    """
    intended_value = _clamp(float(intended_value), 0.0, 1.0)

    # ── Step 1: Read before_state ─────────────────────────────────────────────
    before_vol = _read_volume(track_identifier, executor)
    if before_vol is None:
        raise BeforeStateCaptureError(
            f"Cannot read current volume for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"volume": round(before_vol, 6)}

    # ── Step 2: ALREADY_CORRECT check ────────────────────────────────────────
    if abs(before_vol - intended_value) <= tolerance:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"volume": round(before_vol, 6)},
            "error_code":          "",
            "intended_value":      intended_value,
            "message":             (
                f"Volume was already {before_vol:.4f} "
                f"(target {intended_value:.4f}, within tolerance {tolerance}) — no write sent."
            ),
        }

    # ── Step 3: Execute write ─────────────────────────────────────────────────
    write_code = _build_volume_write_code(track_identifier, intended_value)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_value,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_value,
            "message":             f"Write failed: {raw_error}",
        }

    # ── Step 4: Stabilization delay ───────────────────────────────────────────
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # ── Step 5: Read after_state ──────────────────────────────────────────────
    after_vol = _read_volume(track_identifier, executor)
    if after_vol is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_value,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"volume": round(after_vol, 6)}

    # ── Step 6: Compare ───────────────────────────────────────────────────────
    if abs(after_vol - intended_value) <= tolerance:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_value,
            "message":             f"Volume confirmed at {after_vol:.4f}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_value,
            "message":             (
                f"Readback mismatch: intended {intended_value:.4f}, "
                f"got {after_vol:.4f} (delta {abs(after_vol - intended_value):.4f} "
                f"> tolerance {tolerance:.4f})."
            ),
        }


def verify_track_pan(
    track_identifier: "str | int",
    intended_value: float,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
    tolerance: float           = DEFAULT_PAN_TOLERANCE,
) -> dict:
    """
    Write track pan with before/after readback verification.

    Args:
        track_identifier:    Track name (str) or index (int, 0-based).
        intended_value:      Target pan, normalized 0.0–1.0.
                             0.0 = full left, 0.5 = center, 1.0 = full right.
                             Clamped silently to [0.0, 1.0].
        executor:            ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write before readback.
        tolerance:           Allowed absolute delta before FAILED is returned.

    Returns: same shape as verify_track_volume, state key "pan".
    Raises:  BeforeStateCaptureError / ValueError (same rules as verify_track_volume).
    """
    intended_value = _clamp(float(intended_value), 0.0, 1.0)

    # ── Step 1: Read before_state ─────────────────────────────────────────────
    before_pan = _read_pan(track_identifier, executor)
    if before_pan is None:
        raise BeforeStateCaptureError(
            f"Cannot read current pan for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"pan": round(before_pan, 6)}

    # ── Step 2: ALREADY_CORRECT check ────────────────────────────────────────
    if abs(before_pan - intended_value) <= tolerance:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"pan": round(before_pan, 6)},
            "error_code":          "",
            "intended_value":      intended_value,
            "message":             (
                f"Pan was already {before_pan:.4f} "
                f"(target {intended_value:.4f}, within tolerance {tolerance}) — no write sent."
            ),
        }

    # ── Step 3: Execute write ─────────────────────────────────────────────────
    write_code = _build_pan_write_code(track_identifier, intended_value)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_value,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_value,
            "message":             f"Write failed: {raw_error}",
        }

    # ── Step 4: Stabilization delay ───────────────────────────────────────────
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # ── Step 5: Read after_state ──────────────────────────────────────────────
    after_pan = _read_pan(track_identifier, executor)
    if after_pan is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_value,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"pan": round(after_pan, 6)}

    # ── Step 6: Compare ───────────────────────────────────────────────────────
    if abs(after_pan - intended_value) <= tolerance:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_value,
            "message":             f"Pan confirmed at {after_pan:.4f}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_value,
            "message":             (
                f"Readback mismatch: intended {intended_value:.4f}, "
                f"got {after_pan:.4f} (delta {abs(after_pan - intended_value):.4f} "
                f"> tolerance {tolerance:.4f})."
            ),
        }


def verify_track_mute(
    track_identifier: "str | int",
    intended_value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Write track mute state with before/after readback verification.

    Args:
        track_identifier:    Track name (str) or index (int, 0-based).
        intended_value:      True = mute the track, False = unmute.
        executor:            ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write before readback.

    Boolean exact-match — no tolerance parameter.
    Returns: same structure as verify_track_volume, state key "mute".
    Raises:  BeforeStateCaptureError / ValueError.
    """
    intended_bool = bool(intended_value)

    # ── Step 1: Read before_state ─────────────────────────────────────────────
    before_mute = _read_bool_property(track_identifier, "mute", executor)
    if before_mute is None:
        raise BeforeStateCaptureError(
            f"Cannot read current mute state for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"mute": before_mute}

    # ── Step 2: ALREADY_CORRECT check ────────────────────────────────────────
    if before_mute == intended_bool:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"mute": before_mute},
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             (
                f"Track was already {'muted' if before_mute else 'unmuted'} "
                f"— no write sent."
            ),
        }

    # ── Step 3: Execute write ─────────────────────────────────────────────────
    write_code = _build_bool_property_write_code(track_identifier, "mute", intended_bool)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_bool,
            "message":             f"Write failed: {raw_error}",
        }

    # ── Step 4: Stabilization delay ───────────────────────────────────────────
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # ── Step 5: Read after_state ──────────────────────────────────────────────
    after_mute = _read_bool_property(track_identifier, "mute", executor)
    if after_mute is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_bool,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"mute": after_mute}

    # ── Step 6: Exact boolean comparison ─────────────────────────────────────
    if after_mute == intended_bool:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             f"Mute confirmed: {'muted' if after_mute else 'unmuted'}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             (
                f"Readback mismatch: intended {'muted' if intended_bool else 'unmuted'}, "
                f"got {'muted' if after_mute else 'unmuted'}."
            ),
        }


def verify_track_solo(
    track_identifier: "str | int",
    intended_value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Write track solo state with before/after readback verification.

    Solo is a session-level exclusive in Ableton — soloing one track silences
    others.  This verifier only confirms the TARGET track's solo flag.
    It does not capture the full session state change across all tracks.
    Callers must document this limitation in user-facing summaries.

    Boolean exact-match — no tolerance parameter.
    Returns: same structure as verify_track_volume, state key "solo".
    Raises:  BeforeStateCaptureError / ValueError.
    """
    intended_bool = bool(intended_value)

    # ── Step 1: Read before_state ─────────────────────────────────────────────
    before_solo = _read_bool_property(track_identifier, "solo", executor)
    if before_solo is None:
        raise BeforeStateCaptureError(
            f"Cannot read current solo state for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"solo": before_solo}

    # ── Step 2: ALREADY_CORRECT check ────────────────────────────────────────
    if before_solo == intended_bool:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"solo": before_solo},
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             (
                f"Track was already {'soloed' if before_solo else 'unsoloed'} "
                f"— no write sent."
            ),
        }

    # ── Step 3: Execute write ─────────────────────────────────────────────────
    write_code = _build_bool_property_write_code(track_identifier, "solo", intended_bool)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_bool,
            "message":             f"Write failed: {raw_error}",
        }

    # ── Step 4: Stabilization delay ───────────────────────────────────────────
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # ── Step 5: Read after_state ──────────────────────────────────────────────
    after_solo = _read_bool_property(track_identifier, "solo", executor)
    if after_solo is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_bool,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"solo": after_solo}

    # ── Step 6: Exact boolean comparison ─────────────────────────────────────
    if after_solo == intended_bool:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             f"Solo confirmed: {'soloed' if after_solo else 'unsoloed'}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             (
                f"Readback mismatch: intended {'soloed' if intended_bool else 'unsoloed'}, "
                f"got {'soloed' if after_solo else 'unsoloed'}."
            ),
        }


# ── INTERNALS ─────────────────────────────────────────────────────────────────

def _read_volume(
    track_identifier: "str | int",
    executor: Callable,
) -> "Optional[float]":
    """
    Read current track volume via executor.
    Returns float on success, None on any failure (executor error, track absent,
    result not parseable as float).
    """
    code = _build_volume_read_code(track_identifier)
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_float(resp)
    except Exception:
        return None


def _read_pan(
    track_identifier: "str | int",
    executor: Callable,
) -> "Optional[float]":
    """Read current track pan position via executor.  Returns float or None."""
    code = _build_pan_read_code(track_identifier)
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_float(resp)
    except Exception:
        return None


def _read_bool_property(
    track_identifier: "str | int",
    prop: str,
    executor: Callable,
) -> "Optional[bool]":
    """
    Read a boolean track property (mute or solo) via executor.
    Returns bool on success, None on any failure.
    prop: "mute" | "solo"
    """
    code = _build_bool_property_read_code(track_identifier, prop)
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_bool(resp)
    except Exception:
        return None


def _extract_float(resp: dict) -> "Optional[float]":
    """
    Extract a float value from an executor response.

    Ableton MCP returns:
        {"ok": true, "result": <value>, ...}  — value at top-level "result"
    which the bridge wraps as:
        {"ok": ..., "data": raw_ableton_response, "error": ...}
    so we look for data["result"] first, then data itself if it's numeric.
    """
    data = resp.get("data") or {}

    # Standard path: data is the Ableton response dict, result key holds value
    if isinstance(data, dict):
        val = data.get("result")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                pass
        # Some MCP versions return value at data["data"]
        val2 = data.get("data")
        if val2 is not None:
            try:
                return float(val2)
            except (TypeError, ValueError):
                pass

    # data itself might be the numeric value (mock / simplified executor)
    if isinstance(data, (int, float)) and not isinstance(data, bool):
        return float(data)

    # Last-resort: look for a direct "result" key in the top-level response
    val_top = resp.get("result")
    if val_top is not None:
        try:
            return float(val_top)
        except (TypeError, ValueError):
            pass

    return None


def _extract_bool(resp: dict) -> "Optional[bool]":
    """
    Extract a boolean value from an executor response.

    Handles Python booleans (True/False), JSON booleans (true/false),
    and Ableton's occasional 0/1 integer representation.
    Returns None if the value cannot be cleanly interpreted as bool.

    Note: int(True) == 1 and int(False) == 0, so isinstance checks are
    done BEFORE int coercion to avoid misclassifying numeric results.
    """
    data = resp.get("data") or {}

    if isinstance(data, dict):
        val = data.get("result")
        if val is not None:
            if isinstance(val, bool):
                return val
            try:
                i = int(val)
                if i in (0, 1):
                    return bool(i)
            except (TypeError, ValueError):
                pass
        # Some MCP versions return value at data["data"]
        val2 = data.get("data")
        if val2 is not None:
            if isinstance(val2, bool):
                return val2
            try:
                i2 = int(val2)
                if i2 in (0, 1):
                    return bool(i2)
            except (TypeError, ValueError):
                pass

    # data itself might be a bool or 0/1 (mock / simplified executor)
    if isinstance(data, bool):
        return data
    if isinstance(data, int) and data in (0, 1):
        return bool(data)

    # Last-resort: top-level "result" key
    val_top = resp.get("result")
    if val_top is not None:
        if isinstance(val_top, bool):
            return val_top
        try:
            i_top = int(val_top)
            if i_top in (0, 1):
                return bool(i_top)
        except (TypeError, ValueError):
            pass

    return None


def _build_volume_read_code(track_identifier: "str | int") -> str:
    """Build Python code to read mixer_device.volume.value from Ableton LOM."""
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].mixer_device.volume.value"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'next('
        f'(t.mixer_device.volume.value for t in song.tracks if t.name == "{name}"), '
        f'None'
        f')'
    )


def _build_volume_write_code(track_identifier: "str | int", value: float) -> str:
    """
    Build Python code to set mixer_device.volume.value via Ableton LOM.
    The code assigns the value; we do not read it back here (separate readback call).
    """
    v = f"{value:.6f}"
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].mixer_device.volume.value = {v}"
    name = str(track_identifier).replace('"', '\\"')
    # __vol_tracks__ is a temp name unlikely to conflict with user variables
    return (
        f'__vol_tracks__ = [t for t in song.tracks if t.name == "{name}"]; '
        f'__vol_tracks__[0].mixer_device.volume.value = {v} if __vol_tracks__ else None'
    )


def _build_pan_read_code(track_identifier: "str | int") -> str:
    """Build Python code to read mixer_device.panning.value from Ableton LOM."""
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].mixer_device.panning.value"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'next('
        f'(t.mixer_device.panning.value for t in song.tracks if t.name == "{name}"), '
        f'None'
        f')'
    )


def _build_pan_write_code(track_identifier: "str | int", value: float) -> str:
    """Build Python code to set mixer_device.panning.value via Ableton LOM."""
    v = f"{value:.6f}"
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].mixer_device.panning.value = {v}"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'__pan_tracks__ = [t for t in song.tracks if t.name == "{name}"]; '
        f'__pan_tracks__[0].mixer_device.panning.value = {v} if __pan_tracks__ else None'
    )


def _build_bool_property_read_code(
    track_identifier: "str | int",
    prop: str,
) -> str:
    """
    Build Python code to read a boolean track property from Ableton LOM.
    prop: "mute" | "solo"
    """
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].{prop}"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'next('
        f'(t.{prop} for t in song.tracks if t.name == "{name}"), '
        f'None'
        f')'
    )


def _build_bool_property_write_code(
    track_identifier: "str | int",
    prop: str,
    value: bool,
) -> str:
    """
    Build Python code to set a boolean track property via Ableton LOM.
    prop: "mute" | "solo"
    """
    v = "True" if value else "False"
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].{prop} = {v}"
    name = str(track_identifier).replace('"', '\\"')
    tmp_var = f"__{prop}_tracks__"
    return (
        f'{tmp_var} = [t for t in song.tracks if t.name == "{name}"]; '
        f'{tmp_var}[0].{prop} = {v} if {tmp_var} else None'
    )


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


# ═════════════════════════════════════════════════════════════════════════════
# ACTION EXPANSION — SLICE 1 (Track / Recording)
# Added in Phase D Action Expansion Slice 1.
# Follows the same six-step readback pattern as volume/pan/mute/solo.
# ═════════════════════════════════════════════════════════════════════════════


# ── TRACK ARM ─────────────────────────────────────────────────────────────────

def verify_track_arm(
    track_identifier: "str | int",
    intended_value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Write track arm state with before/after readback verification.

    Identical pattern to verify_track_mute — uses track.arm boolean property.
    Note: arm state is only available on MIDI/audio tracks, not master/return tracks.

    Returns: same structure as verify_track_mute, state key "arm".
    Raises:  BeforeStateCaptureError / ValueError.
    """
    intended_bool = bool(intended_value)

    before_arm = _read_bool_property(track_identifier, "arm", executor)
    if before_arm is None:
        raise BeforeStateCaptureError(
            f"Cannot read current arm state for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"arm": before_arm}

    if before_arm == intended_bool:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"arm": before_arm},
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             (
                f"Track was already {'armed' if before_arm else 'unarmed'} — no write sent."
            ),
        }

    write_code = _build_bool_property_write_code(track_identifier, "arm", intended_bool)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_bool,
            "message":             f"Write failed: {raw_error}",
        }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_arm = _read_bool_property(track_identifier, "arm", executor)
    if after_arm is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_bool,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"arm": after_arm}

    if after_arm == intended_bool:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_bool,
            "message":             f"Arm confirmed: {'armed' if after_arm else 'unarmed'}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_bool,
            "message":             (
                f"Readback mismatch: intended {'armed' if intended_bool else 'unarmed'}, "
                f"got {'armed' if after_arm else 'unarmed'}."
            ),
        }


# ── TRACK MONITOR ─────────────────────────────────────────────────────────────

def verify_track_monitor(
    track_identifier: "str | int",
    intended_mode: int,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Write track monitoring state with before/after readback verification.

    Monitoring modes (Ableton LOM current_monitoring_state):
        0 = In    (always monitor input — useful for live recording)
        1 = Auto  (monitor only when track is armed)
        2 = Off   (never monitor input)

    Args:
        track_identifier:  Track name (str) or index (int, 0-based).
        intended_mode:     0, 1, or 2.  Clamped to [0, 2].
        executor:          ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns: same structure as verify_track_volume, state key "monitor".
    Raises:  BeforeStateCaptureError.
    """
    intended_int = max(0, min(2, int(intended_mode)))

    before_mon = _read_integer_property(track_identifier, "current_monitoring_state", executor)
    if before_mon is None:
        raise BeforeStateCaptureError(
            f"Cannot read current monitoring state for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"monitor": before_mon}

    if before_mon == intended_int:
        _mode_names = {0: "In", 1: "Auto", 2: "Off"}
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"monitor": before_mon},
            "error_code":          "",
            "intended_value":      intended_int,
            "message":             (
                f"Monitoring was already {_mode_names.get(before_mon, before_mon)} "
                f"— no write sent."
            ),
        }

    write_code = _build_integer_property_write_code(
        track_identifier, "current_monitoring_state", intended_int
    )
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_int,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      intended_int,
            "message":             f"Write failed: {raw_error}",
        }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_mon = _read_integer_property(track_identifier, "current_monitoring_state", executor)
    if after_mon is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_int,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"monitor": after_mon}
    _mode_names = {0: "In", 1: "Auto", 2: "Off"}

    if after_mon == intended_int:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_int,
            "message":             f"Monitor confirmed: {_mode_names.get(after_mon, after_mon)}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_int,
            "message":             (
                f"Readback mismatch: intended {_mode_names.get(intended_int, intended_int)}, "
                f"got {_mode_names.get(after_mon, after_mon)}."
            ),
        }


# ── TRACK RENAME ──────────────────────────────────────────────────────────────

def verify_track_rename(
    track_index: int,
    new_name: str,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Rename a track with before/after readback verification.

    IMPORTANT: track_index must be a 0-based integer, not a name.
    The bridge must resolve the track name to an index BEFORE calling this
    function — because the track's name changes during this operation, making
    post-rename name-based lookup impossible.

    Args:
        track_index:       0-based track index (integer).
        new_name:          Target name for the track.
        executor:          ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns: same structure as verify_track_volume, state key "name".
    Raises:  BeforeStateCaptureError.
    """
    if not isinstance(track_index, int):
        track_index = int(track_index)

    before_name = _read_string_property(track_index, "name", executor)
    if before_name is None:
        raise BeforeStateCaptureError(
            f"Cannot read current name for track at index {track_index}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"name": before_name}

    if before_name == new_name:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"name": before_name},
            "error_code":          "",
            "intended_value":      new_name,
            "message":             f"Track was already named {new_name!r} — no write sent.",
        }

    write_code = _build_rename_write_code(track_index, new_name)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      new_name,
            "message":             f"Executor raised during write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      new_name,
            "message":             f"Write failed: {raw_error}",
        }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_name = _read_string_property(track_index, "name", executor)
    if after_name is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      new_name,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"name": after_name}

    if after_name == new_name:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      new_name,
            "message":             f"Track renamed to {new_name!r}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      new_name,
            "message":             (
                f"Readback mismatch: intended {new_name!r}, "
                f"got {after_name!r}."
            ),
        }


# ── TRACK COLOR ───────────────────────────────────────────────────────────────

def verify_track_color(
    track_identifier: "str | int",
    intended_color: int,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set track color with before/after readback verification.

    Ableton snaps the written color to the nearest palette entry.  The
    after_state["color"] reflects the actual palette-snapped value.
    VERIFIED is returned when the color changes (exact match or palette snap).
    FAILED is returned when the write was accepted but color did not change.

    Args:
        track_identifier:  Track name (str) or index (int, 0-based).
        intended_color:    Target color as an integer (Ableton 0xRRGGBB format).
        executor:          ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns: same structure as verify_track_volume, state key "color".
    Raises:  BeforeStateCaptureError.
    """
    intended_int = int(intended_color)

    before_color = _read_integer_property(track_identifier, "color", executor)
    if before_color is None:
        raise BeforeStateCaptureError(
            f"Cannot read current color for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"color": before_color}

    if before_color == intended_int:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"color": before_color},
            "error_code":          "",
            "intended_value":      intended_int,
            "message":             f"Track color was already #{intended_int:06X} — no write sent.",
        }

    write_code = _build_integer_property_write_code(track_identifier, "color", intended_int)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_int,
            "message":             f"Executor raised during write: {exc}",
        }

    # Note: Ableton may not propagate a color write error via LOM — proceed to
    # readback even if write_resp.ok is False (known quirk for some LOM versions).
    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or ""
        if "timeout" in str(raw_error).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":        before_state,
                "after_state":         {},
                "error_code":          BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value":      intended_int,
                "message":             f"Write timed out: {raw_error}",
            }
        # For non-timeout LOM errors, still read back — may have succeeded

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_color = _read_integer_property(track_identifier, "color", executor)
    if after_color is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      intended_int,
            "message":             (
                "Write sent but readback unavailable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"color": after_color}

    if after_color != before_color:
        # Color changed (may be palette-snapped)
        extra = ""
        if after_color != intended_int:
            extra = f" (palette-snapped from #{intended_int:06X} to #{after_color:06X})"
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      intended_int,
            "message":             f"Track color set to #{after_color:06X}.{extra}",
        }
    else:
        # Color did not change despite write attempt
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      intended_int,
            "message":             (
                f"Color write had no effect — before and after both #{after_color:06X}."
            ),
        }


# ── TRACK CREATE ──────────────────────────────────────────────────────────────

def verify_track_create(
    track_type: str,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Create a MIDI or audio track with before/after track count verification.

    Before-state: {"track_count": N}
    After-state:  {"track_count": N+1, "new_track_index": N}

    NOTE: Ableton's create_audio_track() returns a serialization error via
    LOM in some MCP versions, but the track IS created.  This function
    proceeds to readback regardless of the write response for audio tracks.

    The requested track name is NOT placed in after_state here — creation proof
    only attests to count change.  If a rename is requested, the bridge calls
    verify_track_rename separately after this function returns and reports the
    rename outcome independently.

    Args:
        track_type:   "midi" or "audio".  Invalid types default to "midi".
        executor:     ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns:  Standard readback dict, state key "track_count".
    Raises:   BeforeStateCaptureError if before-count unreadable.
    """
    track_type_norm = track_type.lower()
    if track_type_norm not in ("midi", "audio"):
        track_type_norm = "midi"

    # Step 1: Before count
    before_count = _read_track_count(executor)
    if before_count is None:
        raise BeforeStateCaptureError(
            "Cannot read current track count from Ableton. "
            "Execution blocked — cannot verify creation without before_state."
        )
    before_state = {"track_count": before_count}

    # Step 3: Create track
    create_code = (
        "song.create_midi_track(-1)"
        if track_type_norm == "midi"
        else "song.create_audio_track(-1)"
    )
    try:
        write_resp = executor(create_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_type_norm,
            "message":             f"Executor raised during create: {exc}",
        }

    # Audio tracks have a known serialization error but ARE created.
    # For MIDI, a real ok=False with timeout means actual failure.
    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or ""
        if "timeout" in str(raw_error).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":        before_state,
                "after_state":         {},
                "error_code":          BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value":      track_type_norm,
                "message":             f"Track create timed out.",
            }
        # Otherwise: proceed to readback (LOM serialization quirk)

    # Step 4: Stabilization delay
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # Step 5: After count
    after_count = _read_track_count(executor)
    if after_count is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      track_type_norm,
            "message":             (
                "Create sent but track count unreadable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }

    new_idx    = after_count - 1
    after_state = {"track_count": after_count, "new_track_index": new_idx}

    # Step 6: Compare
    if after_count == before_count + 1:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      track_type_norm,
            "message":             (
                f"{track_type_norm.upper()} track created at index {new_idx}."
            ),
        }
    elif after_count > before_count + 1:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_type_norm,
            "message":             (
                f"Unexpected: track count increased by {after_count - before_count} "
                f"(expected 1). Session may have been modified externally."
            ),
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_type_norm,
            "message":             "Track count did not increase — creation may have failed.",
        }


# ── TRACK DELETE ──────────────────────────────────────────────────────────────

def verify_track_delete(
    track_identifier: "str | int",
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Delete a track with count-based verification (track count decreases by 1).

    Before-state: {"track_count": N, "track_name": name, "track_index": idx}
    After-state:  {"track_count": N-1}

    IMPORTANT: undo_eligible MUST be False for delete — before_state contains
    track metadata but Conductor cannot restore a deleted track via LOM.

    Returns:
        FAILED (not ALREADY_CORRECT) if the track is not found — deletion of
        a non-existent track is an error, not a no-op.

    Raises: BeforeStateCaptureError if before-count unreadable.
    """
    # Step 1: Resolve track index + capture before state
    track_idx = _read_track_index(track_identifier, executor)
    if track_idx is None:
        # Track not found — this is an input error, not a capture failure
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        {},
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_TRACK_ABSENT.value,
            "intended_value":      track_identifier,
            "message":             f"Track {track_identifier!r} not found — cannot delete.",
        }

    track_name   = _read_string_property(track_idx, "name", executor) or str(track_identifier)
    before_count = _read_track_count(executor)
    if before_count is None:
        raise BeforeStateCaptureError(
            "Cannot read track count from Ableton. "
            "Execution blocked — cannot verify deletion without before_state."
        )
    before_state = {
        "track_count": before_count,
        "track_name":  track_name,
        "track_index": track_idx,
    }

    # Step 3: Delete
    write_code = f"song.delete_track({track_idx})"
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_identifier,
            "message":             f"Executor raised during delete: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      track_identifier,
            "message":             f"Delete failed: {raw_error}",
        }

    # Step 4: Delay
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # Step 5: After count
    after_count = _read_track_count(executor)
    if after_count is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      track_identifier,
            "message":             (
                "Delete sent but track count unreadable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }
    after_state = {"track_count": after_count}

    # Step 6: Compare
    if after_count == before_count - 1:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      track_identifier,
            "message":             (
                f"Track '{track_name}' (index {track_idx}) deleted. "
                f"Track count: {before_count} → {after_count}."
            ),
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_identifier,
            "message":             (
                f"Track count did not decrease as expected "
                f"(before {before_count}, after {after_count})."
            ),
        }


# ── TRACK DUPLICATE ───────────────────────────────────────────────────────────

def verify_track_duplicate(
    track_identifier: "str | int",
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Duplicate a track with count-based verification (track count increases by 1).

    Before-state: {"track_count": N, "source_track_name": name, "source_track_index": idx}
    After-state:  {"track_count": N+1, "new_track_index": idx+1}

    The duplicate is inserted immediately after the source track.
    undo_eligible=False — structural change not reversible via Conductor.

    Raises: BeforeStateCaptureError if before-count unreadable.
    """
    # Step 1: Resolve + capture
    track_idx = _read_track_index(track_identifier, executor)
    if track_idx is None:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        {},
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_TRACK_ABSENT.value,
            "intended_value":      track_identifier,
            "message":             f"Track {track_identifier!r} not found — cannot duplicate.",
        }

    track_name   = _read_string_property(track_idx, "name", executor) or str(track_identifier)
    before_count = _read_track_count(executor)
    if before_count is None:
        raise BeforeStateCaptureError(
            "Cannot read track count from Ableton. "
            "Execution blocked — cannot verify duplication without before_state."
        )
    before_state = {
        "track_count":        before_count,
        "source_track_name":  track_name,
        "source_track_index": track_idx,
    }

    # Step 3: Duplicate
    write_code = f"song.duplicate_track({track_idx})"
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_identifier,
            "message":             f"Executor raised during duplicate: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or "write call returned ok=False"
        err_code = (
            BridgeErrorCode.BRIDGE_TIMEOUT.value
            if "timeout" in str(raw_error).lower()
            else BridgeErrorCode.STATE_VERIFICATION_FAILED.value
        )
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          err_code,
            "intended_value":      track_identifier,
            "message":             f"Duplicate failed: {raw_error}",
        }

    # Step 4: Delay
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # Step 5: After count
    after_count = _read_track_count(executor)
    if after_count is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      track_identifier,
            "message":             (
                "Duplicate sent but track count unreadable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }

    new_idx    = track_idx + 1  # duplicate inserts immediately after source
    after_state = {"track_count": after_count, "new_track_index": new_idx}

    if after_count == before_count + 1:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      track_identifier,
            "message":             (
                f"Track '{track_name}' duplicated. "
                f"New track at index {new_idx}. "
                f"Track count: {before_count} → {after_count}."
            ),
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      track_identifier,
            "message":             (
                f"Track count did not increase as expected "
                f"(before {before_count}, after {after_count})."
            ),
        }


# ── RETURN TRACK CREATE ───────────────────────────────────────────────────────

def verify_return_track_create(
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Create a return track with before/after return-track count verification.

    Before-state: {"return_track_count": N}
    After-state:  {"return_track_count": N+1, "new_return_track_index": N}

    Return tracks appear in song.return_tracks (separate from song.tracks).
    undo_eligible=False — structural change.

    Raises: BeforeStateCaptureError if before-count unreadable.
    """
    before_count = _read_return_track_count(executor)
    if before_count is None:
        raise BeforeStateCaptureError(
            "Cannot read current return track count from Ableton. "
            "Execution blocked — cannot verify creation without before_state."
        )
    before_state = {"return_track_count": before_count}

    write_code = "song.create_return_track()"
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      "return_track",
            "message":             f"Executor raised during create: {exc}",
        }

    if not write_resp.get("ok"):
        raw_error = write_resp.get("error") or ""
        if "timeout" in str(raw_error).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":        before_state,
                "after_state":         {},
                "error_code":          BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value":      "return_track",
                "message":             "Return track create timed out.",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_count = _read_return_track_count(executor)
    if after_count is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      "return_track",
            "message":             (
                "Create sent but return track count unreadable — cannot confirm. "
                "Do not tell the user 'done'."
            ),
        }

    new_idx    = after_count - 1
    after_state = {"return_track_count": after_count, "new_return_track_index": new_idx}

    if after_count == before_count + 1:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      "return_track",
            "message":             f"Return track created at index {new_idx}.",
        }
    else:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      "return_track",
            "message":             (
                f"Return track count did not increase as expected "
                f"(before {before_count}, after {after_count})."
            ),
        }


# ═════════════════════════════════════════════════════════════════════════════
# NEW INTERNAL HELPERS — Action Expansion
# ═════════════════════════════════════════════════════════════════════════════


def _read_integer_property(
    track_identifier: "str | int",
    prop: str,
    executor: Callable,
) -> "Optional[int]":
    """
    Read an integer track property (e.g. current_monitoring_state, color)
    via executor.  Returns int on success, None on any failure.
    """
    code = _build_integer_property_read_code(track_identifier, prop)
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_int(resp)
    except Exception:
        return None


def _read_string_property(
    track_identifier: "str | int",
    prop: str,
    executor: Callable,
) -> "Optional[str]":
    """
    Read a string track property (e.g. name) via executor.
    track_identifier should be an integer index for stable lookup.
    Returns str on success, None on any failure.
    """
    code = _build_string_property_read_code(track_identifier, prop)
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_str(resp)
    except Exception:
        return None


def _read_track_count(executor: Callable) -> "Optional[int]":
    """Read the number of tracks in song.tracks.  Returns int or None."""
    try:
        resp = executor("len(song.tracks)")
        if not resp.get("ok"):
            return None
        return _extract_int(resp)
    except Exception:
        return None


def _read_return_track_count(executor: Callable) -> "Optional[int]":
    """Read the number of return tracks in song.return_tracks.  Returns int or None."""
    try:
        resp = executor("len(song.return_tracks)")
        if not resp.get("ok"):
            return None
        return _extract_int(resp)
    except Exception:
        return None


def _read_track_index(
    track_identifier: "str | int",
    executor: Callable,
) -> "Optional[int]":
    """
    Resolve a track identifier to its 0-based integer index.

    If track_identifier is already an int, validates it is in bounds.
    If track_identifier is a str, finds the first track with that name.
    Returns None if the track is not found or Ableton is unreachable.
    """
    if isinstance(track_identifier, int):
        # Validate index is in bounds
        count = _read_track_count(executor)
        if count is None or track_identifier < 0 or track_identifier >= count:
            return None
        return track_identifier
    # Name-based lookup
    name = str(track_identifier).replace('"', '\\"')
    code = (
        f'next((i for i,t in enumerate(song.tracks) if t.name == "{name}"), None)'
    )
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_int(resp)
    except Exception:
        return None


def _build_integer_property_read_code(
    track_identifier: "str | int",
    prop: str,
) -> str:
    """Build Python code to read an integer track property from Ableton LOM."""
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].{prop}"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'next('
        f'(t.{prop} for t in song.tracks if t.name == "{name}"), '
        f'None'
        f')'
    )


def _build_integer_property_write_code(
    track_identifier: "str | int",
    prop: str,
    value: int,
) -> str:
    """Build Python code to set an integer track property via Ableton LOM."""
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].{prop} = {value}"
    name = str(track_identifier).replace('"', '\\"')
    tmp_var = f"__{prop}_tracks__"
    return (
        f'{tmp_var} = [t for t in song.tracks if t.name == "{name}"]; '
        f'{tmp_var}[0].{prop} = {value} if {tmp_var} else None'
    )


def _build_string_property_read_code(
    track_identifier: "str | int",
    prop: str,
) -> str:
    """Build Python code to read a string track property from Ableton LOM."""
    if isinstance(track_identifier, int):
        return f"song.tracks[{track_identifier}].{prop}"
    name = str(track_identifier).replace('"', '\\"')
    return (
        f'next('
        f'(t.{prop} for t in song.tracks if t.name == "{name}"), '
        f'None'
        f')'
    )


def _build_rename_write_code(track_index: int, new_name: str) -> str:
    """Build Python code to rename a track by index via Ableton LOM."""
    escaped = new_name.replace("\\", "\\\\").replace('"', '\\"')
    return f'song.tracks[{track_index}].name = "{escaped}"'


def _extract_int(resp: dict) -> "Optional[int]":
    """
    Extract an integer value from an executor response.
    Handles both dict-wrapped and direct numeric responses.
    Returns None if value cannot be extracted or coerced to int.
    """
    data = resp.get("data") or {}

    if isinstance(data, dict):
        val = data.get("result")
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                pass
        val2 = data.get("data")
        if val2 is not None:
            try:
                return int(val2)
            except (TypeError, ValueError):
                pass

    if isinstance(data, (int, float)) and not isinstance(data, bool):
        return int(data)

    val_top = resp.get("result")
    if val_top is not None:
        try:
            return int(val_top)
        except (TypeError, ValueError):
            pass

    return None


def _extract_str(resp: dict) -> "Optional[str]":
    """
    Extract a string value from an executor response.
    Returns None if value cannot be extracted or is not string-like.
    """
    data = resp.get("data") or {}

    if isinstance(data, dict):
        val = data.get("result")
        if val is not None and isinstance(val, str):
            return val
        val2 = data.get("data")
        if val2 is not None and isinstance(val2, str):
            return val2

    if isinstance(data, str):
        return data

    val_top = resp.get("result")
    if val_top is not None and isinstance(val_top, str):
        return val_top

    return None


# ── ACTION EXPANSION SLICE 2 ──────────────────────────────────────────────────
# Routing (track output routing), Sends (mixer send levels), and Transport
# (play, stop, loop, metronome, record).
#
# All functions follow the same six-step before/after readback pattern.
# Song-level actions (transport) have no track_identifier.

# ── HELPERS ───────────────────────────────────────────────────────────────────

def _read_song_bool(prop: str, executor: Callable) -> "Optional[bool]":
    """
    Read a boolean song-level property (loop, metronome, is_playing, record_mode).
    Returns bool on success, None on any failure.
    """
    try:
        resp = executor(f"song.{prop}")
        if not resp.get("ok"):
            return None
        return _extract_bool(resp)
    except Exception:
        return None


def _read_send_value(
    track_identifier: "str | int",
    send_idx: int,
    executor: Callable,
) -> "Optional[float]":
    """
    Read a track's send slot level (mixer_device.sends[idx].value).
    Returns float on success, None on any failure.
    """
    if isinstance(track_identifier, int):
        code = (
            f"song.tracks[{track_identifier}].mixer_device.sends[{send_idx}].value"
        )
    else:
        name = str(track_identifier).replace('"', '\\"')
        code = (
            f"next("
            f"(t.mixer_device.sends[{send_idx}].value "
            f"for t in song.tracks "
            f"if t.name == \"{name}\" and len(t.mixer_device.sends) > {send_idx}), "
            f"None)"
        )
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_float(resp)
    except Exception:
        return None


def _read_route_name(
    track_identifier: "str | int",
    executor: Callable,
) -> "Optional[str]":
    """
    Read a track's current output routing display name.
    Returns str on success, None on any failure.
    """
    if isinstance(track_identifier, int):
        code = f"song.tracks[{track_identifier}].output_routing_type.display_name"
    else:
        name = str(track_identifier).replace('"', '\\"')
        code = (
            f"next("
            f"(t.output_routing_type.display_name "
            f"for t in song.tracks if t.name == \"{name}\"), "
            f"None)"
        )
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_str(resp)
    except Exception:
        return None


def _build_send_write_code(
    track_identifier: "str | int",
    send_idx: int,
    value: float,
) -> str:
    """Build Python code to set a track's send slot level via Ableton LOM."""
    if isinstance(track_identifier, int):
        return (
            f"song.tracks[{track_identifier}].mixer_device"
            f".sends[{send_idx}].value = {value!r}"
        )
    name = str(track_identifier).replace('"', '\\"')
    tmp = f"__send_{send_idx}_t__"
    return (
        f"{tmp} = [t for t in song.tracks if t.name == \"{name}\"]; "
        f"{tmp}[0].mixer_device.sends[{send_idx}].value = {value!r} if {tmp} else None"
    )


def _build_route_write_code(
    track_identifier: "str | int",
    routing_name: str,
) -> str:
    """
    Build Python code to set a track's output routing by display name.

    Sets output_routing_type to the matching OutputRoutingType object from
    available_output_routing_types.  If the routing name is not found, the
    existing routing is kept unchanged (no-op assignment).
    """
    esc_r = routing_name.replace("\\", "\\\\").replace('"', '\\"')
    if isinstance(track_identifier, int):
        return (
            f"__rt = next("
            f"(rt for rt in song.tracks[{track_identifier}].available_output_routing_types "
            f"if rt.display_name == \"{esc_r}\"), None); "
            f"song.tracks[{track_identifier}].output_routing_type = "
            f"__rt if __rt is not None else song.tracks[{track_identifier}].output_routing_type"
        )
    esc_n = str(track_identifier).replace("\\", "\\\\").replace('"', '\\"')
    return (
        f"__route_t = next((t for t in song.tracks if t.name == \"{esc_n}\"), None); "
        f"__rt = next("
        f"(rt for rt in __route_t.available_output_routing_types "
        f"if rt.display_name == \"{esc_r}\"), None) if __route_t else None; "
        f"__route_t.output_routing_type = "
        f"__rt if (__route_t and __rt is not None) "
        f"else (__route_t.output_routing_type if __route_t else None)"
    )


# ── TRACK SEND ────────────────────────────────────────────────────────────────

def verify_track_send(
    track_identifier: "str | int",
    send_idx: int,
    value: float,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set a track's send slot level with before/after readback verification.

    Args:
        track_identifier: Track name (str) or 0-based index (int).
        send_idx:         Send slot index (0-based).
        value:            Target send level, normalized 0.0–1.0.
        executor:         ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns: same structure as verify_track_volume, state key "send_value".
    Raises:  BeforeStateCaptureError.
    """
    value_f   = float(value)          # bridge validates range; no silent clamp here
    send_idx  = int(send_idx)

    before_val = _read_send_value(track_identifier, send_idx, executor)
    if before_val is None:
        raise BeforeStateCaptureError(
            f"Cannot read current send[{send_idx}] level for track "
            f"{track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check Ableton is connected, the track exists, and the send index is valid."
        )
    before_state = {"send_value": round(before_val, 6)}

    if abs(before_val - value_f) <= DEFAULT_VOLUME_TOLERANCE:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":  before_state,
            "after_state":   {"send_value": round(before_val, 6)},
            "error_code":    "",
            "intended_value": value_f,
            "message":       f"Send[{send_idx}] was already {before_val:.3f} — no write sent.",
        }

    write_code = _build_send_write_code(track_identifier, send_idx, value_f)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value": value_f,
            "message":       f"Executor raised during send write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":  before_state,
                "after_state":   {},
                "error_code":    BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value": value_f,
                "message":       f"Send write timed out: {raw_err}",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_val = _read_send_value(track_identifier, send_idx, executor)
    if after_val is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value": value_f,
            "message":       "Send write sent but readback unavailable — cannot confirm. Do not tell the user 'done'.",
        }
    after_state = {"send_value": round(after_val, 6)}

    if abs(after_val - value_f) <= DEFAULT_VOLUME_TOLERANCE:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":  before_state,
            "after_state":   after_state,
            "error_code":    "",
            "intended_value": value_f,
            "message":       f"Send[{send_idx}] set to {after_val:.3f}.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":  before_state,
        "after_state":   after_state,
        "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value": value_f,
        "message":       (
            f"Send[{send_idx}] write mismatch: "
            f"expected {value_f:.3f}, got {after_val:.3f}."
        ),
    }


# ── TRACK ROUTE ───────────────────────────────────────────────────────────────

def verify_track_route(
    track_identifier: "str | int",
    routing_name: str,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set a track's output routing with before/after readback verification.

    Routes by display name (e.g. "Master", "DRUM BUS").
    If the requested routing is not in available_output_routing_types, the
    write is a no-op and FAILED is returned (before == after routing).

    Returns: same structure as verify_track_volume, state key "routing".
    Raises:  BeforeStateCaptureError.
    """
    routing_str = str(routing_name).strip()

    before_routing = _read_route_name(track_identifier, executor)
    if before_routing is None:
        raise BeforeStateCaptureError(
            f"Cannot read current output routing for track {track_identifier!r}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected and the track exists."
        )
    before_state = {"routing": before_routing}

    if before_routing == routing_str:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":  before_state,
            "after_state":   {"routing": before_routing},
            "error_code":    "",
            "intended_value": routing_str,
            "message":       f"Output routing was already '{routing_str}' — no write sent.",
        }

    write_code = _build_route_write_code(track_identifier, routing_str)
    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value": routing_str,
            "message":       f"Executor raised during route write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":  before_state,
                "after_state":   {},
                "error_code":    BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value": routing_str,
                "message":       f"Route write timed out: {raw_err}",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_routing = _read_route_name(track_identifier, executor)
    if after_routing is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value": routing_str,
            "message":       "Route write sent but readback unavailable — cannot confirm. Do not tell the user 'done'.",
        }
    after_state = {"routing": after_routing}

    if after_routing == routing_str:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":  before_state,
            "after_state":   after_state,
            "error_code":    "",
            "intended_value": routing_str,
            "message":       f"Output routing set to '{after_routing}'.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":  before_state,
        "after_state":   after_state,
        "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value": routing_str,
        "message":       (
            f"Route write mismatch: expected '{routing_str}', got '{after_routing}'. "
            "Check that the routing name is in available_output_routing_types."
        ),
    }


# ── TRANSPORT (LOOP / METRONOME / PLAY / STOP / RECORD) ──────────────────────

def _verify_song_bool(
    prop: str,
    value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Internal: set song.{prop} (bool) with six-step before/after readback.
    State key equals prop name.
    Raises: BeforeStateCaptureError.
    """
    value_bool = bool(value)

    before_val = _read_song_bool(prop, executor)
    if before_val is None:
        raise BeforeStateCaptureError(
            f"Cannot read current song.{prop}. "
            "Execution blocked — undo would be impossible without before_state. "
            "Check that Ableton is connected."
        )
    before_state = {prop: before_val}

    if before_val == value_bool:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":  before_state,
            "after_state":   {prop: before_val},
            "error_code":    "",
            "intended_value": value_bool,
            "message":       f"song.{prop} was already {value_bool} — no write sent.",
        }

    try:
        write_resp = executor(f"song.{prop} = {value_bool}")
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value": value_bool,
            "message":       f"Executor raised during song.{prop} write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":  before_state,
                "after_state":   {},
                "error_code":    BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value": value_bool,
                "message":       f"song.{prop} write timed out: {raw_err}",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_val = _read_song_bool(prop, executor)
    if after_val is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value": value_bool,
            "message":       f"song.{prop} write sent but readback unavailable — cannot confirm. Do not tell the user 'done'.",
        }
    after_state = {prop: after_val}

    if after_val == value_bool:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":  before_state,
            "after_state":   after_state,
            "error_code":    "",
            "intended_value": value_bool,
            "message":       f"song.{prop} set to {after_val}.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":  before_state,
        "after_state":   after_state,
        "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value": value_bool,
        "message":       f"song.{prop} write failed: expected {value_bool}, got {after_val}.",
    }


def verify_transport_loop(
    value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set song.loop with before/after readback.
    Returns: same structure as verify_track_mute, state key "loop".
    Raises:  BeforeStateCaptureError.
    """
    return _verify_song_bool("loop", value, executor,
                             stabilization_delay=stabilization_delay)


def verify_transport_metronome(
    value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set song.metronome with before/after readback.
    Returns: same structure as verify_track_mute, state key "metronome".
    Raises:  BeforeStateCaptureError.
    """
    return _verify_song_bool("metronome", value, executor,
                             stabilization_delay=stabilization_delay)


def verify_transport_record(
    value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set song.record_mode with before/after readback.
    Returns: same structure as verify_track_mute, state key "record_mode".
    Raises:  BeforeStateCaptureError.
    """
    return _verify_song_bool("record_mode", value, executor,
                             stabilization_delay=stabilization_delay)


def verify_transport_play(
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Start playback via song.start_playing() with before/after readback.

    ALREADY_CORRECT if transport was already playing.
    VERIFIED if is_playing becomes True after the call.
    State key: "is_playing".
    Raises: BeforeStateCaptureError.
    """
    before_playing = _read_song_bool("is_playing", executor)
    if before_playing is None:
        raise BeforeStateCaptureError(
            "Cannot read current song.is_playing. "
            "Check that Ableton is connected."
        )
    before_state = {"is_playing": before_playing}

    if before_playing:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":  before_state,
            "after_state":   {"is_playing": True},
            "error_code":    "",
            "intended_value": True,
            "message":       "Transport was already playing — no write sent.",
        }

    try:
        write_resp = executor("song.start_playing()")
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value": True,
            "message":       f"Executor raised during start_playing: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":  before_state,
                "after_state":   {},
                "error_code":    BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value": True,
                "message":       f"start_playing timed out: {raw_err}",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_playing = _read_song_bool("is_playing", executor)
    if after_playing is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value": True,
            "message":       "Playback started but is_playing could not be confirmed.",
        }
    after_state = {"is_playing": after_playing}

    if after_playing:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":  before_state,
            "after_state":   after_state,
            "error_code":    "",
            "intended_value": True,
            "message":       "Playback started — confirmed.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":  before_state,
        "after_state":   after_state,
        "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value": True,
        "message":       "start_playing() called but is_playing is still False.",
    }


def verify_transport_stop(
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Stop playback via song.stop_playing() with before/after readback.

    ALREADY_CORRECT if transport was already stopped.
    VERIFIED if is_playing becomes False after the call.
    State key: "is_playing".
    Raises: BeforeStateCaptureError.
    """
    before_playing = _read_song_bool("is_playing", executor)
    if before_playing is None:
        raise BeforeStateCaptureError(
            "Cannot read current song.is_playing. "
            "Check that Ableton is connected."
        )
    before_state = {"is_playing": before_playing}

    if not before_playing:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":  before_state,
            "after_state":   {"is_playing": False},
            "error_code":    "",
            "intended_value": False,
            "message":       "Transport was already stopped — no write sent.",
        }

    try:
        write_resp = executor("song.stop_playing()")
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value": False,
            "message":       f"Executor raised during stop_playing: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":  before_state,
                "after_state":   {},
                "error_code":    BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value": False,
                "message":       f"stop_playing timed out: {raw_err}",
            }

    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    after_playing = _read_song_bool("is_playing", executor)
    if after_playing is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":  before_state,
            "after_state":   {},
            "error_code":    BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value": False,
            "message":       "Stop sent but is_playing could not be confirmed.",
        }
    after_state = {"is_playing": after_playing}

    if not after_playing:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":  before_state,
            "after_state":   after_state,
            "error_code":    "",
            "intended_value": False,
            "message":       "Playback stopped — confirmed.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":  before_state,
        "after_state":   after_state,
        "error_code":    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value": False,
        "message":       "stop_playing() called but is_playing is still True.",
    }


# ── ACTION EXPANSION SLICE 3A — PLUGIN BYPASS ─────────────────────────────────
# Bypass / activate a device (stock or third-party) on any track via
# device.is_active (Ableton LOM).  Partial, case-insensitive device name match.

def _read_plugin_bypass(
    track_identifier: "str | int",
    device_name_query: str,
    executor: Callable,
) -> "Optional[bool]":
    """
    Read is_active for the first device whose name contains device_name_query
    (case-insensitive).  Returns bool or None (not found / executor error).
    Used by the undo engine for drift detection.
    """
    query = str(device_name_query).lower()
    if isinstance(track_identifier, int):
        code = (
            f"next((d.is_active for d in song.tracks[{track_identifier}].devices "
            f"if {query!r} in d.name.lower()), None)"
        )
    else:
        esc_n = str(track_identifier).replace('"', '\\"')
        code = (
            f"next(("
            f"next((d.is_active for d in t.devices if {query!r} in d.name.lower()), None) "
            f"for t in song.tracks if t.name == \"{esc_n}\"), "
            f"None)"
        )
    try:
        resp = executor(code)
        if not resp.get("ok"):
            return None
        return _extract_bool(resp)
    except Exception:
        return None


def verify_plugin_bypass(
    track_identifier: "str | int",
    device_name_query: str,
    is_active_value: bool,
    executor: Callable,
    *,
    stabilization_delay: float = DEFAULT_STABILIZATION_DELAY,
) -> dict:
    """
    Set device.is_active with before/after readback verification.

    Finds the first device whose name contains device_name_query
    (case-insensitive substring match).

    Args:
        track_identifier:  Track name (str) or 0-based index (int).
        device_name_query: Partial device name to match (e.g. "Pro-Q", "Compressor").
        is_active_value:   Target is_active state (True=active, False=bypassed).
        executor:          ableton_execute-compatible callable.
        stabilization_delay: Seconds to wait after write.

    Returns: dict with keys:
        verification_status, before_state, after_state, error_code,
        intended_value, matched_device_name, message.

        before_state: {"device_name": str, "is_active": bool}
        after_state:  {"device_name": str, "is_active": bool}
        state_key:    "is_active"

    If device not found: FAILED + BRIDGE_PLUGIN_ABSENT, no write sent.
    Raises: BeforeStateCaptureError if Ableton is unreachable.
    """
    is_active_bool = bool(is_active_value)
    query          = str(device_name_query).lower()

    # ── 1. Find device + read before state (single executor call) ─────────────
    if isinstance(track_identifier, int):
        find_code = (
            f"next(([d.name, i, d.is_active] "
            f"for i, d in enumerate(song.tracks[{track_identifier}].devices) "
            f"if {query!r} in d.name.lower()), None)"
        )
        esc_n = None   # not needed for index-based writes below
    else:
        esc_n = str(track_identifier).replace('"', '\\"')
        find_code = (
            f"next(("
            f"next(([d.name, i, d.is_active] for i, d in enumerate(t.devices) "
            f"if {query!r} in d.name.lower()), None) "
            f"for t in song.tracks if t.name == \"{esc_n}\"), "
            f"None)"
        )

    try:
        find_resp = executor(find_code)
    except Exception as exc:
        raise BeforeStateCaptureError(
            f"Executor raised while finding device on track {track_identifier!r}: {exc}"
        )

    if not find_resp.get("ok"):
        raise BeforeStateCaptureError(
            f"Cannot list devices on track {track_identifier!r}. "
            "Check Ableton is connected and the track exists."
        )

    find_result = find_resp.get("data", {}).get("result")

    # Device not found — result is None or not a 3-element list
    if (find_result is None
            or not isinstance(find_result, (list, tuple))
            or len(find_result) < 3):
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        {},
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_PLUGIN_ABSENT.value,
            "intended_value":      is_active_bool,
            "matched_device_name": None,
            "message": (
                f"No device matching '{device_name_query}' found on track "
                f"{track_identifier!r}. No write sent."
            ),
        }

    matched_name       = str(find_result[0])
    device_idx         = int(find_result[1])
    before_active_raw  = find_result[2]

    if before_active_raw is None:
        raise BeforeStateCaptureError(
            f"Cannot read is_active for device '{matched_name}' on track "
            f"{track_identifier!r}. Execution blocked — undo would be impossible."
        )
    before_active = bool(before_active_raw)
    before_state  = {"device_name": matched_name, "is_active": before_active}

    # ── 2. ALREADY_CORRECT ────────────────────────────────────────────────────
    if before_active == is_active_bool:
        return {
            "verification_status": VerificationStatus.ALREADY_CORRECT.value,
            "before_state":        before_state,
            "after_state":         {"device_name": matched_name, "is_active": before_active},
            "error_code":          "",
            "intended_value":      is_active_bool,
            "matched_device_name": matched_name,
            "message":             (
                f"Device '{matched_name}' is_active was already {is_active_bool} — no write sent."
            ),
        }

    # ── 3. Write ──────────────────────────────────────────────────────────────
    val_str = "True" if is_active_bool else "False"
    if isinstance(track_identifier, int):
        write_code = (
            f"song.tracks[{track_identifier}].devices[{device_idx}].is_active = {val_str}"
        )
    else:
        write_code = (
            f"__bypass_t = next((t for t in song.tracks if t.name == \"{esc_n}\"), None); "
            f"__bypass_t.devices[{device_idx}].is_active = {val_str} if __bypass_t else None"
        )

    try:
        write_resp = executor(write_code)
    except Exception as exc:
        return {
            "verification_status": VerificationStatus.FAILED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
            "intended_value":      is_active_bool,
            "matched_device_name": matched_name,
            "message":             f"Executor raised during bypass write: {exc}",
        }

    if not write_resp.get("ok"):
        raw_err = write_resp.get("error") or ""
        if "timeout" in str(raw_err).lower():
            return {
                "verification_status": VerificationStatus.FAILED.value,
                "before_state":        before_state,
                "after_state":         {},
                "error_code":          BridgeErrorCode.BRIDGE_TIMEOUT.value,
                "intended_value":      is_active_bool,
                "matched_device_name": matched_name,
                "message":             f"Bypass write timed out: {raw_err}",
            }

    # ── 4. Stabilize ──────────────────────────────────────────────────────────
    if stabilization_delay > 0:
        time.sleep(stabilization_delay)

    # ── 5. Read after state ───────────────────────────────────────────────────
    if isinstance(track_identifier, int):
        after_code = (
            f"song.tracks[{track_identifier}].devices[{device_idx}].is_active"
        )
    else:
        after_code = (
            f"next((t.devices[{device_idx}].is_active "
            f"for t in song.tracks if t.name == \"{esc_n}\"), None)"
        )

    try:
        after_resp      = executor(after_code)
        after_active_raw = (
            after_resp.get("data", {}).get("result")
            if after_resp.get("ok") else None
        )
    except Exception:
        after_active_raw = None

    if after_active_raw is None:
        return {
            "verification_status": VerificationStatus.UNVERIFIED.value,
            "before_state":        before_state,
            "after_state":         {},
            "error_code":          BridgeErrorCode.BRIDGE_READBACK_UNAVAILABLE.value,
            "intended_value":      is_active_bool,
            "matched_device_name": matched_name,
            "message":             (
                "Bypass write sent but readback unavailable — "
                "cannot confirm. Do not tell the user 'done'."
            ),
        }

    after_active = bool(after_active_raw)
    after_state  = {"device_name": matched_name, "is_active": after_active}

    # ── 6. Compare ────────────────────────────────────────────────────────────
    if after_active == is_active_bool:
        return {
            "verification_status": VerificationStatus.VERIFIED.value,
            "before_state":        before_state,
            "after_state":         after_state,
            "error_code":          "",
            "intended_value":      is_active_bool,
            "matched_device_name": matched_name,
            "message":             f"Device '{matched_name}' is_active set to {after_active}.",
        }
    return {
        "verification_status": VerificationStatus.FAILED.value,
        "before_state":        before_state,
        "after_state":         after_state,
        "error_code":          BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
        "intended_value":      is_active_bool,
        "matched_device_name": matched_name,
        "message":             (
            f"Bypass write mismatch: expected is_active={is_active_bool}, "
            f"got {after_active}. Device may not support is_active write."
        ),
    }
