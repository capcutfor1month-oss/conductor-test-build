"""
Phase D Slice 21 — CLARIFY Mode Hardening
==========================================
Tests for Build 14: _compose_clarify_question(), _clarify_safe(),
_CLARIFY_LABEL_RE, and the CLARIFY fast-path in _handle_orchestrate().

All sections are mock-based — no live ChromaDB or LLM calls.
"""

import importlib
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


# ── shared helpers ─────────────────────────────────────────────────────────────

def _make_mock_handler(HarnessHandler, path, body,
                       provider="gemini", model="test-model",
                       api_key="test-key", base_url=""):
    class MockHandler(HarnessHandler):
        def __init__(self):
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

        def send_response(self, code): pass
        def send_header(self, k, v):   pass
        def end_headers(self):         pass
        def log_message(self, *a):     pass

    return MockHandler()


def _make_bridge(mode, risk_reason="", risk_category="", pack_text=""):
    """Return a mock _call_bridge_get that emits CLARIFY (or other) pack data."""
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:
            return {
                "ok":           True,
                "mode":         mode,
                "risk_reason":  risk_reason,
                "risk_category": risk_category,
                "pack":         pack_text or f"## MESSAGE PACK\nMode: {mode}\n",
            }, None
        if "/context/session" in path:
            return {"ok": True, "pack": "## PRODUCER DNA\nProducer: Adi"}, None
        if "/session/state" in path:
            return {"ok": False}, None
        return None, "unknown"
    return _fn


# ── Section D197 ──────────────────────────────────────────────────────────────

