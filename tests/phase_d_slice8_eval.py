"""
Phase D — Action Expansion Slice 3A Eval Suite
Sections D94–D101

Covers:
  D94  verify_plugin_bypass — VERIFIED / ALREADY_CORRECT / UNVERIFIED / FAILED
  D95  Device not found → BRIDGE_PLUGIN_ABSENT, no write
  D96  BeforeStateCaptureError (executor failure on find)
  D97  endpoint via do_POST — HARD_BLOCK→403, offline→503
  D98  endpoint device not found → 400 BRIDGE_PLUGIN_ABSENT
  D99  Undo eligibility — PLUGIN_BYPASS in UNDOABLE_ACTION_TYPES
  D100 execute_undo PLUGIN_BYPASS — drift + restore
  D101 Slice 7 + Phase C regression
"""

import io
import os
import sys
import json as _json
import importlib

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from rag.readback import (
    verify_plugin_bypass,
    BeforeStateCaptureError,
)
from rag.undo_engine import (
    UNDOABLE_ACTION_TYPES,
    execute_undo,
    UndoValidationError,
    _parse_plugin_target,
)
from rag.bridge_errors import BridgeErrorCode

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

SECTIONS = {}


def section(label):
    def decorator(fn):
        SECTIONS[label] = fn
        return fn
    return decorator


# ── helpers ───────────────────────────────────────────────────────────────────

def _seq_exec(*responses):
    """Stateful executor cycling through the given raw response dicts."""
    state = {"i": 0}
    resps = list(responses)
    def _e(code):
        r = resps[min(state["i"], len(resps) - 1)]
        state["i"] += 1
        return r
    return _e


def _ok(result):
    return {"ok": True, "data": {"result": result}, "error": None}

def _err(msg="mock error"):
    return {"ok": False, "data": {}, "error": msg}

def _write_ok():
    return {"ok": True, "data": {}, "error": None}


def _make_bypass_proof(before_active=True, after_active=False,
                       track="Vocal Bus", device="Pro-Q 4", vstat="VERIFIED"):
    """Plain-dict proof for execute_undo."""
    return {
        "action_type":         "PLUGIN_BYPASS",
        "target":              f"track:{track}:device:{device}",
        "intended_value":      not after_active,   # bypass_bool = not is_active
        "before_state":        {"device_name": device, "is_active": before_active},
        "after_state":         {"device_name": device, "is_active": after_active},
        "verification_status": vstat,
        "undo_eligible":       (vstat in ("VERIFIED", "ALREADY_CORRECT")),
        "user_facing_summary": "mock bypass proof",
        "proof_id":            "mock-bypass-001",
    }


# ══════════════════════════════════════════════════════════════════════════════
# D94 — verify_plugin_bypass readback
# ══════════════════════════════════════════════════════════════════════════════

