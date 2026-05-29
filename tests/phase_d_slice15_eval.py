"""
Phase D — Slice 15: Creative Critic v1 Eval Suite
Sections D143–D153

Covers:
  D143  MENTOR mode — call_creative_critic invoked after Explorer;
         final text derived from selected candidate, not raw Explorer answer
  D144  FREEFORM_GENERAL mode — same as D143
  D145  Generic candidate rejected/demoted — critic.rejected contains generic index;
         kept contains session-grounded index
  D146  Session-grounded candidate selected — critic.selected = grounded index
  D147  Session-contradicted candidate rejected — critic.rejected contains contradicted index
  D148  User-facing answer exposes no critic JSON or internal critic labels;
         critic field present as internal data only; composed text aligns to selected candidate
  D149  Fallback safety:
         (A) critic raises exception → 200 OK, text = explorer answer, critic = {}
         (B) empty candidates → critic not called, critic = {}
         (C) invalid selected index (mock bypasses internal check) → _compose_final_answer
             falls back to explorer answer
  D150  WRITE mode bypasses Critic — call_creative_critic never called; type:"action" returned
  D151  Slice 14 Explorer regression + Critic static symbols intact
  D152  Core filtering proof — Explorer answer recommends generic/rejected candidate;
         Critic selects session-grounded candidate; final text aligns to grounded direction;
         final text does not present the rejected candidate as the main recommendation
  D153  Real parser fallback — malformed critic JSON through actual call_creative_critic()
         parser returns ({}, tokens) safely; invalid index returns ({}, tokens) safely
"""

import importlib
import inspect
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


# ── Mock handler factory ──────────────────────────────────────────────────────

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


# ── Canned data ───────────────────────────────────────────────────────────────

def _mentor_pack():
    return {
        "ok": True, "mode": "MENTOR",
        "pack": "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW",
        "risk_reason": "",
    }

def _freeform_general_pack():
    return {
        "ok": True, "mode": "FREEFORM_GENERAL",
        "pack": "## MESSAGE PACK\nMode: FREEFORM_GENERAL\nRisk: LOW",
        "risk_reason": "",
    }

def _write_safe_pack():
    return {
        "ok": True, "mode": "INTERN_WRITE_SAFE",
        "pack": "## MESSAGE PACK\nMode: INTERN_WRITE_SAFE\nRisk: MEDIUM",
        "risk_reason": "",
    }

def _session_pack():
    return {"ok": True, "pack": "## PRODUCER DNA\nProducer: Adi"}

def _session_state_ok():
    return {
        "ok": True, "ableton_connected": True,
        "tempo": 120.0, "time_signature": "4/4",
        "playing": False, "record": False,
        "selected_track": "Lead Vocals",
        "tracks": [
            {"index": 0, "name": "Lead Vocals", "type": "audio",
             "muted": False, "soloed": False, "arm": False},
            {"index": 1, "name": "Kick", "type": "midi",
             "muted": False, "soloed": False, "arm": False},
        ],
        "return_tracks": [{"index": 0, "name": "Reverb"}],
        "state_completeness": {
            "tempo": "full", "tracks": "full", "selected_track": "best_effort",
        },
    }

def _make_bridge(mode_pack):
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:    return mode_pack(), None
        if "/context/session" in path: return _session_pack(), None
        if "/session/state" in path:   return _session_state_ok(), None
        return None, "unknown"
    return _fn

# ── Canned explorer data ──────────────────────────────────────────────────────
# candidates[0] = session-grounded, candidates[1] = generic

_CANNED_EXPLORER_ANSWER = (
    "Your vocal sounds dull because of low-mid buildup around 300 Hz. "
    "Try cutting 2–3 dB there first."
)
_CANNED_EXPLORER_DATA = {
    "question_type": "session",
    "candidates": [
        {
            "direction": "Cut low-mid buildup on Lead Vocals",
            "rationale": "Selected track is Lead Vocals; dullness traces to 200–400 Hz",
            "session_facts_used": ["Selected track: Lead Vocals", "Tempo: 120 BPM"],
            "assumptions": [],
            "source_hints": ["EQ cut at 300 Hz"],
            "actionable": True,
            "confidence": 0.85,
        },
        {
            "direction": "Add reverb to everything",
            "rationale": "Reverb makes things sound wider",
            "session_facts_used": [],
            "assumptions": ["Any mix could benefit from reverb"],
            "source_hints": [],
            "actionable": True,
            "confidence": 0.30,
        },
    ],
}
_CANNED_EXPLORER_TOKENS = {"input": 80, "output": 40, "total": 120}

# Critic selects the session-grounded candidate (index 0)
_CANNED_CRITIC_DATA = {
    "selected": 0,
    "kept": [0],
    "rejected": [1],
    "reasons": {
        "1": "generic — no session facts used; applies to any session regardless of context",
    },
    "critic_summary": "Direction 0 selected — grounded in Lead Vocals track context",
}
_CANNED_CRITIC_TOKENS = {"input": 40, "output": 20, "total": 60}

