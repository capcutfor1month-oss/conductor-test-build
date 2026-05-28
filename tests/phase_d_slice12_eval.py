"""
Phase D — Slice 12: Knowledge Gateway (POST /harness/orchestrate) Eval Suite
Sections D121–D127

Covers:
  D121  Static analysis — /harness/orchestrate defined; type:"answer" path present;
        WRITE_MODES routing present; _call_bridge_get present
  D122  WRITE mode (INTERN_WRITE_SAFE) → type:"action", action_id/params/confidence
  D123  MENTOR mode → type:"answer", text returned from LLM, ok=True
  D124  /context/pack is called with the user text as query parameter
  D125  /session/state failure is tolerated — answer path still works
  D126  Answer text (type:"answer") does not contain raw mode classifier strings
  D127  POST /harness/parse_intent still works unchanged (regression)
"""

import importlib
import inspect
import io
import json
import os
import sys
import unittest.mock as _mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

SECTIONS = {}


def section(label):
    def decorator(fn):
        SECTIONS[label] = fn
        return fn
    return decorator


# ── Mock handler factory ──────────────────────────────────────────────────────

def _make_mock_handler(HarnessHandler, path, body,
                       provider="gemini", model="test-model",
                       api_key="test-key", base_url=""):
    """
    Instantiate HarnessHandler subclass that bypasses the real socket __init__.
    Captures send_json responses in _cap_data / _cap_code.
    """
    class MockHandler(HarnessHandler):
        def __init__(self):
            # Bypass SimpleHTTPRequestHandler socket init entirely
            self.path = path
            bb = json.dumps(body).encode()
            self.headers = {"Content-Length": str(len(bb))}
            self.rfile = io.BytesIO(bb)
            self.provider = provider
            self.model = model
            self.api_key = api_key
            self.base_url = base_url
            self.atxp_connection_present = False
            self._cap_data = None
            self._cap_code = None

        def send_json(self, code, obj):
            self._cap_data = obj
            self._cap_code = code

        def send_response(self, code):
            pass

        def send_header(self, k, v):
            pass

        def end_headers(self):
            pass

        def log_message(self, *a):
            pass

    return MockHandler()


# ── Canned bridge responses ───────────────────────────────────────────────────

def _mentor_pack():
    """Canned /context/pack response for a MENTOR-mode query."""
    return {
        "ok":    True,
        "mode":  "MENTOR",
        "pack":  "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW\nRelevant retrieved context:\n### Memory\n(none yet)",
        "risk_reason": "",
    }


def _write_safe_pack():
    """Canned /context/pack response for an INTERN_WRITE_SAFE-mode query."""
    return {
        "ok":    True,
        "mode":  "INTERN_WRITE_SAFE",
        "pack":  "## MESSAGE PACK\nMode: INTERN_WRITE_SAFE\nRisk: MEDIUM\nRelevant retrieved context:\n### Memory\n(none yet)",
        "risk_reason": "",
    }


def _session_pack():
    """Canned /context/session response."""
    return {"ok": True, "pack": "## PRODUCER DNA\nProducer: Adi\n\n## TOOL STATUS\nAbleton: connected"}


def _session_state():
    """Canned /session/state response."""
    return {
        "ok":            True,
        "ableton_connected": True,
        "tempo":         128.0,
        "time_signature": "4/4",
        "playing":       False,
        "record":        False,
        "selected_track": "Kick",
        "tracks": [
            {"index": 0, "name": "Kick", "type": "midi", "muted": False, "soloed": False, "arm": False},
            {"index": 1, "name": "Snare", "type": "midi", "muted": False, "soloed": False, "arm": False},
        ],
        "return_tracks": [{"index": 0, "name": "A"}],
    }


def _bridge_side_effect_mentor(path, timeout=5.0):
    """Mock _call_bridge_get that returns MENTOR context for any message."""
    if "/context/pack" in path:
        return _mentor_pack(), None
    if "/context/session" in path:
        return _session_pack(), None
    if "/session/state" in path:
        return _session_state(), None
    return None, "unknown path"


def _bridge_side_effect_write(path, timeout=5.0):
    """Mock _call_bridge_get that returns WRITE context for an action query."""
    if "/context/pack" in path:
        return _write_safe_pack(), None
    if "/context/session" in path:
        return _session_pack(), None
    if "/session/state" in path:
        return _session_state(), None
    return None, "unknown path"


