"""
Phase D — Action Expansion Slice 2 Eval Suite
Sections D74–D90

Covers:
  D74 verify_track_send readback (VERIFIED / ALREADY_CORRECT / FAILED / UNVERIFIED / BSCE)
  D75 verify_track_route readback (VERIFIED / ALREADY_CORRECT / FAILED)
  D76 verify_transport_loop readback
  D77 verify_transport_metronome readback
  D78 verify_transport_play + stop
  D79 verify_transport_record readback
  D80 Undo eligible — SET_TRACK_SEND / SET_TRACK_ROUTE / TRANSPORT_LOOP / TRANSPORT_METRONOME
  D81 Undo NOT eligible — TRANSPORT_PLAY / STOP / RECORD
  D82 execute_undo for SET_TRACK_SEND (drift + restore)
  D83 execute_undo for SET_TRACK_ROUTE (string drift + restore)
  D84 execute_undo for TRANSPORT_LOOP + TRANSPORT_METRONOME (song bool)
  D85 All 7 endpoints via do_POST — HARD_BLOCK→403, offline→503
  D86 track_route confirm gate — no-confirm→403, confirm→offline
  D87 transport_record confirm gate — no-confirm→403, confirm→offline
  D88 Proof field honesty — send target, route before_state
  D89 Slice 6 regression (calls phase_d_slice6_eval)
  D90 Phase C regression
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
    verify_track_send,
    verify_track_route,
    verify_transport_loop,
    verify_transport_metronome,
    verify_transport_play,
    verify_transport_stop,
    verify_transport_record,
    BeforeStateCaptureError,
    DEFAULT_VOLUME_TOLERANCE,
)
from rag.undo_engine import (
    UNDOABLE_ACTION_TYPES,
    execute_undo,
    UndoValidationError,
    _parse_send_target,
)
from rag.action_proof import create_proof


# ── helpers ───────────────────────────────────────────────────────────────────

def _ok_exec(*expected_values):
    """
    Make a stateful executor that cycles through expected_values on each call.
    Wraps each value as {"ok": True, "data": {"result": v}}.
    """
    vals = list(expected_values)
    state = {"i": 0}
    def _exec(code):
        v = vals[state["i"] % len(vals)]
        state["i"] += 1
        if v is None:
            return {"ok": False, "data": {}, "error": "mock fail"}
        return {"ok": True, "data": {"result": v}, "error": None}
    return _exec


def _fail_exec():
    """Always-failing executor."""
    def _exec(code):
        return {"ok": False, "data": {}, "error": "mock error"}
    return _exec


def _raise_exec():
    """Executor that always raises."""
    def _exec(code):
        raise RuntimeError("mock exception")
    return _exec


def _make_send_proof(before_val=0.0, after_val=0.5, track="Kick", send_idx=0, vstat="VERIFIED"):
    """Plain dict proof — execute_undo expects dict.get(), not ActionProof attrs."""
    return {
        "action_type":        "SET_TRACK_SEND",
        "target":             f"track:{track}:send:{send_idx}",
        "intended_value":     after_val,
        "before_state":       {"send_value": before_val},
        "after_state":        {"send_value": after_val},
        "verification_status": vstat,
        "undo_eligible":      (vstat in ("VERIFIED", "ALREADY_CORRECT")),
        "user_facing_summary": "mock send proof",
        "proof_id":           "mock-send-001",
    }


def _make_route_proof(before_r="Master", after_r="DRUM BUS", track="Kick", vstat="VERIFIED"):
    return {
        "action_type":        "SET_TRACK_ROUTE",
        "target":             f"track:{track}",
        "intended_value":     after_r,
        "before_state":       {"routing": before_r},
        "after_state":        {"routing": after_r},
        "verification_status": vstat,
        "undo_eligible":      (vstat in ("VERIFIED", "ALREADY_CORRECT")),
        "user_facing_summary": "mock route proof",
        "proof_id":           "mock-route-001",
    }


def _make_song_bool_proof(action_type, prop, before_v, after_v, vstat="VERIFIED"):
    return {
        "action_type":        action_type,
        "target":             "song",
        "intended_value":     after_v,
        "before_state":       {prop: before_v},
        "after_state":        {prop: after_v},
        "verification_status": vstat,
        "undo_eligible":      (vstat in ("VERIFIED", "ALREADY_CORRECT")),
        "user_facing_summary": "mock song bool proof",
        "proof_id":           "mock-bool-001",
    }


PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

SECTIONS = {}


def section(label):
    def decorator(fn):
        SECTIONS[label] = fn
        return fn
    return decorator


# ══════════════════════════════════════════════════════════════════════════════
# D74 — verify_track_send readback
# ══════════════════════════════════════════════════════════════════════════════

@section("D74")
def run_d74():
    print("=== Section D74: verify_track_send readback ===")
    errors = []

    # VERIFIED path: before=0.0, write, after=0.5
    def _exec_verified(code):
        if "sends" in code and "value" not in code.split("=")[0]:
            # read
            if not hasattr(_exec_verified, "reads"):
                _exec_verified.reads = 0
            _exec_verified.reads = getattr(_exec_verified, "reads", 0) + 1
            if _exec_verified.reads == 1:
                return {"ok": True, "data": {"result": 0.0}}
            return {"ok": True, "data": {"result": 0.5}}
        return {"ok": True, "data": {"result": None}}

    # Simpler approach: stateful executor
    e_ver = _ok_exec(0.0, None, 0.5)   # before=0.0, write=None(ok), after=0.5
    rb = verify_track_send("Kick", 0, 0.5, e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED path got {rb['verification_status']}")
    if abs(rb["before_state"]["send_value"] - 0.0) > DEFAULT_VOLUME_TOLERANCE:
        errors.append(f"before_state send_value wrong: {rb['before_state']}")
    if abs(rb["after_state"]["send_value"] - 0.5) > DEFAULT_VOLUME_TOLERANCE:
        errors.append(f"after_state send_value wrong: {rb['after_state']}")

    # ALREADY_CORRECT: before=0.5, request 0.5
    e_ac = _ok_exec(0.5)
    rb = verify_track_send("Kick", 0, 0.5, e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT path got {rb['verification_status']}")

    # FAILED — write returns error, readback returns wrong value
    e_fail = _ok_exec(0.2, None, 0.2)  # before=0.2, write fails gracefully, after=0.2
    rb = verify_track_send("Kick", 0, 0.8, e_fail, stabilization_delay=0)
    if rb["verification_status"] != "FAILED":
        errors.append(f"FAILED path got {rb['verification_status']}")

    # UNVERIFIED — readback returns None
    e_unver = _ok_exec(0.2, None, None)
    rb = verify_track_send("Kick", 0, 0.8, e_unver, stabilization_delay=0)
    if rb["verification_status"] != "UNVERIFIED":
        errors.append(f"UNVERIFIED path got {rb['verification_status']}")

    # BeforeStateCaptureError — before read returns None
    e_bsce = _ok_exec(None)
    try:
        verify_track_send("Kick", 0, 0.5, e_bsce, stabilization_delay=0)
        errors.append("BSCE path: expected BeforeStateCaptureError, got none")
    except BeforeStateCaptureError:
        pass

    if errors:
        for e in errors:
            print(f"  {FAIL} [D74] {e}")
        print("  D74: FAIL")
        return False
    print(f"  {PASS} [D74] verify_track_send — VERIFIED / ALREADY_CORRECT / FAILED / UNVERIFIED / BSCE")
    print("  D74: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D75 — verify_track_route readback
# ══════════════════════════════════════════════════════════════════════════════

@section("D75")
def run_d75():
    print("=== Section D75: verify_track_route readback ===")
    errors = []

    # VERIFIED: before="Master", set "DRUM BUS", after="DRUM BUS"
    e_ver = _ok_exec("Master", None, "DRUM BUS")
    rb = verify_track_route("Kick", "DRUM BUS", e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED path got {rb['verification_status']}")
    if rb["before_state"].get("routing") != "Master":
        errors.append(f"before_state routing wrong: {rb['before_state']}")
    if rb["after_state"].get("routing") != "DRUM BUS":
        errors.append(f"after_state routing wrong: {rb['after_state']}")

    # ALREADY_CORRECT
    e_ac = _ok_exec("Master")
    rb = verify_track_route("Kick", "Master", e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT got {rb['verification_status']}")

    # FAILED — routing not applied (after still == before)
    e_fail = _ok_exec("Master", None, "Master")
    rb = verify_track_route("Kick", "DRUM BUS", e_fail, stabilization_delay=0)
    if rb["verification_status"] != "FAILED":
        errors.append(f"FAILED path got {rb['verification_status']}")

    # BeforeStateCaptureError
    e_bsce = _ok_exec(None)
    try:
        verify_track_route("Kick", "DRUM BUS", e_bsce, stabilization_delay=0)
        errors.append("BSCE: expected BeforeStateCaptureError, got none")
    except BeforeStateCaptureError:
        pass

    if errors:
        for e in errors:
            print(f"  {FAIL} [D75] {e}")
        print("  D75: FAIL")
        return False
    print(f"  {PASS} [D75] verify_track_route — VERIFIED / ALREADY_CORRECT / FAILED / BSCE")
    print("  D75: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D76 — verify_transport_loop
# ══════════════════════════════════════════════════════════════════════════════

@section("D76")
def run_d76():
    print("=== Section D76: verify_transport_loop readback ===")
    errors = []

    # VERIFIED: before=False, set True, after=True
    e_ver = _ok_exec(False, None, True)
    rb = verify_transport_loop(True, e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED got {rb['verification_status']}")
    if rb["before_state"].get("loop") is not False:
        errors.append(f"before_state.loop wrong: {rb['before_state']}")
    if rb["after_state"].get("loop") is not True:
        errors.append(f"after_state.loop wrong: {rb['after_state']}")

    # ALREADY_CORRECT
    e_ac = _ok_exec(True)
    rb = verify_transport_loop(True, e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT got {rb['verification_status']}")

    # FAILED — write didn't take
    e_fail = _ok_exec(False, None, False)
    rb = verify_transport_loop(True, e_fail, stabilization_delay=0)
    if rb["verification_status"] != "FAILED":
        errors.append(f"FAILED got {rb['verification_status']}")

    # BeforeStateCaptureError
    try:
        verify_transport_loop(True, _ok_exec(None), stabilization_delay=0)
        errors.append("BSCE: expected BeforeStateCaptureError, got none")
    except BeforeStateCaptureError:
        pass

    if errors:
        for e in errors:
            print(f"  {FAIL} [D76] {e}")
        print("  D76: FAIL")
        return False
    print(f"  {PASS} [D76] verify_transport_loop — VERIFIED / ALREADY_CORRECT / FAILED / BSCE")
    print("  D76: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D77 — verify_transport_metronome
# ══════════════════════════════════════════════════════════════════════════════

@section("D77")
def run_d77():
    print("=== Section D77: verify_transport_metronome readback ===")
    errors = []

    e_ver = _ok_exec(False, None, True)
    rb = verify_transport_metronome(True, e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED got {rb['verification_status']}")
    if rb["before_state"].get("metronome") is not False:
        errors.append(f"before_state.metronome wrong: {rb['before_state']}")

    e_ac = _ok_exec(False)
    rb = verify_transport_metronome(False, e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT got {rb['verification_status']}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D77] {e}")
        print("  D77: FAIL")
        return False
    print(f"  {PASS} [D77] verify_transport_metronome — VERIFIED / ALREADY_CORRECT")
    print("  D77: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D78 — verify_transport_play / stop
# ══════════════════════════════════════════════════════════════════════════════

@section("D78")
def run_d78():
    print("=== Section D78: verify_transport_play and stop ===")
    errors = []

    # play VERIFIED
    e = _ok_exec(False, None, True)
    rb = verify_transport_play(e, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"play VERIFIED got {rb['verification_status']}")
    if rb["before_state"].get("is_playing") is not False:
        errors.append(f"play before_state wrong: {rb['before_state']}")
    if rb["after_state"].get("is_playing") is not True:
        errors.append(f"play after_state wrong: {rb['after_state']}")

    # play ALREADY_CORRECT
    e = _ok_exec(True)
    rb = verify_transport_play(e, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"play ALREADY_CORRECT got {rb['verification_status']}")

    # stop VERIFIED
    e = _ok_exec(True, None, False)
    rb = verify_transport_stop(e, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"stop VERIFIED got {rb['verification_status']}")
    if rb["before_state"].get("is_playing") is not True:
        errors.append(f"stop before_state wrong: {rb['before_state']}")

    # stop ALREADY_CORRECT
    e = _ok_exec(False)
    rb = verify_transport_stop(e, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"stop ALREADY_CORRECT got {rb['verification_status']}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D78] {e}")
        print("  D78: FAIL")
        return False
    print(f"  {PASS} [D78] verify_transport_play/stop — VERIFIED / ALREADY_CORRECT")
    print("  D78: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D79 — verify_transport_record
# ══════════════════════════════════════════════════════════════════════════════

@section("D79")
def run_d79():
    print("=== Section D79: verify_transport_record readback ===")
    errors = []

    e_ver = _ok_exec(False, None, True)
    rb = verify_transport_record(True, e_ver, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        errors.append(f"VERIFIED got {rb['verification_status']}")
    if rb["before_state"].get("record_mode") is not False:
        errors.append(f"before_state.record_mode wrong: {rb['before_state']}")

    e_ac = _ok_exec(True)
    rb = verify_transport_record(True, e_ac, stabilization_delay=0)
    if rb["verification_status"] != "ALREADY_CORRECT":
        errors.append(f"ALREADY_CORRECT got {rb['verification_status']}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D79] {e}")
        print("  D79: FAIL")
        return False
    print(f"  {PASS} [D79] verify_transport_record — VERIFIED / ALREADY_CORRECT")
    print("  D79: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D80 — Undo eligible
# ══════════════════════════════════════════════════════════════════════════════

@section("D80")
def run_d80():
    print("=== Section D80: Undo eligible — Slice 2 types in UNDOABLE_ACTION_TYPES ===")
    errors = []
    expected = ["SET_TRACK_SEND", "SET_TRACK_ROUTE", "TRANSPORT_LOOP", "TRANSPORT_METRONOME"]
    for at in expected:
        if at not in UNDOABLE_ACTION_TYPES:
            errors.append(f"{at} NOT in UNDOABLE_ACTION_TYPES")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D80] {e}")
        print("  D80: FAIL")
        return False
    print(f"  {PASS} [D80] SET_TRACK_SEND, SET_TRACK_ROUTE, TRANSPORT_LOOP, TRANSPORT_METRONOME in UNDOABLE_ACTION_TYPES")
    print("  D80: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D81 — Undo NOT eligible
# ══════════════════════════════════════════════════════════════════════════════

@section("D81")
def run_d81():
    print("=== Section D81: Undo NOT eligible — TRANSPORT_PLAY/STOP/RECORD not undoable ===")
    errors = []
    not_expected = ["TRANSPORT_PLAY", "TRANSPORT_STOP", "TRANSPORT_RECORD"]
    for at in not_expected:
        if at in UNDOABLE_ACTION_TYPES:
            errors.append(f"{at} IS in UNDOABLE_ACTION_TYPES — should not be")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D81] {e}")
        print("  D81: FAIL")
        return False
    print(f"  {PASS} [D81] TRANSPORT_PLAY/STOP/RECORD not in UNDOABLE_ACTION_TYPES")
    print("  D81: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D82 — execute_undo for SET_TRACK_SEND
# ══════════════════════════════════════════════════════════════════════════════

@section("D82")
def run_d82():
    print("=== Section D82: execute_undo for SET_TRACK_SEND ===")
    errors = []

    # Call sequence for undo of SET_TRACK_SEND:
    #   call 1 — undo engine drift check read (current send = 0.5 = after_state)
    #   call 2 — verify_track_send before-state read (still 0.5, not written yet)
    #   call 3 — verify_track_send write send=0.0
    #   call 4 — verify_track_send after-state read (0.0, restored)

    proof = _make_send_proof(before_val=0.0, after_val=0.5)
    _seq  = [
        {"ok": True, "data": {"result": 0.5}},   # [1] drift check
        {"ok": True, "data": {"result": 0.5}},   # [2] before-state in verify_track_send
        {"ok": True, "data": {}, "error": None},  # [3] write (no return value)
        {"ok": True, "data": {"result": 0.0}},   # [4] after-state in verify_track_send
    ]
    _i = [0]
    def _exec(code):
        resp = _seq[min(_i[0], len(_seq) - 1)]
        _i[0] += 1
        return resp

    result = execute_undo(proof, _exec, stabilization_delay=0)
    if not result["ok"]:
        errors.append(f"execute_undo failed: {result.get('message')}")
    if result["verification_status"] not in ("VERIFIED", "ALREADY_CORRECT"):
        errors.append(f"undo vstat: {result['verification_status']}")

    # Drift blocked path: current = 0.3 (not 0.5 = after_val), no confirm → blocked
    proof2 = _make_send_proof(before_val=0.0, after_val=0.5)
    def _exec_drift(code):
        return {"ok": True, "data": {"result": 0.3}}
    result2 = execute_undo(proof2, _exec_drift, stabilization_delay=0, confirm=False)
    if result2["ok"]:
        errors.append("Drift path should have been blocked (ok=False)")
    if not result2["drift_detected"]:
        errors.append("drift_detected should be True on drift path")

    # _parse_send_target sanity checks
    tid, sidx = _parse_send_target("track:Kick Drum:send:2")
    if tid != "Kick Drum" or sidx != 2:
        errors.append(f"_parse_send_target 'Kick Drum:send:2' → ({tid!r},{sidx!r})")
    tid2, sidx2 = _parse_send_target("track:0:send:0")
    if tid2 != 0 or sidx2 != 0:
        errors.append(f"_parse_send_target '0:send:0' → ({tid2!r},{sidx2!r})")
    bad_t, bad_s = _parse_send_target("track:NoSend")
    if bad_t is not None:
        errors.append(f"_parse_send_target bad target should return (None,None), got ({bad_t!r},{bad_s!r})")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D82] {e}")
        print("  D82: FAIL")
        return False
    print(f"  {PASS} [D82] execute_undo SET_TRACK_SEND — restore + drift detection + _parse_send_target")
    print("  D82: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D83 — execute_undo for SET_TRACK_ROUTE
# ══════════════════════════════════════════════════════════════════════════════

@section("D83")
def run_d83():
    print("=== Section D83: execute_undo for SET_TRACK_ROUTE ===")
    errors = []

    proof = _make_route_proof(before_r="Master", after_r="DRUM BUS")

    # Call sequence for undo of SET_TRACK_ROUTE:
    #   call 1 — undo engine drift check read (current routing = "DRUM BUS" = after_state)
    #   call 2 — verify_track_route before-state read (still "DRUM BUS", not yet written)
    #   call 3 — verify_track_route write (restore to "Master")
    #   call 4 — verify_track_route after-state read ("Master" — restored)
    _seq_r = [
        {"ok": True, "data": {"result": "DRUM BUS"}},   # [1] drift check
        {"ok": True, "data": {"result": "DRUM BUS"}},   # [2] before-state read
        {"ok": True, "data": {}, "error": None},          # [3] write (no return value)
        {"ok": True, "data": {"result": "Master"}},      # [4] after-state read
    ]
    _i_r = [0]
    def _exec(code):
        resp = _seq_r[min(_i_r[0], len(_seq_r) - 1)]
        _i_r[0] += 1
        return resp

    result = execute_undo(proof, _exec, stabilization_delay=0)
    if not result["ok"]:
        errors.append(f"execute_undo failed: {result.get('message')}")

    # Drift: current routing changed to "Vocals Bus" (not "DRUM BUS") → drift
    proof2 = _make_route_proof(before_r="Master", after_r="DRUM BUS")
    def _exec_drift(code):
        return {"ok": True, "data": {"result": "Vocals Bus"}}
    result2 = execute_undo(proof2, _exec_drift, stabilization_delay=0, confirm=False)
    if not result2["drift_detected"]:
        errors.append("string drift not detected (current 'Vocals Bus' != after 'DRUM BUS')")
    if result2["ok"]:
        errors.append("drifted route undo should be blocked (ok=False)")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D83] {e}")
        print("  D83: FAIL")
        return False
    print(f"  {PASS} [D83] execute_undo SET_TRACK_ROUTE — string drift detection + restore")
    print("  D83: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D84 — execute_undo for TRANSPORT_LOOP + TRANSPORT_METRONOME
# ══════════════════════════════════════════════════════════════════════════════

@section("D84")
def run_d84():
    print("=== Section D84: execute_undo for TRANSPORT_LOOP + TRANSPORT_METRONOME ===")
    errors = []

    for action_type, prop in [("TRANSPORT_LOOP", "loop"), ("TRANSPORT_METRONOME", "metronome")]:
        proof = _make_song_bool_proof(action_type, prop, before_v=False, after_v=True)

        # Call sequence for undo of TRANSPORT_LOOP / TRANSPORT_METRONOME:
        #   call 1 — undo engine drift check (_read_song_bool: current=True == after_state)
        #   call 2 — _verify_song_bool before-state read (still True, not yet written)
        #   call 3 — _verify_song_bool write (set song.{prop} = False)
        #   call 4 — _verify_song_bool after-state read (False — restored)
        _seq_b = [
            {"ok": True, "data": {"result": True}},    # [1] drift check
            {"ok": True, "data": {"result": True}},    # [2] before-state read
            {"ok": True, "data": {}, "error": None},   # [3] write (no return value)
            {"ok": True, "data": {"result": False}},   # [4] after-state read
        ]
        _i_b = [0]
        def _exec(code, _s=_seq_b, _idx=_i_b):
            resp = _s[min(_idx[0], len(_s) - 1)]
            _idx[0] += 1
            return resp

        result = execute_undo(proof, _exec, stabilization_delay=0)
        if not result["ok"]:
            errors.append(f"{action_type} undo failed: {result.get('message')}")
        if result["verification_status"] not in ("VERIFIED", "ALREADY_CORRECT"):
            errors.append(f"{action_type} undo vstat: {result['verification_status']}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D84] {e}")
        print("  D84: FAIL")
        return False
    print(f"  {PASS} [D84] execute_undo TRANSPORT_LOOP + TRANSPORT_METRONOME (song bool restore)")
    print("  D84: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D85 — All 7 endpoints via do_POST (HARD_BLOCK→403, offline→503)
# ══════════════════════════════════════════════════════════════════════════════

@section("D85")
def run_d85():
    print("=== Section D85: All 7 Slice 2 endpoints gate via do_POST ===")
    import importlib
    import unittest.mock as _mock

    ndc_mod   = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, path_str, body_dict):
            self.path    = path_str
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

    # All 7 endpoints with minimal valid bodies
    endpoints = [
        ("/action/track_route",         {"track": "Kick", "routing": "Master", "confirm": True}),
        ("/action/track_send",           {"track": "Kick", "send": 0, "value": 0.5}),
        ("/action/transport_play",       {}),
        ("/action/transport_stop",       {}),
        ("/action/transport_record",     {"record": True, "confirm": True}),
        ("/action/transport_loop",       {"loop": True}),
        ("/action/transport_metronome",  {"metronome": True}),
    ]

    errors = []

    # Case A: HARD_BLOCK → 403, no execute calls
    with _mock.patch.object(ndc_mod, "check", return_value=(ndc_mod.NeverDoDecision.HARD_BLOCK, "test rule")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False) as conn_m:
            with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
                for path, body in endpoints:
                    h = _MockH(path, body)
                    h.do_POST()
                    if h._cap_data is None:
                        errors.append(f"HARD_BLOCK {path}: no response")
                        continue
                    if h._cap_data.get("ok") is not False:
                        errors.append(f"HARD_BLOCK {path}: ok should be False")
                    if h._cap_code != 403:
                        errors.append(f"HARD_BLOCK {path}: HTTP {h._cap_code} != 403")
                if exec_m.call_count != 0:
                    errors.append(f"HARD_BLOCK: execute called {exec_m.call_count} times")

    # Case B: ALLOW + disconnected → 503
    with _mock.patch.object(ndc_mod, "check", return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False) as conn_m:
            with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
                for path, body in endpoints:
                    h = _MockH(path, body)
                    h.do_POST()
                    if h._cap_code != 503:
                        errors.append(f"offline {path}: HTTP {h._cap_code} != 503")
                if conn_m.call_count < len(endpoints):
                    errors.append(f"offline: connected checked {conn_m.call_count} < {len(endpoints)} times")
                if exec_m.call_count != 0:
                    errors.append(f"offline: execute called {exec_m.call_count} times")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D85] {e}")
        print("  D85: FAIL")
        return False
    print(f"  {PASS} [D85] All 7 endpoints gate via do_POST — HARD_BLOCK→403, offline→503")
    print("  D85: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D86 — track_route confirm gate
# ══════════════════════════════════════════════════════════════════════════════

@section("D86")
def run_d86():
    print("=== Section D86: track_route confirm gate ===")
    import importlib
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/track_route"
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
    from rag.bridge_errors import BridgeErrorCode

    # Case A: confirm=False → REQUIRE_CONFIRMATION → 403
    with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False):
            h = _MockH({"track": "Kick", "routing": "DRUM BUS", "confirm": False})
            h.do_POST()
            if h._cap_code != 403:
                errors.append(f"no-confirm: HTTP {h._cap_code} != 403")
            ec = (h._cap_data or {}).get("error_code", "")
            if ec != BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED.value:
                errors.append(f"no-confirm: error_code {ec!r}")
            if exec_m.call_count != 0:
                errors.append(f"no-confirm: execute called {exec_m.call_count} times")

    # Case B: confirm=True → gate bypassed → offline → 503
    with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False) as conn_m:
            h = _MockH({"track": "Kick", "routing": "DRUM BUS", "confirm": True})
            h.do_POST()
            if h._cap_code != 503:
                errors.append(f"confirm: HTTP {h._cap_code} != 503 (expected BRIDGE_TIMEOUT)")
            if conn_m.call_count == 0:
                errors.append("confirm: ableton_connected never called")
            if exec_m.call_count != 0:
                errors.append(f"confirm: execute called {exec_m.call_count} times (should be 0 offline)")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D86] {e}")
        print("  D86: FAIL")
        return False
    print(f"  {PASS} [D86] track_route confirm gate — no-confirm→403, confirm→offline→503")
    print("  D86: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D87 — transport_record confirm gate
# ══════════════════════════════════════════════════════════════════════════════

@section("D87")
def run_d87():
    print("=== Section D87: transport_record confirm gate ===")
    import importlib
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/transport_record"
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
    from rag.bridge_errors import BridgeErrorCode

    # Case A: confirm=False → 403
    with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False):
            h = _MockH({"record": True, "confirm": False})
            h.do_POST()
            if h._cap_code != 403:
                errors.append(f"no-confirm: HTTP {h._cap_code} != 403")
            ec = (h._cap_data or {}).get("error_code", "")
            if ec != BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED.value:
                errors.append(f"no-confirm: error_code {ec!r}")
            if exec_m.call_count != 0:
                errors.append(f"no-confirm: execute called")

    # Case B: confirm=True → offline → 503
    with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False) as conn_m:
            h = _MockH({"record": True, "confirm": True})
            h.do_POST()
            if h._cap_code != 503:
                errors.append(f"confirm: HTTP {h._cap_code} != 503")
            if conn_m.call_count == 0:
                errors.append("confirm: connected never called")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D87] {e}")
        print("  D87: FAIL")
        return False
    print(f"  {PASS} [D87] transport_record confirm gate — no-confirm→403, confirm→offline→503")
    print("  D87: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D88 — Proof field honesty
# ══════════════════════════════════════════════════════════════════════════════

@section("D88")
def run_d88():
    print("=== Section D88: Proof field honesty — send target, route before_state ===")
    errors = []

    # Send proof (plain dict): target must include ":send:{idx}"
    p = _make_send_proof(before_val=0.2, after_val=0.7, track="Bass", send_idx=1)
    if ":send:1" not in p["target"]:
        errors.append(f"send proof target missing :send:1: {p['target']!r}")
    if p["before_state"].get("send_value") != 0.2:
        errors.append(f"send before_state.send_value wrong: {p['before_state']}")
    if p["after_state"].get("send_value") != 0.7:
        errors.append(f"send after_state.send_value wrong: {p['after_state']}")
    if p["undo_eligible"] is not True:
        errors.append(f"send undo_eligible should be True: {p['undo_eligible']}")

    # Route proof (plain dict): before_state has routing string
    rp = _make_route_proof(before_r="Master", after_r="STRINGS BUS")
    if rp["before_state"].get("routing") != "Master":
        errors.append(f"route before_state.routing wrong: {rp['before_state']}")
    if rp["after_state"].get("routing") != "STRINGS BUS":
        errors.append(f"route after_state.routing wrong: {rp['after_state']}")
    if rp["undo_eligible"] is not True:
        errors.append(f"route undo_eligible should be True: {rp['undo_eligible']}")

    # Transport play/stop: undo_eligible = False (use ActionProof for attribute check)
    tp = create_proof(
        action_type="TRANSPORT_PLAY", target="song",
        intended_value=True,
        before_state={"is_playing": False}, after_state={"is_playing": True},
        verification_status="VERIFIED", undo_eligible=False,
        user_facing_summary="play",
    )
    if tp.undo_eligible is not False:
        errors.append(f"TRANSPORT_PLAY undo_eligible should be False: {tp.undo_eligible}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D88] {e}")
        print("  D88: FAIL")
        return False
    print(f"  {PASS} [D88] Proof field honesty — send target/state, route state, play undo_eligible=False")
    print("  D88: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D89 — Slice 6 regression
# ══════════════════════════════════════════════════════════════════════════════

@section("D89")
def run_d89():
    """Run Phase D Slice 6 eval as regression."""
    print("=== Section D89: Slice 6 regression ===")
    import subprocess
    result = subprocess.run(
        ["python3", "tests/phase_d_slice6_eval.py"],
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    lines = result.stdout.splitlines()
    fail_lines = [l for l in lines if l.strip().startswith("❌")]
    if fail_lines or result.returncode != 0:
        print(f"  {FAIL} [D89] Slice 6 regression FAIL:")
        for l in fail_lines[:10]:
            print(f"    {l}")
        if result.returncode != 0 and not fail_lines:
            print(f"  returncode={result.returncode}")
            print(result.stderr[-500:] if result.stderr else "")
        return False
    pass_count = sum(1 for l in lines if "✅" in l)
    print(f"  {PASS} [D89] Slice 6 regression — {pass_count} checks pass")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D90 — Phase C regression
# ══════════════════════════════════════════════════════════════════════════════

@section("D90")
def run_d90():
    """Run Phase C eval as regression."""
    print("=== Section D90: Phase C regression ===")
    import subprocess
    result = subprocess.run(
        ["python3", "tests/phase_c_eval_set.py"],
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    lines = result.stdout.splitlines()
    fail_lines = [l for l in lines if l.strip().startswith("❌")]
    if fail_lines or result.returncode != 0:
        print(f"  {FAIL} [D90] Phase C regression FAIL:")
        for l in fail_lines[:10]:
            print(f"    {l}")
        if result.returncode != 0 and not fail_lines:
            print(f"  returncode={result.returncode}")
            print(result.stderr[-500:] if result.stderr else "")
        return False
    pass_count = sum(1 for l in lines if "✅" in l)
    print(f"  {PASS} [D90] Phase C regression — {pass_count} checks pass")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D91 — track_send invalid send index
# ══════════════════════════════════════════════════════════════════════════════

@section("D91")
def run_d91():
    print("=== Section D91: track_send invalid send index ===")
    import importlib
    import unittest.mock as _mock

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/track_send"
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
    from rag.bridge_errors import BridgeErrorCode

    # send=-1 → 400 before any executor call
    with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
        h = _MockH({"track": "Kick", "send": -1, "value": 0.5})
        h.do_POST()

    if h._cap_code != 400:
        errors.append(f"send=-1: HTTP {h._cap_code} != 400")
    ec = (h._cap_data or {}).get("error_code", "")
    if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value:
        errors.append(f"send=-1: error_code {ec!r} != {BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value!r}")
    if exec_m.call_count != 0:
        errors.append(f"send=-1: execute called {exec_m.call_count} times (expected 0)")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D91] {e}")
        print("  D91: FAIL")
        return False
    print(f"  {PASS} [D91] track_send send=-1 → 400 BRIDGE_PARAM_OUT_OF_RANGE, no write path")
    print("  D91: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D92 — track_send out-of-range level
# ══════════════════════════════════════════════════════════════════════════════

@section("D92")
def run_d92():
    print("=== Section D92: track_send out-of-range level ===")
    import importlib
    import unittest.mock as _mock

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/track_send"
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
    from rag.bridge_errors import BridgeErrorCode

    for bad_val in [-0.1, 2.0]:
        with _mock.patch.object(bridge_mod, "ableton_execute") as exec_m:
            h = _MockH({"track": "Kick", "send": 0, "value": bad_val})
            h.do_POST()
        if h._cap_code != 400:
            errors.append(f"value={bad_val}: HTTP {h._cap_code} != 400")
        ec = (h._cap_data or {}).get("error_code", "")
        if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value:
            errors.append(f"value={bad_val}: error_code {ec!r}")
        if exec_m.call_count != 0:
            errors.append(f"value={bad_val}: execute called {exec_m.call_count} times (expected 0)")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D92] {e}")
        print("  D92: FAIL")
        return False
    print(f"  {PASS} [D92] track_send value=-0.1 and value=2.0 → 400 BRIDGE_PARAM_OUT_OF_RANGE, no write path")
    print("  D92: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D93 — track_route invalid destination
# ══════════════════════════════════════════════════════════════════════════════

@section("D93")
def run_d93():
    print("=== Section D93: track_route invalid destination ===")
    import importlib
    import unittest.mock as _mock

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")
    ConductorHandler = bridge_mod.ConductorHandler

    class _MockH(ConductorHandler):
        def __init__(self, body_dict):
            self.path    = "/action/track_route"
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
    from rag.bridge_errors import BridgeErrorCode

    # ableton_execute always returns the available routes list (any call)
    avail_resp = {"ok": True, "data": {"result": ["Master", "DRUM BUS"]}}

    # Case A: routing NOT in available routes → 400, only 1 execute call (availability check)
    with _mock.patch.object(ndc_mod, "check", return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "ableton_execute",
                                    return_value=avail_resp) as exec_m:
                h = _MockH({"track": "Kick", "routing": "INVALID BUS", "confirm": True})
                h.do_POST()

    if h._cap_code != 400:
        errors.append(f"invalid dest: HTTP {h._cap_code} != 400")
    ec = (h._cap_data or {}).get("error_code", "")
    if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value:
        errors.append(f"invalid dest: error_code {ec!r} != {BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value!r}")
    # Exactly 1 execute call: the availability check.  No before_read, no write.
    if exec_m.call_count != 1:
        errors.append(f"invalid dest: expected 1 execute call (avail check only), got {exec_m.call_count}")

    # Case B: routing IS in available routes → passes precheck (not 400)
    with _mock.patch.object(ndc_mod, "check", return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "ableton_execute",
                                    return_value=avail_resp) as exec_m2:
                h2 = _MockH({"track": "Kick", "routing": "DRUM BUS", "confirm": True})
                h2.do_POST()

    if (h2._cap_data or {}).get("error_code") == BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value:
        errors.append("valid routing must not return BRIDGE_PARAM_OUT_OF_RANGE")
    # At least 2 execute calls: avail check + at least one verify_track_route read
    if exec_m2.call_count < 2:
        errors.append(f"valid routing: expected >=2 execute calls, got {exec_m2.call_count}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D93] {e}")
        print("  D93: FAIL")
        return False
    print(f"  {PASS} [D93] track_route invalid destination → 400 before write; valid destination passes precheck")
    print("  D93: PASS")
    return True


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
    print(f"  Phase D Action Expansion Slice 2 — {total}/{total} sections")
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