# Expected composed text when critic selects candidates[0]
_COMPOSED_FROM_CANDIDATE_0 = (
    "Cut low-mid buildup on Lead Vocals. "
    "Selected track is Lead Vocals; dullness traces to 200–400 Hz."
)

# Canned action mapping for WRITE tests
_CANNED_ACTION_PARSED = {
    "ok": True, "action_id": "mute",
    "params": {"track": "Kick", "mute": True},
    "confidence": 0.95, "needs_confirmation": False,
    "clarification": None, "reason": "Muting Kick.",
}
_CANNED_ACTION_TOKENS = {"input": 10, "output": 5, "total": 15}

# Mirror of _STRUCTURAL_RE from harness_server.py
_STRUCTURAL_RE_TEST = _re.compile(
    r"(?i)\b("
    r"candidates|direction|rationale|session_facts_used"
    r"|assumptions|source_hints|actionable|confidence|question_type"
    r")\b"
)


def _check_no_internal_exposure(text, label, errors):
    """Guard: user-facing text must not expose internal schema or critic JSON."""
    if not text or not text.strip():
        errors.append(f"{label}: text is empty or blank")
        return
    stripped = text.strip()
    if stripped.startswith("{"):
        errors.append(f"{label}: text starts with '{{' — raw JSON exposed")
    if stripped.startswith("```"):
        errors.append(f"{label}: text starts with '```' — fenced content exposed")
    m = _STRUCTURAL_RE_TEST.search(text)
    if m:
        errors.append(
            f"{label}: text contains internal schema marker {m.group()!r}"
        )
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and (
            "selected" in parsed or "candidates" in parsed or "answer" in parsed
        ):
            errors.append(f"{label}: text parses as internal JSON")
    except (json.JSONDecodeError, TypeError):
        pass


# ── Provider-level mock helper ────────────────────────────────────────────────

def _gemini_resp(inner_text):
    """Build a mock urlopen return value simulating a Gemini response."""
    body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": inner_text}]}}],
        "usageMetadata": {
            "promptTokenCount": 50,
            "candidatesTokenCount": 30,
            "totalTokenCount": 80,
        },
    }).encode()
    mock_resp = _mock.MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda *_: mock_resp
    mock_resp.__exit__  = lambda *_: None
    return mock_resp


# ══════════════════════════════════════════════════════════════════════════════
# D143 — MENTOR mode: final text derived from selected candidate, not Explorer answer
# ══════════════════════════════════════════════════════════════════════════════

