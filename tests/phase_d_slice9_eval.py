"""
Phase D — Slice 9: Strict Confirm Parser Eval Suite
Sections D103–D108

Covers:
  D103  _parse_confirm_strict unit — absent / bool / string / invalid
  D104  /action/undo         → invalid confirm → 400
  D105  /action/track_delete
          invalid confirm ("maybe", "yes", "no", 1, 0, [], {}) → 400
          confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED, execute==0
  D106  /action/tracks_create_multiple (count=5)
          invalid confirm → 400
          confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED, execute==0
  D107  /action/track_route
          invalid confirm → 400
          confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED, execute==0
  D108  /action/transport_record
          invalid confirm → 400
          confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED, execute==0
"""

import io
import os
import sys
import json as _json
import importlib
import unittest.mock as _mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from rag.bridge_errors import BridgeErrorCode

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

SECTIONS = {}


def section(label):
    def decorator(fn):
        SECTIONS[label] = fn
        return fn
    return decorator


# ── shared mock handler factory ───────────────────────────────────────────────

def _make_mock_h(ConductorHandler, path_str, body_dict):
    class _MockH(ConductorHandler):
        def __init__(self, path, body):
            self.path    = path
            bb           = _json.dumps(body).encode()
            self.headers = {"Content-Length": str(len(bb))}
            self.rfile   = io.BytesIO(bb)
            self._cap_data = None
            self._cap_code = None
        def _send_json(self, data, code=200):
            self._cap_data = data
            self._cap_code = code
        def log_message(self, *a):
            pass
    return _MockH(path_str, body_dict)


def _assert_false_string_gate_closed(
    bridge_mod, ndc_mod, path, body, confirm_val, errors, label
):
    """
    Assert that confirm=<confirm_val> with ndc=REQUIRE_CONFIRMATION produces:
      - HTTP 403
      - error_code == SECURITY_CONFIRMATION_REQUIRED
      - ableton_execute call count == 0
      - NOT 400

    This proves "false"/"FALSE" stays unconfirmed and no write reaches Ableton.
    """
    NeverDoDecision = ndc_mod.NeverDoDecision

    with _mock.patch.object(
        ndc_mod, "check",
        return_value=(NeverDoDecision.REQUIRE_CONFIRMATION, "test rule")
    ):
        with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
            with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
                body_with_confirm = dict(body, confirm=confirm_val)
                h = _make_mock_h(bridge_mod.ConductorHandler, path, body_with_confirm)
                h.do_POST()

                if h._cap_code == 400:
                    errors.append(
                        f"{label} confirm={confirm_val!r} → 400 "
                        "(should be 403 SECURITY_CONFIRMATION_REQUIRED, "
                        "not a param validation error)"
                    )
                if h._cap_code != 403:
                    errors.append(
                        f"{label} confirm={confirm_val!r} → HTTP {h._cap_code}, "
                        "expected 403"
                    )
                if h._cap_data:
                    ec = h._cap_data.get("error_code", "")
                    if ec != BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED:
                        errors.append(
                            f"{label} confirm={confirm_val!r} → "
                            f"error_code={ec!r}, "
                            f"expected SECURITY_CONFIRMATION_REQUIRED"
                        )
                    if h._cap_data.get("ok") is not False:
                        errors.append(
                            f"{label} confirm={confirm_val!r} → ok should be False"
                        )
                else:
                    errors.append(
                        f"{label} confirm={confirm_val!r} → no response data captured"
                    )
                if exec_mock.call_count != 0:
                    errors.append(
                        f"{label} confirm={confirm_val!r} → ableton_execute "
                        f"called {exec_mock.call_count} time(s), expected 0 "
                        "(write must not reach Ableton when not confirmed)"
                    )


# ══════════════════════════════════════════════════════════════════════════════
# D103 — _parse_confirm_strict unit tests
# ══════════════════════════════════════════════════════════════════════════════

