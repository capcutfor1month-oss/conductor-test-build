"""
Phase D Slice 1 — Offline Eval Suite
──────────────────────────────────────
Tests for: ActionProof, Black Box Log, Never-Do Preflight,
           Bridge Error Codes, Readback Verification.

All tests run WITHOUT a live Ableton connection.
The executor (ableton_execute) is mocked via lambdas.

Run:
    /Volumes/T7 Shield/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3 \
        tests/phase_d_slice1_eval.py

Sections:
    D1  — ActionProof schema + JSONL persistence       (6 checks)
    D2  — Black box log separation + event types       (6 checks)
    D3  — Never-do preflight decisions                 (9 checks)
    D4  — Bridge error codes + response helpers        (4 checks)
    D5  — Readback: VERIFIED                           (2 checks)
    D6  — Readback: FAILED (write error)               (2 checks)
    D7  — Readback: FAILED (readback mismatch)         (2 checks)
    D8  — Readback: UNVERIFIED                         (2 checks)
    D9  — Readback: ALREADY_CORRECT                    (2 checks)
    D10 — Readback: before-state capture failure       (2 checks)
    D11 — Phase A/B/C eval suites still pass           (1 check)

Total: 38 checks (37 offline + 1 subprocess)
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
    """Mock executor that always returns the given float as the result."""
    def _executor(code):
        return {"ok": True, "data": {"result": value}, "error": None}
    return _executor


def _exec_sequence(*values):
    """
    Mock executor that returns values from the sequence in order.
    First call → values[0], second call → values[1], etc.
    After exhausting the list, returns the last value.
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


def _exec_write_fails():
    """Mock executor where write call (second call) fails."""
    state = {"i": 0}

    def _executor(code):
        i = state["i"]
        state["i"] += 1
        if i == 0:
            return {"ok": True, "data": {"result": 0.7}, "error": None}   # before read
        return {"ok": False, "data": {}, "error": "Ableton MCP timeout"}   # write fails
    return _executor


def _exec_before_state_fails():
    """Mock executor where the first call (before-state read) fails."""
    def _executor(code):
        return {"ok": False, "data": {}, "error": "Ableton not connected"}
    return _executor


# ── SECTION D1: ActionProof ────────────────────────────────────────────────────

def run_action_proof_checks() -> bool:
    print("\n=== Section D1: ActionProof schema + JSONL persistence ===")
    ok = True

    from rag.action_proof import (
        create_proof, read_last_proof, read_all_proofs,
        ActionProof, VerificationStatus, PROOF_LOG_PATH,
    )

    # A — create_proof returns ActionProof with all 14 required fields
    proof = create_proof(
        action_type         = "SET_TRACK_VOLUME",
        target              = "track:Kick",
        intended_value      = 0.85,
        before_state        = {"volume": 0.70},
        after_state         = {"volume": 0.85},
        verification_status = VerificationStatus.VERIFIED,
        undo_eligible       = True,
        user_facing_summary = "Volume set to 0.85 — confirmed.",
        action_id           = "test_action_d1a",
        request_id          = "req_d1a",
        session_id          = "sess_test",
        project_id          = "TestProject",
    )
    REQUIRED_FIELDS = [
        "proof_id", "action_id", "request_id", "session_id", "project_id",
        "timestamp", "action_type", "target", "intended_value", "before_state",
        "after_state", "verification_status", "undo_eligible", "user_facing_summary",
    ]
    d = proof.to_dict()
    missing = [f for f in REQUIRED_FIELDS if f not in d]
    if missing:
        print(f"{FAIL} [D1-A] Missing required fields: {missing}")
        ok = False
    else:
        print(f"{PASS} [D1-A] All 14 required fields present in ActionProof")

    # B — proof is an ActionProof instance
    if not isinstance(proof, ActionProof):
        print(f"{FAIL} [D1-B] create_proof did not return ActionProof instance")
        ok = False
    else:
        print(f"{PASS} [D1-B] create_proof returns ActionProof instance")

    # C — proof_id and action_id are non-empty strings
    if not proof.proof_id or not proof.action_id:
        print(f"{FAIL} [D1-C] proof_id={proof.proof_id!r} action_id={proof.action_id!r}")
        ok = False
    else:
        print(f"{PASS} [D1-C] proof_id and action_id populated")

    # D — proof written to JSONL (read_last_proof returns matching record)
    last = read_last_proof()
    if last is None:
        print(f"{FAIL} [D1-D] ActionProof not written to JSONL (read_last_proof returned None)")
        ok = False
    elif last.get("proof_id") != proof.proof_id:
        print(f"{FAIL} [D1-D] Last proof_id mismatch: {last.get('proof_id')!r} vs {proof.proof_id!r}")
        ok = False
    else:
        print(f"{PASS} [D1-D] ActionProof written to JSONL and readable")

    # E — verification_status is stored correctly
    if proof.verification_status != VerificationStatus.VERIFIED:
        print(f"{FAIL} [D1-E] verification_status wrong: {proof.verification_status!r}")
        ok = False
    else:
        print(f"{PASS} [D1-E] verification_status = VERIFIED stored correctly")

    # F — JSONL path is action_proof_log.jsonl (not context_pack_log.jsonl)
    if "action_proof_log.jsonl" not in PROOF_LOG_PATH:
        print(f"{FAIL} [D1-F] PROOF_LOG_PATH should be action_proof_log.jsonl, got: {PROOF_LOG_PATH}")
        ok = False
    elif "context_pack_log" in PROOF_LOG_PATH:
        print(f"{FAIL} [D1-F] PROOF_LOG_PATH must not be context_pack_log.jsonl")
        ok = False
    else:
        print(f"{PASS} [D1-F] PROOF_LOG_PATH is action_proof_log.jsonl (separate from Phase C)")

    return ok