@section("D143")
def run_d143():
    print("=== Section D143: MENTOR — final text = composed from selected candidate ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    critic_call_args = {}

    def _capture_critic(candidates, question_text, session_context,
                        provider, model, api_key, base_url=None, card_context="",
                        knowledge_status_context=""):
        critic_call_args["candidates"]    = candidates
        critic_call_args["question_text"] = question_text
        return _CANNED_CRITIC_DATA, _CANNED_CRITIC_TOKENS

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             side_effect=_capture_critic):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull what should I do"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("type") != "answer":
        errors.append(f"type={d.get('type')!r}, expected 'answer'")

    # Critic must have been called with the explorer candidates
    if not critic_call_args:
        errors.append("call_creative_critic was NOT called for MENTOR mode")
    elif not critic_call_args.get("candidates"):
        errors.append("call_creative_critic called with empty candidates")

    text = d.get("text", "")

    # Final text must be COMPOSED from the selected candidate (index 0),
    # not the raw Explorer synthesised answer
    if text == _CANNED_EXPLORER_ANSWER:
        errors.append(
            "text equals raw explorer answer — Critic did not influence final text; "
            "_compose_final_answer must derive text from selected candidate"
        )

    # Must contain content from the selected candidate (direction or rationale)
    selected_direction = _CANNED_EXPLORER_DATA["candidates"][0]["direction"]
    if selected_direction not in text:
        errors.append(
            f"text={str(text)[:100]!r} — does not contain selected candidate direction "
            f"{selected_direction!r}"
        )

    # Must not expose internal schema markers or raw JSON
    _check_no_internal_exposure(text, "D143 text", errors)

    # Critic field must be present (internal) and match canned data
    if "critic" not in d:
        errors.append("'critic' key missing from MENTOR response")
    elif d["critic"] != _CANNED_CRITIC_DATA:
        errors.append(f"critic={d.get('critic')!r}, expected canned critic data")

    if errors:
        for e in errors: print(f"  {FAIL} [D143] {e}")
        print("  D143: FAIL"); return False

    print(f"  {PASS} [D143] MENTOR: call_creative_critic called; "
          "final text composed from selected candidate; "
          "not raw explorer answer; no internal markers")
    print("  D143: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D144 — FREEFORM_GENERAL mode: Critic invoked, critic key in response
# ══════════════════════════════════════════════════════════════════════════════

@section("D144")
def run_d144():
    print("=== Section D144: FREEFORM_GENERAL — Critic invoked after Explorer ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    critic_called = {"count": 0}

    def _capture_critic(candidates, question_text, session_context,
                        provider, model, api_key, base_url=None, card_context="",
                        knowledge_status_context=""):
        critic_called["count"] += 1
        return _CANNED_CRITIC_DATA, _CANNED_CRITIC_TOKENS

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_freeform_general_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             side_effect=_capture_critic):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "how do I make my mix wider"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if d.get("type") != "answer":
        errors.append(f"type={d.get('type')!r}, expected 'answer'")
    if d.get("mode") != "FREEFORM_GENERAL":
        errors.append(f"mode={d.get('mode')!r}, expected 'FREEFORM_GENERAL'")
    if critic_called["count"] != 1:
        errors.append(f"call_creative_critic called {critic_called['count']}×, expected 1")
    if "critic" not in d:
        errors.append("'critic' key missing from FREEFORM_GENERAL response")

    # Text must be composed from selected candidate, not raw explorer answer
    text = d.get("text", "")
    selected_direction = _CANNED_EXPLORER_DATA["candidates"][0]["direction"]
    if text == _CANNED_EXPLORER_ANSWER:
        errors.append("text equals raw explorer answer — Critic did not influence final text")
    if selected_direction not in text:
        errors.append(
            f"text does not contain selected candidate direction {selected_direction!r}"
        )
    _check_no_internal_exposure(text, "D144 text", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D144] {e}")
        print("  D144: FAIL"); return False

    print(f"  {PASS} [D144] FREEFORM_GENERAL: Critic invoked; "
          "final text composed from selected candidate; 'critic' key present")
    print("  D144: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D145 — Generic candidate rejected / session-grounded candidate kept
# ══════════════════════════════════════════════════════════════════════════════

@section("D145")
def run_d145():
    print("=== Section D145: generic candidate rejected; session-grounded kept ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    critic_result = {
        "selected": 0,
        "kept": [0],
        "rejected": [1],
        "reasons": {"1": "generic — no session facts used; applies to any session"},
        "critic_summary": "Direction 0 selected — grounded in Lead Vocals track context",
    }
    critic_tokens = {"input": 30, "output": 15, "total": 45}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(critic_result, critic_tokens)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    critic = d.get("critic", {})
    if not critic:
        errors.append("critic field is empty — expected critic result")
    else:
        if 1 not in (critic.get("rejected") or []):
            errors.append(f"critic.rejected={critic.get('rejected')!r}, expected [1]")
        if 0 not in (critic.get("kept") or []):
            errors.append(f"critic.kept={critic.get('kept')!r}, expected [0]")
        reasons = critic.get("reasons", {})
        if "1" not in reasons and 1 not in reasons:
            errors.append(f"critic.reasons missing entry for index 1: {reasons!r}")
        if not critic.get("critic_summary"):
            errors.append("critic.critic_summary is empty")

    # Final text must be composed from selected (grounded) candidate
    text = d.get("text", "")
    grounded_direction = _CANNED_EXPLORER_DATA["candidates"][0]["direction"]
    if grounded_direction not in text:
        errors.append(
            f"text does not contain grounded direction {grounded_direction!r}; got {text[:80]!r}"
        )
    _check_no_internal_exposure(text, "D145 text", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D145] {e}")
        print("  D145: FAIL"); return False

    print(f"  {PASS} [D145] generic index 1 rejected; grounded index 0 kept; "
          "final text contains grounded direction")
    print("  D145: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D146 — Session-grounded candidate is selected
# ══════════════════════════════════════════════════════════════════════════════

@section("D146")
def run_d146():
    print("=== Section D146: session-grounded candidate selected (critic.selected = 0) ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    explorer_data_with_grounded = {
        "question_type": "session",
        "candidates": [
            {
                "direction": "Cut low-mid buildup on Lead Vocals",
                "rationale": "Selected track is Lead Vocals",
                "session_facts_used": ["Selected track: Lead Vocals", "Tempo: 120 BPM"],
                "assumptions": [],
                "source_hints": ["EQ cut at 300 Hz"],
                "actionable": True,
                "confidence": 0.85,
            },
            {
                "direction": "Apply saturation",
                "rationale": "Saturation adds harmonics",
                "session_facts_used": [],
                "assumptions": ["Any track might benefit from saturation"],
                "source_hints": [],
                "actionable": True,
                "confidence": 0.40,
            },
        ],
    }
    grounded_explorer_answer = "Try some EQ on your vocal — cutting 300 Hz should help."

    critic_result = {
        "selected": 0,
        "kept": [0],
        "rejected": [1],
        "reasons": {"1": "generic — no session facts used"},
        "critic_summary": "Direction 0 selected — grounded in Lead Vocals session context",
    }
    critic_tokens = {"input": 35, "output": 18, "total": 53}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(grounded_explorer_answer, explorer_data_with_grounded,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(critic_result, critic_tokens)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    critic = d.get("critic", {})
    if critic.get("selected") != 0:
        errors.append(f"critic.selected={critic.get('selected')!r}, expected 0")

    text = d.get("text", "")
    # Must contain the grounded direction (index 0)
    if "Cut low-mid" not in text and "Lead Vocals" not in text:
        errors.append(
            f"text={text[:80]!r} — does not contain words from the grounded direction"
        )
    _check_no_internal_exposure(text, "D146 text", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D146] {e}")
        print("  D146: FAIL"); return False

    print(f"  {PASS} [D146] critic.selected=0; final text aligned to grounded candidate")
    print("  D146: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D147 — Session-contradicted candidate rejected
# ══════════════════════════════════════════════════════════════════════════════

@section("D147")
def run_d147():
    print("=== Section D147: session-contradicted candidate rejected ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    explorer_data_with_contradiction = {
        "question_type": "session",
        "candidates": [
            {
                "direction": "Cut low-mid buildup on Lead Vocals",
                "rationale": "Selected track is Lead Vocals",
                "session_facts_used": ["Selected track: Lead Vocals"],
                "assumptions": [],
                "source_hints": ["EQ"],
                "actionable": True,
                "confidence": 0.85,
            },
            {
                "direction": "Start fresh — no existing tracks to work with",
                "rationale": "Session appears empty",
                "session_facts_used": [],
                "assumptions": ["Session has no tracks loaded"],
                "source_hints": [],
                "actionable": False,
                "confidence": 0.10,
            },
        ],
    }

    critic_result = {
        "selected": 0,
        "kept": [0],
        "rejected": [1],
        "reasons": {
            "1": (
                "session_contradiction — claims session is empty but "
                "Lead Vocals and Kick tracks are visible"
            ),
        },
        "critic_summary": "Direction 0 selected — contradiction in direction 1 dismissed",
    }
    critic_tokens = {"input": 38, "output": 19, "total": 57}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       explorer_data_with_contradiction,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(critic_result, critic_tokens)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    critic = d.get("critic", {})
    if 1 not in (critic.get("rejected") or []):
        errors.append(f"critic.rejected={critic.get('rejected')!r}, expected index 1")
    reasons = critic.get("reasons", {})
    reason_text = reasons.get("1") or reasons.get(1) or ""
    if "contradiction" not in reason_text.lower():
        errors.append(f"reason for index 1={reason_text!r}, expected 'contradiction' mentioned")

    text = d.get("text", "")
    # Final text should NOT recommend the contradicted "start fresh" direction
    if "Start fresh" in text or "no existing tracks" in text.lower():
        errors.append(
            f"text={text[:100]!r} — presents the session-contradicted candidate"
        )
    _check_no_internal_exposure(text, "D147 text", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D147] {e}")
        print("  D147: FAIL"); return False

    print(f"  {PASS} [D147] session-contradicted candidate rejected; "
          "reason contains 'contradiction'; contradicted text not in final answer")
    print("  D147: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D148 — User-facing answer: no critic JSON, text aligns to selected candidate
# ══════════════════════════════════════════════════════════════════════════════

@section("D148")
def run_d148():
    print("=== Section D148: user-facing text: no internal labels; aligned to selected candidate ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(_CANNED_CRITIC_DATA, _CANNED_CRITIC_TOKENS)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    text = d.get("text", "")
    _check_no_internal_exposure(text, "D148 text", errors)

    # text must NOT be the raw serialised critic dict
    critic_json = json.dumps(_CANNED_CRITIC_DATA)
    if text == critic_json:
        errors.append("text == serialised critic JSON — critic data exposed as user-facing text")

    # text must not contain raw critic JSON field names
    for field in ('"selected"', '"kept"', '"rejected"', '"critic_summary"'):
        if field in text:
            errors.append(f"text contains critic JSON key {field!r}")

    # critic field must be present (internal) and non-empty
    if "critic" not in d:
        errors.append("'critic' key missing — internal critic data not stored")
    elif not d["critic"]:
        errors.append("critic field is empty — expected non-empty critic result")

    # text must be derived from the selected candidate, not equal to the raw explorer answer
    if text == _CANNED_EXPLORER_ANSWER:
        errors.append(
            "text still equals raw explorer answer — _compose_final_answer not applied"
        )
    selected_direction = _CANNED_EXPLORER_DATA["candidates"][0]["direction"]
    if selected_direction not in text:
        errors.append(
            f"text does not contain selected candidate direction {selected_direction!r}"
        )

    if errors:
        for e in errors: print(f"  {FAIL} [D148] {e}")
        print("  D148: FAIL"); return False

    print(f"  {PASS} [D148] no critic JSON/internal labels in text; "
          "text aligned to selected candidate; critic field present internally")
    print("  D148: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D149 — Fallback safety: exception, empty candidates, invalid index
# ══════════════════════════════════════════════════════════════════════════════

@section("D149")
def run_d149():
    print("=== Section D149: fallback safety — exception / empty candidates / invalid index ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Sub-case A: critic raises an exception ────────────────────────────────
    def _critic_raises(*_a, **_kw):
        raise RuntimeError("simulated critic LLM failure")

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             side_effect=_critic_raises):
                ha = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                ha.do_POST()

    if ha._cap_code != 200:
        errors.append(f"[A] HTTP {ha._cap_code}, expected 200 when critic raises")
    da = ha._cap_data or {}
    if da.get("ok") is not True:
        errors.append(f"[A] ok={da.get('ok')!r}, expected True")
    # critic raises → no valid critic_data → _compose_final_answer returns explorer_answer
    if da.get("text") != _CANNED_EXPLORER_ANSWER:
        errors.append(
            f"[A] text={str(da.get('text'))[:80]!r}, expected explorer answer when critic fails"
        )
    if da.get("critic") != {}:
        errors.append(f"[A] critic={da.get('critic')!r}, expected {{}} when critic raises")
    _check_no_internal_exposure(da.get("text", ""), "[A] fallback text", errors)

    # ── Sub-case B: empty candidates → critic not called ─────────────────────
    empty_data = {"question_type": "factual", "candidates": []}
    critic_b_called = {"count": 0}
    def _critic_b(*_a, **_kw):
        critic_b_called["count"] += 1
        return _CANNED_CRITIC_DATA, _CANNED_CRITIC_TOKENS

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER, empty_data,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             side_effect=_critic_b):
                hb = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                hb.do_POST()

    if hb._cap_code != 200:
        errors.append(f"[B] HTTP {hb._cap_code}, expected 200 for empty candidates")
    db = hb._cap_data or {}
    if critic_b_called["count"] != 0:
        errors.append(
            f"[B] call_creative_critic called {critic_b_called['count']}× — "
            "must not be called when candidates list is empty"
        )
    if db.get("critic") != {}:
        errors.append(f"[B] critic={db.get('critic')!r}, expected {{}} when no candidates")
    # Empty candidates → no critic → _compose_final_answer sees empty critic_data
    # → falls back to explorer answer
    if db.get("text") != _CANNED_EXPLORER_ANSWER:
        errors.append(
            f"[B] text={str(db.get('text'))[:80]!r}, expected explorer answer (empty candidates)"
        )

    # ── Sub-case C: invalid selected index → _compose_final_answer falls back ──
    # Mock call_creative_critic to return an out-of-range selected index.
    # _compose_final_answer must detect this and return explorer_answer.
    bad_critic = {
        "selected": 999,   # out of range — candidates only has 2 items
        "kept": [999],
        "rejected": [],
        "reasons": {},
        "critic_summary": "invalid",
    }
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(bad_critic, _CANNED_CRITIC_TOKENS)):
                hc = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                hc.do_POST()

    if hc._cap_code != 200:
        errors.append(f"[C] HTTP {hc._cap_code}, expected 200 for invalid selected index")
    dc = hc._cap_data or {}
    if dc.get("ok") is not True:
        errors.append(f"[C] ok={dc.get('ok')!r}, expected True")
    # invalid index → _compose_final_answer falls back to explorer_answer
    if dc.get("text") != _CANNED_EXPLORER_ANSWER:
        errors.append(
            f"[C] text={str(dc.get('text'))[:80]!r}, expected explorer answer "
            "when selected index is out of range"
        )
    _check_no_internal_exposure(dc.get("text", ""), "[C] fallback text", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D149] {e}")
        print("  D149: FAIL"); return False

    print(f"  {PASS} [D149] "
          "[A] critic raises → 200, explorer answer, critic={{}}; "
          "[B] empty candidates → critic not called, critic={{}}; "
          "[C] invalid index → _compose_final_answer falls back to explorer answer")
    print("  D149: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D150 — WRITE mode bypasses Critic entirely
# ══════════════════════════════════════════════════════════════════════════════

@section("D150")
def run_d150():
    print("=== Section D150: WRITE mode bypasses Critic — type:action returned ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_write_safe_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer") as mock_explorer:
            with _mock.patch("tools.harness_server.call_creative_critic") as mock_critic:
                with _mock.patch("tools.harness_server.call_knowledge_answer") as mock_direct:
                    with _mock.patch("tools.harness_server.call_gemini",
                                     return_value=(_CANNED_ACTION_PARSED,
                                                   _CANNED_ACTION_TOKENS)):
                        h = _make_mock_handler(
                            hs_mod.HarnessHandler,
                            path="/harness/orchestrate",
                            body={"text": "mute the kick"},
                        )
                        h.do_POST()

    d = h._cap_data or {}

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if mock_explorer.call_count != 0:
        errors.append(f"call_knowledge_explorer called {mock_explorer.call_count}× on WRITE")
    if mock_critic.call_count != 0:
        errors.append(f"call_creative_critic called {mock_critic.call_count}× on WRITE")
    if mock_direct.call_count != 0:
        errors.append(f"call_knowledge_answer called {mock_direct.call_count}× on WRITE")
    if d.get("type") != "action":
        errors.append(f"type={d.get('type')!r}, expected 'action'")
    if d.get("action_id") != "mute":
        errors.append(f"action_id={d.get('action_id')!r}, expected 'mute'")
    if "critic" in d:
        errors.append("'critic' key must not appear on type:action responses")
    if "explorer" in d:
        errors.append("'explorer' key must not appear on type:action responses")

    if errors:
        for e in errors: print(f"  {FAIL} [D150] {e}")
        print("  D150: FAIL"); return False

    print(f"  {PASS} [D150] WRITE mode: Critic not called; type:action; no critic/explorer keys")
    print("  D150: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D151 — Slice 14 regression + Critic + Composer static symbols
# ══════════════════════════════════════════════════════════════════════════════

@section("D151")
def run_d151():
    print("=== Section D151: Slice 14 regression + Critic + Composer symbols ===")

    hs_mod = importlib.import_module("tools.harness_server")
    src = inspect.getsource(hs_mod)
    errors = []

    # ── Part A: Critic + Composer symbols must be present ─────────────────────
    required_symbols = [
        ("call_creative_critic",     "call_creative_critic defined"),
        ("_build_critic_prompt",     "_build_critic_prompt defined"),
        ("_CRITIC_JSON_SCHEMA",      "_CRITIC_JSON_SCHEMA defined"),
        ("_compose_final_answer",    "_compose_final_answer defined"),
        ("final_text",               "final_text variable used in handler"),
        ('"critic"',                 '"critic" key in response'),
    ]
    for symbol, label in required_symbols:
        if symbol not in src:
            errors.append(f"[A] {label}: {symbol!r} not in harness_server source")

    # Spacing-insensitive check: explorer answer response must use final_text, not answer_text.
    # Build 15 added response_id which shifted alignment, so we match flexibly.
    import re as _re
    if not _re.search(r'"text"\s*:\s*final_text', src):
        errors.append('[A] text field uses final_text (not raw answer_text): '
                      r'"text"\s*:\s*final_text not found in harness_server source')

    # ── Part B: Slice 14 symbols still intact ─────────────────────────────────
    slice14_symbols = [
        ("call_knowledge_explorer",        "call_knowledge_explorer intact"),
        ("_EXPLORER_MODES",                "_EXPLORER_MODES intact"),
        ("_STRUCTURAL_RE",                 "_STRUCTURAL_RE intact"),
        ("_build_explorer_instructions",   "_build_explorer_instructions intact"),
        ("call_knowledge_answer",          "call_knowledge_answer intact"),
        ('"answer"',                       'type:"answer" produced'),
        ('"action"',                       'type:"action" produced'),
    ]
    for symbol, label in slice14_symbols:
        if symbol not in src:
            errors.append(f"[B] Slice14 regression — {label}: {symbol!r} not in source")

    # ── Part C: MENTOR → answer + critic + composed text ─────────────────────
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER,
                                       _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(_CANNED_CRITIC_DATA, _CANNED_CRITIC_TOKENS)):
                hc = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "what should I do with my mix"},
                )
                hc.do_POST()

    if hc._cap_code != 200:
        errors.append(f"[C] HTTP {hc._cap_code}, expected 200 for MENTOR")
    dc = hc._cap_data or {}
    if dc.get("type") != "answer":
        errors.append(f"[C] type={dc.get('type')!r}, expected 'answer'")
    if "explorer" not in dc:
        errors.append("[C] 'explorer' key missing from MENTOR response")
    if "critic" not in dc:
        errors.append("[C] 'critic' key missing from MENTOR response")
    # text must be composed from selected candidate
    selected_direction = _CANNED_EXPLORER_DATA["candidates"][0]["direction"]
    if selected_direction not in (dc.get("text") or ""):
        errors.append(
            f"[C] text does not contain selected direction {selected_direction!r}"
        )

    # ── Part D: WRITE → action, no critic ─────────────────────────────────────
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_write_safe_pack)):
        with _mock.patch("tools.harness_server.call_gemini",
                         return_value=(_CANNED_ACTION_PARSED, _CANNED_ACTION_TOKENS)):
            with _mock.patch("tools.harness_server.call_creative_critic") as mock_critic_d:
                hd = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "mute the kick"},
                )
                hd.do_POST()

    if hd._cap_code != 200:
        errors.append(f"[D] HTTP {hd._cap_code}, expected 200 for WRITE")
    dd = hd._cap_data or {}
    if dd.get("type") != "action":
        errors.append(f"[D] type={dd.get('type')!r}, expected 'action'")
    if mock_critic_d.call_count != 0:
        errors.append(f"[D] call_creative_critic called {mock_critic_d.call_count}× on WRITE")

    if errors:
        for e in errors: print(f"  {FAIL} [D151] {e}")
        print("  D151: FAIL"); return False

    print(f"  {PASS} [D151] Critic+Composer symbols present; Slice 14 intact; "
          "MENTOR→answer+critic+composed; WRITE→action")
    print("  D151: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D152 — Core filtering proof: Explorer generic answer replaced by selected candidate
# ══════════════════════════════════════════════════════════════════════════════

@section("D152")
def run_d152():
    print("=== Section D152: core filtering proof — Explorer generic answer replaced ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Explorer synthesised its answer from the GENERIC candidate (index 1)
    _GENERIC_BASED_ANSWER = (
        "Adding reverb to everything will give your mix more depth and space."
    )
    _GROUNDED_DIRECTION  = "Cut low-mid buildup on Lead Vocals"
    _GROUNDED_RATIONALE  = "Selected track is Lead Vocals; dullness traces to 200–400 Hz"
    _GENERIC_DIRECTION   = "Add reverb to everything"

    explorer_data = {
        "question_type": "session",
        "candidates": [
            {
                # index 0 — session-grounded (this is the BETTER candidate)
                "direction": _GROUNDED_DIRECTION,
                "rationale": _GROUNDED_RATIONALE,
                "session_facts_used": ["Selected track: Lead Vocals"],
                "assumptions": [],
                "source_hints": ["EQ cut at 300 Hz"],
                "actionable": True,
                "confidence": 0.85,
            },
            {
                # index 1 — generic (Explorer wrongly synthesised from this)
                "direction": _GENERIC_DIRECTION,
                "rationale": "Reverb adds depth",
                "session_facts_used": [],
                "assumptions": ["Any mix could benefit from reverb"],
                "source_hints": [],
                "actionable": True,
                "confidence": 0.30,
            },
        ],
    }
    explorer_tokens = {"input": 90, "output": 50, "total": 140}

    # Critic correctly selects the session-grounded candidate (0) and rejects generic (1)
    critic_data = {
        "selected": 0,
        "kept":     [0],
        "rejected": [1],
        "reasons":  {"1": "generic — no session facts used; applies to any session"},
        "critic_summary": "Direction 0 selected — grounded in Lead Vocals context",
    }
    critic_tokens = {"input": 45, "output": 22, "total": 67}

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_GENERIC_BASED_ANSWER, explorer_data, explorer_tokens)):
            with _mock.patch("tools.harness_server.call_creative_critic",
                             return_value=(critic_data, critic_tokens)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull"},
                )
                h.do_POST()

    d = h._cap_data or {}
    text = d.get("text", "")

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")

    # ── Proof 1: final text ≠ generic Explorer answer ─────────────────────────
    if text == _GENERIC_BASED_ANSWER:
        errors.append(
            "text equals the generic Explorer answer — "
            "Critic filtering had no effect on the final response"
        )

    # ── Proof 2: final text aligns to the selected (grounded) candidate ───────
    if _GROUNDED_DIRECTION not in text:
        errors.append(
            f"text={text[:100]!r} — does not contain grounded direction {_GROUNDED_DIRECTION!r}; "
            "final text must be derived from the Critic-selected candidate"
        )

    # ── Proof 3: final text does not present the rejected candidate as the main answer ──
    # The generic direction "Add reverb to everything" should not be
    # the leading recommendation in the final answer.
    if text.startswith(_GENERIC_DIRECTION) or text.lower().startswith("adding reverb"):
        errors.append(
            f"text starts with the rejected/generic candidate: {text[:80]!r}; "
            "rejected candidate must not control the final answer"
        )

    # ── Proof 4: no internal schema markers or raw JSON ───────────────────────
    _check_no_internal_exposure(text, "D152 text", errors)

    # ── Proof 5: critic internal data not exposed in user-facing text ─────────
    for key in ('"selected"', '"kept"', '"rejected"', '"critic_summary"'):
        if key in text:
            errors.append(f"text contains critic JSON key {key!r}")
    if json.dumps(critic_data) == text:
        errors.append("text == serialised critic JSON — critic data exposed to user")

    if errors:
        for e in errors: print(f"  {FAIL} [D152] {e}")
        print("  D152: FAIL"); return False

    print(f"  {PASS} [D152] filtering proof: "
          "text ≠ generic Explorer answer; "
          "text contains grounded direction; "
          "rejected candidate not the main recommendation; "
          "no critic/internal labels in text")
    print("  D152: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D153 — Real parser fallback: malformed + invalid-index through call_creative_critic()
# ══════════════════════════════════════════════════════════════════════════════

@section("D153")
def run_d153():
    print("=== Section D153: real call_creative_critic() parser fallback ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    _candidates = _CANNED_EXPLORER_DATA["candidates"]

    # ── Sub-case A: malformed JSON from provider → ({}, tokens) ──────────────
    # LLM returns garbage — json.loads fails.
    # call_creative_critic must return ({}, tokens) without raising.
    malformed = "this is not json at all: { selected: oops"

    with _mock.patch("urllib.request.urlopen",
                     return_value=_gemini_resp(malformed)):
        result_a, tokens_a = hs_mod.call_creative_critic(
            _candidates, "test question", "",
            "gemini", "test-model", "test-key",
        )

    if result_a != {}:
        errors.append(
            f"[A] malformed JSON → call_creative_critic returned {result_a!r}, expected {{}}"
        )
    if not isinstance(tokens_a, dict):
        errors.append(f"[A] tokens={tokens_a!r}, expected dict")

    # ── Sub-case B: valid JSON but "selected" key missing → ({}, tokens) ─────
    no_selected = json.dumps({
        "kept": [0], "rejected": [1],
        "reasons": {"1": "generic"},
        "critic_summary": "missing selected",
    })

    with _mock.patch("urllib.request.urlopen",
                     return_value=_gemini_resp(no_selected)):
        result_b, tokens_b = hs_mod.call_creative_critic(
            _candidates, "test question", "",
            "gemini", "test-model", "test-key",
        )

    if result_b != {}:
        errors.append(
            f"[B] missing 'selected' key → returned {result_b!r}, expected {{}}"
        )

    # ── Sub-case C: valid JSON with out-of-range selected index → ({}, tokens) ─
    # call_creative_critic's own validation should catch this and return {}.
    out_of_range = json.dumps({
        "selected": 999,
        "kept": [999], "rejected": [],
        "reasons": {}, "critic_summary": "oops",
    })

    with _mock.patch("urllib.request.urlopen",
                     return_value=_gemini_resp(out_of_range)):
        result_c, tokens_c = hs_mod.call_creative_critic(
            _candidates, "test question", "",
            "gemini", "test-model", "test-key",
        )

    if result_c != {}:
        errors.append(
            f"[C] out-of-range selected index → returned {result_c!r}, expected {{}}"
        )

    # ── Sub-case D: valid critic JSON → returns critic_data with correct shape ─
    good_critic_json = json.dumps({
        "selected": 0,
        "kept": [0], "rejected": [1],
        "reasons": {"1": "generic"},
        "critic_summary": "direction 0 selected",
    })

    with _mock.patch("urllib.request.urlopen",
                     return_value=_gemini_resp(good_critic_json)):
        result_d, tokens_d = hs_mod.call_creative_critic(
            _candidates, "test question", "",
            "gemini", "test-model", "test-key",
        )

    if not result_d:
        errors.append("[D] valid critic JSON → returned empty dict; expected populated critic_data")
    else:
        if result_d.get("selected") != 0:
            errors.append(f"[D] selected={result_d.get('selected')!r}, expected 0")
        if result_d.get("rejected") != [1]:
            errors.append(f"[D] rejected={result_d.get('rejected')!r}, expected [1]")
        if not result_d.get("critic_summary"):
            errors.append("[D] critic_summary is empty")

    # ── Sub-case E: _compose_final_answer with invalid index falls back ───────
    compose = hs_mod._compose_final_answer
    fb = compose("explorer fallback", _CANNED_EXPLORER_DATA, {"selected": 999})
    if fb != "explorer fallback":
        errors.append(
            f"[E] _compose_final_answer with invalid index returned {fb!r}, "
            "expected 'explorer fallback'"
        )

    # ── Sub-case F: _compose_final_answer with empty critic_data falls back ───
    fb2 = compose("explorer fallback", _CANNED_EXPLORER_DATA, {})
    if fb2 != "explorer fallback":
        errors.append(
            f"[F] _compose_final_answer with empty critic_data returned {fb2!r}, "
            "expected 'explorer fallback'"
        )

    # ── Sub-case G: _compose_final_answer with valid critic returns composed ──
    composed = compose("explorer answer", _CANNED_EXPLORER_DATA, _CANNED_CRITIC_DATA)
    # selected=0 → direction="Cut low-mid buildup on Lead Vocals"
    if "Cut low-mid" not in composed:
        errors.append(
            f"[G] _compose_final_answer with valid critic returned {composed!r}; "
            "expected composed text containing selected direction"
        )
    if composed == "explorer answer":
        errors.append("[G] _compose_final_answer returned unchanged explorer answer for valid critic")

    if errors:
        for e in errors: print(f"  {FAIL} [D153] {e}")
        print("  D153: FAIL"); return False

    print(f"  {PASS} [D153] real parser: "
          "[A] malformed JSON → ({{}, tokens}); "
          "[B] missing selected → ({{}, tokens}); "
          "[C] out-of-range index → ({{}, tokens}); "
          "[D] valid JSON → critic_data with correct shape; "
          "[E-F] _compose_final_answer invalid/empty → fallback; "
          "[G] _compose_final_answer valid critic → composed text")
    print("  D153: PASS"); return True


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
    print(f"Phase D Slice 15 — Creative Critic v1: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