@section("D103")
def run_d103():
    print("=== Section D103: _parse_confirm_strict unit tests ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    fn = bridge_mod._parse_confirm_strict

    errors = []

    # ── absent / None → (False, "") — not an error, gate stays closed ─────────
    val, err = fn(None)
    if val is not False or err != "":
        errors.append(f"None → expected (False, ''), got ({val!r}, {err!r})")

    # ── JSON false → (False, "") ───────────────────────────────────────────────
    val, err = fn(False)
    if val is not False or err != "":
        errors.append(f"False → expected (False, ''), got ({val!r}, {err!r})")

    # ── JSON true → (True, "") ────────────────────────────────────────────────
    val, err = fn(True)
    if val is not True or err != "":
        errors.append(f"True → expected (True, ''), got ({val!r}, {err!r})")

    # ── string "false" / "FALSE" / "False" → (False, "") — NOT truthy ─────────
    for s in ("false", "FALSE", "False", "  false  ", "  FALSE  "):
        val, err = fn(s)
        if val is not False or err != "":
            errors.append(f"{s!r} → expected (False, ''), got ({val!r}, {err!r})")
        # Critical: must NOT be truthy (the bool('false') footgun)
        if val:
            errors.append(f"{s!r} → parsed as truthy — bool('false') footgun still present")

    # ── string "true" / "TRUE" / "True" → (True, "") ─────────────────────────
    for s in ("true", "TRUE", "True", "  true  "):
        val, err = fn(s)
        if val is not True or err != "":
            errors.append(f"{s!r} → expected (True, ''), got ({val!r}, {err!r})")

    # ── invalid strings → (None, non-empty error) → caller returns 400 ────────
    for bad in ("maybe", "yes", "no", "1", "0", "ok", "nope", "", "  "):
        val, err = fn(bad)
        if val is not None:
            errors.append(f"{bad!r} → expected (None, msg), got val={val!r}")
        if not err:
            errors.append(f"{bad!r} → expected non-empty error msg, got empty string")

    # ── invalid types → (None, non-empty error) ───────────────────────────────
    for bad in (1, 0, 1.0, [], {}, [True], {"confirm": True}):
        val, err = fn(bad)
        if val is not None:
            errors.append(f"{bad!r} (type {type(bad).__name__}) → expected (None, msg), got val={val!r}")
        if not err:
            errors.append(f"{bad!r} → expected non-empty error msg, got empty string")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D103] {e}")
        print("  D103: FAIL")
        return False

    print(f"  {PASS} [D103] _parse_confirm_strict — all unit cases passed")
    print("  D103: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D104 — /action/undo rejects invalid confirm → 400
# ══════════════════════════════════════════════════════════════════════════════

@section("D104")
def run_d104():
    print("=== Section D104: /action/undo invalid confirm → 400 ===")

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")

    errors = []

    invalid_confirms = ["maybe", "yes", "no", 1, 0, [], {}]

    for bad in invalid_confirms:
        with _mock.patch.object(ndc_mod, "check",
                                return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
            with _mock.patch.object(bridge_mod, "ableton_connected",
                                    return_value=True):
                h = _make_mock_h(bridge_mod.ConductorHandler,
                                 "/action/undo",
                                 {"confirm": bad})
                h.do_POST()

                if h._cap_code != 400:
                    errors.append(
                        f"confirm={bad!r}: expected 400, got {h._cap_code}"
                    )
                if h._cap_data and h._cap_data.get("ok") is not False:
                    errors.append(f"confirm={bad!r}: ok should be False")
                if h._cap_data:
                    ec = h._cap_data.get("error_code", "")
                    if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                        errors.append(
                            f"confirm={bad!r}: error_code={ec!r}, "
                            f"expected BRIDGE_PARAM_OUT_OF_RANGE"
                        )

    # Absent confirm must NOT produce BRIDGE_PARAM_OUT_OF_RANGE.
    # /action/undo also requires proof_id or action_id, so an empty body returns
    # 400 UNDO_PROOF_NOT_FOUND — but that is a different 400, not a confirm error.
    with _mock.patch.object(ndc_mod, "check",
                            return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
        with _mock.patch.object(bridge_mod, "ableton_connected",
                                return_value=True):
            h = _make_mock_h(bridge_mod.ConductorHandler,
                             "/action/undo",
                             {})
            h.do_POST()
            if h._cap_data:
                ec = h._cap_data.get("error_code", "")
                if ec == BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                    errors.append(
                        "absent confirm → BRIDGE_PARAM_OUT_OF_RANGE (should be "
                        "treated as confirm=False, not as an invalid value)"
                    )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D104] {e}")
        print("  D104: FAIL")
        return False

    print(f"  {PASS} [D104] /action/undo invalid confirm → 400 BRIDGE_PARAM_OUT_OF_RANGE")
    print("  D104: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D105 — /action/track_delete
#   Part A: invalid confirm → 400 BRIDGE_PARAM_OUT_OF_RANGE
#   Part B: confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED,
#           ableton_execute called 0 times
# ══════════════════════════════════════════════════════════════════════════════

@section("D105")
def run_d105():
    print("=== Section D105: /action/track_delete confirm parsing ===")

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")

    errors = []

    # ── Part A: invalid values → 400 BRIDGE_PARAM_OUT_OF_RANGE ────────────────
    # The endpoint must reject these before reaching the security gate.
    invalid_confirms = ["maybe", "yes", "no", 1, 0, [], {}]

    for bad in invalid_confirms:
        with _mock.patch.object(ndc_mod, "check",
                                return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
            with _mock.patch.object(bridge_mod, "ableton_connected",
                                    return_value=True):
                with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
                    h = _make_mock_h(bridge_mod.ConductorHandler,
                                     "/action/track_delete",
                                     {"track": "Kick", "confirm": bad})
                    h.do_POST()

                    if h._cap_code != 400:
                        errors.append(
                            f"[A] confirm={bad!r}: expected 400, got {h._cap_code}"
                        )
                    if h._cap_data and h._cap_data.get("ok") is not False:
                        errors.append(f"[A] confirm={bad!r}: ok should be False")
                    if h._cap_data:
                        ec = h._cap_data.get("error_code", "")
                        if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                            errors.append(
                                f"[A] confirm={bad!r}: error_code={ec!r}, "
                                f"expected BRIDGE_PARAM_OUT_OF_RANGE"
                            )
                    if exec_mock.call_count != 0:
                        errors.append(
                            f"[A] confirm={bad!r}: execute called "
                            f"{exec_mock.call_count} time(s), expected 0"
                        )

    # ── Part B: confirm="false" / "FALSE" → gate closed, NOT executed ─────────
    # ndc=REQUIRE_CONFIRMATION simulates an action that needs explicit confirmation.
    # confirm="false" must parse to False → bypass_ok=False → 403, zero writes.
    for false_str in ("false", "FALSE"):
        _assert_false_string_gate_closed(
            bridge_mod, ndc_mod,
            path="/action/track_delete",
            body={"track": "Kick"},
            confirm_val=false_str,
            errors=errors,
            label="track_delete",
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D105] {e}")
        print("  D105: FAIL")
        return False

    print(f"  {PASS} [D105] track_delete: invalid→400, false/FALSE→403 SCR, execute==0")
    print("  D105: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D106 — /action/tracks_create_multiple (count=5, which is > 3)
#   Part A: invalid confirm → 400 BRIDGE_PARAM_OUT_OF_RANGE
#   Part B: confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED,
#           ableton_execute called 0 times
# ══════════════════════════════════════════════════════════════════════════════

@section("D106")
def run_d106():
    print("=== Section D106: /action/tracks_create_multiple (count=5) confirm parsing ===")

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")

    errors = []

    # ── Part A: invalid values → 400 ──────────────────────────────────────────
    invalid_confirms = ["maybe", "yes", "no", 1, 0, [], {}]

    for bad in invalid_confirms:
        with _mock.patch.object(ndc_mod, "check",
                                return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
            with _mock.patch.object(bridge_mod, "ableton_connected",
                                    return_value=True):
                with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
                    h = _make_mock_h(bridge_mod.ConductorHandler,
                                     "/action/tracks_create_multiple",
                                     {"count": 5, "confirm": bad})
                    h.do_POST()

                    if h._cap_code != 400:
                        errors.append(
                            f"[A] confirm={bad!r}: expected 400, got {h._cap_code}"
                        )
                    if h._cap_data and h._cap_data.get("ok") is not False:
                        errors.append(f"[A] confirm={bad!r}: ok should be False")
                    if h._cap_data:
                        ec = h._cap_data.get("error_code", "")
                        if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                            errors.append(
                                f"[A] confirm={bad!r}: error_code={ec!r}, "
                                f"expected BRIDGE_PARAM_OUT_OF_RANGE"
                            )
                    if exec_mock.call_count != 0:
                        errors.append(
                            f"[A] confirm={bad!r}: execute called "
                            f"{exec_mock.call_count} time(s), expected 0"
                        )

    # ── Part B: confirm="false" / "FALSE" with count=5 (> 3) → gate closed ────
    for false_str in ("false", "FALSE"):
        _assert_false_string_gate_closed(
            bridge_mod, ndc_mod,
            path="/action/tracks_create_multiple",
            body={"count": 5},
            confirm_val=false_str,
            errors=errors,
            label="tracks_create_multiple(count=5)",
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D106] {e}")
        print("  D106: FAIL")
        return False

    print(f"  {PASS} [D106] tracks_create_multiple(count=5): invalid→400, false/FALSE→403 SCR, execute==0")
    print("  D106: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D107 — /action/track_route
#   Part A: invalid confirm → 400 BRIDGE_PARAM_OUT_OF_RANGE
#   Part B: confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED,
#           ableton_execute called 0 times
# ══════════════════════════════════════════════════════════════════════════════

@section("D107")
def run_d107():
    print("=== Section D107: /action/track_route confirm parsing ===")

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")

    errors = []

    # ── Part A: invalid values → 400 ──────────────────────────────────────────
    invalid_confirms = ["maybe", "yes", "no", 1, 0, [], {}]

    for bad in invalid_confirms:
        with _mock.patch.object(ndc_mod, "check",
                                return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
            with _mock.patch.object(bridge_mod, "ableton_connected",
                                    return_value=True):
                with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
                    h = _make_mock_h(bridge_mod.ConductorHandler,
                                     "/action/track_route",
                                     {"track": "Kick", "routing": "DRUM BUS",
                                      "confirm": bad})
                    h.do_POST()

                    if h._cap_code != 400:
                        errors.append(
                            f"[A] confirm={bad!r}: expected 400, got {h._cap_code}"
                        )
                    if h._cap_data and h._cap_data.get("ok") is not False:
                        errors.append(f"[A] confirm={bad!r}: ok should be False")
                    if h._cap_data:
                        ec = h._cap_data.get("error_code", "")
                        if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                            errors.append(
                                f"[A] confirm={bad!r}: error_code={ec!r}, "
                                f"expected BRIDGE_PARAM_OUT_OF_RANGE"
                            )
                    if exec_mock.call_count != 0:
                        errors.append(
                            f"[A] confirm={bad!r}: execute called "
                            f"{exec_mock.call_count} time(s), expected 0"
                        )

    # ── Part B: confirm="false" / "FALSE" → gate closed, NOT executed ─────────
    for false_str in ("false", "FALSE"):
        _assert_false_string_gate_closed(
            bridge_mod, ndc_mod,
            path="/action/track_route",
            body={"track": "Kick", "routing": "DRUM BUS"},
            confirm_val=false_str,
            errors=errors,
            label="track_route",
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D107] {e}")
        print("  D107: FAIL")
        return False

    print(f"  {PASS} [D107] track_route: invalid→400, false/FALSE→403 SCR, execute==0")
    print("  D107: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D108 — /action/transport_record
#   Part A: invalid confirm → 400 BRIDGE_PARAM_OUT_OF_RANGE
#   Part B: confirm="false"/"FALSE" → 403 SECURITY_CONFIRMATION_REQUIRED,
#           ableton_execute called 0 times
# ══════════════════════════════════════════════════════════════════════════════

@section("D108")
def run_d108():
    print("=== Section D108: /action/transport_record confirm parsing ===")

    ndc_mod    = importlib.import_module("rag.never_do_check")
    bridge_mod = importlib.import_module("tools.conductor_bridge")

    errors = []

    # ── Part A: invalid values → 400 ──────────────────────────────────────────
    invalid_confirms = ["maybe", "yes", "no", 1, 0, [], {}]

    for bad in invalid_confirms:
        with _mock.patch.object(ndc_mod, "check",
                                return_value=(ndc_mod.NeverDoDecision.ALLOW, "")):
            with _mock.patch.object(bridge_mod, "ableton_connected",
                                    return_value=True):
                with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
                    h = _make_mock_h(bridge_mod.ConductorHandler,
                                     "/action/transport_record",
                                     {"record": True, "confirm": bad})
                    h.do_POST()

                    if h._cap_code != 400:
                        errors.append(
                            f"[A] confirm={bad!r}: expected 400, got {h._cap_code}"
                        )
                    if h._cap_data and h._cap_data.get("ok") is not False:
                        errors.append(f"[A] confirm={bad!r}: ok should be False")
                    if h._cap_data:
                        ec = h._cap_data.get("error_code", "")
                        if ec != BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE:
                            errors.append(
                                f"[A] confirm={bad!r}: error_code={ec!r}, "
                                f"expected BRIDGE_PARAM_OUT_OF_RANGE"
                            )
                    if exec_mock.call_count != 0:
                        errors.append(
                            f"[A] confirm={bad!r}: execute called "
                            f"{exec_mock.call_count} time(s), expected 0"
                        )

    # ── Part B: confirm="false" / "FALSE" → gate closed, NOT executed ─────────
    for false_str in ("false", "FALSE"):
        _assert_false_string_gate_closed(
            bridge_mod, ndc_mod,
            path="/action/transport_record",
            body={"record": True},
            confirm_val=false_str,
            errors=errors,
            label="transport_record",
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D108] {e}")
        print("  D108: FAIL")
        return False

    print(f"  {PASS} [D108] transport_record: invalid→400, false/FALSE→403 SCR, execute==0")
    print("  D108: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def main():
    results = {}
    for label, fn in sorted(SECTIONS.items()):
        try:
            results[label] = fn()
        except Exception as exc:
            print(f"  {FAIL} [{label}] EXCEPTION: {exc}")
            import traceback; traceback.print_exc()
            results[label] = False
        print()

    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    print("=" * 60)
    print(f"Phase D Slice 9 — Strict Confirm Parser: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
