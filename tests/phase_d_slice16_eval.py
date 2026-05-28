"""
Phase D — Slice 16: Card-aware Creative Critic v1 Eval Suite
Sections D154–D161

Covers:
  D154  No-card case preserves Build 7 prompt/composer behavior
  D155  Card context is included in critic prompt when present
  D156  operator_card_compliance criterion is present
  D157  /harness/orchestrate extracts existing Operator Card snippet from
        /context/pack and passes it to Creative Critic
  D158  No-card /harness/orchestrate passes empty card context and preserves
        Build 7 behavior
  D159  Card Never Do / Risky Writes can reject unsafe/plugin-wrong candidate;
        final answer follows card-compliant selected candidate
  D160  WRITE mode still bypasses Explorer/Critic and returns type:"action"
  D161  READ/direct mode remains unchanged; no Explorer/Critic call
"""

import importlib
import io
import json
import os
import re as _re
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


def _session_pack():
    return {"ok": True, "pack": "## PRODUCER DNA\nProducer: Adi"}


def _session_state_ok():
    return {
        "ok": True,
        "ableton_connected": True,
        "tempo": 124.0,
        "time_signature": "4/4",
        "playing": False,
        "selected_track": "Lead Vocals",
        "tracks": [
            {"index": 0, "name": "Lead Vocals", "type": "audio",
             "muted": False, "soloed": False, "arm": False},
            {"index": 1, "name": "Kick", "type": "midi",
             "muted": False, "soloed": False, "arm": False},
        ],
        "return_tracks": [{"index": 0, "name": "Reverb"}],
        "state_completeness": {"tempo": "full", "tracks": "full"},
    }


def _mentor_pack_no_card():
    return {
        "ok": True,
        "mode": "MENTOR",
        "pack": "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW",
    }


def _mentor_pack_with_card():
    return {
        "ok": True,
        "mode": "MENTOR",
        "pack": (
            "## MESSAGE PACK\n"
            "Mode: MENTOR\n"
            "Risk: LOW\n\n"
            "## OPERATOR CARD — Ozone 12\n"
            "Identity: Mastering suite. Use carefully on master bus.\n"
            "Never Do:\n"
            "- Do not recommend aggressive maximizer gain on an already-hot master.\n"
            "Risky Writes:\n"
            "- Maximizer threshold and ceiling changes require caution.\n\n"
            "## OTHER CONTEXT\n"
            "This should not be included in the card block."
        ),
    }


def _read_pack():
    return {
        "ok": True,
        "mode": "INTERN_READ",
        "pack": "## MESSAGE PACK\nMode: INTERN_READ\nRisk: LOW",
    }


def _write_safe_pack():
    return {
        "ok": True,
        "mode": "INTERN_WRITE_SAFE",
        "pack": "## MESSAGE PACK\nMode: INTERN_WRITE_SAFE\nRisk: MEDIUM",
    }