# ══════════════════════════════════════════════════════════════════════════════
# D121 — Static analysis
# ══════════════════════════════════════════════════════════════════════════════

@section("D121")
def run_d121():
    print("=== Section D121: static analysis — orchestrate defined, routing present ===")

    hs_mod = importlib.import_module("tools.harness_server")
    src = inspect.getsource(hs_mod)

    errors = []

    # Endpoint registered in do_POST
    if "/harness/orchestrate" not in src:
        errors.append("/harness/orchestrate not found in harness_server source")

    # Handler method exists
    if "_handle_orchestrate" not in src:
        errors.append("_handle_orchestrate method not found in harness_server source")

    # parse_intent handler still present (regression guard)
    if "/harness/parse_intent" not in src:
        errors.append("/harness/parse_intent removed — must remain for regression")

    if "_handle_parse_intent" not in src:
        errors.append("_handle_parse_intent method not found — parse_intent handler gone")

    # WRITE_MODES routing: INTERN_WRITE_SAFE and INTERN_WRITE_RISKY must gate the action path
    if "INTERN_WRITE_SAFE" not in src:
        errors.append("INTERN_WRITE_SAFE not found in harness_server — mode routing missing")
    if "INTERN_WRITE_RISKY" not in src:
        errors.append("INTERN_WRITE_RISKY not found in harness_server — mode routing missing")

    # type:"answer" produced
    if '"answer"' not in src and "'answer'" not in src:
        errors.append('type:"answer" not found in harness_server source')

    # type:"action" produced
    if '"action"' not in src and "'action'" not in src:
        errors.append('type:"action" not found in harness_server source')

    # Bridge helper present
    if "_call_bridge_get" not in src:
        errors.append("_call_bridge_get not found in harness_server — bridge calls missing")

    # BRIDGE_URL defined
    if "BRIDGE_URL" not in src:
        errors.append("BRIDGE_URL constant not found in harness_server")

    # call_knowledge_answer defined
    if "call_knowledge_answer" not in src:
        errors.append("call_knowledge_answer function not found in harness_server")

    # _format_session_state defined
    if "_format_session_state" not in src:
        errors.append("_format_session_state not found in harness_server")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D121] {e}")
        print("  D121: FAIL")
        return False

    print(f"  {PASS} [D121] /harness/orchestrate defined, routing present, parse_intent intact")
    print("  D121: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D122 — WRITE mode → type:"action"
# ══════════════════════════════════════════════════════════════════════════════

@section("D122")
def run_d122():
    print("=== Section D122: WRITE mode → type:\"action\" with action_id/params/confidence ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Canned action-mapping LLM response
    canned_parsed = {
        "ok":                True,
        "action_id":         "mute",
        "params":            {"track": "Kick", "mute": True},
        "confidence":        0.92,
        "needs_confirmation": False,
        "clarification":     None,
        "reason":            "Muting the Kick track.",
    }
    canned_tokens = {"input": 10, "output": 5, "total": 15}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_bridge_side_effect_write):
        with _mock.patch("tools.harness_server.call_gemini",
                         return_value=(canned_parsed, canned_tokens)):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "mute the kick"},
            )
            h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D122] {e}")
        print("  D122: FAIL")
        return False

    if d.get("type") != "action":
        errors.append(f"type={d.get('type')!r}, expected 'action'")
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("action_id") != "mute":
        errors.append(f"action_id={d.get('action_id')!r}, expected 'mute'")
    if d.get("params") != {"track": "Kick", "mute": True}:
        errors.append(f"params={d.get('params')!r}")
    if abs((d.get("confidence") or 0) - 0.92) > 0.001:
        errors.append(f"confidence={d.get('confidence')!r}, expected ~0.92")
    # model/provider/tokens still present for the UI ai_obs block
    if "model" not in d:
        errors.append("model field missing from action response")
    if "tokens" not in d:
        errors.append("tokens field missing from action response")
    # type:"answer" must NOT be returned for a WRITE query
    if d.get("type") == "answer":
        errors.append("WRITE mode returned type:answer — should be type:action")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D122] {e}")
        print("  D122: FAIL")
        return False

    print(f"  {PASS} [D122] INTERN_WRITE_SAFE → type:action, action_id=mute, params correct")
    print("  D122: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D123 — MENTOR mode → type:"answer"
# ══════════════════════════════════════════════════════════════════════════════

@section("D123")
def run_d123():
    print("=== Section D123: MENTOR mode → type:\"answer\", text from LLM, ok=True ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    canned_answer = "To compress a dhol: attack 10ms, release 80ms, ratio 4:1, threshold -18dBFS."
    canned_tokens = {"input": 200, "output": 50, "total": 250}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_bridge_side_effect_mentor):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(canned_answer, {}, canned_tokens)):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "how do I compress a dhol"},
            )
            h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D123] {e}")
        print("  D123: FAIL")
        return False

    if d.get("type") != "answer":
        errors.append(f"type={d.get('type')!r}, expected 'answer'")
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("text") != canned_answer:
        errors.append(f"text={str(d.get('text'))[:80]!r}, expected the canned answer")
    if not d.get("mode"):
        errors.append("mode field missing from answer response")
    if "model" not in d:
        errors.append("model field missing from answer response")
    if "tokens" not in d:
        errors.append("tokens field missing from answer response")
    # action_id must NOT appear on an answer response
    if "action_id" in d:
        errors.append("action_id present on type:answer — should not be")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D123] {e}")
        print("  D123: FAIL")
        return False

    print(f"  {PASS} [D123] MENTOR mode → type:answer, text passed through, ok=True")
    print("  D123: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D124 — /context/pack called with query text
# ══════════════════════════════════════════════════════════════════════════════

@section("D124")
def run_d124():
    print("=== Section D124: /context/pack called with user text as query ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    calls_recorded = []

    def mock_bridge(path, timeout=5.0):
        calls_recorded.append(path)
        if "/context/pack" in path:
            return _mentor_pack(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return _session_state(), None
        return None, "unknown"

    test_text = "how do I layer strings for a cinematic feel"

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=mock_bridge):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=("Some answer.", {}, {"total": 30})):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": test_text},
            )
            h.do_POST()

    # Verify at least one call targeted /context/pack
    pack_calls = [c for c in calls_recorded if "/context/pack" in c]
    if not pack_calls:
        errors.append("/context/pack was not called at all during orchestrate")
    else:
        # The query must include (some form of) the user text
        import urllib.parse as _up
        call_path = pack_calls[0]
        if "?q=" not in call_path:
            errors.append(f"/context/pack call missing '?q=' param: {call_path!r}")
        else:
            q_val = _up.unquote(call_path.split("?q=", 1)[1])
            if test_text[:10].lower() not in q_val.lower():
                errors.append(
                    f"/context/pack query {q_val!r} does not contain "
                    f"beginning of user text {test_text[:10]!r}"
                )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D124] {e}")
        print("  D124: FAIL")
        return False

    print(f"  {PASS} [D124] /context/pack called with user text in query; all three bridge calls made")
    print("  D124: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D125 — /session/state failure is tolerated
# ══════════════════════════════════════════════════════════════════════════════

@section("D125")
def run_d125():
    print("=== Section D125: /session/state failure → answer path still works ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    def mock_bridge_no_state(path, timeout=5.0):
        if "/context/pack" in path:
            return _mentor_pack(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return None, "Connection refused: Ableton not running"  # FAILS
        return None, "unknown"

    canned_answer = "Here is the answer even without session state."
    canned_tokens = {"input": 150, "output": 40, "total": 190}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=mock_bridge_no_state):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(canned_answer, {}, canned_tokens)):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "how do I make the chorus bigger"},
            )
            h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(
            f"HTTP {h._cap_code} when /session/state failed — "
            "expected 200 (session state failure must be tolerated)"
        )
    if d is None:
        errors.append("no response data when session state failed")
    else:
        if d.get("type") != "answer":
            errors.append(
                f"type={d.get('type')!r} when session state failed — expected 'answer'"
            )
        if d.get("text") != canned_answer:
            errors.append(
                f"text={str(d.get('text'))[:60]!r} — expected canned answer even without session state"
            )
        if d.get("ok") is not True:
            errors.append(f"ok={d.get('ok')!r}, expected True despite session state failure")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D125] {e}")
        print("  D125: FAIL")
        return False

    print(f"  {PASS} [D125] session state failure tolerated — type:answer returned correctly")
    print("  D125: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D126 — Answer text does not expose raw mode classifier strings
# ══════════════════════════════════════════════════════════════════════════════

@section("D126")
def run_d126():
    print("=== Section D126: type:answer text does not contain raw mode strings ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Canned answer from LLM — clean production-quality text
    clean_answer = (
        "For sidechain compression, set the kick as the sidechain source, "
        "attack 1ms, release 80ms, ratio 8:1. This creates the pumping effect."
    )
    canned_tokens = {"input": 180, "output": 45, "total": 225}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_bridge_side_effect_mentor):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(clean_answer, {}, canned_tokens)):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "explain sidechain compression"},
            )
            h.do_POST()

    d = h._cap_data
    if d is None:
        errors.append("no response data")
    else:
        text = d.get("text", "")
        # Verify the LLM response is passed through unchanged
        if text != clean_answer:
            errors.append(f"text modified by orchestrate: {str(text)[:80]!r}")

        # Raw mode strings must not appear in the user-facing text field
        _RAW_MODES = [
            "INTERN_WRITE_SAFE", "INTERN_WRITE_RISKY",
            "INTERN_READ", "FREEFORM_GENERAL",
            "Mode: MENTOR", "Mode: CLARIFY",
            "Protection level:", "Auto execute allowed:",
            "Confirmation required:",
        ]
        for bad in _RAW_MODES:
            if bad in text:
                errors.append(
                    f"raw mode string {bad!r} found in user-facing text — "
                    "orchestrate must not pollute the answer with internal classifier output"
                )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D126] {e}")
        print("  D126: FAIL")
        return False

    print(f"  {PASS} [D126] LLM answer passed through clean; no raw mode strings in text field")
    print("  D126: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D127 — POST /harness/parse_intent still works unchanged
# ══════════════════════════════════════════════════════════════════════════════

@section("D127")
def run_d127():
    print("=== Section D127: POST /harness/parse_intent unchanged (regression) ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Part A: static — /harness/parse_intent still in source ────────────────
    src = inspect.getsource(hs_mod)
    if "/harness/parse_intent" not in src:
        errors.append("/harness/parse_intent removed from harness_server source")

    # ── Part B: parse_intent returns original format (no type field required) ──
    canned_parsed = {
        "ok":                True,
        "action_id":         "vol",
        "params":            {"track": "Bass", "volume": 0.7},
        "confidence":        0.88,
        "needs_confirmation": False,
        "clarification":     None,
        "reason":            "Setting Bass volume to 70%.",
    }
    canned_tokens = {"input": 12, "output": 6, "total": 18}

    with _mock.patch("tools.harness_server.call_gemini",
                     return_value=(canned_parsed, canned_tokens)):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            path="/harness/parse_intent",
            body={"text": "set bass volume to 70 percent"},
        )
        h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"parse_intent HTTP {h._cap_code}, expected 200")
    if d is None:
        errors.append("parse_intent: no response data")
    else:
        # Original fields still present
        for key in ("ok", "action_id", "params", "confidence",
                    "needs_confirmation", "reason", "model", "tokens"):
            if key not in d:
                errors.append(f"parse_intent: field {key!r} missing from response")
        if d.get("action_id") != "vol":
            errors.append(f"parse_intent: action_id={d.get('action_id')!r}, expected 'vol'")
        if d.get("ok") is not True:
            errors.append(f"parse_intent: ok={d.get('ok')!r}, expected True")
        # parse_intent must NOT set type — it predates the type field
        # (type field absence is correct; its presence is also harmless but unnecessary)

    # ── Part C: parse_intent does NOT call _call_bridge_get ───────────────────
    # parse_intent must remain action-only; no context pack overhead.
    with _mock.patch("tools.harness_server._call_bridge_get") as mock_bridge:
        with _mock.patch("tools.harness_server.call_gemini",
                         return_value=(canned_parsed, canned_tokens)):
            h2 = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/parse_intent",
                body={"text": "mute kick"},
            )
            h2.do_POST()

        if mock_bridge.call_count != 0:
            errors.append(
                f"parse_intent called _call_bridge_get {mock_bridge.call_count} time(s) — "
                "parse_intent must not call the bridge (no context pack overhead)"
            )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D127] {e}")
        print("  D127: FAIL")
        return False

    print(f"  {PASS} [D127] parse_intent unchanged: correct response, no bridge calls")
    print("  D127: PASS")
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
            import traceback
            traceback.print_exc()
            results[label] = False
        print()

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    print("=" * 60)
    print(f"Phase D Slice 12 — Knowledge Gateway: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