@section("D94")
def run_d94():
    print("=== Section D94: verify_plugin_bypass readback ===")
    errors = []

    # VERIFIED: device found+active, bypass → is_active=False, confirmed
    # Call seq: [find+read] → [write] → [after_read]
    e_ver = _seq_exec(
        _ok(["Pro-Q 4", 0, True]),   # find: name, idx, is_active=True
        _write_ok(),                  # write: set is_active=False
        _ok(False),                   # after read: is_active=False
    )
    rb = verify_plugin_bypass("Vocal", "Pro-Q", False, e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED got {rb['verification_status']}: {rb['message']}")
    if rb["before_state"].get("is_active") is not True:
        errors.append(f"VERIFIED before_state wrong: {rb['before_state']}")
    if rb["after_state"].get("is_active") is not False:
        errors.append(f"VERIFIED after_state wrong: {rb['after_state']}")
    if rb.get("matched_device_name") != "Pro-Q 4":
        errors.append(f"VERIFIED matched_device_name wrong: {rb.get('matched_device_name')}")

    # ALREADY_CORRECT: device already has desired is_active
    e_ac = _seq_exec(_ok(["Pro-Q 4", 0, False]))   # already inactive
    rb = verify_plugin_bypass("Vocal", "Pro-Q", False, e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT got {rb['verification_status']}")

    # FAILED: write succeeds but readback returns wrong value
    e_fail = _seq_exec(
        _ok(["Pro-Q 4", 0, True]),   # find: active
        _write_ok(),                  # write ok
        _ok(True),                    # after: still True (write didn't take)
    )
    rb = verify_plugin_bypass("Vocal", "Pro-Q", False, e_fail, stabilization_delay=0)
    if rb["verification_status"] != "FAILED":
        errors.append(f"FAILED got {rb['verification_status']}")

    # UNVERIFIED: after read returns None (ok=False from _err)
    e_unver = _seq_exec(
        _ok(["Pro-Q 4", 0, True]),   # find: active
        _write_ok(),                  # write ok
        _err(),                       # after read fails → ok=False → result=None
    )
    rb = verify_plugin_bypass("Vocal", "Pro-Q", False, e_unver, stabilization_delay=0)
    if rb["verification_status"] != "UNVERIFIED":
        errors.append(f"UNVERIFIED got {rb['verification_status']}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D94] {e}")
        print("  D94: FAIL")
        return False
    print(f"  {PASS} [D94] verify_plugin_bypass — VERIFIED / ALREADY_CORRECT / FAILED / UNVERIFIED")
    print("  D94: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D95 — Device not found → BRIDGE_PLUGIN_ABSENT, no write
# ══════════════════════════════════════════════════════════════════════════════

@section("D95")
def run_d95():
    print("=== Section D95: device not found → BRIDGE_PLUGIN_ABSENT ===")
    errors = []

    # Ableton returns ok=True but result=None (device not matched)
    calls = []
    def _exec_not_found(code):
        calls.append(code)
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_plugin_bypass("Vocal", "NonExistentPlugin", False,
                               _exec_not_found, stabilization_delay=0)
    if rb["verification_status"] != "FAILED":
        errors.append(f"vstat {rb['verification_status']} != FAILED")
    if rb.get("error_code") != BridgeErrorCode.BRIDGE_PLUGIN_ABSENT.value:
        errors.append(f"error_code {rb.get('error_code')!r} != BRIDGE_PLUGIN_ABSENT")
    if rb.get("before_state"):
        errors.append(f"before_state should be empty: {rb.get('before_state')}")
    if len(calls) != 1:
        errors.append(f"expected 1 executor call (find only), got {len(calls)}")

    # Also verify BSCE is raised when executor itself fails (ok=False on find)
    try:
        verify_plugin_bypass("Vocal", "Pro-Q", False,
                              lambda c: _err(), stabilization_delay=0)
        errors.append("BSCE: expected BeforeStateCaptureError, got none")
    except BeforeStateCaptureError:
        pass

    if errors:
        for e in errors:
            print(f"  {FAIL} [D95] {e}")
        print("  D95: FAIL")
        return False
    print(f"  {PASS} [D95] device not found → BRIDGE_PLUGIN_ABSENT (1 call, no write); executor fail → BSCE")
    print("  D95: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D96 — BeforeStateCaptureError on executor raise
# ══════════════════════════════════════════════════════════════════════════════

@section("D96")
def run_d96():
    print("=== Section D96: executor raise → BeforeStateCaptureError ===")
    errors = []

    def _raising(code):
        raise RuntimeError("connection dropped")

    try:
        verify_plugin_bypass("Vocal", "Pro-Q", False, _raising, stabilization_delay=0)
        errors.append("expected BeforeStateCaptureError, got none")
    except BeforeStateCaptureError:
        pass

    if errors:
        for e in errors:
            print(f"  {FAIL} [D96] {e}")
        print("  D96: FAIL")
        return False
    print(f"  {PASS} [D96] executor raise → BeforeStateCaptureError")
    print("  D96: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D97 — endpoint: HARD_BLOCK→403, offline→503
# ══════════════════════════════════════════════════════════════════════════════

@section("D97")
def run_d97():
    print("=== Section D97: /action/plugin_bypass — HARD_BLOCK→403, offline→503 ===")
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/plugin_bypass"
            bb           = _json.dumps(body_dict).encode()
            self.headers = {"Content-Length": str(len(bb))}
            self.rfile   = io.BytesIO(bb)
            self._cap_data = None
            self._cap_code = None
        def _send_json(self, data, code=200):
            self._cap_data = data
            self._cap_code = code
        def log_message(self, *a):
            pass

    errors = []
    body   = {"track": "Vocal Bus", "device_name": "Pro-Q", "bypass": True}

    # HARD_BLOCK → 403, no execute calls
    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.HARD_BLOCK, "test rule")):
        with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
            h = _MockH(body)
            h.do_POST()
    if h._cap_code != 403:
        errors.append(f"HARD_BLOCK: HTTP {h._cap_code} != 403")
    if exec_m.call_count != 0:
        errors.append(f"HARD_BLOCK: execute called {exec_m.call_count} times")

    # offline → 503, no execute calls
    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False):
            with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m2:
                h2 = _MockH(body)
                h2.do_POST()
    if h2._cap_code != 503:
        errors.append(f"offline: HTTP {h2._cap_code} != 503")
    if exec_m2.call_count != 0:
        errors.append(f"offline: execute called {exec_m2.call_count} times")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D97] {e}")
        print("  D97: FAIL")
        return False
    print(f"  {PASS} [D97] /action/plugin_bypass HARD_BLOCK→403 / offline→503")
    print("  D97: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D98 — endpoint device not found → 400 BRIDGE_PLUGIN_ABSENT
# ══════════════════════════════════════════════════════════════════════════════

@section("D98")
def run_d98():
    print("=== Section D98: endpoint device not found → 400 BRIDGE_PLUGIN_ABSENT ===")
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/plugin_bypass"
            bb           = _json.dumps(body_dict).encode()
            self.headers = {"Content-Length": str(len(bb))}
            self.rfile   = io.BytesIO(bb)
            self._cap_data = None
            self._cap_code = None
        def _send_json(self, data, code=200):
            self._cap_data = data
            self._cap_code = code
        def log_message(self, *a):
            pass

    errors = []
    # Execute returns ok=True, result=None (device not matched)
    not_found_resp = {"ok": True, "data": {"result": None}, "error": None}

    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "ableton_execute",
                                    return_value=not_found_resp) as exec_m:
                h = _MockH({"track": "Vocal Bus", "device_name": "NOPE", "bypass": True})
                h.do_POST()

    if h._cap_code != 400:
        errors.append(f"device not found: HTTP {h._cap_code} != 400")
    ec = (h._cap_data or {}).get("error_code", "")
    if ec != BridgeErrorCode.BRIDGE_PLUGIN_ABSENT.value:
        errors.append(f"device not found: error_code {ec!r} != BRIDGE_PLUGIN_ABSENT")
    # Exactly 1 execute call (find only — no write)
    if exec_m.call_count != 1:
        errors.append(f"device not found: expected 1 execute call, got {exec_m.call_count}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D98] {e}")
        print("  D98: FAIL")
        return False
    print(f"  {PASS} [D98] endpoint device not found → 400 BRIDGE_PLUGIN_ABSENT, 1 execute call, no write")
    print("  D98: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D99 — Undo eligibility
# ══════════════════════════════════════════════════════════════════════════════

@section("D99")
def run_d99():
    print("=== Section D99: PLUGIN_BYPASS in UNDOABLE_ACTION_TYPES ===")
    errors = []

    if "PLUGIN_BYPASS" not in UNDOABLE_ACTION_TYPES:
        errors.append("PLUGIN_BYPASS not in UNDOABLE_ACTION_TYPES")

    # _parse_plugin_target sanity
    tid, dname = _parse_plugin_target("track:Vocal Bus:device:Pro-Q 4")
    if tid != "Vocal Bus" or dname != "Pro-Q 4":
        errors.append(f"_parse_plugin_target 'Vocal Bus:device:Pro-Q 4' → ({tid!r},{dname!r})")
    tid2, dname2 = _parse_plugin_target("track:0:device:Compressor")
    if tid2 != 0 or dname2 != "Compressor":
        errors.append(f"_parse_plugin_target '0:device:Compressor' → ({tid2!r},{dname2!r})")
    bad_t, bad_d = _parse_plugin_target("track:NoBus")
    if bad_t is not None:
        errors.append(f"_parse_plugin_target bad target → ({bad_t!r},{bad_d!r})")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D99] {e}")
        print("  D99: FAIL")
        return False
    print(f"  {PASS} [D99] PLUGIN_BYPASS in UNDOABLE_ACTION_TYPES; _parse_plugin_target correct")
    print("  D99: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D100 — execute_undo for PLUGIN_BYPASS
# ══════════════════════════════════════════════════════════════════════════════

@section("D100")
def run_d100():
    print("=== Section D100: execute_undo PLUGIN_BYPASS — drift + restore ===")
    errors = []

    # Proof: device was active (True), action set it to inactive (False)
    # Undo: restore is_active=True
    # Call sequence:
    #   [1] _read_plugin_bypass — drift check  → False (== after_state, no drift)
    #   [2] verify_plugin_bypass find+read      → ["Pro-Q 4", 0, False] (before of undo)
    #   [3] verify_plugin_bypass write          → ok
    #   [4] verify_plugin_bypass after read     → True (restored)
    proof = _make_bypass_proof(before_active=True, after_active=False)

    _seq = [
        _ok(False),                       # [1] drift check (current=False=after_state)
        _ok(["Pro-Q 4", 0, False]),       # [2] undo verify find+read
        _write_ok(),                      # [3] undo verify write
        _ok(True),                        # [4] undo verify after read
    ]
    result = execute_undo(proof, _seq_exec(*_seq), stabilization_delay=0)
    if not result["ok"]:
        errors.append(f"undo failed: {result.get('message')}")
    if result["verification_status"] not in ("VERIFIED", "ALREADY_CORRECT"):
        errors.append(f"undo vstat: {result['verification_status']}")

    # Drift blocked: current=True != after_state(False), no confirm
    proof2 = _make_bypass_proof(before_active=True, after_active=False)
    result2 = execute_undo(proof2, _seq_exec(_ok(True)), stabilization_delay=0, confirm=False)
    if result2["ok"]:
        errors.append("drifted undo should be blocked (ok=False)")
    if not result2["drift_detected"]:
        errors.append("drift_detected should be True")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D100] {e}")
        print("  D100: FAIL")
        return False
    print(f"  {PASS} [D100] execute_undo PLUGIN_BYPASS — restore + drift detection")
    print("  D100: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D102 — Slice 3A blocker fixes: ALLOW gate, strict bool, success path
# ══════════════════════════════════════════════════════════════════════════════

@section("D102")
def run_d102():
    print("=== Section D102: ALLOW gate / strict bool / endpoint success ===")
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    rb_mod     = importlib.import_module("rag.readback")
    ap_mod     = importlib.import_module("rag.action_proof")
    bbl_mod    = importlib.import_module("rag.black_box_log")
    ConductorHandler = bridge_mod.ConductorHandler

    errors = []

    # ── 1. Real ndc check: PLUGIN_BYPASS must be ALLOW ────────────────────────
    decision, _rule = ndc_mod.check("PLUGIN_BYPASS", {})
    if decision != ndc_mod.NeverDoDecision.ALLOW:
        errors.append(f"check(PLUGIN_BYPASS) → {decision!r}, expected ALLOW")
    else:
        print(f"  {PASS} [D102] check('PLUGIN_BYPASS') == ALLOW")

    # ── shared mock handler ────────────────────────────────────────────────────
    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/plugin_bypass"
            bb           = _json.dumps(body_dict).encode()
            self.headers = {"Content-Length": str(len(bb))}
            self.rfile   = io.BytesIO(bb)
            self._cap_data = None
            self._cap_code = None
        def _send_json(self, data, code=200):
            self._cap_data = data
            self._cap_code = code
        def log_message(self, *a):
            pass

    _verified_rb = {
        "verification_status": "VERIFIED",
        "matched_device_name": "Pro-Q 4",
        "before_state": {"device_name": "Pro-Q 4", "is_active": True},
        "after_state":  {"device_name": "Pro-Q 4", "is_active": False},
        "message": "", "error_code": "",
    }
    _fake_proof = type("P", (), {"proof_id": "test-proof-001"})()

    # ── 2a. "false" string must be parsed as False → is_active_val=True ───────
    captured_is_active = []
    def _vpb_capture(track, device, is_active_val, executor, **kw):
        captured_is_active.append(is_active_val)
        return _verified_rb

    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "load_config",
                                    return_value={"readback_stabilization_delay": "0"}):
                with _mock.patch.object(rb_mod,  "verify_plugin_bypass", side_effect=_vpb_capture):
                    with _mock.patch.object(ap_mod,  "create_proof", return_value=_fake_proof):
                        with _mock.patch.object(bbl_mod, "log_verified"):
                            with _mock.patch.object(bbl_mod, "log_requested"):
                                h_false = _MockH({"track": "Vocal Bus",
                                                  "device_name": "Pro-Q", "bypass": "false"})
                                h_false.do_POST()

    if not captured_is_active:
        errors.append('"false" string: verify_plugin_bypass not called; '
                      f'HTTP={h_false._cap_code} msg={( h_false._cap_data or {}).get("message","")}')
    else:
        if captured_is_active[0] is not True:
            errors.append(f'"false" → is_active_val={captured_is_active[0]!r}, expected True')
        else:
            print(f"  {PASS} [D102] bypass='false' → is_active_val=True (activate)")

    # ── 2b. Invalid string → 400, 0 execute calls ────────────────────────────
    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "ableton_execute") as exec_inv:
                h_inv = _MockH({"track": "Vocal Bus",
                                "device_name": "Pro-Q", "bypass": "maybe"})
                h_inv.do_POST()
    if h_inv._cap_code != 400:
        errors.append(f'invalid bypass string: HTTP {h_inv._cap_code} != 400')
    else:
        print(f"  {PASS} [D102] bypass='maybe' → 400")
    if exec_inv.call_count != 0:
        errors.append(f'invalid bypass string: execute called {exec_inv.call_count} times (expected 0)')

    # ── 3. Endpoint success: ok=True, undo_eligible=True, proof/log wired ─────
    _fake_proof2 = type("P", (), {"proof_id": "success-proof-001"})()
    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "load_config",
                                    return_value={"readback_stabilization_delay": "0"}):
                with _mock.patch.object(rb_mod,  "verify_plugin_bypass",
                                        return_value=_verified_rb):
                    with _mock.patch.object(ap_mod,  "create_proof",
                                            return_value=_fake_proof2) as cp2:
                        with _mock.patch.object(bbl_mod, "log_verified") as lv:
                            with _mock.patch.object(bbl_mod, "log_requested"):
                                h_ok = _MockH({"track": "Vocal Bus",
                                               "device_name": "Pro-Q", "bypass": True})
                                h_ok.do_POST()
    resp = h_ok._cap_data or {}
    if not resp.get("ok"):
        errors.append(f"success: ok={resp.get('ok')!r}, expected True")
    if not resp.get("undo_eligible"):
        errors.append(f"success: undo_eligible={resp.get('undo_eligible')!r}, expected True")
    if resp.get("proof_id") != "success-proof-001":
        errors.append(f"success: proof_id={resp.get('proof_id')!r}")
    if not cp2.called:
        errors.append("success: create_proof not called")
    if not lv.called:
        errors.append("success: log_verified not called")
    if not errors:
        print(f"  {PASS} [D102] success: ok=True, undo_eligible=True, proof_id set, log_verified called")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D102] {e}")
        print("  D102: FAIL")
        return False
    print("  D102: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D101 — Slice 7 + Phase C regression
# ══════════════════════════════════════════════════════════════════════════════

@section("D101")
def run_d101():
    print("=== Section D101: Slice 7 + Phase C regression ===")
    import subprocess

    ok = True
    for suite, label in [
        ("tests/phase_d_slice7_eval.py", "Slice 7"),
        ("tests/phase_c_eval_set.py",    "Phase C"),
    ]:
        result = subprocess.run(
            ["python3", suite], capture_output=True, text=True, cwd=_ROOT)
        lines      = result.stdout.splitlines()
        fail_lines = [l for l in lines if l.strip().startswith("❌")]
        if fail_lines or result.returncode != 0:
            print(f"  {FAIL} [D101] {label} FAIL:")
            for l in fail_lines[:5]:
                print(f"    {l}")
            if result.returncode != 0 and not fail_lines:
                print(result.stderr[-300:] if result.stderr else "")
            ok = False
        else:
            pass_count = sum(1 for l in lines if "✅" in l)
            print(f"  {PASS} [D101] {label} — {pass_count} checks pass")
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

def run_all():
    passed  = 0
    failed  = 0
    failing = []
    for label, fn in SECTIONS.items():
        try:
            ok = fn()
        except Exception as exc:
            print(f"  {FAIL} [{label}] CRASHED: {exc}")
            import traceback; traceback.print_exc()
            ok = False
        print()
        if ok:
            passed += 1
        else:
            failed += 1
            failing.append(label)
    total = passed + failed
    print("=" * 60)
    print(f"  Phase D Action Expansion Slice 3A — {total}/{total} sections")
    if failed == 0:
        print(f"  {passed}/{total} PASS")
        print("  All sections PASS.")
    else:
        print(f"  {FAIL}  {failed} section(s) FAILED: {', '.join(failing)}")
    print("=" * 60)
    return failed == 0


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
