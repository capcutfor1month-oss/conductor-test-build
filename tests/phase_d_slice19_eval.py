"""
Phase D Slice 19 — Knowledge Status Context to Critic
======================================================
Tests for Build 12: _extract_knowledge_status_context(),
knowledge_status_context param in _build_critic_prompt() and
call_creative_critic(), and _handle_orchestrate() integration.

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


# ── shared pack fixtures ───────────────────────────────────────────────────────

_PACK_WITH_STATUS = (
    "## MESSAGE PACK\n"
    "Mode: MENTOR\n"
    "Risk: LOW\n\n"
    "### Memory\n"
    "(none yet — builds over sessions)\n\n"
    "## KNOWLEDGE STATUS\n"
    "Plugin recognized: Diva\n"
    "Operator card: not available — answer from general knowledge only\n"
    "Flag any plugin-specific parameter or workflow claims as unverified."
)

_PACK_WITH_CARD = (
    "## MESSAGE PACK\n"
    "Mode: MENTOR\n"
    "Risk: LOW\n\n"
    "## OPERATOR CARD — Pro-Q 4\n"
    "## Identity\n"
    "FabFilter Pro-Q 4. Dynamic EQ + linear phase modes.\n"
    "## Risky Writes\n"
    "- Band bypass changes are immediate."
)

_PACK_EMPTY = (
    "## MESSAGE PACK\n"
    "Mode: MENTOR\n"
    "Risk: LOW"
)

_PACK_STATUS_THEN_OTHER = (
    "## MESSAGE PACK\n"
    "Mode: MENTOR\n\n"
    "## KNOWLEDGE STATUS\n"
    "Plugin recognized: Valhalla Room\n"
    "Operator card: not available — answer from general knowledge only\n"
    "Flag any plugin-specific parameter or workflow claims as unverified.\n\n"
    "## SOME OTHER SECTION\n"
    "This line must not appear in the extracted block."
)


# ── shared mock helpers ────────────────────────────────────────────────────────

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
        "ok": True, "tempo": 120.0, "time_signature": "4/4",
        "playing": False, "selected_track": "Synth Lead",
        "tracks": [{"index": 0, "name": "Synth Lead", "type": "midi",
                    "muted": False, "soloed": False, "arm": False}],
        "return_tracks": [],
    }


def _make_bridge(pack_fn):
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:
            return pack_fn(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return _session_state_ok(), None
        return None, "unknown"
    return _fn


_EXPLORER_ANSWER = "Use a gentle low-pass on Diva — general principles apply here."
_EXPLORER_DATA = {
    "question_type": "creative",
    "candidates": [
        {
            "direction": "Set Diva filter cutoff to 4kHz with resonance at 50%",
            "rationale": "Standard starting point for subtractive synthesis",
            "session_facts_used": [],
            "assumptions": [],
            "source_hints": ["subtractive synthesis"],
            "actionable": True,
            "confidence": 0.75,
        },
        {
            "direction": "Use gentle low-pass filtering from general synthesis principles",
            "rationale": "No Operator Card available — framing as general guidance",
            "session_facts_used": [],
            "assumptions": ["No Diva card — using general subtractive principles"],
            "source_hints": ["subtractive synthesis"],
            "actionable": True,
            "confidence": 0.45,
        },
    ],
}
_TOKENS = {"input": 80, "output": 40, "total": 120}


# ── Section D177 ──────────────────────────────────────────────────────────────

@section("D177")
def run_d177():
    """
    _extract_knowledge_status_context returns the full ## KNOWLEDGE STATUS block
    from a pack that contains one (multi-line, all lines included).
    """
    print("=== Section D177: extracts full KNOWLEDGE STATUS block ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    result = hs_mod._extract_knowledge_status_context(_PACK_WITH_STATUS)

    if not result:
        errors.append("returned empty string — expected KNOWLEDGE STATUS block")
    if "## KNOWLEDGE STATUS" not in result:
        errors.append("extracted block missing '## KNOWLEDGE STATUS' header")
    if "Plugin recognized: Diva" not in result:
        errors.append("extracted block missing 'Plugin recognized: Diva'")
    if "Operator card: not available" not in result:
        errors.append("extracted block missing 'Operator card: not available'")
    if "Flag any plugin-specific" not in result:
        errors.append("extracted block missing third line of KNOWLEDGE STATUS")

    return errors


# ── Section D178 ──────────────────────────────────────────────────────────────

@section("D178")
def run_d178():
    """
    _extract_knowledge_status_context returns "" when the pack contains only an
    OPERATOR CARD block (no KNOWLEDGE STATUS present).
    """
    print("=== Section D178: returns '' when KNOWLEDGE STATUS absent ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Pack with only an OPERATOR CARD
    result_card = hs_mod._extract_knowledge_status_context(_PACK_WITH_CARD)
    if result_card != "":
        errors.append(
            f"expected '' for pack with OPERATOR CARD only, got {result_card!r}"
        )

    # Empty pack
    result_empty = hs_mod._extract_knowledge_status_context(_PACK_EMPTY)
    if result_empty != "":
        errors.append(
            f"expected '' for pack with no special blocks, got {result_empty!r}"
        )

    # None / empty string input
    result_none = hs_mod._extract_knowledge_status_context("")
    if result_none != "":
        errors.append(f"expected '' for empty input, got {result_none!r}")

    return errors


# ── Section D179 ──────────────────────────────────────────────────────────────

@section("D179")
def run_d179():
    """
    _extract_knowledge_status_context stops at the next ## section.
    Content from ## SOME OTHER SECTION must not appear in the extracted block.
    """
    print("=== Section D179: stops at next ## section (isolation) ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    result = hs_mod._extract_knowledge_status_context(_PACK_STATUS_THEN_OTHER)

    if "## KNOWLEDGE STATUS" not in result:
        errors.append("extracted block missing KNOWLEDGE STATUS header")
    if "Plugin recognized: Valhalla Room" not in result:
        errors.append("Valhalla Room not in extracted block")
    if "## SOME OTHER SECTION" in result:
        errors.append("extracted block leaked into ## SOME OTHER SECTION")
    if "This line must not appear" in result:
        errors.append("content from SOME OTHER SECTION leaked into extracted block")

    return errors


# ── Section D180 ──────────────────────────────────────────────────────────────

@section("D180")
def run_d180():
    """
    _build_critic_prompt with knowledge_status_context=<block> includes an
    internal ## Plugin Knowledge Context section in the prompt.
    """
    print("=== Section D180: critic prompt includes knowledge-status block when present ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    ks_block = (
        "## KNOWLEDGE STATUS\n"
        "Plugin recognized: Diva\n"
        "Operator card: not available — answer from general knowledge only\n"
        "Flag any plugin-specific parameter or workflow claims as unverified."
    )
    prompt = hs_mod._build_critic_prompt(
        _EXPLORER_DATA["candidates"],
        "How should I set Diva's filter?",
        "## LIVE ABLETON SESSION\nTracks (1): Synth Lead",
        knowledge_status_context=ks_block,
    )

    if "## Plugin Knowledge Context" not in prompt:
        errors.append("'## Plugin Knowledge Context' section missing from prompt")
    if "Plugin recognized: Diva" not in prompt:
        errors.append("Diva plugin name not injected into critic prompt")
    if "knowledge_evidence" not in prompt:
        errors.append("'knowledge_evidence' criterion missing from prompt")
    if "Penalize candidates" not in prompt and "penalize candidates" not in prompt:
        errors.append("penalize instruction missing from Plugin Knowledge Context block")
    # Confirm user-facing instruction not to expose the block
    if "user-facing answer" not in prompt:
        errors.append("'do not surface in user-facing answer' instruction missing")

    return errors


# ── Section D181 ──────────────────────────────────────────────────────────────

@section("D181")
def run_d181():
    """
    _build_critic_prompt with empty knowledge_status_context="" adds NO
    Plugin Knowledge Context block (backward compatibility — D156 behavior).
    """
    print("=== Section D181: no knowledge-status block when context empty (backward compat) ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # No knowledge_status_context (default)
    prompt_default = hs_mod._build_critic_prompt(
        _EXPLORER_DATA["candidates"],
        "How should I EQ the strings?",
        "",
    )
    if "## Plugin Knowledge Context" in prompt_default:
        errors.append("Plugin Knowledge Context appeared with empty default knowledge_status_context")

    # Explicit empty string
    prompt_explicit = hs_mod._build_critic_prompt(
        _EXPLORER_DATA["candidates"],
        "How should I EQ the strings?",
        "",
        knowledge_status_context="",
    )
    if "## Plugin Knowledge Context" in prompt_explicit:
        errors.append("Plugin Knowledge Context appeared with explicit empty knowledge_status_context")

    # Other criteria must still be present (regression guard for D156)
    for criterion in ("operator_card_compliance", "knowledge_evidence",
                      "genericity", "session_grounding"):
        if criterion not in prompt_default:
            errors.append(f"existing criterion '{criterion}' missing from prompt (regression)")

    return errors


# ── Section D182 ──────────────────────────────────────────────────────────────

@section("D182")
def run_d182():
    """
    call_creative_critic accepts knowledge_status_context= kwarg and passes it
    through to _build_critic_prompt (verified via mock capture on the prompt
    builder; LLM layer mocked with a valid Gemini-envelope response).
    """
    print("=== Section D182: call_creative_critic accepts/passes knowledge_status_context ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    captured = {}

    def fake_build_prompt(candidates, question_text, session_context, card_context="",
                          knowledge_status_context=""):
        captured["knowledge_status_context"] = knowledge_status_context
        return "## Creative Critic\nfake prompt"

    ks_block = (
        "## KNOWLEDGE STATUS\n"
        "Plugin recognized: Diva\n"
        "Operator card: not available — answer from general knowledge only"
    )

    # Critic JSON that the LLM would return (wrapped inside the Gemini API envelope)
    critic_json_str = json.dumps({
        "selected": 0,
        "kept": [0],
        "rejected": [],
        "reasons": {},
        "critic_summary": "Direction 0 selected",
    })
    # Gemini API envelope: {"candidates": [{"content": {"parts": [{"text": "..."}]}}], ...}
    gemini_envelope = json.dumps({
        "candidates": [{"content": {"parts": [{"text": critic_json_str}]}}],
        "usageMetadata": {"promptTokenCount": 80, "candidatesTokenCount": 40,
                          "totalTokenCount": 120},
    }).encode()

    import urllib.request as _ureq
    mock_resp = _mock.MagicMock()
    mock_resp.read.return_value = gemini_envelope
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = _mock.MagicMock(return_value=False)

    with _mock.patch.object(hs_mod, "_build_critic_prompt", side_effect=fake_build_prompt), \
         _mock.patch.object(_ureq, "urlopen", return_value=mock_resp):
        hs_mod.call_creative_critic(
            _EXPLORER_DATA["candidates"],
            "How should I set Diva's filter?",
            "",
            provider="gemini",
            model="gemini-test",
            api_key="test-key",
            knowledge_status_context=ks_block,
        )

    if "knowledge_status_context" not in captured:
        errors.append("_build_critic_prompt was not called (call_creative_critic broken)")
    elif captured["knowledge_status_context"] != ks_block:
        errors.append(
            f"knowledge_status_context not passed through: "
            f"expected {ks_block!r}, got {captured['knowledge_status_context']!r}"
        )

    return errors


# ── Section D183 ──────────────────────────────────────────────────────────────

@section("D183")
def run_d183():
    """
    _handle_orchestrate integration: when /context/pack contains ## KNOWLEDGE STATUS,
    Critic receives it via knowledge_status_context=.
    Mirrors the D157 pattern for Operator Card context.
    """
    print("=== Section D183: orchestrate passes KNOWLEDGE STATUS to Critic ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []
    captured = {}

    def pack_with_status():
        return {"ok": True, "mode": "MENTOR", "pack": _PACK_WITH_STATUS}

    def fake_explorer(*args, **kwargs):
        return _EXPLORER_ANSWER, _EXPLORER_DATA, _TOKENS

    def fake_critic(candidates, question_text, session_context,
                    provider, model, api_key, base_url=None,
                    card_context="", knowledge_status_context=""):
        captured["knowledge_status_context"] = knowledge_status_context
        captured["card_context"] = card_context
        return {
            "selected": 1,
            "kept": [1],
            "rejected": [0],
            "reasons": {"0": "knowledge_evidence — made confident Diva-specific claims without acknowledging gap"},
            "critic_summary": "Direction 1 selected — gap acknowledged",
        }, {"input": 20, "output": 10, "total": 30}

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(pack_with_status)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "How should I set Diva's filter cutoff?"},
        )
        h.do_POST()

    if h._cap_code != 200:
        errors.append(f"expected HTTP 200, got {h._cap_code}")

    ks = captured.get("knowledge_status_context", "MISSING")
    if ks == "MISSING":
        errors.append("Critic was not called or knowledge_status_context arg was not captured")
    elif "KNOWLEDGE STATUS" not in ks:
        errors.append(
            f"Critic did not receive ## KNOWLEDGE STATUS block; got {ks!r}"
        )
    if "Plugin recognized: Diva" not in ks:
        errors.append("'Plugin recognized: Diva' not in knowledge_status_context passed to Critic")

    # card_context must be empty (no OPERATOR CARD in this pack)
    if captured.get("card_context") != "":
        errors.append(
            f"expected empty card_context when no OPERATOR CARD present, "
            f"got {captured.get('card_context')!r}"
        )

    # Final answer must not expose internal block labels
    text = (h._cap_data or {}).get("text", "")
    if "Plugin Knowledge Context" in text:
        errors.append("internal '## Plugin Knowledge Context' label leaked into user-facing answer")
    if "KNOWLEDGE STATUS" in text:
        errors.append("internal '## KNOWLEDGE STATUS' label leaked into user-facing answer")

    return errors


# ── Section D184 ──────────────────────────────────────────────────────────────

@section("D184")
def run_d184():
    """
    Regression: orchestrate with no ## KNOWLEDGE STATUS in pack passes
    knowledge_status_context="" to Critic (no breakage).
    Also verifies the card-present path (D157 regression) still works.
    """
    print("=== Section D184: no KNOWLEDGE STATUS passes '' and D157-style card path preserved ===")
    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Sub-case A: pack with no KNOWLEDGE STATUS and no OPERATOR CARD ─────────
    captured_a = {}

    def pack_no_status():
        return {"ok": True, "mode": "MENTOR",
                "pack": "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW"}

    def fake_critic_a(candidates, question_text, session_context,
                      provider, model, api_key, base_url=None,
                      card_context="", knowledge_status_context=""):
        captured_a["knowledge_status_context"] = knowledge_status_context
        captured_a["card_context"] = card_context
        return {"selected": 0, "kept": [0], "rejected": [], "reasons": {},
                "critic_summary": "ok"}, _TOKENS

    def fake_explorer(*args, **kwargs):
        return _EXPLORER_ANSWER, _EXPLORER_DATA, _TOKENS

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(pack_no_status)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic_a), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h_a = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "how do I compress a dhol?"},
        )
        h_a.do_POST()

    if captured_a.get("knowledge_status_context") != "":
        errors.append(
            f"[A] expected knowledge_status_context='', "
            f"got {captured_a.get('knowledge_status_context')!r}"
        )
    if captured_a.get("card_context") != "":
        errors.append(
            f"[A] expected card_context='', "
            f"got {captured_a.get('card_context')!r}"
        )
    if h_a._cap_code != 200:
        errors.append(f"[A] expected HTTP 200, got {h_a._cap_code}")

    # ── Sub-case B: pack with OPERATOR CARD but no KNOWLEDGE STATUS (D157 reg) ─
    captured_b = {}

    _CARD_PACK_TEXT = (
        "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW\n\n"
        "## OPERATOR CARD — Ozone 12\n"
        "Identity: Mastering suite.\n"
        "Never Do:\n"
        "- Do not recommend aggressive maximizer gain on an already-hot master."
    )

    def pack_with_card_b():
        return {"ok": True, "mode": "MENTOR", "pack": _CARD_PACK_TEXT}

    def fake_critic_b(candidates, question_text, session_context,
                      provider, model, api_key, base_url=None,
                      card_context="", knowledge_status_context=""):
        captured_b["knowledge_status_context"] = knowledge_status_context
        captured_b["card_context"] = card_context
        return {"selected": 0, "kept": [0], "rejected": [], "reasons": {},
                "critic_summary": "ok"}, _TOKENS

    with _mock.patch.object(hs_mod, "_call_bridge_get", side_effect=_make_bridge(pack_with_card_b)), \
         _mock.patch.object(hs_mod, "call_knowledge_explorer", side_effect=fake_explorer), \
         _mock.patch.object(hs_mod, "call_creative_critic", side_effect=fake_critic_b), \
         _mock.patch.object(hs_mod, "_load_system_prompt", return_value="SYSTEM"):
        h_b = _make_mock_handler(
            hs_mod.HarnessHandler,
            "/harness/orchestrate",
            {"text": "Should I push Ozone harder?"},
        )
        h_b.do_POST()

    if captured_b.get("knowledge_status_context") != "":
        errors.append(
            f"[B] expected knowledge_status_context='' with card-only pack, "
            f"got {captured_b.get('knowledge_status_context')!r}"
        )
    if "OPERATOR CARD — Ozone 12" not in captured_b.get("card_context", ""):
        errors.append("[B] Ozone 12 card not in card_context (D157 regression)")
    if h_b._cap_code != 200:
        errors.append(f"[B] expected HTTP 200, got {h_b._cap_code}")

    return errors


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    total = 0
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
        print(f"{FAIL} Phase D Slice 19: {failed}/{total} sections failed")
        raise SystemExit(1)
    print(f"{PASS} Phase D Slice 19: {total}/{total} sections passed")


if __name__ == "__main__":
    main()