# ── SECTION D2: Black Box Log ─────────────────────────────────────────────────

def run_black_box_log_checks() -> bool:
    print("\n=== Section D2: Black box log separation + event types ===")
    ok = True

    from rag.black_box_log import (
        log_requested, log_verified, log_failed, log_unverified,
        log_never_do_blocked, read_last_event, read_all_events,
        BBL_LOG_PATH, _PHASE_C_LOG_NAME,
        ACTION_REQUESTED, ACTION_VERIFIED, ACTION_FAILED,
        ACTION_UNVERIFIED, NEVER_DO_BLOCKED,
    )
    from rag.context_pack_logger import LOG_PATH as PHASE_C_LOG_PATH

    # A — black box log path is different from Phase C context_pack_log.jsonl
    if BBL_LOG_PATH == PHASE_C_LOG_PATH:
        print(f"{FAIL} [D2-A] BBL_LOG_PATH must differ from Phase C LOG_PATH")
        ok = False
    elif os.path.basename(BBL_LOG_PATH) == _PHASE_C_LOG_NAME:
        print(f"{FAIL} [D2-A] BBL_LOG_PATH must not be named context_pack_log.jsonl")
        ok = False
    else:
        print(f"{PASS} [D2-A] Black box log is separate from Phase C log")

    # B — log_requested writes ACTION_REQUESTED event
    log_requested("SET_TRACK_VOLUME", "track:TestKick_D2B",
                  request_id="req_d2b", action_id="act_d2b")
    last = read_last_event()
    if last is None or last.get("_type") != ACTION_REQUESTED:
        print(f"{FAIL} [D2-B] Expected ACTION_REQUESTED event, got: {last}")
        ok = False
    else:
        print(f"{PASS} [D2-B] log_requested writes ACTION_REQUESTED event")

    # C — log_verified writes ACTION_VERIFIED event
    log_verified("SET_TRACK_VOLUME", "track:TestKick_D2C",
                 "proof_d2c", "VERIFIED", request_id="req_d2c")
    last = read_last_event()
    if last is None or last.get("_type") != ACTION_VERIFIED:
        print(f"{FAIL} [D2-C] Expected ACTION_VERIFIED event, got: {last}")
        ok = False
    else:
        print(f"{PASS} [D2-C] log_verified writes ACTION_VERIFIED event")

    # D — log_failed writes ACTION_FAILED event
    log_failed("SET_TRACK_VOLUME", "track:TestKick_D2D",
               "STATE_VERIFICATION_FAILED", request_id="req_d2d")
    last = read_last_event()
    if last is None or last.get("_type") != ACTION_FAILED:
        print(f"{FAIL} [D2-D] Expected ACTION_FAILED event, got: {last}")
        ok = False
    else:
        print(f"{PASS} [D2-D] log_failed writes ACTION_FAILED event")

    # E — log_unverified writes ACTION_UNVERIFIED event
    log_unverified("SET_TRACK_VOLUME", "track:TestKick_D2E",
                   "proof_d2e", request_id="req_d2e")
    last = read_last_event()
    if last is None or last.get("_type") != ACTION_UNVERIFIED:
        print(f"{FAIL} [D2-E] Expected ACTION_UNVERIFIED event, got: {last}")
        ok = False
    else:
        print(f"{PASS} [D2-E] log_unverified writes ACTION_UNVERIFIED event")

    # F — log_never_do_blocked writes NEVER_DO_BLOCKED event
    log_never_do_blocked("DELETE_TRACK", "track:TestKick_D2F",
                         "HARD_BLOCK", request_id="req_d2f",
                         rule_text="NEVER delete tracks without confirmation")
    last = read_last_event()
    if last is None or last.get("_type") != NEVER_DO_BLOCKED:
        print(f"{FAIL} [D2-F] Expected NEVER_DO_BLOCKED event, got: {last}")
        ok = False
    else:
        print(f"{PASS} [D2-F] log_never_do_blocked writes NEVER_DO_BLOCKED event")

    return ok


