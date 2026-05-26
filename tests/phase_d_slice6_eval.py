"""
Conductor — Phase D Action Expansion Slice 1 Eval Suite (D52–D73)
──────────────────────────────────────────────────────────────────
Track / Recording actions: arm, monitor, rename, color, create,
delete, duplicate, return_track_create, tracks_create_multiple.

Tests are fully offline — no Ableton connection required.

Run:
    python3 tests/phase_d_slice6_eval.py

Sections:
    D52  — New action type decisions (CREATE, DUPLICATE, ARM, MONITOR, COLOR)
    D53  — DELETE_TRACK is REQUIRE_CONFIRMATION (not HARD_BLOCK)
    D54  — Batch escalation: CREATE_TRACK with track_count>3 → REQUIRE_CONFIRMATION
    D55  — All Slice 1 action types have known (non-CLARIFY) decisions
    D56  — verify_track_arm: VERIFIED path
    D57  — verify_track_arm: ALREADY_CORRECT path
    D58  — verify_track_monitor: VERIFIED path + ALREADY_CORRECT
    D59  — verify_track_create: VERIFIED + count-based readback
    D60  — verify_track_delete: VERIFIED + FAILED (track absent)
    D61  — verify_track_duplicate: VERIFIED path
    D62  — verify_track_rename: VERIFIED + index-based stability
    D63  — verify_track_color: VERIFIED + palette-snap handling
    D64  — Bridge /action/track_arm — ALLOW path (mocked executor)
    D65  — Bridge /action/track_arm — non-ALLOW gate blocks before write
    D66  — Bridge /action/track_delete — no confirm → 403 CONFIRMATION_REQUIRED
    D67  — Bridge /action/track_delete — confirm=True bypasses gate
    D68  — Bridge /action/tracks_create_multiple — batch confirm gate
    D69  — Undo ARM_TRACK: undo_eligible + UndoValidationError for unsupported
    D70  — Undo SET_TRACK_MONITOR: undo_eligible
    D71  — BeforeStateCaptureError: new endpoints block write on unreadable before
    D72  — Black box log: new action types produce NEVER_DO_BLOCKED events
    D73  — Slice 1–5 + Phase C regressions still pass
"""

import os
import sys
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

PASS = "✅"
FAIL = "❌"


# ── MOCK EXECUTOR HELPERS ──────────────────────────────────────────────────────

def _make_executor(responses: dict, default=None):
    """
    Build a mock executor for offline readback tests.

    responses: dict mapping code-substring → response dict
    default:   fallback response when no substring matches (default: ok=True, result=0)

    Matches by checking if the key is a substring of the code string.
    First match wins (dict iteration order = insertion order in Python 3.7+).
    """
    _default = default or {"ok": True, "data": {"result": 0}, "error": None}

    def _exec(code, timeout=10.0):
        for key, resp in responses.items():
            if key in str(code):
                return resp
        return _default

    return _exec


def _ok(value):
    return {"ok": True, "data": {"result": value}, "error": None}


def _fail(msg="error"):
    return {"ok": False, "data": {}, "error": msg}


# ── SECTION D52: New action type decisions ─────────────────────────────────────

def run_d52() -> bool:
    """New action types added in Slice 1 all have ALLOW decisions."""
    print("\n=== Section D52: Slice 1 ALLOW action types ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    allow_types = [
        "CREATE_TRACK",
        "CREATE_AUDIO_TRACK",
        "CREATE_RETURN_TRACK",
        "DUPLICATE_TRACK",
        "ARM_TRACK",
        "SET_TRACK_MONITOR",
        "RENAME_TRACK",
        "SET_TRACK_COLOR",
    ]

    for action in allow_types:
        decision, _ = check(action)
        if decision != NeverDoDecision.ALLOW:
            print(f"{FAIL} [D52] {action} should be ALLOW, got {decision!r}")
            ok = False
        else:
            print(f"{PASS} [D52] {action} → ALLOW")

    print(f"\n  D52 Slice 1 ALLOW table: {'all' if ok else 'SOME FAIL'}")
    return ok


# ── SECTION D53: DELETE_TRACK is REQUIRE_CONFIRMATION ─────────────────────────

