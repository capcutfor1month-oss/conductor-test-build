"""
Phase D Slice 2 — Offline Eval Suite
──────────────────────────────────────
Tests for: pan/mute/solo readback verification, BBL event correlation,
           error_code on FAILED/UNVERIFIED, no-"done" rule enforcement,
           NEVER_DO_BLOCKED correlation, strict boolean parsing.

All tests run WITHOUT a live Ableton connection.
The executor (ableton_execute) is mocked via closures.

Run:
    /Volumes/T7 Shield/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3 \
        tests/phase_d_slice2_eval.py

Sections:
    D12 — Volume response polish: error_code on FAILED/UNVERIFIED   (4 checks)
    D13 — BBL event correlation: action_id/session_id propagated     (4 checks)
    D14 — Pan: VERIFIED / ALREADY_CORRECT / FAILED / BeforeState    (5 checks)
    D15 — Mute: VERIFIED / ALREADY_CORRECT / FAILED / BeforeState   (5 checks)
    D16 — Solo: VERIFIED / ALREADY_CORRECT / FAILED / BeforeState   (5 checks)
    D17 — No "done" unless VERIFIED or ALREADY_CORRECT               (4 checks)
    D18 — Phase D logs remain separate from Phase C                  (2 checks)
    D19 — Slice 1 tests still pass                                   (1 check)
    D20 — Phase C eval still passes                                  (1 check)
    D21 — NEVER_DO_BLOCKED events include action_id/session_id       (3 checks)
    D22 — Strict boolean parsing (_parse_bool_strict)                (9 checks)

Total: 43 checks (41 offline + 2 subprocess)
"""

import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️ "


# ── MOCK EXECUTORS ─────────────────────────────────────────────────────────────

def _exec_returns(value):
    """Mock executor that always returns the given value as result."""
    def _executor(code):
        return {"ok": True, "data": {"result": value}, "error": None}
    return _executor


def _exec_sequence(*values):
    """
    Mock executor returning values in order.
    None → ok=False (simulates readback unavailable).
    """
    vals = list(values)
    state = {"i": 0}

    def _executor(code):
        idx = min(state["i"], len(vals) - 1)
        state["i"] += 1
        v = vals[idx]
        if v is None:
            return {"ok": False, "data": {}, "error": "readback unavailable (mock)"}
        return {"ok": True, "data": {"result": v}, "error": None}
    return _executor


def _exec_write_fails(before_value):
    """Mock executor where the write call (second call) fails."""
    state = {"i": 0}

    def _executor(code):
        i = state["i"]
        state["i"] += 1
        if i == 0:
            return {"ok": True, "data": {"result": before_value}, "error": None}
        return {"ok": False, "data": {}, "error": "Ableton MCP timeout"}
    return _executor


def _exec_before_state_fails():
    """Mock executor where the first call (before-state read) always fails."""
    def _executor(code):
        return {"ok": False, "data": {}, "error": "Ableton not connected"}
    return _executor


# ── SECTION D12: Volume response polish ────────────────────────────────────────