# ── SECTION D3: Never-Do Preflight ────────────────────────────────────────────

def run_never_do_checks() -> bool:
    print("\n=== Section D3: Never-do preflight decisions ===")
    ok = True

    from rag.never_do_check import (
        check, check_allows, is_hard_block,
        NeverDoDecision, _clear_rules_cache,
    )

    _clear_rules_cache()   # ensure clean parse state

    # A — SET_TRACK_VOLUME on normal track → ALLOW
    decision, rule = check("SET_TRACK_VOLUME", {"target": "Kick"})
    if decision != NeverDoDecision.ALLOW:
        print(f"{FAIL} [D3-A] SET_TRACK_VOLUME(Kick) should ALLOW, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-A] SET_TRACK_VOLUME normal track → ALLOW")

    # B — DELETE_TRACK → REQUIRE_CONFIRMATION (moved from HARD_BLOCK in Action Expansion Slice 1)
    decision, rule = check("DELETE_TRACK")
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D3-B] DELETE_TRACK should REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-B] DELETE_TRACK → REQUIRE_CONFIRMATION")

    # C — REMOVE_NOTES → HARD_BLOCK
    decision, rule = check("REMOVE_NOTES")
    if decision != NeverDoDecision.HARD_BLOCK:
        print(f"{FAIL} [D3-C] REMOVE_NOTES should HARD_BLOCK, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-C] REMOVE_NOTES → HARD_BLOCK")

    # D — SET_TEMPO → REQUIRE_CONFIRMATION
    decision, rule = check("SET_TEMPO")
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D3-D] SET_TEMPO should REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-D] SET_TEMPO → REQUIRE_CONFIRMATION")

    # E — WARP_AUDIO → REQUIRE_CONFIRMATION
    decision, rule = check("WARP_AUDIO")
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D3-E] WARP_AUDIO should REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-E] WARP_AUDIO → REQUIRE_CONFIRMATION")

    # F — context override: SET_TRACK_VOLUME targeting "master" → HARD_BLOCK
    decision, rule = check("SET_TRACK_VOLUME", {"target": "master"})
    if decision != NeverDoDecision.HARD_BLOCK:
        print(f"{FAIL} [D3-F] SET_TRACK_VOLUME(master) should HARD_BLOCK, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-F] Context override: target=master escalates to HARD_BLOCK")

    # G — context override: SET_TRACK_VOLUME targeting "Master Bus" → HARD_BLOCK
    decision, rule = check("SET_TRACK_VOLUME", {"target": "Master Bus"})
    if decision != NeverDoDecision.HARD_BLOCK:
        print(f"{FAIL} [D3-G] SET_TRACK_VOLUME(Master Bus) should HARD_BLOCK, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-G] Context override: target='Master Bus' escalates to HARD_BLOCK")

    # H — unknown action type → CLARIFY_REQUIRED
    decision, rule = check("UNKNOWN_ACTION_XYZ_999")
    if decision != NeverDoDecision.CLARIFY_REQUIRED:
        print(f"{FAIL} [D3-H] Unknown action should return CLARIFY_REQUIRED, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-H] Unknown action type → CLARIFY_REQUIRED")

    # I — batch escalation: SET_TRACK_VOLUME with track_count=5 → REQUIRE_CONFIRMATION
    decision, rule = check("SET_TRACK_VOLUME", {"target": "Drum Bus", "track_count": 5})
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D3-I] Batch (track_count=5) should REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D3-I] Batch escalation (track_count > 3) → REQUIRE_CONFIRMATION")

    return ok


