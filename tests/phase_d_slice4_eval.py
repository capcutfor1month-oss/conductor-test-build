"""
Conductor — Phase D Slice 4 Eval Suite
───────────────────────────────────────
Offline tests for compensating undo with drift detection.
No Ableton MCP connection required — all Ableton calls are mocked.
No ChromaDB required — no Phase C code touched.

Sections:
    D31  Undo success creates new proof, original proof unchanged (5 checks)
    D32  FAILED/UNVERIFIED proof cannot be undone (4 checks)
    D33  Unsupported action_type rejected (5 checks)
    D34  Empty before_state rejected (2 checks)
    D35  Drift detection — blocks write; confirm=True overrides (6 checks)
    D36  Undo proof fields correct (UNDO_ prefix, undo_eligible=False) (5 checks)
    D37  Slice 1+2+3 regressions (1 check)
    D38  Phase C regression (1 check)
    D39  Drift read unavailable → fail closed, no write (4 checks)
    D40  Missing after_state[key] rejected before mutation (4 checks)

Total: 35 checks
"""

import os
import sys
import subprocess
import tempfile
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)


# ── MOCK EXECUTOR ─────────────────────────────────────────────────────────────

class _FixedSequence:
    """
    Mock executor that returns a fixed sequence of responses in order,
    cycling back to the last element once the list is exhausted.

    Each element is either:
        {"ok": True/False, "data": {"result": value}, "error": None}
    or a callable(code) → dict for conditional logic.
    """
    def __init__(self, responses: list):
        self._resp  = responses
        self._calls = 0

    def __call__(self, code: str) -> dict:
        idx  = min(self._calls, len(self._resp) - 1)
        resp = self._resp[idx]
        self._calls += 1
        if callable(resp):
            return resp(code)
        return resp


def _ok(value):
    """Return an ok executor response with the given value at data['result']."""
    return {"ok": True, "data": {"result": value}, "error": None}

def _err(msg="write failed"):
    """Return a failed executor response."""
    return {"ok": False, "data": {}, "error": msg}


# ── PROOF FACTORIES ───────────────────────────────────────────────────────────

def _make_proof(
    action_type        = "SET_TRACK_VOLUME",
    vstat              = "VERIFIED",
    before_value       = 0.8,
    after_value        = 0.5,
    state_key          = "volume",
    target             = "track:Kick",
):
    """Build a minimal proof dict as returned by read_all_proofs()."""
    return {
        "proof_id":            uuid.uuid4().hex[:16],
        "action_id":           uuid.uuid4().hex[:12],
        "request_id":          "req_test",
        "session_id":          "sess_test",
        "project_id":          "TestProject",
        "timestamp":           "2026-01-01T00:00:00Z",
        "action_type":         action_type,
        "target":              target,
        "intended_value":      after_value,
        "before_state":        {state_key: before_value},
        "after_state":         {state_key: after_value},
        "verification_status": vstat,
        "undo_eligible":       True,
        "user_facing_summary": f"Test proof for {action_type}",
    }


# ── SECTION D31: Undo success ─────────────────────────────────────────────────