def _make_bridge(mode_pack):
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:
            return mode_pack(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return _session_state_ok(), None
        return None, "unknown"
    return _fn


_EXPLORER_ANSWER = "Push Ozone hard for loudness."
_EXPLORER_DATA = {
    "question_type": "creative",
    "candidates": [
        {
            "direction": "Push Ozone Maximizer aggressively",
            "rationale": "More limiting will make the master louder quickly",
            "session_facts_used": ["Selected track: Lead Vocals"],
            "assumptions": ["Master has enough headroom"],
            "source_hints": ["Ozone Maximizer"],
            "actionable": True,
            "confidence": 0.40,
        },
        {
            "direction": "Use gentle Ozone mastering moves",
            "rationale": "The card warns against aggressive maximizer gain on already-hot masters",
            "session_facts_used": ["Operator Card — Ozone 12"],
            "assumptions": [],
            "source_hints": ["Ozone Risky Writes"],
            "actionable": True,
            "confidence": 0.80,
        },
    ],
}
_TOKENS = {"input": 80, "output": 40, "total": 120}

_ACTION_PARSED = {
    "ok": True,
    "action_id": "mute",
    "params": {"track": "Kick", "mute": True},
    "confidence": 0.95,
    "needs_confirmation": False,
    "clarification": None,
    "reason": "Muting Kick.",
}
_ACTION_TOKENS = {"input": 10, "output": 5, "total": 15}

_STRUCTURAL_RE_TEST = _re.compile(
    r"(?i)\b("
    r"candidates|direction|rationale|session_facts_used"
    r"|assumptions|source_hints|actionable|confidence|question_type"
    r"|selected|kept|rejected|critic_summary|operator_card_compliance"
    r")\b"
)


def _check_no_internal_exposure(text, label, errors):
    if not text or not text.strip():
        errors.append(f"{label}: text is empty")
        return
    stripped = text.strip()
    if stripped.startswith("{"):
        errors.append(f"{label}: raw JSON exposed")
    if stripped.startswith("```"):
        errors.append(f"{label}: markdown fence exposed")
    match = _STRUCTURAL_RE_TEST.search(text)
    if match:
        errors.append(f"{label}: internal marker exposed: {match.group()!r}")


@section("D154")
def run_d154():
    print("=== Section D154: no-card case preserves Build 7 behavior ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    candidates = _EXPLORER_DATA["candidates"]
    prompt = hs_mod._build_critic_prompt(
        candidates,
        "How should I master this?",
        "## LIVE ABLETON SESSION\nSelected track: Lead Vocals",
    )
    if "## Operator Card Context" in prompt:
        errors.append("no-card prompt unexpectedly contains Operator Card block")

    answer = hs_mod._compose_final_answer(
        "Explorer answer",
        _EXPLORER_DATA,
        {"selected": 1, "kept": [1], "rejected": [0]},
    )
    expected = (
        "Use gentle Ozone mastering moves. "
        "The card warns against aggressive maximizer gain on already-hot masters."
    )
    if answer != expected:
        errors.append(f"Build 7 composer changed: got {answer!r}")

    return errors


@section("D155")
def run_d155():
    print("=== Section D155: card context included in critic prompt + adjacent-card isolation ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Sub-case A: single card ───────────────────────────────────────────────
    card = hs_mod._extract_operator_card_context(_mentor_pack_with_card()["pack"])
    prompt = hs_mod._build_critic_prompt(
        _EXPLORER_DATA["candidates"],
        "How should I master this?",
        "## LIVE ABLETON SESSION\nSelected track: Lead Vocals",
        card_context=card,
    )
    if "## Operator Card Context" not in prompt:
        errors.append("[A] critic prompt missing Operator Card Context block")
    if "OPERATOR CARD — Ozone 12" not in prompt:
        errors.append("[A] critic prompt missing Ozone card content")
    if "aggressive maximizer gain" not in prompt:
        errors.append("[A] critic prompt missing Never Do text")
    if "## OTHER CONTEXT" in card:
        errors.append("[A] card extractor leaked following non-card context")

    # ── Sub-case B: adjacent cards — extractor must stop at first card boundary ─
    adjacent_pack = (
        "## MESSAGE PACK\n"
        "Mode: MENTOR\n\n"
        "## OPERATOR CARD — Ozone 12\n"
        "Never Do:\n"
        "- Avoid aggressive maximizer gain on an already-hot master.\n\n"
        "## OPERATOR CARD — Pro-Q 4\n"
        "Never Do:\n"
        "- Never set Q above 4.0 unless surgical notch.\n"
    )
    extracted = hs_mod._extract_operator_card_context(adjacent_pack)
    if "OPERATOR CARD — Ozone 12" not in extracted:
        errors.append("[B] adjacent-card pack: Ozone 12 card not extracted")
    if "OPERATOR CARD — Pro-Q 4" in extracted:
        errors.append("[B] adjacent-card pack: Pro-Q 4 card leaked into extraction (stop condition broken)")
    if "surgical notch" in extracted:
        errors.append("[B] adjacent-card pack: Pro-Q 4 content leaked into extraction")

    return errors


@section("D156")
def run_d156():
    print("=== Section D156: operator_card_compliance criterion present ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    prompt = hs_mod._build_critic_prompt(
        _EXPLORER_DATA["candidates"],
        "How should I master this?",
        "",
        card_context="## OPERATOR CARD — Ozone 12\nNever Do:\n- Avoid aggressive maximizer gain.",
    )
    if "operator_card_compliance" not in prompt:
        errors.append("missing 7th criterion: operator_card_compliance")
    if "Never Do" not in prompt or "Risky Writes" not in prompt:
        errors.append("prompt does not instruct critic to enforce card constraints")

    return errors


@section("D157")
def run_d157():
    print("=== Section D157: orchestrate passes extracted Operator Card to Critic ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    captured = {}

    def fake_explorer(*args, **kwargs):
        return _EXPLORER_ANSWER, _EXPLORER_DATA, _TOKENS

    def fake_critic(candidates, question_text, session_context,
                    provider, model, api_key, base_url=None, card_context=""):
        captured["card_context"] = card_context
        return {
            "selected": 1,
            "kept": [1],
            "rejected": [0],
            "reasons": {
                "0": "operator_card_compliance — violates Ozone Never Do guidance",
            },
            "critic_summary": "Direction 1 selected — card-compliant",
        }, {"input": 20, "output": 10, "total": 30}

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(_mentor_pack_with_card)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "Should I push Ozone harder?"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")
    card_context = captured.get("card_context", "")
    if "OPERATOR CARD — Ozone 12" not in card_context:
        errors.append("critic did not receive extracted Operator Card block")
    if "## OTHER CONTEXT" in card_context:
        errors.append("critic received context beyond the card block")
    text = (h._cap_data or {}).get("text", "")
    if not text.startswith("Use gentle Ozone mastering moves."):
        errors.append(f"final answer did not follow selected card-compliant candidate: {text!r}")
    _check_no_internal_exposure(text, "D157 text", errors)

    return errors


@section("D158")
def run_d158():
    print("=== Section D158: no-card orchestrate preserves Build 7 behavior ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    captured = {}

    def fake_explorer(*args, **kwargs):
        return _EXPLORER_ANSWER, _EXPLORER_DATA, _TOKENS

    def fake_critic(candidates, question_text, session_context,
                    provider, model, api_key, base_url=None, card_context=""):
        captured["card_context"] = card_context
        return {"selected": 1, "kept": [1], "rejected": [0]}, _TOKENS

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(_mentor_pack_no_card)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "How should I master this?"},
        )
        h.do_POST()

    if captured.get("card_context") != "":
        errors.append(f"expected empty card_context, got {captured.get('card_context')!r}")
    if h._cap_code != 200 or (h._cap_data or {}).get("type") != "answer":
        errors.append(f"unexpected response: {h._cap_code}, {h._cap_data}")

    return errors


@section("D159")
def run_d159():
    print("=== Section D159: unsafe card-violating candidate rejected/demoted ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    critic = {
        "selected": 1,
        "kept": [1],
        "rejected": [0],
        "reasons": {
            "0": "operator_card_compliance — violates Never Do and Risky Writes guidance",
        },
        "critic_summary": "Direction 1 selected — card-compliant",
    }
    text = hs_mod._compose_final_answer(_EXPLORER_ANSWER, _EXPLORER_DATA, critic)
    if "Use gentle Ozone mastering moves" not in text:
        errors.append("final answer did not follow card-compliant selected candidate")
    if text.startswith("Push Ozone"):
        errors.append("unsafe/rejected candidate still controls final answer")
    _check_no_internal_exposure(text, "D159 text", errors)

    return errors


@section("D160")
def run_d160():
    print("=== Section D160: WRITE mode bypasses Explorer/Critic ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(_write_safe_pack)), \
         _mock.patch.object(hs_mod, "call_openai", return_value=(_ACTION_PARSED, _ACTION_TOKENS)), \
         _mock.patch.object(hs_mod, "call_gemini", return_value=(_ACTION_PARSED, _ACTION_TOKENS)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer") as explorer_mock, \
         _mock.patch.object(hs_mod, "call_creative_critic") as critic_mock:
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "mute Kick"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")
    if (h._cap_data or {}).get("type") != "action":
        errors.append(f"WRITE did not return type action: {h._cap_data}")
    if explorer_mock.called:
        errors.append("WRITE path incorrectly called Explorer")
    if critic_mock.called:
        errors.append("WRITE path incorrectly called Creative Critic")

    return errors


@section("D161")
def run_d161():
    print("=== Section D161: READ/direct mode remains unchanged ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(_read_pack)), \
         _mock.patch.object(hs_mod, "call_knowledge_answer", return_value=("Direct read answer.", _TOKENS)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer") as explorer_mock, \
         _mock.patch.object(hs_mod, "call_creative_critic") as critic_mock, \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "What tracks are in my session?"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")
    if (h._cap_data or {}).get("text") != "Direct read answer.":
        errors.append(f"direct answer changed unexpectedly: {h._cap_data}")
    if explorer_mock.called:
        errors.append("READ/direct path incorrectly called Explorer")
    if critic_mock.called:
        errors.append("READ/direct path incorrectly called Creative Critic")

    return errors


def main():
    total = 0
    failed = 0
    for label in sorted(SECTIONS.keys()):
        total += 1
        try:
            errors = SECTIONS[label]()
        except Exception as exc:
            errors = [f"exception: {type(exc).__name__}: {exc}"]
        if errors:
            failed += 1
            print(f"{FAIL} Section {label} FAIL")
            for e in errors:
                print("  -", e)
        else:
            print(f"{PASS} Section {label} PASS")
    print()
    if failed:
        print(f"{FAIL} Phase D Slice 16: {failed}/{total} sections failed")
        raise SystemExit(1)
    print(f"{PASS} Phase D Slice 16: {total}/{total} sections passed")


if __name__ == "__main__":
    main()