# ── SECTION D4: Bridge Error Codes ────────────────────────────────────────────

def run_bridge_error_checks() -> bool:
    print("\n=== Section D4: Bridge error codes + response helpers ===")
    ok = True

    from rag.bridge_errors import BridgeErrorCode, error_response, ok_response

    # A — all expected error codes exist as enum members
    expected = [
        "BRIDGE_TIMEOUT", "BRIDGE_READBACK_UNAVAILABLE",
        "BRIDGE_PARAM_OUT_OF_RANGE", "BRIDGE_TRACK_ABSENT",
        "BRIDGE_PLUGIN_ABSENT", "STATE_VERIFICATION_FAILED",
        "SECURITY_NEVER_DO_BLOCK", "STATE_CAPTURE_FAILED",
    ]
    names = {e.name for e in BridgeErrorCode}
    missing = [e for e in expected if e not in names]
    if missing:
        print(f"{FAIL} [D4-A] Missing BridgeErrorCode members: {missing}")
        ok = False
    else:
        print(f"{PASS} [D4-A] All expected BridgeErrorCode members present")

    # B — error_response sets ok=False + error_code
    resp = error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                          "Track 'Kick' not found", request_id="req_d4b")
    if resp.get("ok") is not False or resp.get("error_code") != "BRIDGE_TRACK_ABSENT":
        print(f"{FAIL} [D4-B] error_response structure wrong: {resp}")
        ok = False
    else:
        print(f"{PASS} [D4-B] error_response returns ok=False + correct error_code")

    # C — ok_response(VERIFIED) → ok=True
    resp = ok_response("proof_d4c", "VERIFIED", before_state={}, after_state={})
    if not resp.get("ok"):
        print(f"{FAIL} [D4-C] ok_response(VERIFIED) should return ok=True")
        ok = False
    else:
        print(f"{PASS} [D4-C] ok_response(VERIFIED) → ok=True")

    # D — ok_response(FAILED) → ok=False
    resp = ok_response("proof_d4d", "FAILED")
    if resp.get("ok") is not False:
        print(f"{FAIL} [D4-D] ok_response(FAILED) should return ok=False")
        ok = False
    else:
        print(f"{PASS} [D4-D] ok_response(FAILED) → ok=False (never say done)")

    return ok


# ── SECTION D5: Readback — VERIFIED ──────────────────────────────────────────