def run_volume_response_polish_checks() -> bool:
    print("\n=== Section D12: Volume response — error_code on FAILED/UNVERIFIED ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    # A — FAILED (write error) response includes non-empty error_code
    executor = _exec_write_fails(0.7)
    result = verify_track_volume("Kick", 0.85, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D12-A] Expected FAILED, got {result['verification_status']}")
        ok = False
    elif not result.get("error_code"):
        print(f"{FAIL} [D12-A] FAILED response missing error_code: {result}")
        ok = False
    else:
        print(f"{PASS} [D12-A] FAILED response has error_code: {result['error_code']!r}")

    # B — FAILED (readback mismatch) response includes non-empty error_code
    executor = _exec_sequence(0.70, True, 0.71)  # before, write ok, after=wrong
    result = verify_track_volume("Kick", 0.85, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D12-B] Expected FAILED (mismatch), got {result['verification_status']}")
        ok = False
    elif not result.get("error_code"):
        print(f"{FAIL} [D12-B] FAILED mismatch response missing error_code")
        ok = False
    else:
        print(f"{PASS} [D12-B] FAILED (mismatch) response has error_code: {result['error_code']!r}")

    # C — UNVERIFIED response includes error_code = BRIDGE_READBACK_UNAVAILABLE
    executor = _exec_sequence(0.70, True, None)  # before, write ok, readback fails
    result = verify_track_volume("Kick", 0.85, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.UNVERIFIED:
        print(f"{FAIL} [D12-C] Expected UNVERIFIED, got {result['verification_status']}")
        ok = False
    elif result.get("error_code") != "BRIDGE_READBACK_UNAVAILABLE":
        print(f"{FAIL} [D12-C] UNVERIFIED should have BRIDGE_READBACK_UNAVAILABLE, "
              f"got {result.get('error_code')!r}")
        ok = False
    else:
        print(f"{PASS} [D12-C] UNVERIFIED response has error_code=BRIDGE_READBACK_UNAVAILABLE")

    # D — VERIFIED and ALREADY_CORRECT have empty error_code
    executor = _exec_sequence(0.70, True, 0.85)
    result_v = verify_track_volume("Kick", 0.85, executor, stabilization_delay=0.0)
    executor2 = _exec_sequence(0.85)
    result_ac = verify_track_volume("Kick", 0.85, executor2, stabilization_delay=0.0,
                                    tolerance=0.005)
    v_errcode  = result_v.get("error_code", "MISSING")
    ac_errcode = result_ac.get("error_code", "MISSING")
    if v_errcode != "" or ac_errcode != "":
        print(f"{FAIL} [D12-D] VERIFIED error_code={v_errcode!r}, "
              f"ALREADY_CORRECT error_code={ac_errcode!r} — both should be empty")
        ok = False
    else:
        print(f"{PASS} [D12-D] VERIFIED and ALREADY_CORRECT have empty error_code")

    return ok


# ── SECTION D13: BBL event correlation ────────────────────────────────────────

def run_bbl_correlation_checks() -> bool:
    print("\n=== Section D13: BBL event correlation — proof_id/action_id/session_id ===")
    ok = True

    from rag.black_box_log import (
        log_requested, log_verified, log_failed, log_unverified,
        read_last_event, ACTION_REQUESTED, ACTION_VERIFIED,
        ACTION_FAILED, ACTION_UNVERIFIED,
    )

    # A — ACTION_REQUESTED carries action_id and session_id
    log_requested("SET_TRACK_VOLUME", "track:Kick_D13A",
                  request_id="req_d13a", action_id="act_d13a",
                  session_id="sess_d13a")
    last = read_last_event()
    if last is None:
        print(f"{FAIL} [D13-A] No event written")
        ok = False
    elif last.get("action_id") != "act_d13a" or last.get("session_id") != "sess_d13a":
        print(f"{FAIL} [D13-A] action_id={last.get('action_id')!r} "
              f"session_id={last.get('session_id')!r} — expected act_d13a/sess_d13a")
        ok = False
    else:
        print(f"{PASS} [D13-A] ACTION_REQUESTED carries action_id + session_id")

    # B — ACTION_VERIFIED carries proof_id, action_id, session_id
    log_verified("SET_TRACK_VOLUME", "track:Kick_D13B", "proof_d13b",
                 "VERIFIED", request_id="req_d13b",
                 action_id="act_d13b", session_id="sess_d13b")
    last = read_last_event()
    missing = []
    if last.get("proof_id") != "proof_d13b":
        missing.append(f"proof_id={last.get('proof_id')!r}")
    if last.get("action_id") != "act_d13b":
        missing.append(f"action_id={last.get('action_id')!r}")
    if last.get("session_id") != "sess_d13b":
        missing.append(f"session_id={last.get('session_id')!r}")
    if missing:
        print(f"{FAIL} [D13-B] ACTION_VERIFIED missing/wrong: {', '.join(missing)}")
        ok = False
    else:
        print(f"{PASS} [D13-B] ACTION_VERIFIED carries proof_id + action_id + session_id")

    # C — ACTION_FAILED carries proof_id, action_id, session_id
    log_failed("SET_TRACK_VOLUME", "track:Kick_D13C",
               "STATE_VERIFICATION_FAILED",
               proof_id="proof_d13c", request_id="req_d13c",
               action_id="act_d13c", session_id="sess_d13c",
               message="D13C test failure")
    last = read_last_event()
    missing = []
    if last.get("proof_id") != "proof_d13c":
        missing.append(f"proof_id={last.get('proof_id')!r}")
    if last.get("action_id") != "act_d13c":
        missing.append(f"action_id={last.get('action_id')!r}")
    if last.get("session_id") != "sess_d13c":
        missing.append(f"session_id={last.get('session_id')!r}")
    if missing:
        print(f"{FAIL} [D13-C] ACTION_FAILED missing/wrong: {', '.join(missing)}")
        ok = False
    else:
        print(f"{PASS} [D13-C] ACTION_FAILED carries proof_id + action_id + session_id")

    # D — ACTION_UNVERIFIED carries proof_id, action_id, session_id
    log_unverified("SET_TRACK_VOLUME", "track:Kick_D13D", "proof_d13d",
                   request_id="req_d13d",
                   action_id="act_d13d", session_id="sess_d13d")
    last = read_last_event()
    missing = []
    if last.get("proof_id") != "proof_d13d":
        missing.append(f"proof_id={last.get('proof_id')!r}")
    if last.get("action_id") != "act_d13d":
        missing.append(f"action_id={last.get('action_id')!r}")
    if last.get("session_id") != "sess_d13d":
        missing.append(f"session_id={last.get('session_id')!r}")
    if missing:
        print(f"{FAIL} [D13-D] ACTION_UNVERIFIED missing/wrong: {', '.join(missing)}")
        ok = False
    else:
        print(f"{PASS} [D13-D] ACTION_UNVERIFIED carries proof_id + action_id + session_id")

    return ok


# ── SECTION D14: Pan readback ─────────────────────────────────────────────────

def run_pan_readback_checks() -> bool:
    print("\n=== Section D14: Pan readback — VERIFIED / ALREADY_CORRECT / FAILED ===")
    ok = True

    from rag.readback import verify_track_pan, BeforeStateCaptureError
    from rag.action_proof import VerificationStatus

    # A — VERIFIED: before=0.4, write ok, after=0.6 (matches intended)
    executor = _exec_sequence(0.4, True, 0.6)
    result = verify_track_pan("Kick", 0.6, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.VERIFIED:
        print(f"{FAIL} [D14-A] Expected VERIFIED, got {result['verification_status']!r}")
        ok = False
    elif not result.get("before_state") or not result.get("after_state"):
        print(f"{FAIL} [D14-A] before/after_state not populated on VERIFIED pan")
        ok = False
    else:
        print(f"{PASS} [D14-A] Pan VERIFIED — before={result['before_state']}, "
              f"after={result['after_state']}")

    # B — ALREADY_CORRECT: before == intended (within tolerance)
    executor = _exec_sequence(0.5)  # only one read needed
    result = verify_track_pan("Kick", 0.5, executor, stabilization_delay=0.0,
                              tolerance=0.005)
    if result["verification_status"] != VerificationStatus.ALREADY_CORRECT:
        print(f"{FAIL} [D14-B] Expected ALREADY_CORRECT, got {result['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D14-B] Pan ALREADY_CORRECT — no write sent")

    # C — FAILED (write error): error_code must be present
    executor = _exec_write_fails(0.4)
    result = verify_track_pan("Kick", 0.6, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D14-C] Expected FAILED (write error), "
              f"got {result['verification_status']!r}")
        ok = False
    elif not result.get("error_code"):
        print(f"{FAIL} [D14-C] FAILED pan response missing error_code")
        ok = False
    else:
        print(f"{PASS} [D14-C] Pan FAILED (write error) with error_code={result['error_code']!r}")

    # D — FAILED (readback mismatch)
    executor = _exec_sequence(0.4, True, 0.41)  # after != intended 0.6
    result = verify_track_pan("Kick", 0.6, executor, stabilization_delay=0.0)
    after_pan = result.get("after_state", {}).get("pan")
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D14-D] Expected FAILED (mismatch), "
              f"got {result['verification_status']!r}")
        ok = False
    elif after_pan is None or abs(after_pan - 0.6) < 0.01:
        print(f"{FAIL} [D14-D] after_state should show actual wrong value, "
              f"got {after_pan}")
        ok = False
    else:
        print(f"{PASS} [D14-D] Pan FAILED (mismatch) — after={after_pan} ≠ intended 0.6")

    # E — BeforeStateCaptureError raised when before-state unavailable
    executor = _exec_before_state_fails()
    raised = False
    try:
        verify_track_pan("Kick", 0.6, executor, stabilization_delay=0.0)
    except BeforeStateCaptureError:
        raised = True
    except Exception as exc:
        print(f"{FAIL} [D14-E] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
        return ok
    if not raised:
        print(f"{FAIL} [D14-E] BeforeStateCaptureError not raised for pan")
        ok = False
    else:
        print(f"{PASS} [D14-E] BeforeStateCaptureError raised for pan before-state failure")

    return ok


# ── SECTION D15: Mute readback ────────────────────────────────────────────────

def run_mute_readback_checks() -> bool:
    print("\n=== Section D15: Mute readback — VERIFIED / ALREADY_CORRECT / FAILED ===")
    ok = True

    from rag.readback import verify_track_mute, BeforeStateCaptureError
    from rag.action_proof import VerificationStatus

    # A — VERIFIED: before=False (unmuted), intended=True (mute), after=True
    executor = _exec_sequence(False, True, True)
    result = verify_track_mute("Kick", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.VERIFIED:
        print(f"{FAIL} [D15-A] Expected VERIFIED, got {result['verification_status']!r}")
        ok = False
    elif result.get("after_state", {}).get("mute") is not True:
        print(f"{FAIL} [D15-A] after_state.mute should be True, "
              f"got {result.get('after_state')}")
        ok = False
    else:
        print(f"{PASS} [D15-A] Mute VERIFIED — track muted, after_state.mute=True")

    # B — ALREADY_CORRECT: track is already muted, intended=True
    executor = _exec_sequence(True)
    result = verify_track_mute("Kick", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.ALREADY_CORRECT:
        print(f"{FAIL} [D15-B] Expected ALREADY_CORRECT, "
              f"got {result['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D15-B] Mute ALREADY_CORRECT — already muted, no write sent")

    # C — FAILED (write error): error_code must be present
    executor = _exec_write_fails(False)  # before=False, write=fail
    result = verify_track_mute("Kick", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D15-C] Expected FAILED, got {result['verification_status']!r}")
        ok = False
    elif not result.get("error_code"):
        print(f"{FAIL} [D15-C] FAILED mute response missing error_code")
        ok = False
    else:
        print(f"{PASS} [D15-C] Mute FAILED (write error) with error_code={result['error_code']!r}")

    # D — FAILED (readback mismatch): write ok but after != intended
    # before=False, write ok, after=False (didn't change to True)
    executor = _exec_sequence(False, True, False)
    result = verify_track_mute("Kick", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D15-D] Expected FAILED (mismatch), "
              f"got {result['verification_status']!r}")
        ok = False
    elif result.get("after_state", {}).get("mute") is not False:
        print(f"{FAIL} [D15-D] after_state.mute should be False (actual value), "
              f"got {result.get('after_state')}")
        ok = False
    else:
        print(f"{PASS} [D15-D] Mute FAILED (mismatch) — after=False ≠ intended True")

    # E — BeforeStateCaptureError raised when before-state unavailable
    executor = _exec_before_state_fails()
    raised = False
    try:
        verify_track_mute("Kick", True, executor, stabilization_delay=0.0)
    except BeforeStateCaptureError:
        raised = True
    except Exception as exc:
        print(f"{FAIL} [D15-E] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
        return ok
    if not raised:
        print(f"{FAIL} [D15-E] BeforeStateCaptureError not raised for mute")
        ok = False
    else:
        print(f"{PASS} [D15-E] BeforeStateCaptureError raised for mute before-state failure")

    return ok


# ── SECTION D16: Solo readback ────────────────────────────────────────────────

def run_solo_readback_checks() -> bool:
    print("\n=== Section D16: Solo readback — VERIFIED / ALREADY_CORRECT / FAILED ===")
    ok = True

    from rag.readback import verify_track_solo, BeforeStateCaptureError
    from rag.action_proof import VerificationStatus

    # A — VERIFIED: before=False (not soloed), intended=True (solo), after=True
    executor = _exec_sequence(False, True, True)
    result = verify_track_solo("Lead", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.VERIFIED:
        print(f"{FAIL} [D16-A] Expected VERIFIED, got {result['verification_status']!r}")
        ok = False
    elif result.get("after_state", {}).get("solo") is not True:
        print(f"{FAIL} [D16-A] after_state.solo should be True, "
              f"got {result.get('after_state')}")
        ok = False
    else:
        print(f"{PASS} [D16-A] Solo VERIFIED — track soloed, after_state.solo=True")

    # B — ALREADY_CORRECT: track already not soloed, intended=False
    executor = _exec_sequence(False)
    result = verify_track_solo("Lead", False, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.ALREADY_CORRECT:
        print(f"{FAIL} [D16-B] Expected ALREADY_CORRECT, "
              f"got {result['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D16-B] Solo ALREADY_CORRECT — already unsoloed, no write sent")

    # C — FAILED (write error): error_code must be present
    executor = _exec_write_fails(False)
    result = verify_track_solo("Lead", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D16-C] Expected FAILED, got {result['verification_status']!r}")
        ok = False
    elif not result.get("error_code"):
        print(f"{FAIL} [D16-C] FAILED solo response missing error_code")
        ok = False
    else:
        print(f"{PASS} [D16-C] Solo FAILED (write error) with error_code={result['error_code']!r}")

    # D — FAILED (readback mismatch)
    executor = _exec_sequence(False, True, False)  # after stayed False
    result = verify_track_solo("Lead", True, executor, stabilization_delay=0.0)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D16-D] Expected FAILED (mismatch), "
              f"got {result['verification_status']!r}")
        ok = False
    elif result.get("after_state", {}).get("solo") is not False:
        print(f"{FAIL} [D16-D] after_state.solo should be False (actual), "
              f"got {result.get('after_state')}")
        ok = False
    else:
        print(f"{PASS} [D16-D] Solo FAILED (mismatch) — after=False ≠ intended True")

    # E — BeforeStateCaptureError raised when before-state unavailable
    executor = _exec_before_state_fails()
    raised = False
    try:
        verify_track_solo("Lead", True, executor, stabilization_delay=0.0)
    except BeforeStateCaptureError:
        raised = True
    except Exception as exc:
        print(f"{FAIL} [D16-E] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
        return ok
    if not raised:
        print(f"{FAIL} [D16-E] BeforeStateCaptureError not raised for solo")
        ok = False
    else:
        print(f"{PASS} [D16-E] BeforeStateCaptureError raised for solo before-state failure")

    return ok


# ── SECTION D17: No "done" unless VERIFIED or ALREADY_CORRECT ────────────────

def run_no_done_checks() -> bool:
    print("\n=== Section D17: ok=False on FAILED/UNVERIFIED (never say done) ===")
    ok = True

    from rag.bridge_errors import ok_response

    # A — ok_response(VERIFIED) → ok=True
    resp = ok_response("proof_d17a", "VERIFIED")
    if not resp.get("ok"):
        print(f"{FAIL} [D17-A] ok_response(VERIFIED) should return ok=True")
        ok = False
    else:
        print(f"{PASS} [D17-A] VERIFIED → ok=True (may say done)")

    # B — ok_response(ALREADY_CORRECT) → ok=True
    resp = ok_response("proof_d17b", "ALREADY_CORRECT")
    if not resp.get("ok"):
        print(f"{FAIL} [D17-B] ok_response(ALREADY_CORRECT) should return ok=True")
        ok = False
    else:
        print(f"{PASS} [D17-B] ALREADY_CORRECT → ok=True (may say done)")

    # C — ok_response(FAILED) → ok=False
    resp = ok_response("proof_d17c", "FAILED")
    if resp.get("ok") is not False:
        print(f"{FAIL} [D17-C] ok_response(FAILED) should return ok=False")
        ok = False
    else:
        print(f"{PASS} [D17-C] FAILED → ok=False (must not say done)")

    # D — ok_response(UNVERIFIED) → ok=False
    resp = ok_response("proof_d17d", "UNVERIFIED")
    if resp.get("ok") is not False:
        print(f"{FAIL} [D17-D] ok_response(UNVERIFIED) should return ok=False")
        ok = False
    else:
        print(f"{PASS} [D17-D] UNVERIFIED → ok=False (must not say done)")

    return ok


# ── SECTION D18: Phase D logs remain separate from Phase C ───────────────────

def run_log_separation_checks() -> bool:
    print("\n=== Section D18: Phase D logs separate from Phase C ===")
    ok = True

    from rag.black_box_log import BBL_LOG_PATH, _PHASE_C_LOG_NAME
    from rag.action_proof import PROOF_LOG_PATH

    # A — BBL action_log.jsonl is not context_pack_log.jsonl
    if os.path.basename(BBL_LOG_PATH) == _PHASE_C_LOG_NAME:
        print(f"{FAIL} [D18-A] BBL_LOG_PATH must not be context_pack_log.jsonl, "
              f"got: {BBL_LOG_PATH}")
        ok = False
    elif "action_log" not in BBL_LOG_PATH:
        print(f"{FAIL} [D18-A] BBL_LOG_PATH should contain 'action_log', "
              f"got: {BBL_LOG_PATH}")
        ok = False
    else:
        print(f"{PASS} [D18-A] BBL log is action_log.jsonl (separate from Phase C)")

    # B — ActionProof log is action_proof_log.jsonl (not context_pack_log.jsonl)
    if _PHASE_C_LOG_NAME in PROOF_LOG_PATH:
        print(f"{FAIL} [D18-B] PROOF_LOG_PATH must not be context_pack_log.jsonl, "
              f"got: {PROOF_LOG_PATH}")
        ok = False
    elif "action_proof_log" not in PROOF_LOG_PATH:
        print(f"{FAIL} [D18-B] PROOF_LOG_PATH should contain 'action_proof_log', "
              f"got: {PROOF_LOG_PATH}")
        ok = False
    else:
        print(f"{PASS} [D18-B] ActionProof log is action_proof_log.jsonl (separate from Phase C)")

    return ok


# ── SECTION D19: Slice 1 tests still pass ────────────────────────────────────

def run_slice1_regression_check() -> bool:
    print("\n=== Section D19: Slice 1 eval suite regression ===")

    slice1_script = os.path.join(_ROOT, "tests", "phase_d_slice1_eval.py")
    python = sys.executable

    if not os.path.exists(slice1_script):
        print(f"{SKIP} [D19] phase_d_slice1_eval.py not found — skipped")
        return True

    try:
        result = subprocess.run(
            [python, slice1_script],
            capture_output=True, text=True, timeout=180,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            print(f"{PASS} [D19] phase_d_slice1_eval.py passed (Slice 1 unchanged)")
            return True
        else:
            print(f"{FAIL} [D19] phase_d_slice1_eval.py FAILED:")
            lines = (result.stdout + result.stderr).strip().splitlines()
            for line in lines[-20:]:
                print(f"       {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{FAIL} [D19] phase_d_slice1_eval.py timed out after 180s")
        return False
    except Exception as exc:
        print(f"{FAIL} [D19] Failed to run phase_d_slice1_eval.py: {exc}")
        return False


# ── SECTION D20: Phase C eval still passes ───────────────────────────────────

def run_phase_c_regression_check() -> bool:
    print("\n=== Section D20: Phase C eval suite regression ===")

    phase_c_script = os.path.join(_ROOT, "tests", "phase_c_eval_set.py")
    python = sys.executable

    if not os.path.exists(phase_c_script):
        print(f"{SKIP} [D20] phase_c_eval_set.py not found — skipped")
        return True

    try:
        result = subprocess.run(
            [python, phase_c_script],
            capture_output=True, text=True, timeout=120,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            print(f"{PASS} [D20] phase_c_eval_set.py passed (Phase A/B/C unchanged)")
            return True
        else:
            print(f"{FAIL} [D20] phase_c_eval_set.py FAILED:")
            lines = (result.stdout + result.stderr).strip().splitlines()
            for line in lines[-20:]:
                print(f"       {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{FAIL} [D20] phase_c_eval_set.py timed out after 120s")
        return False
    except Exception as exc:
        print(f"{FAIL} [D20] Failed to run phase_c_eval_set.py: {exc}")
        return False


# ── SECTION D21: NEVER_DO_BLOCKED event correlation ──────────────────────────

def run_never_do_blocked_correlation_checks() -> bool:
    print("\n=== Section D21: NEVER_DO_BLOCKED events include action_id/session_id ===")
    ok = True

    from rag.black_box_log import (
        log_never_do_blocked, read_last_event, NEVER_DO_BLOCKED,
    )

    # A — log_never_do_blocked writes action_id into event
    log_never_do_blocked(
        "DELETE_TRACK", "track:Kick_D21A", "HARD_BLOCK",
        request_id="req_d21a", action_id="act_d21a",
        session_id="sess_d21a", rule_text="NEVER delete tracks",
    )
    last = read_last_event()
    if last is None or last.get("_type") != NEVER_DO_BLOCKED:
        print(f"{FAIL} [D21-A] Expected NEVER_DO_BLOCKED event, got: {last}")
        ok = False
    elif last.get("action_id") != "act_d21a":
        print(f"{FAIL} [D21-A] action_id wrong: "
              f"got {last.get('action_id')!r}, expected 'act_d21a'")
        ok = False
    else:
        print(f"{PASS} [D21-A] NEVER_DO_BLOCKED event carries action_id")

    # B — log_never_do_blocked writes session_id into event
    if last is None or last.get("session_id") != "sess_d21a":
        print(f"{FAIL} [D21-B] session_id wrong: "
              f"got {last.get('session_id') if last else None!r}, expected 'sess_d21a'")
        ok = False
    else:
        print(f"{PASS} [D21-B] NEVER_DO_BLOCKED event carries session_id")

    # C — proof_id is absent/empty on NEVER_DO_BLOCKED (no proof for blocked actions)
    if last is None:
        print(f"{FAIL} [D21-C] No event to check proof_id on")
        ok = False
    elif last.get("proof_id"):
        print(f"{FAIL} [D21-C] NEVER_DO_BLOCKED should have empty proof_id "
              f"(blocked actions have no proof), got {last.get('proof_id')!r}")
        ok = False
    else:
        print(f"{PASS} [D21-C] NEVER_DO_BLOCKED has no proof_id (correct — blocked before proof)")

    return ok


# ── SECTION D22: Strict boolean parsing ──────────────────────────────────────

def run_strict_bool_parsing_checks() -> bool:
    print("\n=== Section D22: _parse_bool_strict — safe boolean coercion ===")
    ok = True

    # Import the helper from bridge tools
    sys.path.insert(0, os.path.join(_ROOT, "tools"))
    try:
        from conductor_bridge import _parse_bool_strict
    except ImportError as e:
        print(f"{FAIL} [D22] Cannot import _parse_bool_strict from conductor_bridge: {e}")
        return False

    # ── Accepted values ────────────────────────────────────────────────────────

    # A — JSON true (Python bool True) → True
    val, err = _parse_bool_strict(True, "mute")
    if val is not True or err:
        print(f"{FAIL} [D22-A] True → {val!r}, err={err!r} (expected True, '')")
        ok = False
    else:
        print(f"{PASS} [D22-A] JSON true (Python bool True) → True")

    # B — JSON false (Python bool False) → False  [the critical bug case]
    val, err = _parse_bool_strict(False, "mute")
    if val is not False or err:
        print(f"{FAIL} [D22-B] False → {val!r}, err={err!r} (expected False, '')")
        ok = False
    else:
        print(f"{PASS} [D22-B] JSON false (Python bool False) → False  "
              f"[note: bool(False)=False but bool('false')=True — parser handles this]")

    # C — string "false" → False  (safe string path)
    val, err = _parse_bool_strict("false", "mute")
    if val is not False or err:
        print(f"{FAIL} [D22-C] 'false' → {val!r}, err={err!r} (expected False, '')")
        ok = False
    else:
        print(f"{PASS} [D22-C] String 'false' → False  (not True as bool() would give)")

    # D — string "true" → True
    val, err = _parse_bool_strict("true", "solo")
    if val is not True or err:
        print(f"{FAIL} [D22-D] 'true' → {val!r}, err={err!r} (expected True, '')")
        ok = False
    else:
        print(f"{PASS} [D22-D] String 'true' → True")

    # ── Rejected values ────────────────────────────────────────────────────────

    # E — string "yes" → error (not accepted)
    val, err = _parse_bool_strict("yes", "mute")
    if val is not None or not err:
        print(f"{FAIL} [D22-E] 'yes' should be rejected, got val={val!r} err={err!r}")
        ok = False
    else:
        print(f"{PASS} [D22-E] String 'yes' rejected with error")

    # F — string "0" → error (not accepted)
    val, err = _parse_bool_strict("0", "mute")
    if val is not None or not err:
        print(f"{FAIL} [D22-F] '0' should be rejected, got val={val!r} err={err!r}")
        ok = False
    else:
        print(f"{PASS} [D22-F] String '0' rejected with error")

    # G — integer 1 → error (not accepted — would silently become True with bool())
    val, err = _parse_bool_strict(1, "mute")
    if val is not None or not err:
        print(f"{FAIL} [D22-G] Integer 1 should be rejected, got val={val!r} err={err!r}")
        ok = False
    else:
        print(f"{PASS} [D22-G] Integer 1 rejected (not a bool, even though bool(1)==True)")

    # H — integer 0 → error
    val, err = _parse_bool_strict(0, "mute")
    if val is not None or not err:
        print(f"{FAIL} [D22-H] Integer 0 should be rejected, got val={val!r} err={err!r}")
        ok = False
    else:
        print(f"{PASS} [D22-H] Integer 0 rejected (not a bool)")

    # I — empty string → error
    val, err = _parse_bool_strict("", "solo")
    if val is not None or not err:
        print(f"{FAIL} [D22-I] Empty string should be rejected, got val={val!r} err={err!r}")
        ok = False
    else:
        print(f"{PASS} [D22-I] Empty string rejected with error")

    return ok


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Conductor — Phase D Slice 2 Eval Suite")
    print("=" * 60)

    t0 = time.time()

    d12_ok = run_volume_response_polish_checks()
    d13_ok = run_bbl_correlation_checks()
    d14_ok = run_pan_readback_checks()
    d15_ok = run_mute_readback_checks()
    d16_ok = run_solo_readback_checks()
    d17_ok = run_no_done_checks()
    d18_ok = run_log_separation_checks()
    d19_ok = run_slice1_regression_check()
    d20_ok = run_phase_c_regression_check()
    d21_ok = run_never_do_blocked_correlation_checks()
    d22_ok = run_strict_bool_parsing_checks()

    elapsed = time.time() - t0

    all_pass = all([
        d12_ok, d13_ok, d14_ok, d15_ok, d16_ok,
        d17_ok, d18_ok, d19_ok, d20_ok, d21_ok, d22_ok,
    ])

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    results = [
        ("D12  Volume response: error_code on FAILED/UNVERIFIED",       d12_ok),
        ("D13  BBL correlation: proof_id/action_id/session_id",         d13_ok),
        ("D14  Pan VERIFIED / ALREADY_CORRECT / FAILED (5 checks)",     d14_ok),
        ("D15  Mute VERIFIED / ALREADY_CORRECT / FAILED (5 checks)",    d15_ok),
        ("D16  Solo VERIFIED / ALREADY_CORRECT / FAILED (5 checks)",    d16_ok),
        ("D17  No 'done' unless VERIFIED/ALREADY_CORRECT (4 checks)",   d17_ok),
        ("D18  Phase D logs separate from Phase C",                      d18_ok),
        ("D19  Slice 1 regression",                                      d19_ok),
        ("D20  Phase C regression",                                      d20_ok),
        ("D21  NEVER_DO_BLOCKED correlation (3 checks)",                 d21_ok),
        ("D22  Strict boolean parsing (9 checks)",                       d22_ok),
    ]
    for label, passed in results:
        icon = PASS if passed else FAIL
        print(f"  {icon}  {label}")

    print(f"\n  {'ALL PASS' if all_pass else 'FAILURES DETECTED'}  ({elapsed:.1f}s)")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)