def run_d31():
    """Undo success: new proof created, correct fields, original unchanged."""
    print("\n=== Section D31: Undo success creates new ActionProof ===")
    from rag.undo_engine    import execute_undo
    from rag.action_proof   import create_proof, read_all_proofs, VerificationStatus

    passed = failed = 0

    # Original proof: volume set 0.8 → 0.5 — written to the actual JSONL log
    orig = create_proof(
        action_type         = "SET_TRACK_VOLUME",
        target              = "track:Kick",
        intended_value      = 0.5,
        before_state        = {"volume": 0.8},
        after_state         = {"volume": 0.5},
        verification_status = VerificationStatus.VERIFIED.value,
        undo_eligible       = True,
        user_facing_summary = "D31 seed proof",
        action_id           = "d31_action_" + uuid.uuid4().hex[:8],
        request_id          = "req_d31_seed",
        session_id          = "sess_d31",
        project_id          = "TestProject",
    )
    proof = orig.to_dict()
    original_id = orig.proof_id

    # Executor sequence:
    #   [0] drift check:  current=0.5 (matches after_state → no drift)
    #   [1] verify before: current=0.5
    #   [2] write:         ok
    #   [3] verify after:  current=0.8 (restored)
    exec_mock = _FixedSequence([
        _ok(0.5),   # drift check
        _ok(0.5),   # readback before-state inside verify_track_volume
        _ok(None),  # write response (value not checked)
        _ok(0.8),   # readback after-state
    ])

    result = execute_undo(
        proof, exec_mock,
        confirm=False, stabilization_delay=0.0,
        request_id="req_d31", session_id="sess_d31",
    )

    ok = result["ok"]
    print(f"  {'✅' if ok else '❌'} [D31-A] execute_undo returns ok=True")
    if ok: passed += 1
    else:  failed += 1

    undo_proof = result.get("undo_proof")
    has_proof = undo_proof is not None
    print(f"  {'✅' if has_proof else '❌'} [D31-B] result contains undo_proof")
    if has_proof: passed += 1
    else:         failed += 1

    drift_false = not result.get("drift_detected", True)
    print(f"  {'✅' if drift_false else '❌'} [D31-C] drift_detected=False (no drift)")
    if drift_false: passed += 1
    else:           failed += 1

    # Verify original proof is still in log, unchanged
    all_proofs = read_all_proofs()
    orig = next((p for p in all_proofs if p.get("proof_id") == original_id), None)
    orig_ok = orig is not None and orig.get("verification_status") == "VERIFIED"
    print(f"  {'✅' if orig_ok else '❌'} [D31-D] original proof present and unchanged in log")
    if orig_ok: passed += 1
    else:       failed += 1

    vstat_ok = result.get("verification_status") in ("VERIFIED", "ALREADY_CORRECT")
    print(f"  {'✅' if vstat_ok else '❌'} [D31-E] verification_status is VERIFIED or ALREADY_CORRECT")
    if vstat_ok: passed += 1
    else:        failed += 1

    print(f"\n  D31 Undo success: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D32: FAILED/UNVERIFIED proof rejected ────────────────────────────

def run_d32():
    """FAILED and UNVERIFIED proofs cannot be undone."""
    print("\n=== Section D32: FAILED/UNVERIFIED original proof cannot be undone ===")
    from rag.undo_engine  import execute_undo, UndoValidationError
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0
    exec_mock = _FixedSequence([_ok(0.5)])  # should never be called

    for vstat in ("FAILED", "UNVERIFIED", "PARTIAL"):
        proof = _make_proof(vstat=vstat)
        try:
            execute_undo(proof, exec_mock, stabilization_delay=0.0)
            ok = False
            detail = "no exception raised"
        except UndoValidationError as uve:
            ok = uve.bridge_error_code == BridgeErrorCode.UNDO_NOT_ELIGIBLE
            detail = str(uve.bridge_error_code)
        except Exception as exc:
            ok = False
            detail = f"wrong exception: {exc}"
        print(f"  {'✅' if ok else '❌'} [D32] vstat={vstat!r} → UNDO_NOT_ELIGIBLE ({detail})")
        if ok: passed += 1
        else:  failed += 1

    # Confirm ALREADY_CORRECT IS allowed
    proof_ac = _make_proof(vstat="ALREADY_CORRECT")
    exec_ac = _FixedSequence([
        _ok(0.5), _ok(0.5), _ok(None), _ok(0.8),
    ])
    try:
        r = execute_undo(proof_ac, exec_ac, stabilization_delay=0.0)
        ac_ok = True   # no exception → eligible
    except UndoValidationError:
        ac_ok = False
    print(f"  {'✅' if ac_ok else '❌'} [D32] ALREADY_CORRECT proof IS eligible (no exception)")
    if ac_ok: passed += 1
    else:     failed += 1

    print(f"\n  D32 FAILED/UNVERIFIED rejected: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D33: Unsupported action type ─────────────────────────────────────

def run_d33():
    """Unsupported action_type raises UNDO_UNSUPPORTED_ACTION."""
    print("\n=== Section D33: Unsupported action type rejected ===")
    from rag.undo_engine   import execute_undo, UndoValidationError
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0
    exec_mock = _FixedSequence([_ok(0.5)])

    unsupported = [
        "SET_MASTER_VOLUME",
        "SET_PLUGIN_PARAM",
        "LOAD_INSTRUMENT",
        "UNKNOWN_ACTION",
    ]

    for atype in unsupported:
        proof = _make_proof(action_type=atype)
        try:
            execute_undo(proof, exec_mock, stabilization_delay=0.0)
            ok = False
        except UndoValidationError as uve:
            ok = uve.bridge_error_code == BridgeErrorCode.UNDO_UNSUPPORTED_ACTION
        except Exception:
            ok = False
        print(f"  {'✅' if ok else '❌'} [D33] {atype!r} → UNDO_UNSUPPORTED_ACTION")
        if ok: passed += 1
        else:  failed += 1

    # All four supported types must NOT raise UNDO_UNSUPPORTED_ACTION
    supported_checks = 0
    for atype, sk, bv, av in [
        ("SET_TRACK_VOLUME", "volume", 0.8, 0.5),
        ("SET_TRACK_PAN",    "pan",    0.5, 0.3),
        ("SET_TRACK_MUTE",   "mute",   False, True),
        ("SET_TRACK_SOLO",   "solo",   False, True),
    ]:
        proof = _make_proof(action_type=atype, state_key=sk,
                            before_value=bv, after_value=av)
        exec2 = _FixedSequence([_ok(av), _ok(av), _ok(None), _ok(bv)])
        try:
            execute_undo(proof, exec2, stabilization_delay=0.0)
            supported_checks += 1
        except UndoValidationError as uve:
            if uve.bridge_error_code != BridgeErrorCode.UNDO_UNSUPPORTED_ACTION:
                supported_checks += 1  # other validation error is fine here
        except Exception:
            pass
    all_supported = supported_checks == 4
    print(f"  {'✅' if all_supported else '❌'} [D33] All 4 supported action types pass validation")
    if all_supported: passed += 1
    else:             failed += 1

    print(f"\n  D33 Unsupported action rejected: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D34: Missing before_state ────────────────────────────────────────

def run_d34():
    """Empty or missing before_state raises UNDO_NO_BEFORE_STATE."""
    print("\n=== Section D34: Empty before_state rejected ===")
    from rag.undo_engine   import execute_undo, UndoValidationError
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0
    exec_mock = _FixedSequence([_ok(0.5)])

    # Case A: before_state is empty dict
    proof_empty = _make_proof()
    proof_empty["before_state"] = {}
    try:
        execute_undo(proof_empty, exec_mock, stabilization_delay=0.0)
        ok_a = False
    except UndoValidationError as uve:
        ok_a = uve.bridge_error_code == BridgeErrorCode.UNDO_NO_BEFORE_STATE
    except Exception:
        ok_a = False
    print(f"  {'✅' if ok_a else '❌'} [D34-A] before_state={{}} → UNDO_NO_BEFORE_STATE")
    if ok_a: passed += 1
    else:    failed += 1

    # Case B: before_state has wrong key (missing "volume" for SET_TRACK_VOLUME)
    proof_wrong_key = _make_proof(action_type="SET_TRACK_VOLUME")
    proof_wrong_key["before_state"] = {"pan": 0.5}   # wrong key
    try:
        execute_undo(proof_wrong_key, exec_mock, stabilization_delay=0.0)
        ok_b = False
    except UndoValidationError as uve:
        ok_b = uve.bridge_error_code == BridgeErrorCode.UNDO_NO_BEFORE_STATE
    except Exception:
        ok_b = False
    print(f"  {'✅' if ok_b else '❌'} [D34-B] before_state with wrong key → UNDO_NO_BEFORE_STATE")
    if ok_b: passed += 1
    else:    failed += 1

    print(f"\n  D34 Missing before_state: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D35: Drift detection ─────────────────────────────────────────────

def run_d35():
    """Drift blocks write; confirm=True overrides; confirmed undo succeeds."""
    print("\n=== Section D35: Drift detection ===")
    from rag.undo_engine   import execute_undo
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0

    # Original proof: volume 0.8 → 0.5
    proof = _make_proof(before_value=0.8, after_value=0.5)

    # ── D35-A: Current state drifted (0.3 ≠ after_state 0.5) → blocked ─────
    exec_drift = _FixedSequence([_ok(0.3)])  # drift check: current=0.3, expected=0.5
    result_drift = execute_undo(
        proof, exec_drift,
        confirm=False, stabilization_delay=0.0,
    )
    drift_ok = (
        result_drift["drift_detected"] == True
        and result_drift["ok"] == False
        and result_drift.get("verification_status") == "FAILED"
    )
    print(f"  {'✅' if drift_ok else '❌'} [D35-A] drifted current state → drift_detected=True, ok=False")
    if drift_ok: passed += 1
    else:        failed += 1

    # ── D35-B: drift_state carries the current live value ─────────────────
    ds = result_drift.get("drift_state", {})
    ds_ok = ds.get("volume") is not None and abs(float(ds.get("volume", 0)) - 0.3) < 0.001
    print(f"  {'✅' if ds_ok else '❌'} [D35-B] drift_state has current live volume ≈0.3 ({ds})")
    if ds_ok: passed += 1
    else:     failed += 1

    # ── D35-C: undo_proof stub still written to log even on drift block ────
    stub_proof = result_drift.get("undo_proof")
    stub_ok = stub_proof is not None and stub_proof.proof_id != ""
    print(f"  {'✅' if stub_ok else '❌'} [D35-C] drift stub proof persisted with proof_id")
    if stub_ok: passed += 1
    else:       failed += 1

    # ── D35-D: confirm=True overrides drift, proceeds to write ─────────────
    # Executor sequence with confirm:
    #   [0] drift check: current=0.3 (drifted) — drift detected
    #   [1] verify before: current=0.3 (the current state before undo write)
    #   [2] write: ok
    #   [3] verify after: current=0.8 (restored)
    exec_confirm = _FixedSequence([
        _ok(0.3),   # drift check
        _ok(0.3),   # readback before inside verify_track_volume
        _ok(None),  # write
        _ok(0.8),   # readback after
    ])
    result_confirm = execute_undo(
        proof, exec_confirm,
        confirm=True, stabilization_delay=0.0,
    )
    confirm_ok = (
        result_confirm["ok"] == True
        and result_confirm["drift_detected"] == True   # drift was present
        and result_confirm.get("verification_status") in ("VERIFIED", "ALREADY_CORRECT")
    )
    print(f"  {'✅' if confirm_ok else '❌'} [D35-D] confirm=True allows write despite drift")
    if confirm_ok: passed += 1
    else:          failed += 1

    # ── D35-E: no drift when current matches after_state ──────────────────
    exec_no_drift = _FixedSequence([
        _ok(0.5),   # drift check: current=0.5, matches after_state=0.5
        _ok(0.5),   # verify before
        _ok(None),  # write
        _ok(0.8),   # verify after
    ])
    result_no_drift = execute_undo(
        proof, exec_no_drift,
        confirm=False, stabilization_delay=0.0,
    )
    no_drift_ok = (
        result_no_drift["drift_detected"] == False
        and result_no_drift["ok"] == True
    )
    print(f"  {'✅' if no_drift_ok else '❌'} [D35-E] no drift when current==after_state")
    if no_drift_ok: passed += 1
    else:           failed += 1

    # ── D35-F: boolean drift (mute) ───────────────────────────────────────
    proof_mute = _make_proof(
        action_type="SET_TRACK_MUTE", state_key="mute",
        before_value=False, after_value=True,
    )
    # Drift: current=False, expected after_state=True → drifted
    exec_bool_drift = _FixedSequence([_ok(False)])
    result_bool = execute_undo(
        proof_mute, exec_bool_drift,
        confirm=False, stabilization_delay=0.0,
    )
    bool_drift_ok = result_bool["drift_detected"] == True and result_bool["ok"] == False
    print(f"  {'✅' if bool_drift_ok else '❌'} [D35-F] boolean drift (mute) detected correctly")
    if bool_drift_ok: passed += 1
    else:             failed += 1

    print(f"\n  D35 Drift detection: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D36: Undo proof field correctness ─────────────────────────────────

def run_d36():
    """Undo proof has UNDO_ prefix, undo_eligible=False, correct original_proof_id."""
    print("\n=== Section D36: Undo proof field correctness ===")
    from rag.undo_engine import execute_undo

    passed = failed = 0

    proof = _make_proof(
        action_type="SET_TRACK_PAN", state_key="pan",
        before_value=0.5, after_value=0.3,
    )
    original_id = proof["proof_id"]

    exec_mock = _FixedSequence([
        _ok(0.3),   # drift check: current=0.3, matches after_state=0.3
        _ok(0.3),   # verify before
        _ok(None),  # write
        _ok(0.5),   # verify after (restored to before=0.5)
    ])
    result = execute_undo(proof, exec_mock, stabilization_delay=0.0)
    up = result["undo_proof"]

    # A: action_type has UNDO_ prefix
    at_ok = up.action_type == "UNDO_SET_TRACK_PAN"
    print(f"  {'✅' if at_ok else '❌'} [D36-A] undo_proof.action_type == 'UNDO_SET_TRACK_PAN' (got {up.action_type!r})")
    if at_ok: passed += 1
    else:     failed += 1

    # B: undo_eligible is False
    ue_ok = up.undo_eligible == False
    print(f"  {'✅' if ue_ok else '❌'} [D36-B] undo_proof.undo_eligible == False")
    if ue_ok: passed += 1
    else:     failed += 1

    # C: original_proof_id matches
    orig_ok = result["original_proof_id"] == original_id
    print(f"  {'✅' if orig_ok else '❌'} [D36-C] result.original_proof_id matches original proof_id")
    if orig_ok: passed += 1
    else:       failed += 1

    # D: target has undo: prefix
    tgt_ok = up.target.startswith("undo:")
    print(f"  {'✅' if tgt_ok else '❌'} [D36-D] undo_proof.target starts with 'undo:' (got {up.target!r})")
    if tgt_ok: passed += 1
    else:      failed += 1

    # E: undo proof is a different proof_id than original
    diff_ok = up.proof_id != original_id
    print(f"  {'✅' if diff_ok else '❌'} [D36-E] undo_proof.proof_id != original proof_id")
    if diff_ok: passed += 1
    else:       failed += 1

    print(f"\n  D36 Undo proof fields: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D39: Drift read unavailable → fail closed ────────────────────────

def run_d39():
    """
    Gate 2 (UNDO_DRIFT_READ_UNAVAILABLE): executor returns None for live-state
    read → undo blocked immediately, no write attempted.
    confirm=True must NOT bypass this gate.
    """
    print("\n=== Section D39: Drift read unavailable → fail closed ===")
    from rag.undo_engine   import execute_undo
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0

    # ── D39-A: scalar (volume) — drift read fails ─────────────────────────────
    proof_vol = _make_proof(
        action_type="SET_TRACK_VOLUME", state_key="volume",
        before_value=0.8, after_value=0.5,
    )
    exec_unavail_a = _FixedSequence([_err("Ableton disconnected")])
    result_a = execute_undo(
        proof_vol, exec_unavail_a, confirm=False, stabilization_delay=0.0,
    )
    a_ok = (
        result_a["ok"] == False
        and result_a.get("verification_status") == "FAILED"
        and result_a.get("error_code") == BridgeErrorCode.UNDO_DRIFT_READ_UNAVAILABLE.value
    )
    print(f"  {'✅' if a_ok else '❌'} [D39-A] volume drift-read unavailable → ok=False, "
          f"UNDO_DRIFT_READ_UNAVAILABLE (got error_code={result_a.get('error_code')!r})")
    if a_ok: passed += 1
    else:    failed += 1

    # ── D39-B: boolean (mute) — drift read fails ──────────────────────────────
    proof_mute = _make_proof(
        action_type="SET_TRACK_MUTE", state_key="mute",
        before_value=False, after_value=True,
    )
    exec_unavail_b = _FixedSequence([_err("track not found")])
    result_b = execute_undo(
        proof_mute, exec_unavail_b, confirm=False, stabilization_delay=0.0,
    )
    b_ok = (
        result_b["ok"] == False
        and result_b.get("error_code") == BridgeErrorCode.UNDO_DRIFT_READ_UNAVAILABLE.value
    )
    print(f"  {'✅' if b_ok else '❌'} [D39-B] mute drift-read unavailable → ok=False, "
          f"UNDO_DRIFT_READ_UNAVAILABLE (got error_code={result_b.get('error_code')!r})")
    if b_ok: passed += 1
    else:    failed += 1

    # ── D39-C: confirm=True does NOT bypass read-unavailable ──────────────────
    exec_unavail_c = _FixedSequence([_err("Ableton disconnected")])
    result_c = execute_undo(
        proof_vol, exec_unavail_c, confirm=True, stabilization_delay=0.0,
    )
    c_ok = (
        result_c["ok"] == False
        and result_c.get("error_code") == BridgeErrorCode.UNDO_DRIFT_READ_UNAVAILABLE.value
    )
    print(f"  {'✅' if c_ok else '❌'} [D39-C] confirm=True does NOT bypass read-unavailable "
          f"(got ok={result_c['ok']!r}, error_code={result_c.get('error_code')!r})")
    if c_ok: passed += 1
    else:    failed += 1

    # ── D39-D: executor called exactly once (drift read only), write never sent
    # One executor call = the drift read. Verify_track_volume's before-read,
    # write, and after-read are never reached.
    exec_counting = _FixedSequence([_err("unavailable")])
    execute_undo(
        proof_vol, exec_counting, confirm=False, stabilization_delay=0.0,
    )
    d_ok = exec_counting._calls == 1
    print(f"  {'✅' if d_ok else '❌'} [D39-D] executor called exactly 1× "
          f"(drift read only, no write) — got {exec_counting._calls} call(s)")
    if d_ok: passed += 1
    else:    failed += 1

    print(f"\n  D39 Drift read unavailable: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D40: Missing after_state[state_key] rejected ──────────────────────

def run_d40():
    """
    Gate 1 (UNDO_NO_AFTER_STATE): after_state[state_key] absent →
    UndoValidationError raised in step 1, before any executor call.
    confirm=True must NOT bypass this gate.
    """
    print("\n=== Section D40: Missing after_state[state_key] rejected before mutation ===")
    from rag.undo_engine   import execute_undo, UndoValidationError
    from rag.bridge_errors import BridgeErrorCode

    passed = failed = 0

    # ── D40-A: after_state is empty dict ─────────────────────────────────────
    exec_mock_a = _FixedSequence([_ok(0.5)])
    proof_no_after = _make_proof()
    proof_no_after["after_state"] = {}
    try:
        execute_undo(proof_no_after, exec_mock_a, confirm=False, stabilization_delay=0.0)
        a_ok = False
    except UndoValidationError as uve:
        a_ok = uve.bridge_error_code == BridgeErrorCode.UNDO_NO_AFTER_STATE
    except Exception as exc:
        a_ok = False
        print(f"    (unexpected exception: {exc})")
    print(f"  {'✅' if a_ok else '❌'} [D40-A] after_state={{}} → UNDO_NO_AFTER_STATE")
    if a_ok: passed += 1
    else:    failed += 1

    # ── D40-B: after_state has wrong key ─────────────────────────────────────
    exec_mock_b = _FixedSequence([_ok(0.5)])
    proof_wrong_key = _make_proof(action_type="SET_TRACK_VOLUME")
    proof_wrong_key["after_state"] = {"pan": 0.3}   # wrong key for a VOLUME action
    try:
        execute_undo(proof_wrong_key, exec_mock_b, confirm=False, stabilization_delay=0.0)
        b_ok = False
    except UndoValidationError as uve:
        b_ok = uve.bridge_error_code == BridgeErrorCode.UNDO_NO_AFTER_STATE
    except Exception as exc:
        b_ok = False
        print(f"    (unexpected exception: {exc})")
    print(f"  {'✅' if b_ok else '❌'} [D40-B] after_state with wrong key → UNDO_NO_AFTER_STATE")
    if b_ok: passed += 1
    else:    failed += 1

    # ── D40-C: confirm=True does NOT bypass missing after_state ───────────────
    exec_mock_c = _FixedSequence([_ok(0.5)])
    proof_confirm = _make_proof()
    proof_confirm["after_state"] = {}
    try:
        execute_undo(proof_confirm, exec_mock_c, confirm=True, stabilization_delay=0.0)
        c_ok = False   # must raise — confirm only bypasses value drift
    except UndoValidationError as uve:
        c_ok = uve.bridge_error_code == BridgeErrorCode.UNDO_NO_AFTER_STATE
    except Exception as exc:
        c_ok = False
        print(f"    (unexpected exception: {exc})")
    print(f"  {'✅' if c_ok else '❌'} [D40-C] confirm=True does NOT bypass missing after_state")
    if c_ok: passed += 1
    else:    failed += 1

    # ── D40-D: executor never called when after_state missing ─────────────────
    # Validation raises in step 1 — before any executor call whatsoever.
    exec_counting = _FixedSequence([_ok(0.5)])
    proof_count = _make_proof()
    proof_count["after_state"] = {}
    try:
        execute_undo(proof_count, exec_counting, confirm=False, stabilization_delay=0.0)
    except UndoValidationError:
        pass
    d_ok = exec_counting._calls == 0
    print(f"  {'✅' if d_ok else '❌'} [D40-D] executor never called when after_state missing "
          f"— got {exec_counting._calls} call(s)")
    if d_ok: passed += 1
    else:    failed += 1

    print(f"\n  D40 Missing after_state rejected: {passed} pass / {failed} fail")
    return failed == 0


# ── SECTION D37: Slice 1+2+3 regressions ─────────────────────────────────────

def run_d37():
    """Run Slice 1, 2, and 3 evals — must still pass after Slice 4 additions."""
    print("\n=== Section D37: Slice 1 + Slice 2 + Slice 3 regressions ===")

    py = sys.executable
    results = []
    for suite, label in [
        ("phase_d_slice1_eval.py", "Slice 1"),
        ("phase_d_slice2_eval.py", "Slice 2"),
        ("phase_d_slice3_eval.py", "Slice 3"),
    ]:
        try:
            path = os.path.join(_HERE, suite)
            r = subprocess.run(
                [py, path],
                capture_output=True, text=True,
                timeout=300,
                cwd=_ROOT,
            )
            ok = r.returncode == 0
            # Extract summary line
            last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            summary = last[-1] if last else "(no output)"
            print(f"  {'✅' if ok else '❌'} [{label}] {summary}")
            if not ok:
                # Show last 8 lines for diagnosis
                for l in last[-8:]:
                    print(f"       {l}")
            results.append(ok)
        except subprocess.TimeoutExpired:
            print(f"  ❌ [{label}] TIMEOUT")
            results.append(False)
        except Exception as exc:
            print(f"  ❌ [{label}] ERROR: {exc}")
            results.append(False)

    all_ok = all(results)
    print(f"\n  Slice 1+2+3 regressions: {'pass' if all_ok else 'FAIL'}")
    return all_ok


# ── SECTION D38: Phase C regression ──────────────────────────────────────────

def run_d38():
    """Phase C eval must still pass — no Phase C code was touched."""
    print("\n=== Section D38: Phase C eval regression ===")
    py  = sys.executable
    path = os.path.join(_HERE, "phase_c_eval_set.py")
    try:
        r = subprocess.run(
            [py, path],
            capture_output=True, text=True,
            timeout=600,
            cwd=_ROOT,
        )
        ok = r.returncode == 0
        last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
        summary = last[-1] if last else "(no output)"
        print(f"  {'✅' if ok else '❌'} [D38] {summary}")
        if not ok:
            for l in last[-10:]:
                print(f"       {l}")
    except subprocess.TimeoutExpired:
        print("  ❌ [D38] TIMEOUT")
        ok = False
    except Exception as exc:
        print(f"  ❌ [D38] ERROR: {exc}")
        ok = False
    print(f"\n  Phase C regression: {'pass' if ok else 'FAIL'}")
    return ok


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Conductor — Phase D Slice 4 Eval Suite")
    print("=" * 60)

    results = {
        "D31": run_d31(),
        "D32": run_d32(),
        "D33": run_d33(),
        "D34": run_d34(),
        "D35": run_d35(),
        "D36": run_d36(),
        "D37": run_d37(),
        "D38": run_d38(),
        "D39": run_d39(),
        "D40": run_d40(),
    }

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    labels = {
        "D31": "Undo success creates new proof (5 checks)",
        "D32": "FAILED/UNVERIFIED proof rejected (4 checks)",
        "D33": "Unsupported action rejected (5 checks)",
        "D34": "Empty before_state rejected (2 checks)",
        "D35": "Drift detection (6 checks)",
        "D36": "Undo proof field correctness (5 checks)",
        "D37": "Slice 1+2+3 regressions",
        "D38": "Phase C regression",
        "D39": "Drift read unavailable → fail closed (4 checks)",
        "D40": "Missing after_state[key] rejected (4 checks)",
    }
    any_fail = False
    for key, ok in results.items():
        sym = "✅" if ok else "❌"
        print(f"  {sym}  {key}  {labels[key]}")
        if not ok:
            any_fail = True

    print()
    if any_fail:
        print("  FAILURES DETECTED")
        sys.exit(1)
    else:
        print("  ALL PASS")
        sys.exit(0)