def run_readback_verified_checks() -> bool:
    print("\n=== Section D5: Readback — VERIFIED path ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    # Sequence: before=0.70, write=ok, after=0.85 (matches intended)
    executor = _exec_sequence(0.70, True, 0.85)

    result = verify_track_volume(
        "Kick", 0.85, executor, stabilization_delay=0.0,
    )

    # A — verification_status is VERIFIED
    if result["verification_status"] != VerificationStatus.VERIFIED:
        print(f"{FAIL} [D5-A] Expected VERIFIED, got {result['verification_status']}")
        ok = False
    else:
        print(f"{PASS} [D5-A] Successful write → VERIFIED")

    # B — before_state and after_state are populated
    if not result.get("before_state") or not result.get("after_state"):
        print(f"{FAIL} [D5-B] before_state={result.get('before_state')} after_state={result.get('after_state')}")
        ok = False
    else:
        print(f"{PASS} [D5-B] before_state and after_state populated on VERIFIED")

    return ok


# ── SECTION D6: Readback — FAILED (write error) ───────────────────────────────

def run_readback_write_error_checks() -> bool:
    print("\n=== Section D6: Readback — FAILED (write error) ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    executor = _exec_write_fails()
    result = verify_track_volume(
        "Kick", 0.85, executor, stabilization_delay=0.0,
    )

    # A — verification_status is FAILED (not VERIFIED)
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D6-A] Write error should return FAILED, got {result['verification_status']}")
        ok = False
    else:
        print(f"{PASS} [D6-A] Write executor error → FAILED (never VERIFIED)")

    # B — error_code is set
    if not result.get("error_code"):
        print(f"{FAIL} [D6-B] error_code should be set on FAILED, got empty")
        ok = False
    else:
        print(f"{PASS} [D6-B] error_code present on FAILED: {result['error_code']}")

    return ok


# ── SECTION D7: Readback — FAILED (mismatch) ─────────────────────────────────

def run_readback_mismatch_checks() -> bool:
    print("\n=== Section D7: Readback — FAILED (readback mismatch) ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    # Sequence: before=0.70, write=ok, after=0.71 (does NOT match intended 0.85)
    executor = _exec_sequence(0.70, True, 0.71)
    result = verify_track_volume(
        "Kick", 0.85, executor, stabilization_delay=0.0,
    )

    # A — verification_status is FAILED
    if result["verification_status"] != VerificationStatus.FAILED:
        print(f"{FAIL} [D7-A] Readback mismatch should return FAILED, got {result['verification_status']}")
        ok = False
    else:
        print(f"{PASS} [D7-A] Readback mismatch → FAILED")

    # B — after_state reflects the wrong value (not the intended one)
    after_vol = result.get("after_state", {}).get("volume")
    if after_vol is None or abs(after_vol - 0.85) < 0.01:
        print(f"{FAIL} [D7-B] after_state should show the actual (wrong) value, got {after_vol}")
        ok = False
    else:
        print(f"{PASS} [D7-B] after_state records actual value ({after_vol}) not intended (0.85)")

    return ok


# ── SECTION D8: Readback — UNVERIFIED ─────────────────────────────────────────

def run_readback_unverified_checks() -> bool:
    print("\n=== Section D8: Readback — UNVERIFIED (readback unavailable) ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    # Sequence: before=0.70, write=ok, readback=None (unavailable)
    executor = _exec_sequence(0.70, True, None)
    result = verify_track_volume(
        "Kick", 0.85, executor, stabilization_delay=0.0,
    )

    # A — verification_status is UNVERIFIED
    if result["verification_status"] != VerificationStatus.UNVERIFIED:
        print(f"{FAIL} [D8-A] Readback unavailable should return UNVERIFIED, got {result['verification_status']}")
        ok = False
    else:
        print(f"{PASS} [D8-A] Readback unavailable → UNVERIFIED")

    # B — error_code is BRIDGE_READBACK_UNAVAILABLE
    if result.get("error_code") != "BRIDGE_READBACK_UNAVAILABLE":
        print(f"{FAIL} [D8-B] error_code should be BRIDGE_READBACK_UNAVAILABLE, got {result.get('error_code')!r}")
        ok = False
    else:
        print(f"{PASS} [D8-B] UNVERIFIED carries BRIDGE_READBACK_UNAVAILABLE error_code")

    return ok


# ── SECTION D9: Readback — ALREADY_CORRECT ────────────────────────────────────

def run_readback_already_correct_checks() -> bool:
    print("\n=== Section D9: Readback — ALREADY_CORRECT ===")
    ok = True

    from rag.readback import verify_track_volume
    from rag.action_proof import VerificationStatus

    # before=0.85, intended=0.85 → already correct, no write sent
    executor = _exec_sequence(0.85)   # only one read needed
    result = verify_track_volume(
        "Kick", 0.85, executor, stabilization_delay=0.0, tolerance=0.005,
    )

    # A — verification_status is ALREADY_CORRECT
    if result["verification_status"] != VerificationStatus.ALREADY_CORRECT:
        print(f"{FAIL} [D9-A] Value already at target should return ALREADY_CORRECT, got {result['verification_status']}")
        ok = False
    else:
        print(f"{PASS} [D9-A] Value already at target → ALREADY_CORRECT (no write sent)")

    # B — before_state is populated
    if not result.get("before_state"):
        print(f"{FAIL} [D9-B] before_state should be populated for ALREADY_CORRECT")
        ok = False
    else:
        print(f"{PASS} [D9-B] before_state populated on ALREADY_CORRECT")

    return ok


# ── SECTION D10: Before-state capture failure ─────────────────────────────────

def run_before_state_failure_checks() -> bool:
    print("\n=== Section D10: Before-state capture failure blocks execution ===")
    ok = True

    from rag.readback import verify_track_volume, BeforeStateCaptureError

    executor = _exec_before_state_fails()

    # A — BeforeStateCaptureError is raised (not silently swallowed)
    raised = False
    try:
        result = verify_track_volume(
            "Kick", 0.85, executor, stabilization_delay=0.0,
        )
    except BeforeStateCaptureError:
        raised = True
    except Exception as exc:
        print(f"{FAIL} [D10-A] Wrong exception type raised: {type(exc).__name__}: {exc}")
        ok = False
        return ok

    if not raised:
        print(f"{FAIL} [D10-A] BeforeStateCaptureError should be raised when before_state capture fails")
        ok = False
    else:
        print(f"{PASS} [D10-A] BeforeStateCaptureError raised — execution blocked")

    # B — the error message mentions undo impossibility
    try:
        verify_track_volume("Kick", 0.85, executor, stabilization_delay=0.0)
    except BeforeStateCaptureError as e:
        if "undo" in str(e).lower() or "before_state" in str(e).lower():
            print(f"{PASS} [D10-B] BeforeStateCaptureError message explains undo risk")
        else:
            print(f"{FAIL} [D10-B] Error message should mention undo/before_state: {e}")
            ok = False
    except Exception:
        pass   # already handled in A

    return ok


# ── SECTION D11: Phase A/B/C eval suites still pass ──────────────────────────

def run_phase_c_regression_check() -> bool:
    print("\n=== Section D11: Phase C eval suite regression ===")

    phase_c_script = os.path.join(_ROOT, "tests", "phase_c_eval_set.py")
    python = sys.executable

    if not os.path.exists(phase_c_script):
        print(f"{SKIP} [D11] phase_c_eval_set.py not found — skipped")
        return True

    try:
        result = subprocess.run(
            [python, phase_c_script],
            capture_output=True, text=True, timeout=120,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            print(f"{PASS} [D11] phase_c_eval_set.py passed (Phase A/B/C unchanged)")
            return True
        else:
            print(f"{FAIL} [D11] phase_c_eval_set.py FAILED:")
            # Show last 20 lines of output for diagnosis
            lines = (result.stdout + result.stderr).strip().splitlines()
            for line in lines[-20:]:
                print(f"       {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{FAIL} [D11] phase_c_eval_set.py timed out after 120s")
        return False
    except Exception as exc:
        print(f"{FAIL} [D11] Failed to run phase_c_eval_set.py: {exc}")
        return False


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Conductor — Phase D Slice 1 Eval Suite")
    print("=" * 60)

    t0 = time.time()

    d1_ok  = run_action_proof_checks()
    d2_ok  = run_black_box_log_checks()
    d3_ok  = run_never_do_checks()
    d4_ok  = run_bridge_error_checks()
    d5_ok  = run_readback_verified_checks()
    d6_ok  = run_readback_write_error_checks()
    d7_ok  = run_readback_mismatch_checks()
    d8_ok  = run_readback_unverified_checks()
    d9_ok  = run_readback_already_correct_checks()
    d10_ok = run_before_state_failure_checks()
    d11_ok = run_phase_c_regression_check()

    elapsed = time.time() - t0

    all_pass = all([
        d1_ok, d2_ok, d3_ok, d4_ok, d5_ok,
        d6_ok, d7_ok, d8_ok, d9_ok, d10_ok, d11_ok,
    ])

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    results = [
        ("D1  ActionProof schema + JSONL",           d1_ok),
        ("D2  Black box log separation",              d2_ok),
        ("D3  Never-do preflight (9 checks)",         d3_ok),
        ("D4  Bridge error codes",                    d4_ok),
        ("D5  Readback VERIFIED",                     d5_ok),
        ("D6  Readback FAILED (write error)",         d6_ok),
        ("D7  Readback FAILED (mismatch)",            d7_ok),
        ("D8  Readback UNVERIFIED",                   d8_ok),
        ("D9  Readback ALREADY_CORRECT",              d9_ok),
        ("D10 Before-state capture failure",          d10_ok),
        ("D11 Phase C regression",                    d11_ok),
    ]
    for label, passed in results:
        icon = PASS if passed else FAIL
        print(f"  {icon}  {label}")

    print(f"\n  {'ALL PASS' if all_pass else 'FAILURES DETECTED'}  ({elapsed:.1f}s)")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)