@section("D197")
def run_d197():
    """
    _compose_clarify_question() unit tests — all template branches.
    Covers:
      [A] unclear_target with recognisable verb → "Which track or plugin should I {verb}?"
      [B] unclear_target with NO verb → generic target question
      [C] too_short → fixed natural question
      [D] *_unclear_scope → track/bus/plugin question
      [E] generic fallback from safe risk_reason
      [F] unsupported/block category → returns '' (fall back to LLM)
      [G] empty inputs → returns ''
    """
    print("=== Section D197: _compose_clarify_question() — all template branches ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    # [A] unclear_target with verb
    result_a = hs._compose_clarify_question("Lower it by 1 dB", "", "unclear_target")
    if not result_a:
        errors.append("[A] unclear+verb: returned empty string")
    elif "lower" not in result_a.lower():
        errors.append(f"[A] unclear+verb: expected 'lower' in question, got {result_a!r}")
    elif not result_a.strip().endswith("?"):
        errors.append(f"[A] unclear+verb: does not end with '?': {result_a!r}")

    # [B] unclear_target without a known verb
    result_b = hs._compose_clarify_question("Do something with it", "", "unclear_target")
    if not result_b:
        errors.append("[B] unclear+no-verb: returned empty string")
    elif not result_b.strip().endswith("?"):
        errors.append(f"[B] unclear+no-verb: does not end with '?': {result_b!r}")
    elif "track" not in result_b.lower() and "plugin" not in result_b.lower():
        errors.append(f"[B] unclear+no-verb: missing 'track' or 'plugin': {result_b!r}")

    # [C] too_short
    result_c = hs._compose_clarify_question("ok", "Message too short to determine intent safely.", "too_short")
    if not result_c:
        errors.append("[C] too_short: returned empty string")
    elif not result_c.strip().endswith("?"):
        errors.append(f"[C] too_short: does not end with '?': {result_c!r}")
    elif len(result_c.split("?")[0].split()) < 3:
        errors.append(f"[C] too_short: response too minimal: {result_c!r}")

    # [D] *_unclear_scope
    result_d = hs._compose_clarify_question("Boost it", "", "routing_unclear_scope")
    if not result_d:
        errors.append("[D] unclear_scope: returned empty string")
    elif not result_d.strip().endswith("?"):
        errors.append(f"[D] unclear_scope: does not end with '?': {result_d!r}")
    elif "track" not in result_d.lower() and "bus" not in result_d.lower():
        errors.append(f"[D] unclear_scope: missing 'track' or 'bus': {result_d!r}")

    # [E] generic fallback from safe risk_reason (unknown category)
    result_e = hs._compose_clarify_question(
        "Do the thing",
        "The target is ambiguous in this context",
        "some_other_category",
    )
    if result_e and not result_e.strip().endswith("?"):
        errors.append(f"[E] generic fallback: does not end with '?': {result_e!r}")
    # result_e may be '' if the reason is filtered — that's acceptable

    # [F] BLOCK_UNSUPPORTED / unsupported category → should return ''
    result_f = hs._compose_clarify_question(
        "Open the plugin GUI and drag by hand",
        "Block: unsupported manual GUI action.",
        "unsupported_manual_gui",
    )
    if result_f != "":
        errors.append(f"[F] block/unsupported: expected '', got {result_f!r}")

    # [G] empty inputs → ''
    result_g = hs._compose_clarify_question("", "", "")
    if result_g != "":
        errors.append(f"[G] empty inputs: expected '', got {result_g!r}")

    return errors


# ── Section D198 ──────────────────────────────────────────────────────────────

@section("D198")
def run_d198():
    """
    _compose_clarify_question() and _clarify_safe() never expose internal labels.
    Covers: Mode:, Risk:, CLARIFY, CLARIFY_REQUIRED, Protection:,
            risk_category, protection_level, unclear_target, too_short.
    """
    print("=== Section D198: clarify output never exposes internal labels ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    forbidden = [
        "Mode:", "Risk:", "Protection:", "CLARIFY", "CLARIFY_REQUIRED",
        "risk_category", "protection_level", "unclear_target",
        "too_short", "unsupported_manual_gui", "BLOCK_UNSUPPORTED",
    ]

    cases = [
        ("Lower it", "", "unclear_target"),
        ("Compress it", "", "unclear_pronoun"),
        ("Pan it right", "", "unclear_target"),
        ("ok", "Message too short.", "too_short"),
        ("Route it", "", "routing_unclear_scope"),
        ("Do something", "The target is unclear.", "some_category"),
    ]

    for orig, reason, cat in cases:
        result = hs._compose_clarify_question(orig, reason, cat)
        if result:  # '' means fallback — nothing to check
            for label in forbidden:
                if label.lower() in result.lower():
                    errors.append(
                        f"label {label!r} leaked for ({orig!r}, {cat!r}): {result!r}"
                    )

    # _clarify_safe() must reject a contaminated question
    contaminated = "Could you clarify — Mode: CLARIFY_REQUIRED issue?"
    if hs._clarify_safe(contaminated) != "":
        errors.append(f"_clarify_safe did not reject contaminated question: {contaminated!r}")

    # _clarify_safe() must accept a clean question
    clean = "Which track or plugin should I compress?"
    if hs._clarify_safe(clean) != clean:
        errors.append(f"_clarify_safe rejected clean question: {clean!r}")

    # _clarify_safe() must reject a non-question (no '?')
    non_q = "Lower the kick track"
    if hs._clarify_safe(non_q) != "":
        errors.append(f"_clarify_safe accepted non-question: {non_q!r}")

    return errors


# ── Section D199 ──────────────────────────────────────────────────────────────

@section("D199")
def run_d199():
    """
    Integration: pronoun / unclear_target message →
    _handle_orchestrate returns type:"clarify", one question, no internal labels.
    No LLM call made.
    """
    print("=== Section D199: orchestrate CLARIFY (pronoun) → type:clarify ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    lll_called = []

    def fake_knowledge_answer(*a, **kw):
        lll_called.append(True)
        return "LLM fallback answer", {"input": 1, "output": 1, "total": 2}

    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge(
                                "CLARIFY",
                                risk_reason="ask one clarifying question (which track/bus/plugin?) before proceeding.",
                                risk_category="unclear_target",
                            )), \
         _mock.patch.object(hs_mod, "call_knowledge_answer",
                            side_effect=fake_knowledge_answer), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "Lower it by 2 dB"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")
        return errors

    data = h._cap_data or {}
    if data.get("type") != "clarify":
        errors.append(f"expected type:'clarify', got {data.get('type')!r}")

    text = data.get("text", "")
    if not text.strip().endswith("?"):
        errors.append(f"response does not end with '?': {text!r}")

    # Must contain "lower" (verb extracted from original message)
    if "lower" not in text.lower():
        errors.append(f"verb 'lower' not reflected in clarify question: {text!r}")

    # Must not have made an LLM call
    if lll_called:
        errors.append("LLM was called but should not have been (fast-path should have fired)")

    # No internal labels
    for label in ["Mode:", "CLARIFY", "Risk:", "Protection:", "unclear_target"]:
        if label.lower() in text.lower():
            errors.append(f"internal label {label!r} in response text: {text!r}")

    return errors


# ── Section D200 ──────────────────────────────────────────────────────────────

@section("D200")
def run_d200():
    """
    Integration: too_short message ("ok") →
    type:"clarify", natural question, no LLM call.
    """
    print("=== Section D200: orchestrate CLARIFY (too_short) → type:clarify ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    llm_called = []

    def fake_knowledge_answer(*a, **kw):
        llm_called.append(True)
        return "LLM fallback answer", {"input": 1, "output": 1, "total": 2}

    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge(
                                "CLARIFY",
                                risk_reason="Message too short to determine intent safely.",
                                risk_category="too_short",
                            )), \
         _mock.patch.object(hs_mod, "call_knowledge_answer",
                            side_effect=fake_knowledge_answer), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "ok"},
        )
        h.do_POST()

    if (h._cap_data or {}).get("type") != "clarify":
        errors.append(f"expected type:'clarify', got {(h._cap_data or {}).get('type')!r}")

    text = (h._cap_data or {}).get("text", "")
    if not text.strip().endswith("?"):
        errors.append(f"too_short response does not end with '?': {text!r}")

    if llm_called:
        errors.append("LLM called for too_short — should use fast-path")

    for label in ["Mode:", "CLARIFY", "Risk:", "Protection:"]:
        if label.lower() in text.lower():
            errors.append(f"internal label {label!r} in too_short response: {text!r}")

    return errors