def run_d53() -> bool:
    """DELETE_TRACK is REQUIRE_CONFIRMATION, not HARD_BLOCK."""
    print("\n=== Section D53: DELETE_TRACK = REQUIRE_CONFIRMATION ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    decision, rule = check("DELETE_TRACK")
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D53] DELETE_TRACK should be REQUIRE_CONFIRMATION, got {decision!r}")
        ok = False
    else:
        print(f"{PASS} [D53] DELETE_TRACK → REQUIRE_CONFIRMATION")

    # DELETE_CLIP should still be HARD_BLOCK
    decision2, _ = check("DELETE_CLIP")
    if decision2 != NeverDoDecision.HARD_BLOCK:
        print(f"{FAIL} [D53] DELETE_CLIP should still be HARD_BLOCK, got {decision2!r}")
        ok = False
    else:
        print(f"{PASS} [D53] DELETE_CLIP → HARD_BLOCK (unchanged)")

    print(f"\n  D53: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D54: Batch escalation ─────────────────────────────────────────────

def run_d54() -> bool:
    """CREATE_TRACK with track_count > 3 escalates to REQUIRE_CONFIRMATION."""
    print("\n=== Section D54: Batch escalation (count>3) ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache, _BATCH_THRESHOLD
    _clear_rules_cache()

    # Below threshold — ALLOW
    decision_ok, _ = check("CREATE_TRACK", {"track_count": _BATCH_THRESHOLD})
    if decision_ok != NeverDoDecision.ALLOW:
        print(f"{FAIL} [D54] CREATE_TRACK count={_BATCH_THRESHOLD} should be ALLOW, got {decision_ok!r}")
        ok = False
    else:
        print(f"{PASS} [D54] CREATE_TRACK count={_BATCH_THRESHOLD} → ALLOW")

    # Above threshold — REQUIRE_CONFIRMATION
    decision_batch, rule_batch = check("CREATE_TRACK", {"track_count": _BATCH_THRESHOLD + 1})
    if decision_batch != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D54] CREATE_TRACK count={_BATCH_THRESHOLD+1} should be REQUIRE_CONFIRMATION, "
              f"got {decision_batch!r}")
        ok = False
    else:
        print(f"{PASS} [D54] CREATE_TRACK count={_BATCH_THRESHOLD+1} → REQUIRE_CONFIRMATION")

    print(f"\n  D54: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D55: All Slice 1 action types have known decisions ────────────────

def run_d55() -> bool:
    """All new action types return a known decision (not CLARIFY_REQUIRED)."""
    print("\n=== Section D55: No CLARIFY on known Slice 1 types ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    all_new_types = [
        "CREATE_TRACK", "CREATE_AUDIO_TRACK", "CREATE_RETURN_TRACK",
        "DUPLICATE_TRACK", "ARM_TRACK", "SET_TRACK_MONITOR",
        "RENAME_TRACK", "SET_TRACK_COLOR", "DELETE_TRACK",
        "BATCH_CREATE_TRACKS",
    ]

    for action in all_new_types:
        decision, _ = check(action)
        if decision == NeverDoDecision.CLARIFY_REQUIRED:
            print(f"{FAIL} [D55] {action} returned CLARIFY_REQUIRED (unknown action)")
            ok = False
        else:
            print(f"{PASS} [D55] {action} → {decision.value}")

    print(f"\n  D55: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D56: verify_track_arm ─────────────────────────────────────────────

def run_d56() -> bool:
    """verify_track_arm: VERIFIED and ALREADY_CORRECT paths."""
    print("\n=== Section D56: verify_track_arm ===")
    ok = True

    from rag.readback import verify_track_arm, BeforeStateCaptureError

    # VERIFIED: before=False, write ok, after=True
    # Stateful mock needed: read code and write code both contain "song.tracks".
    # Write code is uniquely identified by "__arm_tracks__" (the temp var).
    _read_n = [0]
    def _exec_arm_verified(code, timeout=10.0):
        if "__arm_tracks__" in str(code):   # write code
            return {"ok": True, "data": {"result": None}, "error": None}
        else:                               # read code (before + after share same string)
            _read_n[0] += 1
            val = False if _read_n[0] == 1 else True
            return {"ok": True, "data": {"result": val}, "error": None}

    rb = verify_track_arm("Kick", True, _exec_arm_verified, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D56] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"] != {"arm": False}:
        print(f"{FAIL} [D56] before_state wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"] != {"arm": True}:
        print(f"{FAIL} [D56] after_state wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D56] VERIFIED path: arm False → True")

    # ALREADY_CORRECT: before=True, intended=True → no write
    exec2 = _make_executor({}, default=_ok(True))  # always returns True
    rb2 = verify_track_arm("Kick", True, exec2, stabilization_delay=0)
    if rb2["verification_status"] != "ALREADY_CORRECT":
        print(f"{FAIL} [D56] Expected ALREADY_CORRECT, got {rb2['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D56] ALREADY_CORRECT: arm already True")

    # BeforeStateCaptureError: before read returns None
    exec3 = _make_executor({}, default=_fail("Ableton unreachable"))
    try:
        verify_track_arm("Kick", True, exec3, stabilization_delay=0)
        print(f"{FAIL} [D56] Should have raised BeforeStateCaptureError")
        ok = False
    except BeforeStateCaptureError:
        print(f"{PASS} [D56] BeforeStateCaptureError raised on unreadable before")

    print(f"\n  D56: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D57: verify_track_monitor ─────────────────────────────────────────

def run_d57() -> bool:
    """verify_track_monitor: VERIFIED (0→1) and ALREADY_CORRECT paths."""
    print("\n=== Section D57: verify_track_monitor ===")
    ok = True

    from rag.readback import verify_track_monitor

    # VERIFIED: before=0 (In), write, after=1 (Auto)
    calls = {"current_monitoring_state": 0}
    call_count = [0]

    def exec_monitor(code, timeout=10.0):
        if "current_monitoring_state = " in str(code):
            calls["write_called"] = True
            return {"ok": True, "data": {"result": None}, "error": None}
        call_count[0] += 1
        val = 0 if call_count[0] == 1 else 1  # before=0, after=1
        return {"ok": True, "data": {"result": val}, "error": None}

    rb = verify_track_monitor("Bass", 1, exec_monitor, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D57] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"].get("monitor") != 0:
        print(f"{FAIL} [D57] before_state monitor wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"].get("monitor") != 1:
        print(f"{FAIL} [D57] after_state monitor wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D57] VERIFIED: monitor 0 (In) → 1 (Auto)")

    # ALREADY_CORRECT: before=2, intended=2
    rb2 = verify_track_monitor("Bass", 2, _make_executor({}, default=_ok(2)), stabilization_delay=0)
    if rb2["verification_status"] != "ALREADY_CORRECT":
        print(f"{FAIL} [D57] Expected ALREADY_CORRECT, got {rb2['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D57] ALREADY_CORRECT: monitor already Off (2)")

    print(f"\n  D57: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D58: verify_track_create ──────────────────────────────────────────

def run_d58() -> bool:
    """verify_track_create: VERIFIED when count increases by 1."""
    print("\n=== Section D58: verify_track_create ===")
    ok = True

    from rag.readback import verify_track_create

    count_state = {"count": 3}

    def exec_create(code, timeout=10.0):
        if "create_midi_track" in code:
            count_state["count"] += 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "len(song.tracks)" in code:
            return {"ok": True, "data": {"result": count_state["count"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_track_create("midi", exec_create, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D58] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"].get("track_count") != 3:
        print(f"{FAIL} [D58] before track_count wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"].get("track_count") != 4:
        print(f"{FAIL} [D58] after track_count wrong: {rb['after_state']}")
        ok = False
    elif rb["after_state"].get("new_track_index") != 3:
        print(f"{FAIL} [D58] new_track_index wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D58] VERIFIED: track_count 3 → 4, new_track_index=3")

    # FAILED: count does not increase
    rb2 = verify_track_create("midi",
                               _make_executor({"len(song.tracks)": _ok(5),
                                               "create_midi_track": _fail("lom error")}),
                               stabilization_delay=0)
    # count never changes → FAILED
    if rb2["verification_status"] not in ("FAILED", "UNVERIFIED"):
        print(f"{FAIL} [D58] Expected FAILED/UNVERIFIED when count unchanged, got {rb2['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D58] FAILED/UNVERIFIED when count does not increase")

    print(f"\n  D58: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D59: verify_track_delete ──────────────────────────────────────────

def run_d59() -> bool:
    """verify_track_delete: VERIFIED when count decreases; FAILED when track absent."""
    print("\n=== Section D59: verify_track_delete ===")
    ok = True

    from rag.readback import verify_track_delete

    count_state = {"count": 5}

    def exec_delete(code, timeout=10.0):
        if "delete_track" in code:
            count_state["count"] -= 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "len(song.tracks)" in code:
            return {"ok": True, "data": {"result": count_state["count"]}, "error": None}
        if "enumerate(song.tracks)" in code:
            return {"ok": True, "data": {"result": 2}, "error": None}   # track at index 2
        if "song.tracks[2].name" in code:
            return {"ok": True, "data": {"result": "Snare"}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_track_delete("Snare", exec_delete, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D59] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"].get("track_count") != 5:
        print(f"{FAIL} [D59] before track_count wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"].get("track_count") != 4:
        print(f"{FAIL} [D59] after track_count wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D59] VERIFIED: track_count 5 → 4")

    # FAILED: track not found — _read_track_index returns None
    rb2 = verify_track_delete("GhostTrack",
                               _make_executor({"enumerate(song.tracks)": _ok(None)}),
                               stabilization_delay=0)
    from rag.bridge_errors import BridgeErrorCode
    if rb2["verification_status"] != "FAILED":
        print(f"{FAIL} [D59] Expected FAILED for absent track, got {rb2['verification_status']!r}")
        ok = False
    elif rb2["error_code"] != BridgeErrorCode.BRIDGE_TRACK_ABSENT.value:
        print(f"{FAIL} [D59] Expected BRIDGE_TRACK_ABSENT, got {rb2['error_code']!r}")
        ok = False
    else:
        print(f"{PASS} [D59] FAILED with BRIDGE_TRACK_ABSENT for missing track")

    print(f"\n  D59: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D60: verify_track_duplicate ───────────────────────────────────────

def run_d60() -> bool:
    """verify_track_duplicate: VERIFIED when count increases by 1."""
    print("\n=== Section D60: verify_track_duplicate ===")
    ok = True

    from rag.readback import verify_track_duplicate

    count_state = {"count": 4}

    def exec_dup(code, timeout=10.0):
        if "duplicate_track" in code:
            count_state["count"] += 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "len(song.tracks)" in code:
            return {"ok": True, "data": {"result": count_state["count"]}, "error": None}
        if "enumerate(song.tracks)" in code:
            return {"ok": True, "data": {"result": 1}, "error": None}  # track at index 1
        if "song.tracks[1].name" in code:
            return {"ok": True, "data": {"result": "Kick"}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_track_duplicate("Kick", exec_dup, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D60] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"].get("track_count") != 4:
        print(f"{FAIL} [D60] before_state wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"].get("track_count") != 5:
        print(f"{FAIL} [D60] after_state wrong: {rb['after_state']}")
        ok = False
    elif rb["after_state"].get("new_track_index") != 2:  # idx 1 + 1
        print(f"{FAIL} [D60] new_track_index wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D60] VERIFIED: duplicate of index 1, new at 2")

    print(f"\n  D60: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D61: verify_track_rename ──────────────────────────────────────────

def run_d61() -> bool:
    """verify_track_rename: index-based, VERIFIED and ALREADY_CORRECT."""
    print("\n=== Section D61: verify_track_rename ===")
    ok = True

    from rag.readback import verify_track_rename

    name_state = {"name": "OldName"}

    def exec_rename(code, timeout=10.0):
        if '.name = "' in str(code):
            # Write: extract the new name from the code
            import re
            m = re.search(r'\.name = "([^"]*)"', str(code))
            if m:
                name_state["name"] = m.group(1)
            return {"ok": True, "data": {"result": None}, "error": None}
        if "song.tracks[" in str(code) and ".name" in str(code):
            return {"ok": True, "data": {"result": name_state["name"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_track_rename(0, "NewName", exec_rename, stabilization_delay=0)
    if rb["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D61] Expected VERIFIED, got {rb['verification_status']!r}")
        ok = False
    elif rb["before_state"].get("name") != "OldName":
        print(f"{FAIL} [D61] before_state name wrong: {rb['before_state']}")
        ok = False
    elif rb["after_state"].get("name") != "NewName":
        print(f"{FAIL} [D61] after_state name wrong: {rb['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D61] VERIFIED: renamed OldName → NewName at index 0")

    # ALREADY_CORRECT: name is already the same
    rb2 = verify_track_rename(0, "NewName",
                               _make_executor({}, default=_ok("NewName")),
                               stabilization_delay=0)
    if rb2["verification_status"] != "ALREADY_CORRECT":
        print(f"{FAIL} [D61] Expected ALREADY_CORRECT, got {rb2['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D61] ALREADY_CORRECT: name unchanged")

    print(f"\n  D61: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D62: verify_track_color ───────────────────────────────────────────

def run_d62() -> bool:
    """verify_track_color: VERIFIED on change, ALREADY_CORRECT if same, palette-snap note."""
    print("\n=== Section D62: verify_track_color ===")
    ok = True

    from rag.readback import verify_track_color

    # VERIFIED: before=#FF0000, write accepted, after=#FE0000 (palette snap)
    color_state = {"color": 0xFF0000}

    def exec_color(code, timeout=10.0):
        if ".color = " in str(code):
            # Simulate palette snap
            color_state["color"] = 0xFE0000
            return {"ok": True, "data": {"result": None}, "error": None}
        if ".color" in str(code):
            return {"ok": True, "data": {"result": color_state["color"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb = verify_track_color("Lead", 0xFF0000, exec_color, stabilization_delay=0)
    # before=0xFF0000, intended=0xFF0000 → ALREADY_CORRECT (same)
    if rb["verification_status"] != "ALREADY_CORRECT":
        print(f"{FAIL} [D62] Expected ALREADY_CORRECT (same color), got {rb['verification_status']!r}")
        ok = False
    else:
        print(f"{PASS} [D62] ALREADY_CORRECT: color was already the target")

    # VERIFIED: before different from intended
    color_state2 = {"color": 0x000000}

    def exec_color2(code, timeout=10.0):
        if ".color = " in str(code):
            color_state2["color"] = 0xFE0000   # palette snap
            return {"ok": True, "data": {"result": None}, "error": None}
        if ".color" in str(code):
            return {"ok": True, "data": {"result": color_state2["color"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb2 = verify_track_color("Lead", 0xFF0000, exec_color2, stabilization_delay=0)
    if rb2["verification_status"] != "VERIFIED":
        print(f"{FAIL} [D62] Expected VERIFIED (palette snap), got {rb2['verification_status']!r}")
        ok = False
    elif rb2["after_state"].get("color") != 0xFE0000:
        print(f"{FAIL} [D62] after_state color wrong: {rb2['after_state']}")
        ok = False
    else:
        snap_noted = "palette-snapped" in rb2.get("message", "").lower()
        print(f"{PASS} [D62] VERIFIED with palette snap: #{0xFE0000:06X}"
              f"{' (snap noted in message)' if snap_noted else ''}")

    print(f"\n  D62: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D63: All 9 endpoints — gate block via _MockHandler.do_POST() ───────

def run_d63() -> bool:
    """
    All 9 Slice 1 endpoints: a HARD_BLOCK never-do decision stops execution
    before any Ableton call.  Tests are fully offline — no connection needed.

    Pattern: monkeypatch ndc_mod.check → HARD_BLOCK, call do_POST() via
    _MockHandler, assert ok=False + SECURITY_NEVER_DO_BLOCK + 0 Ableton calls.
    """
    print("\n=== Section D63: All 9 endpoints — gate block via do_POST ===")
    ok = True

    import io, json as _json, importlib
    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision
    from conductor_bridge   import ConductorHandler

    execute_calls   = [0]
    connected_calls = [0]
    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    _orig_check     = ndc_mod.check

    def _track_execute(code, timeout=10.0):
        execute_calls[0] += 1
        return {"ok": False, "error": "sentinel", "data": {}}

    def _track_connected():
        connected_calls[0] += 1
        return False

    _cb_mod.ableton_execute   = _track_execute
    _cb_mod.ableton_connected = _track_connected

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

    # 9 endpoints with minimal valid bodies
    endpoints = [
        ("/action/track_arm",              {"track": "Kick",  "arm": True}),
        ("/action/track_monitor",          {"track": "Kick",  "mode": 1}),
        ("/action/track_rename",           {"track": "Kick",  "name": "NewKick"}),
        ("/action/track_color",            {"track": "Kick",  "color": 0xFF0000}),
        ("/action/track_create",           {"type": "midi"}),
        ("/action/track_delete",           {"track": "Kick",  "confirm": True}),
        ("/action/track_duplicate",        {"track": "Kick"}),
        ("/action/return_track_create",    {}),
        ("/action/tracks_create_multiple", {"count": 2}),
    ]

    try:
        for path, body in endpoints:
            execute_calls[0]   = 0
            connected_calls[0] = 0
            ndc_mod.check      = lambda a, ctx=None: (NeverDoDecision.HARD_BLOCK, "test-rule-d63")

            h = _MockH(path, body)
            h.do_POST()

            ep = path.split("/")[-1]
            fail_msgs = []

            if h._cap_data is None:
                fail_msgs.append("no response captured")
            else:
                if h._cap_data.get("ok") is not False:
                    fail_msgs.append(f"ok={h._cap_data.get('ok')!r} (expected False)")
                if h._cap_data.get("error_code") != "SECURITY_NEVER_DO_BLOCK":
                    fail_msgs.append(
                        f"error_code={h._cap_data.get('error_code')!r} "
                        "(expected SECURITY_NEVER_DO_BLOCK)")
                if h._cap_code != 403:
                    fail_msgs.append(f"http={h._cap_code} (expected 403)")

            if execute_calls[0] != 0:
                fail_msgs.append(
                    f"ableton_execute called {execute_calls[0]}x (must be 0)")
            if connected_calls[0] != 0:
                fail_msgs.append(
                    f"ableton_connected called {connected_calls[0]}x (must be 0)")

            if fail_msgs:
                for m in fail_msgs:
                    print(f"{FAIL} [D63] {ep}: {m}")
                ok = False
            else:
                print(f"{PASS} [D63] {ep}: HARD_BLOCK → 403, 0 Ableton calls")

    finally:
        ndc_mod.check             = _orig_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    print(f"\n  D63: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D64: All 9 endpoints — offline path via _MockHandler.do_POST() ────

def run_d64() -> bool:
    """
    All 9 Slice 1 endpoints: ALLOW gate passes, ableton_connected returns False
    → each endpoint returns BRIDGE_TIMEOUT (503), connected called ≥1 time,
    execute called 0 times.
    """
    print("\n=== Section D64: All 9 endpoints — ALLOW + disconnected via do_POST ===")
    ok = True

    import io, json as _json
    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision
    from conductor_bridge   import ConductorHandler

    execute_calls   = [0]
    connected_calls = [0]
    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    _orig_check     = ndc_mod.check

    def _track_execute(code, timeout=10.0):
        execute_calls[0] += 1
        return {"ok": False, "error": "sentinel", "data": {}}

    def _track_connected():
        connected_calls[0] += 1
        return False  # always offline

    _cb_mod.ableton_execute   = _track_execute
    _cb_mod.ableton_connected = _track_connected

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

    endpoints = [
        ("/action/track_arm",              {"track": "Kick",  "arm": True}),
        ("/action/track_monitor",          {"track": "Kick",  "mode": 1}),
        ("/action/track_rename",           {"track": "Kick",  "name": "NewKick"}),
        ("/action/track_color",            {"track": "Kick",  "color": 0xFF0000}),
        ("/action/track_create",           {"type": "midi"}),
        ("/action/track_delete",           {"track": "Kick",  "confirm": True}),
        ("/action/track_duplicate",        {"track": "Kick"}),
        ("/action/return_track_create",    {}),
        ("/action/tracks_create_multiple", {"count": 2}),
    ]

    _SECURITY_CODES = {
        "SECURITY_NEVER_DO_BLOCK",
        "SECURITY_CONFIRMATION_REQUIRED",
        "SECURITY_CLARIFY_REQUIRED",
    }

    try:
        for path, body in endpoints:
            execute_calls[0]   = 0
            connected_calls[0] = 0
            ndc_mod.check      = lambda a, ctx=None: (NeverDoDecision.ALLOW, "")

            h = _MockH(path, body)
            h.do_POST()

            ep = path.split("/")[-1]
            fail_msgs = []

            if h._cap_data is None:
                fail_msgs.append("no response captured")
            else:
                ec = h._cap_data.get("error_code", "")
                if ec in _SECURITY_CODES:
                    fail_msgs.append(
                        f"ALLOW was gate-blocked (error_code={ec!r})")
                if h._cap_data.get("error_code") != "BRIDGE_TIMEOUT":
                    fail_msgs.append(
                        f"error_code={h._cap_data.get('error_code')!r} "
                        "(expected BRIDGE_TIMEOUT when offline)")
                if h._cap_code != 503:
                    fail_msgs.append(f"http={h._cap_code} (expected 503)")

            if connected_calls[0] == 0:
                fail_msgs.append(
                    "ableton_connected not called — gate may have misfired")
            if execute_calls[0] != 0:
                fail_msgs.append(
                    f"ableton_execute called {execute_calls[0]}x (must be 0 when offline)")

            if fail_msgs:
                for m in fail_msgs:
                    print(f"{FAIL} [D64] {ep}: {m}")
                ok = False
            else:
                print(f"{PASS} [D64] {ep}: ALLOW+offline → BRIDGE_TIMEOUT, "
                      f"connected {connected_calls[0]}x, execute 0x")

    finally:
        ndc_mod.check             = _orig_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    print(f"\n  D64: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D65: track_delete — confirm gate via do_POST() ────────────────────

def run_d65() -> bool:
    """
    /action/track_delete via do_POST():
      - confirm=False → REQUIRE_CONFIRMATION gate fires → 403
        SECURITY_CONFIRMATION_REQUIRED, 0 execute/connected calls.
      - confirm=True → gate bypassed, ALLOW path → connected called,
        offline → 503 BRIDGE_TIMEOUT.
    """
    print("\n=== Section D65: /action/track_delete — confirm gate via do_POST ===")
    ok = True

    import io, json as _json
    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision
    from conductor_bridge   import ConductorHandler

    execute_calls   = [0]
    connected_calls = [0]
    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    _orig_check     = ndc_mod.check

    def _track_execute(code, timeout=10.0):
        execute_calls[0] += 1
        return {"ok": False, "error": "sentinel", "data": {}}

    def _track_connected():
        connected_calls[0] += 1
        return False

    _cb_mod.ableton_execute   = _track_execute
    _cb_mod.ableton_connected = _track_connected

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

    try:
        from rag.never_do_check import _clear_rules_cache
        _clear_rules_cache()

        # Case A: confirm=False → gate fires (REQUIRE_CONFIRMATION not bypassed)
        execute_calls[0]   = 0
        connected_calls[0] = 0
        # Use real check — DELETE_TRACK is REQUIRE_CONFIRMATION
        ndc_mod.check = _orig_check

        h_noconfirm = _MockH("/action/track_delete", {"track": "Kick", "confirm": False})
        h_noconfirm.do_POST()

        fail_a = []
        if h_noconfirm._cap_data is None:
            fail_a.append("no response")
        else:
            if h_noconfirm._cap_data.get("error_code") != "SECURITY_CONFIRMATION_REQUIRED":
                fail_a.append(
                    f"error_code={h_noconfirm._cap_data.get('error_code')!r} "
                    "(expected SECURITY_CONFIRMATION_REQUIRED)")
            if h_noconfirm._cap_code != 403:
                fail_a.append(f"http={h_noconfirm._cap_code} (expected 403)")
        if execute_calls[0] != 0:
            fail_a.append(f"execute called {execute_calls[0]}x (must be 0)")
        if connected_calls[0] != 0:
            fail_a.append(f"connected called {connected_calls[0]}x (must be 0)")

        if fail_a:
            for m in fail_a:
                print(f"{FAIL} [D65-A] confirm=False: {m}")
            ok = False
        else:
            print(f"{PASS} [D65-A] confirm=False → 403 SECURITY_CONFIRMATION_REQUIRED, 0 calls")

        # Case B: confirm=True → gate bypassed, offline → BRIDGE_TIMEOUT
        execute_calls[0]   = 0
        connected_calls[0] = 0
        ndc_mod.check = _orig_check

        h_confirm = _MockH("/action/track_delete", {"track": "Kick", "confirm": True})
        h_confirm.do_POST()

        fail_b = []
        if h_confirm._cap_data is None:
            fail_b.append("no response")
        else:
            ec = h_confirm._cap_data.get("error_code", "")
            if ec == "SECURITY_CONFIRMATION_REQUIRED":
                fail_b.append("confirm=True was still blocked by confirmation gate")
            if ec != "BRIDGE_TIMEOUT":
                fail_b.append(f"error_code={ec!r} (expected BRIDGE_TIMEOUT when offline)")
        if connected_calls[0] == 0:
            fail_b.append("ableton_connected not called — gate may have misfired")
        if execute_calls[0] != 0:
            fail_b.append(f"execute called {execute_calls[0]}x (must be 0 when offline)")

        if fail_b:
            for m in fail_b:
                print(f"{FAIL} [D65-B] confirm=True: {m}")
            ok = False
        else:
            print(f"{PASS} [D65-B] confirm=True → gate bypassed → BRIDGE_TIMEOUT (offline)")

    finally:
        ndc_mod.check             = _orig_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    print(f"\n  D65: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D66: tracks_create_multiple — batch confirm gate via do_POST() ────

def run_d66() -> bool:
    """
    /action/tracks_create_multiple via do_POST():
      - count>3, confirm=False → REQUIRE_CONFIRMATION gate fires → 403, 0 calls.
      - count=2, no confirm needed → ALLOW → offline → 503 BRIDGE_TIMEOUT.
    """
    print("\n=== Section D66: tracks_create_multiple — batch confirm gate via do_POST ===")
    ok = True

    import io, json as _json
    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision, _BATCH_THRESHOLD
    from conductor_bridge   import ConductorHandler

    execute_calls   = [0]
    connected_calls = [0]
    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    _orig_check     = ndc_mod.check

    def _track_execute(code, timeout=10.0):
        execute_calls[0] += 1
        return {"ok": False, "error": "sentinel", "data": {}}

    def _track_connected():
        connected_calls[0] += 1
        return False

    _cb_mod.ableton_execute   = _track_execute
    _cb_mod.ableton_connected = _track_connected

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

    try:
        from rag.never_do_check import _clear_rules_cache
        _clear_rules_cache()

        # Case A: count > threshold, no confirm → gate fires
        big_count = _BATCH_THRESHOLD + 2
        execute_calls[0]   = 0
        connected_calls[0] = 0
        ndc_mod.check = _orig_check

        h_big = _MockH("/action/tracks_create_multiple",
                       {"count": big_count, "confirm": False})
        h_big.do_POST()

        fail_a = []
        if h_big._cap_data is None:
            fail_a.append("no response")
        else:
            if h_big._cap_data.get("error_code") != "SECURITY_CONFIRMATION_REQUIRED":
                fail_a.append(
                    f"error_code={h_big._cap_data.get('error_code')!r} "
                    "(expected SECURITY_CONFIRMATION_REQUIRED)")
            if h_big._cap_code != 403:
                fail_a.append(f"http={h_big._cap_code} (expected 403)")
        if execute_calls[0] != 0:
            fail_a.append(f"execute called {execute_calls[0]}x (must be 0)")
        if connected_calls[0] != 0:
            fail_a.append(f"connected called {connected_calls[0]}x (must be 0)")

        if fail_a:
            for m in fail_a:
                print(f"{FAIL} [D66-A] count={big_count} no confirm: {m}")
            ok = False
        else:
            print(f"{PASS} [D66-A] count={big_count} no confirm → "
                  f"403 SECURITY_CONFIRMATION_REQUIRED, 0 calls")

        # Case B: count ≤ threshold → ALLOW → offline → BRIDGE_TIMEOUT
        execute_calls[0]   = 0
        connected_calls[0] = 0
        ndc_mod.check = _orig_check

        h_small = _MockH("/action/tracks_create_multiple", {"count": 2})
        h_small.do_POST()

        fail_b = []
        if h_small._cap_data is None:
            fail_b.append("no response")
        else:
            ec = h_small._cap_data.get("error_code", "")
            if ec == "SECURITY_CONFIRMATION_REQUIRED":
                fail_b.append("count=2 was unexpectedly gate-blocked")
            if ec != "BRIDGE_TIMEOUT":
                fail_b.append(f"error_code={ec!r} (expected BRIDGE_TIMEOUT when offline)")
        if connected_calls[0] == 0:
            fail_b.append("ableton_connected not called — gate may have misfired")
        if execute_calls[0] != 0:
            fail_b.append(f"execute called {execute_calls[0]}x (must be 0 when offline)")

        if fail_b:
            for m in fail_b:
                print(f"{FAIL} [D66-B] count=2: {m}")
            ok = False
        else:
            print(f"{PASS} [D66-B] count=2 → ALLOW → BRIDGE_TIMEOUT (offline), "
                  f"connected {connected_calls[0]}x")

    finally:
        ndc_mod.check             = _orig_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    print(f"\n  D66: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D67: Undo ARM_TRACK ───────────────────────────────────────────────

def run_d67() -> bool:
    """ARM_TRACK is in UNDOABLE_ACTION_TYPES; UndoValidationError on unsupported."""
    print("\n=== Section D67: Undo ARM_TRACK eligibility ===")
    ok = True

    from rag.undo_engine import UNDOABLE_ACTION_TYPES, execute_undo, UndoValidationError

    if "ARM_TRACK" not in UNDOABLE_ACTION_TYPES:
        print(f"{FAIL} [D67] ARM_TRACK not in UNDOABLE_ACTION_TYPES")
        ok = False
    else:
        print(f"{PASS} [D67] ARM_TRACK in UNDOABLE_ACTION_TYPES")

    # Undo with valid proof
    proof = {
        "proof_id":            "test_arm_proof",
        "action_type":         "ARM_TRACK",
        "target":              "track:Kick",
        "verification_status": "VERIFIED",
        "before_state":        {"arm": False},
        "after_state":         {"arm": True},
    }

    arm_state = {"arm": True}
    def exec_arm(code, timeout=10.0):
        if "arm = " in str(code):
            arm_state["arm"] = False
            return {"ok": True, "data": {"result": None}, "error": None}
        if ".arm" in str(code):
            return {"ok": True, "data": {"result": arm_state["arm"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    try:
        result = execute_undo(proof, exec_arm, confirm=False, stabilization_delay=0)
        if result.get("ok"):
            print(f"{PASS} [D67] ARM_TRACK undo executed successfully")
        else:
            print(f"{FAIL} [D67] ARM_TRACK undo returned ok=False: {result.get('message')}")
            ok = False
    except UndoValidationError as e:
        print(f"{FAIL} [D67] UndoValidationError on valid ARM_TRACK proof: {e}")
        ok = False

    # Unsupported action type still raises
    bad_proof = {
        "proof_id": "p2", "action_type": "RENAME_TRACK",
        "target": "track:0", "verification_status": "VERIFIED",
        "before_state": {"name": "Old"}, "after_state": {"name": "New"},
    }
    try:
        execute_undo(bad_proof, exec_arm, confirm=False, stabilization_delay=0)
        print(f"{FAIL} [D67] RENAME_TRACK should raise UndoValidationError")
        ok = False
    except UndoValidationError:
        print(f"{PASS} [D67] RENAME_TRACK raises UndoValidationError (not in UNDOABLE_ACTION_TYPES)")

    print(f"\n  D67: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D68: Undo SET_TRACK_MONITOR ───────────────────────────────────────

def run_d68() -> bool:
    """SET_TRACK_MONITOR is in UNDOABLE_ACTION_TYPES and undo restores integer mode."""
    print("\n=== Section D68: Undo SET_TRACK_MONITOR ===")
    ok = True

    from rag.undo_engine import UNDOABLE_ACTION_TYPES, execute_undo, UndoValidationError

    if "SET_TRACK_MONITOR" not in UNDOABLE_ACTION_TYPES:
        print(f"{FAIL} [D68] SET_TRACK_MONITOR not in UNDOABLE_ACTION_TYPES")
        ok = False
    else:
        print(f"{PASS} [D68] SET_TRACK_MONITOR in UNDOABLE_ACTION_TYPES")

    proof = {
        "proof_id":            "test_mon_proof",
        "action_type":         "SET_TRACK_MONITOR",
        "target":              "track:Bass",
        "verification_status": "VERIFIED",
        "before_state":        {"monitor": 1},   # was Auto
        "after_state":         {"monitor": 0},   # set to In
    }

    mon_state = {"val": 0}
    def exec_mon(code, timeout=10.0):
        if "current_monitoring_state = " in str(code):
            mon_state["val"] = 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "current_monitoring_state" in str(code):
            return {"ok": True, "data": {"result": mon_state["val"]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    try:
        result = execute_undo(proof, exec_mon, confirm=False, stabilization_delay=0)
        if result.get("ok"):
            print(f"{PASS} [D68] SET_TRACK_MONITOR undo executed (restoring mode 1)")
        else:
            print(f"{FAIL} [D68] SET_TRACK_MONITOR undo returned ok=False: {result.get('message')}")
            ok = False
    except UndoValidationError as e:
        print(f"{FAIL} [D68] UndoValidationError on valid SET_TRACK_MONITOR proof: {e}")
        ok = False

    print(f"\n  D68: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D69: BeforeStateCaptureError on unreadable before ─────────────────

def run_d69() -> bool:
    """
    Verify that all new verify_* functions that use before_state
    raise BeforeStateCaptureError when the Ableton executor fails.
    """
    print("\n=== Section D69: BeforeStateCaptureError propagation ===")
    ok = True

    from rag.readback import (
        verify_track_arm, verify_track_monitor,
        verify_track_rename, verify_track_color,
        BeforeStateCaptureError,
    )

    dead_executor = _make_executor({}, default=_fail("Ableton dead"))

    cases = [
        ("verify_track_arm",     lambda: verify_track_arm("Kick", True, dead_executor, stabilization_delay=0)),
        ("verify_track_monitor", lambda: verify_track_monitor("Bass", 1, dead_executor, stabilization_delay=0)),
        ("verify_track_rename",  lambda: verify_track_rename(0, "NewName", dead_executor, stabilization_delay=0)),
        ("verify_track_color",   lambda: verify_track_color("Lead", 0xFF0000, dead_executor, stabilization_delay=0)),
    ]

    for name, fn in cases:
        try:
            fn()
            print(f"{FAIL} [D69] {name} should raise BeforeStateCaptureError on dead executor")
            ok = False
        except BeforeStateCaptureError:
            print(f"{PASS} [D69] {name} → BeforeStateCaptureError on dead executor")
        except Exception as e:
            print(f"{FAIL} [D69] {name} raised unexpected {type(e).__name__}: {e}")
            ok = False

    print(f"\n  D69: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D70: Never-do log events for new action types ─────────────────────

def run_d70() -> bool:
    """
    log_never_do_blocked works for new Slice 1 action types — NEVER_DO_BLOCKED
    event is written to the black box log.
    """
    print("\n=== Section D70: BBL NEVER_DO_BLOCKED for Slice 1 types ===")
    ok = True

    from rag.black_box_log import log_never_do_blocked, read_all_events, NEVER_DO_BLOCKED

    before_count = len(read_all_events())

    log_never_do_blocked("CREATE_TRACK", "new_midi_track:unnamed",
                         "REQUIRE_CONFIRMATION",
                         request_id="req_d70", action_id="act_d70",
                         session_id="sess_d70", rule_text="test rule")

    events = read_all_events()
    new_events = events[before_count:]
    found = any(
        e.get("_type") == NEVER_DO_BLOCKED
        and e.get("action_type") == "CREATE_TRACK"
        and e.get("request_id") == "req_d70"
        for e in new_events
    )
    if not found:
        print(f"{FAIL} [D70] NEVER_DO_BLOCKED event for CREATE_TRACK not found in BBL")
        ok = False
    else:
        print(f"{PASS} [D70] NEVER_DO_BLOCKED event written for CREATE_TRACK")

    print(f"\n  D70: {'PASS' if ok else 'FAIL'}")
    return ok


# ── SECTION D71: Slice 1–5 regressions ───────────────────────────────────────

def run_d71() -> bool:
    """Run Phase D Slice 5 eval as regression (must still pass with DELETE_TRACK change)."""
    print("\n=== Section D71: Slice 5 regression ===")
    import subprocess
    result = subprocess.run(
        ["python3", "tests/phase_d_slice5_eval.py"],
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    lines = result.stdout.splitlines()
    fail_lines = [l for l in lines if l.strip().startswith("❌")]
    if fail_lines or result.returncode != 0:
        print(f"\n  D71 Slice 5 regression FAIL:")
        for l in fail_lines[:10]:
            print(f"    {l}")
        if result.returncode != 0 and not fail_lines:
            print(f"  returncode={result.returncode}")
            print(result.stderr[-500:] if result.stderr else "")
        return False
    # Count pass lines
    pass_count = sum(1 for l in lines if "✅" in l)
    print(f"{PASS} [D71] Slice 5 regression — {pass_count} checks pass")
    return True


# ── SECTION D72: Phase C regression ───────────────────────────────────────────

def run_d72() -> bool:
    """Run Phase C eval as regression."""
    print("\n=== Section D72: Phase C regression ===")
    import subprocess
    result = subprocess.run(
        ["python3", "tests/phase_c_eval_set.py"],
        capture_output=True, text=True,
        cwd=_ROOT,
    )
    lines = result.stdout.splitlines()
    fail_lines = [l for l in lines if l.strip().startswith("❌")]
    if fail_lines or result.returncode != 0:
        print(f"\n  D72 Phase C regression FAIL:")
        for l in fail_lines[:10]:
            print(f"    {l}")
        if result.returncode != 0 and not fail_lines:
            print(f"  returncode={result.returncode}")
            print(result.stderr[-500:] if result.stderr else "")
        return False
    pass_count = sum(1 for l in lines if "✅" in l)
    print(f"{PASS} [D72] Phase C regression — {pass_count} checks pass")
    return True


# ── SECTION D73: Proof field honesty — rename + batch ────────────────────────

def run_d73() -> bool:
    """
    Verify proof field honesty for the two cases identified as blockers:

    D73-A  verify_track_create after_state must NOT contain "name".
           The name is not verified by creation readback; putting it in
           the proof would claim verification of an unverified field.

    D73-B  /action/tracks_create_multiple response must include top-level
           proof_id, verification_status, before_state, after_state, and
           undo_eligible=False (blocker 4 contract).

    D73-C  SET_TRACK_COLOR is in UNDOABLE_ACTION_TYPES and undo engine
           can restore a color value (blocker 2 contract).
    """
    print("\n=== Section D73: Proof field honesty (rename + batch + color undo) ===")
    ok = True

    # ── D73-A: verify_track_create after_state never contains "name" ──────────
    from rag.readback import verify_track_create

    _count_a = [3]
    def _exec_create_a(code, timeout=10.0):
        if "create_midi_track" in str(code):
            _count_a[0] += 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "len(song.tracks)" in str(code):
            return {"ok": True, "data": {"result": _count_a[0]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    rb_a = verify_track_create("midi", _exec_create_a, stabilization_delay=0)
    if "name" in rb_a.get("after_state", {}):
        print(f"{FAIL} [D73-A] after_state contains 'name' key: {rb_a['after_state']}")
        ok = False
    else:
        print(f"{PASS} [D73-A] after_state does not contain 'name' "
              f"(fields: {list(rb_a.get('after_state', {}).keys())})")

    # ── D73-B: batch handler response includes top-level proof fields ─────────
    import io, json as _json
    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision
    from conductor_bridge   import ConductorHandler

    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    _orig_check     = ndc_mod.check

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

    # Stateful mock: starts at 3 tracks, each create adds 1
    _count_b = [3]
    def _exec_batch(code, timeout=10.0):
        if "create_midi_track" in str(code):
            _count_b[0] += 1
            return {"ok": True, "data": {"result": None}, "error": None}
        if "len(song.tracks)" in str(code):
            return {"ok": True, "data": {"result": _count_b[0]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    try:
        ndc_mod.check             = lambda a, ctx=None: (NeverDoDecision.ALLOW, "")
        _cb_mod.ableton_execute   = _exec_batch
        _cb_mod.ableton_connected = lambda: True   # online

        h_b = _MockH("/action/tracks_create_multiple", {"count": 1, "type": "midi"})
        h_b.do_POST()

        d_b = h_b._cap_data or {}
        required_fields = ["proof_id", "verification_status", "before_state",
                           "after_state", "undo_eligible"]
        missing = [f for f in required_fields if f not in d_b]
        if missing:
            print(f"{FAIL} [D73-B] batch response missing fields: {missing}")
            ok = False
        else:
            # Spot-check field values
            b_ok = True
            if not d_b.get("proof_id"):
                print(f"{FAIL} [D73-B] proof_id is empty/falsy")
                b_ok = ok = False
            if d_b.get("undo_eligible") is not False:
                print(f"{FAIL} [D73-B] undo_eligible={d_b.get('undo_eligible')!r} (expected False)")
                b_ok = ok = False
            if "track_count" not in d_b.get("before_state", {}):
                print(f"{FAIL} [D73-B] before_state missing track_count: {d_b.get('before_state')}")
                b_ok = ok = False
            if "tracks_created" not in d_b.get("after_state", {}):
                print(f"{FAIL} [D73-B] after_state missing tracks_created: {d_b.get('after_state')}")
                b_ok = ok = False
            if b_ok:
                print(f"{PASS} [D73-B] batch response has proof_id, vstat, before/after, "
                      f"undo_eligible=False")

    finally:
        ndc_mod.check             = _orig_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    # ── D73-C: SET_TRACK_COLOR undo engine wiring ─────────────────────────────
    from rag.undo_engine import UNDOABLE_ACTION_TYPES, execute_undo, UndoValidationError

    if "SET_TRACK_COLOR" not in UNDOABLE_ACTION_TYPES:
        print(f"{FAIL} [D73-C] SET_TRACK_COLOR not in UNDOABLE_ACTION_TYPES")
        ok = False
    else:
        print(f"{PASS} [D73-C] SET_TRACK_COLOR in UNDOABLE_ACTION_TYPES")

    color_proof = {
        "proof_id":            "test_color_proof",
        "action_type":         "SET_TRACK_COLOR",
        "target":              "track:Lead",
        "verification_status": "VERIFIED",
        "before_state":        {"color": 0x000000},
        "after_state":         {"color": 0xFF0000},
    }
    _color_state = [0xFF0000]
    def _exec_color_undo(code, timeout=10.0):
        if ".color = " in str(code):
            _color_state[0] = 0x000000
            return {"ok": True, "data": {"result": None}, "error": None}
        if ".color" in str(code):
            return {"ok": True, "data": {"result": _color_state[0]}, "error": None}
        return {"ok": True, "data": {"result": None}, "error": None}

    try:
        result = execute_undo(color_proof, _exec_color_undo,
                              confirm=False, stabilization_delay=0)
        if result.get("ok"):
            print(f"{PASS} [D73-C] SET_TRACK_COLOR undo executed (restoring 0x000000)")
        else:
            print(f"{FAIL} [D73-C] SET_TRACK_COLOR undo returned ok=False: "
                  f"{result.get('message')}")
            ok = False
    except UndoValidationError as e:
        print(f"{FAIL} [D73-C] UndoValidationError on valid SET_TRACK_COLOR proof: {e}")
        ok = False

    print(f"\n  D73: {'PASS' if ok else 'FAIL'}")
    return ok


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════

SECTIONS = {
    "D52": ("New Slice 1 ALLOW decisions",             run_d52),
    "D53": ("DELETE_TRACK = REQUIRE_CONFIRMATION",      run_d53),
    "D54": ("Batch escalation >threshold",              run_d54),
    "D55": ("All Slice 1 types have known decisions",   run_d55),
    "D56": ("verify_track_arm VERIFIED/ALREADY_CORRECT/BeforeCapture", run_d56),
    "D57": ("verify_track_monitor VERIFIED/ALREADY_CORRECT",           run_d57),
    "D58": ("verify_track_create count-based",          run_d58),
    "D59": ("verify_track_delete count + absent",       run_d59),
    "D60": ("verify_track_duplicate count-based",       run_d60),
    "D61": ("verify_track_rename index-stable",         run_d61),
    "D62": ("verify_track_color palette-snap",          run_d62),
    "D63": ("All 9 endpoints gate via do_POST (HARD_BLOCK→403, 0 calls)", run_d63),
    "D64": ("All 9 endpoints offline via do_POST (ALLOW+disconn→503)",    run_d64),
    "D65": ("track_delete do_POST: no-confirm→403, confirm→offline",       run_d65),
    "D66": ("tracks_create_multiple do_POST: >3 no-confirm→403, ≤3→offline", run_d66),
    "D67": ("Undo ARM_TRACK eligible",                  run_d67),
    "D68": ("Undo SET_TRACK_MONITOR eligible",          run_d68),
    "D69": ("BeforeStateCaptureError propagation",      run_d69),
    "D70": ("BBL NEVER_DO_BLOCKED for Slice 1 types",  run_d70),
    "D71": ("Slice 5 regression",                       run_d71),
    "D72": ("Phase C regression",                       run_d72),
    "D73": ("Proof field honesty: rename+batch+color undo", run_d73),
}

if __name__ == "__main__":
    results = {}
    for sid, (label, fn) in SECTIONS.items():
        try:
            results[sid] = fn()
        except Exception as exc:
            print(f"\n{FAIL} [{sid}] Crashed: {exc}")
            import traceback
            traceback.print_exc()
            results[sid] = False

    total  = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed

    print("\n" + "═" * 56)
    print(f"  Phase D Action Expansion Slice 1 Blockers — {passed}/{total} PASS")
    if failed:
        print("  FAILED sections:")
        for sid, v in results.items():
            if not v:
                print(f"    {FAIL} {sid}: {SECTIONS[sid][0]}")
    else:
        print("  All sections PASS.")
    print("═" * 56)
    raise SystemExit(0 if failed == 0 else 1)