# ── Section D201 ──────────────────────────────────────────────────────────────

@section("D201")
def run_d201():
    """
    Integration: composer returns '' (BLOCK / unsupported_manual_gui) →
    falls back to call_knowledge_answer(), returns type:"answer".
    Verifies the fallback path is intact — no regression.
    """
    print("=== Section D201: CLARIFY composer '' → fallback to call_knowledge_answer ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    llm_called = []

    def fake_knowledge_answer(*a, **kw):
        llm_called.append(True)
        return "Sorry, I can't control GUI elements directly.", {"input": 10, "output": 5, "total": 15}

    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge(
                                "CLARIFY",
                                risk_reason="Block: unsupported manual GUI action.",
                                risk_category="unsupported_manual_gui",
                            )), \
         _mock.patch.object(hs_mod, "call_knowledge_answer",
                            side_effect=fake_knowledge_answer), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "Open the plugin GUI and drag the knob"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")

    data = h._cap_data or {}
    # Fallback uses type:"answer" — same as READ path
    if data.get("type") != "answer":
        errors.append(f"expected type:'answer' for fallback, got {data.get('type')!r}")

    if not llm_called:
        errors.append("call_knowledge_answer was not called — fallback did not fire")

    return errors


# ── Section D202 ──────────────────────────────────────────────────────────────

@section("D202")
def run_d202():
    """
    Regression: MENTOR mode is completely unaffected by Build 14.
    CLARIFY branch must not intercept non-CLARIFY modes.
    """
    print("=== Section D202: MENTOR mode unaffected by CLARIFY branch ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    _EXPLORER_ANSWER = "Use parallel compression to add punch to the drums."
    _EXPLORER_DATA = {
        "question_type": "creative",
        "candidates": [
            {
                "direction": "Use parallel compression",
                "rationale":  "Adds punch without killing transients",
                "session_facts_used": [],
                "assumptions": [],
                "source_hints": [],
                "actionable": True,
                "confidence": 0.8,
            }
        ],
    }

    def fake_explorer(*a, **kw):
        return _EXPLORER_ANSWER, _EXPLORER_DATA, {"input": 50, "output": 20, "total": 70}

    def fake_critic(*a, **kw):
        return {"selected": 0, "kept": [0], "rejected": [], "reasons": {}, "critic_summary": "ok"}, {"input": 10, "output": 5, "total": 15}

    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge("MENTOR")), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "How should I compress the drums?"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")
    data = h._cap_data or {}
    if data.get("type") != "answer":
        errors.append(f"MENTOR expected type:'answer', got {data.get('type')!r}")
    if data.get("mode") != "MENTOR":
        errors.append(f"MENTOR mode expected in response, got {data.get('mode')!r}")
    if "clarify" in str(data.get("type", "")).lower():
        errors.append("MENTOR response has type:'clarify' — Build 14 branch leaked into MENTOR")

    return errors


# ── Section D203 ──────────────────────────────────────────────────────────────

@section("D203")
def run_d203():
    """
    risk_reason and risk_category are correctly extracted from pack_data
    and flow into _compose_clarify_question() via _handle_orchestrate().
    Verified by checking the clarify question reflects the extracted verb.
    """
    print("=== Section D203: risk_reason/risk_category extraction from pack_data ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Pack data with specific risk fields — the question should reflect the verb
    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge(
                                "CLARIFY",
                                risk_reason="Pronoun 'it' has no clear referent in the message.",
                                risk_category="unclear_target",
                            )), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "Mute it for the chorus"},
        )
        h.do_POST()

    data = h._cap_data or {}
    if data.get("type") != "clarify":
        errors.append(f"expected type:'clarify', got {data.get('type')!r}")

    text = data.get("text", "")
    # "mute" is a recognised verb — should appear in the question
    if "mute" not in text.lower():
        errors.append(
            f"verb 'mute' not in clarify question — risk_category may not have flowed: {text!r}"
        )
    if not text.strip().endswith("?"):
        errors.append(f"question does not end with '?': {text!r}")

    # Pack_data with missing risk fields — should still return 200 (graceful)
    with _mock.patch.object(hs_mod, "_call_bridge_get",
                            side_effect=_make_bridge("CLARIFY")), \
         _mock.patch.object(hs_mod, "call_knowledge_answer",
                            return_value=("LLM fallback", {"input": 1, "output": 1, "total": 2})), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h2 = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "ok"},
        )
        h2.do_POST()

    if h2._cap_code != 200:
        errors.append(f"missing risk fields: expected HTTP 200, got {h2._cap_code}")

    return errors


# ── Section D204 ──────────────────────────────────────────────────────────────

@section("D204")
def run_d204():
    """
    Symbol importability and output-shape contracts:
    - _compose_clarify_question importable
    - _clarify_safe importable
    - _CLARIFY_LABEL_RE importable and compiled
    - All template branches return str (not None)
    - Ends-with-'?' contract on non-empty returns
    """
    print("=== Section D204: symbol importability and output shape ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    # Symbols must exist
    for sym in ("_compose_clarify_question", "_clarify_safe", "_CLARIFY_LABEL_RE"):
        if not hasattr(hs, sym):
            errors.append(f"symbol {sym!r} not found in harness_server")

    if errors:
        return errors  # can't go further

    import re as _re
    if not isinstance(hs._CLARIFY_LABEL_RE, type(_re.compile(""))):
        errors.append("_CLARIFY_LABEL_RE is not a compiled regex")

    # Every non-empty return must end with '?'
    cases = [
        ("Lower it", "", "unclear_target"),
        ("Compress it", "", "unclear_pronoun"),
        ("ok", "Too short.", "too_short"),
        ("Route it", "", "routing_unclear_scope"),
    ]
    for orig, reason, cat in cases:
        result = hs._compose_clarify_question(orig, reason, cat)
        if not isinstance(result, str):
            errors.append(f"non-str return for ({orig!r}, {cat!r}): {result!r}")
        elif result and not result.strip().endswith("?"):
            errors.append(f"non-empty result doesn't end with '?' for ({orig!r}, {cat!r}): {result!r}")

    # Empty-return cases must return exactly ''
    for orig, reason, cat in [
        ("Open GUI", "Block: unsupported.", "unsupported_manual_gui"),
        ("", "", ""),
    ]:
        result = hs._compose_clarify_question(orig, reason, cat)
        if result != "":
            errors.append(f"expected '' for block/empty case ({orig!r}, {cat!r}), got {result!r}")

    return errors


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    total  = 0
    failed = 0
    for label in sorted(SECTIONS.keys()):
        total += 1
        try:
            errors = SECTIONS[label]()
        except Exception as exc:
            import traceback
            errors = [f"exception: {type(exc).__name__}: {exc}"]
            traceback.print_exc()
        if errors:
            failed += 1
            print(f"{FAIL} Section {label} FAIL")
            for e in errors:
                print("  -", e)
        else:
            print(f"{PASS} Section {label} PASS")
        print()

    print("=" * 60)
    if failed:
        print(f"{FAIL} Phase D Slice 21: {failed}/{total} sections failed")
        raise SystemExit(1)
    print(f"{PASS} Phase D Slice 21: {total}/{total} sections passed")


if __name__ == "__main__":
    main()
