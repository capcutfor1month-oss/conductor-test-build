"""
Phase D — Slice 14: Knowledge Explorer v1 Eval Suite
Sections D135–D142

Covers:
  D135  MENTOR mode — end-to-end: provider response mocked at urlopen level;
         valid explorer JSON parsed; answer extracted; candidates shape correct
  D136  FREEFORM_GENERAL routing — provider response mocked at urlopen level;
         routes through explorer; answer returned; type:"answer" + explorer key
  D137  Malformed / partial JSON hardening:
         (A) truncated JSON with candidate keys → fallback text, no raw JSON
         (B) valid JSON missing "answer" key → fallback text, not empty string
         (C) valid JSON with whitespace-only "answer" → fallback text
         (D) YAML-style non-JSON with unquoted markers → fallback, no raw schema
         (E) markdown-fenced partial schema → fallback, no raw schema
         (F) mixed-case internal markers (CANDIDATES:, Direction:) → fallback
         All sub-cases: text must not expose candidate / schema markers
  D138  Session facts used when session state is available
  D139  Missing session state handled honestly — still 200, session_available=False
  D140  Factual question (READ mode) uses direct answer path — explorer NOT called
  D141  Write/action request still returns type:"action" — explorer never reached
  D142  Slice 12 orchestrate behaviour regression: MENTOR→answer, WRITE→action
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


# ── Mock handler factory (same as slice 12) ───────────────────────────────────

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

        def send_response(self, code):
            pass

        def send_header(self, k, v):
            pass

        def end_headers(self):
            pass

        def log_message(self, *a):
            pass

    return MockHandler()


# ── Canned data ───────────────────────────────────────────────────────────────

def _mentor_pack():
    return {
        "ok":   True, "mode": "MENTOR",
        "pack": "## MESSAGE PACK\nMode: MENTOR\nRisk: LOW",
        "risk_reason": "",
    }

def _freeform_general_pack():
    return {
        "ok":   True, "mode": "FREEFORM_GENERAL",
        "pack": "## MESSAGE PACK\nMode: FREEFORM_GENERAL\nRisk: LOW",
        "risk_reason": "",
    }

def _read_pack():
    return {
        "ok":   True, "mode": "READ",
        "pack": "## MESSAGE PACK\nMode: READ\nRisk: LOW",
        "risk_reason": "",
    }

def _write_safe_pack():
    return {
        "ok":   True, "mode": "INTERN_WRITE_SAFE",
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
            {"index": 1, "name": "Kick",        "type": "midi",
             "muted": False, "soloed": False, "arm": False},
        ],
        "return_tracks": [{"index": 0, "name": "Reverb"}],
        "state_completeness": {
            "tempo": "full", "tracks": "full", "selected_track": "best_effort",
        },
    }

def _make_bridge(mode_pack):
    """Bridge side_effect that returns the given mode pack + session data + state."""
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:
            return mode_pack(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return _session_state_ok(), None
        return None, "unknown"
    return _fn

def _make_bridge_no_state(mode_pack):
    """Bridge side_effect where /session/state fails."""
    def _fn(path, timeout=5.0):
        if "/context/pack" in path:
            return mode_pack(), None
        if "/context/session" in path:
            return _session_pack(), None
        if "/session/state" in path:
            return None, "timeout"
        return None, "unknown"
    return _fn

# Canned explorer return value (answer + internal candidates + tokens)
_CANNED_EXPLORER_ANSWER  = "Your vocal sounds dull because of low-mid buildup around 300 Hz. Try cutting 2–3 dB there first."
_CANNED_EXPLORER_DATA    = {
    "question_type": "session",
    "candidates": [
        {
            "direction": "Cut low-mid buildup on Lead Vocals",
            "rationale": "Selected track is Lead Vocals; dullness often traces to 200–400 Hz.",
            "session_facts_used": ["Selected track: Lead Vocals", "Tempo: 120 BPM"],
            "assumptions": [],
            "source_hints": ["EQ around 300 Hz", "vocal presence boost at 3–5 kHz"],
            "actionable": True,
            "confidence": 0.82,
        },
        {
            "direction": "Check for masking from Kick track",
            "rationale": "Kick is the only other track visible — could mask vocal body.",
            "session_facts_used": ["Kick track present"],
            "assumptions": ["No other tracks loaded besides Kick and Lead Vocals"],
            "source_hints": ["sidechain EQ", "spectrum comparison"],
            "actionable": True,
            "confidence": 0.65,
        },
    ],
}
_CANNED_EXPLORER_TOKENS  = {"input": 80, "output": 40, "total": 120}

# Canned direct answer return value
_CANNED_DIRECT_ANSWER   = "Compression ratio controls how much gain reduction is applied above the threshold."
_CANNED_DIRECT_TOKENS   = {"input": 30, "output": 15, "total": 45}

# ── Provider-level mock helpers ───────────────────────────────────────────────

# Valid explorer JSON string the LLM would return
_VALID_EXPLORER_ANSWER = (
    "Your vocal is dull due to low-mid buildup — "
    "cut around 300 Hz on Lead Vocals."
)
_VALID_EXPLORER_JSON = json.dumps({
    "answer": _VALID_EXPLORER_ANSWER,
    "question_type": "session",
    "candidates": [
        {
            "direction": "Cut low-mid buildup on Lead Vocals",
            "rationale": "Selected track is Lead Vocals; dullness = 200-400 Hz buildup",
            "session_facts_used": ["Selected track: Lead Vocals", "Tempo: 120 BPM"],
            "assumptions": [],
            "source_hints": ["EQ cut at 300 Hz", "presence boost at 3-5 kHz"],
            "actionable": True,
            "confidence": 0.85,
        },
        {
            "direction": "Check for masking from Kick track",
            "rationale": "Kick is present in session and can mask vocal body",
            "session_facts_used": ["Kick track present"],
            "assumptions": ["No other tracks beyond visible ones"],
            "source_hints": ["Spectrum comparison", "sidechain EQ"],
            "actionable": True,
            "confidence": 0.65,
        },
    ],
})


def _gemini_resp(inner_text):
    """
    Build a mock urllib.request.urlopen return value that simulates a Gemini API
    response with `inner_text` as the model-generated text.
    Supports context-manager protocol (with urllib.request.urlopen(...) as resp).
    """
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


# ── Forbidden markers — all 9 internal schema keys, unquoted lowercase ───────
# Used in D135 for literal case-sensitive substring checks on extracted answer text.
_INTERNAL_MARKERS = (
    "candidates", "direction", "rationale", "session_facts_used",
    "assumptions", "source_hints", "actionable", "confidence", "question_type",
)

# Case-insensitive word-boundary regex — mirrors _STRUCTURAL_RE in harness_server.py.
# Used in _check_no_internal_exposure to catch quoted/unquoted/YAML/mixed-case markers.
_STRUCTURAL_RE_TEST = _re.compile(
    r"(?i)\b("
    r"candidates|direction|rationale|session_facts_used"
    r"|assumptions|source_hints|actionable|confidence|question_type"
    r")\b"
)


# Canned action-mapping return value
_CANNED_ACTION_PARSED   = {
    "ok": True, "action_id": "mute",
    "params": {"track": "Kick", "mute": True},
    "confidence": 0.95, "needs_confirmation": False,
    "clarification": None, "reason": "Muting Kick.",
}
_CANNED_ACTION_TOKENS   = {"input": 10, "output": 5, "total": 15}


# ══════════════════════════════════════════════════════════════════════════════
# D135 — MENTOR mode → Knowledge Explorer path
# ══════════════════════════════════════════════════════════════════════════════

@section("D135")
def run_d135():
    print("=== Section D135: MENTOR mode + valid JSON — end-to-end parse via urlopen mock ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # Mock at the provider/HTTP level: let the real call_knowledge_explorer parse
    # the response — this exercises the actual JSON parsing path, not a stub.
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_answer") as mock_direct:
            with _mock.patch("urllib.request.urlopen",
                             return_value=_gemini_resp(_VALID_EXPLORER_JSON)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "my vocal sounds dull what should I do"},
                )
                h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    # call_knowledge_answer must NOT be called for MENTOR mode
    if mock_direct.call_count != 0:
        errors.append(
            f"call_knowledge_answer called {mock_direct.call_count}× on MENTOR mode — "
            "must not be called when explorer handles it"
        )

    if d is None:
        errors.append("no response data")
        for e in errors: print(f"  {FAIL} [D135] {e}")
        print("  D135: FAIL"); return False

    if d.get("type") != "answer":
        errors.append(f"type={d.get('type')!r}, expected 'answer'")
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("mode") != "MENTOR":
        errors.append(f"mode={d.get('mode')!r}, expected 'MENTOR'")

    # Text must be the extracted natural answer — not the raw JSON wrapper
    text = d.get("text", "")
    if text != _VALID_EXPLORER_ANSWER:
        errors.append(f"text={str(text)[:80]!r}, expected extracted answer")
    if text.strip().startswith("{"):
        errors.append("text starts with '{' — raw JSON wrapper exposed to user")
    for marker in _INTERNAL_MARKERS:
        if marker in text:
            errors.append(f"text contains internal marker {marker!r}")

    # Explorer key must be present and contain properly shaped candidates
    if "explorer" not in d:
        errors.append("'explorer' key missing from MENTOR response")
    else:
        explorer = d["explorer"]
        candidates = explorer.get("candidates", [])
        if len(candidates) < 1:
            errors.append(f"explorer.candidates has {len(candidates)} items, expected ≥1")
        _REQUIRED = ("direction", "rationale", "session_facts_used",
                     "assumptions", "source_hints", "actionable", "confidence")
        for i, cand in enumerate(candidates):
            for field in _REQUIRED:
                if field not in cand:
                    errors.append(f"candidates[{i}] missing field {field!r}")
            if "actionable" in cand and not isinstance(cand["actionable"], bool):
                errors.append(f"candidates[{i}].actionable is not bool")
            if "session_facts_used" in cand and not isinstance(cand["session_facts_used"], list):
                errors.append(f"candidates[{i}].session_facts_used is not list")

    if errors:
        for e in errors: print(f"  {FAIL} [D135] {e}")
        print("  D135: FAIL"); return False

    print(f"  {PASS} [D135] MENTOR + valid JSON: answer extracted, candidates shaped, "
          "no raw JSON in text, call_knowledge_answer not called")
    print("  D135: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D136 — Explorer output contains candidate directions with all required fields
# ══════════════════════════════════════════════════════════════════════════════

@section("D136")
def run_d136():
    print("=== Section D136: FREEFORM_GENERAL routing → explorer path via urlopen mock ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Part A: FREEFORM_GENERAL routes through explorer ─────────────────────
    freeform_answer = "A wide pad usually comes from chorus depth and stereo spread on the synth."
    freeform_explorer_json = json.dumps({
        "answer": freeform_answer,
        "question_type": "creative",
        "candidates": [
            {
                "direction": "Add chorus / ensemble on the pad",
                "rationale": "Chorus adds detuning and stereo spread without pitch shift",
                "session_facts_used": [],
                "assumptions": ["No live session context available for this question"],
                "source_hints": ["chorus depth", "stereo imager"],
                "actionable": True,
                "confidence": 0.80,
            },
        ],
    })

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_freeform_general_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_answer") as mock_direct:
            with _mock.patch("urllib.request.urlopen",
                             return_value=_gemini_resp(freeform_explorer_json)):
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "how do I make my pad wider"},
                )
                h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"[A] HTTP {h._cap_code}, expected 200")

    if mock_direct.call_count != 0:
        errors.append(
            f"[A] call_knowledge_answer called {mock_direct.call_count}× on FREEFORM_GENERAL — "
            "must route through explorer, not direct path"
        )

    if d is None:
        errors.append("[A] no response data")
        for e in errors: print(f"  {FAIL} [D136] {e}")
        print("  D136: FAIL"); return False

    if d.get("type") != "answer":
        errors.append(f"[A] type={d.get('type')!r}, expected 'answer'")
    if d.get("ok") is not True:
        errors.append(f"[A] ok={d.get('ok')!r}, expected True")
    if d.get("mode") != "FREEFORM_GENERAL":
        errors.append(f"[A] mode={d.get('mode')!r}, expected 'FREEFORM_GENERAL'")
    if "explorer" not in d:
        errors.append("[A] 'explorer' key missing from FREEFORM_GENERAL response")
    if d.get("text") != freeform_answer:
        errors.append(f"[A] text={str(d.get('text'))[:80]!r}, expected freeform answer")

    # ── Part B: verify _EXPLORER_MODES constant contains FREEFORM_GENERAL ─────
    src = inspect.getsource(hs_mod)
    if "FREEFORM_GENERAL" not in src:
        errors.append("[B] 'FREEFORM_GENERAL' not found in harness_server source")
    if '"FREEFORM"' in src and '"FREEFORM_GENERAL"' not in src:
        errors.append("[B] source still uses synthetic 'FREEFORM' mode — must be 'FREEFORM_GENERAL'")
    # Ensure the _EXPLORER_MODES set contains FREEFORM_GENERAL
    if "FREEFORM_GENERAL" not in getattr(hs_mod, "_EXPLORER_MODES", set()):
        errors.append(
            f"[B] _EXPLORER_MODES={getattr(hs_mod, '_EXPLORER_MODES', None)!r} — "
            "must contain 'FREEFORM_GENERAL'"
        )

    if errors:
        for e in errors: print(f"  {FAIL} [D136] {e}")
        print("  D136: FAIL"); return False

    print(f"  {PASS} [D136] FREEFORM_GENERAL routes through explorer; "
          "answer extracted; call_knowledge_answer not called; "
          "_EXPLORER_MODES contains FREEFORM_GENERAL")
    print("  D136: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D137 — User-facing text is natural language, not raw JSON / candidate structure
# ══════════════════════════════════════════════════════════════════════════════

def _check_no_internal_exposure(text, label, errors):
    """
    Shared guard: assert text does not expose internal JSON / candidate structure.

    Uses _STRUCTURAL_RE_TEST (case-insensitive word-boundary regex) so it catches
    markers whether quoted, unquoted, YAML-style, mixed-case, or markdown-fenced.
    """
    if not text or not text.strip():
        errors.append(f"{label}: text is empty or blank")
        return
    stripped = text.strip()
    if stripped.startswith("{"):
        errors.append(f"{label}: text starts with '{{' — raw JSON exposed to user")
    if stripped.startswith("```"):
        errors.append(f"{label}: text starts with '```' — raw fenced content exposed to user")
    m = _STRUCTURAL_RE_TEST.search(text)
    if m:
        errors.append(
            f"{label}: text contains internal schema marker {m.group()!r} "
            "(case-insensitive word-boundary — no raw schema in user-facing text)"
        )
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict) and ("candidates" in parsed or "answer" in parsed):
            errors.append(
                f"{label}: text parses as JSON with internal keys — "
                "explorer structure exposed to user"
            )
    except (json.JSONDecodeError, TypeError):
        pass  # Good — not valid JSON


@section("D137")
def run_d137():
    print("=== Section D137: malformed / partial JSON hardening ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    # ── Sub-case A: truncated JSON that contains candidate keys ───────────────
    # The LLM response is cut off mid-stream — json.loads fails.
    # Since the truncated text contains '"candidates"', it looks structural.
    # Expected: safe fallback string, no raw JSON fragment.
    truncated = '{"answer": "", "question_type": "session", "candidates": [{"direction": "Cut EQ'

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(truncated)):
            ha = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            ha.do_POST()

    if ha._cap_code != 200:
        errors.append(f"[A] HTTP {ha._cap_code}, expected 200 on truncated JSON")
    da = ha._cap_data or {}
    if da.get("ok") is not True:
        errors.append(f"[A] ok={da.get('ok')!r}, expected True")
    _check_no_internal_exposure(da.get("text", ""), "[A] truncated JSON", errors)

    # ── Sub-case B: valid JSON but "answer" key is absent ─────────────────────
    # LOM responses are valid but LLM forgot to include the "answer" field.
    # Expected: safe fallback, not an empty string or raw JSON dump.
    no_answer_json = json.dumps({
        "question_type": "session",
        "candidates": [
            {
                "direction": "Cut low-mid buildup",
                "rationale": "Dullness traces to 200-400 Hz",
                "session_facts_used": [],
                "assumptions": [],
                "source_hints": ["EQ"],
                "actionable": True,
                "confidence": 0.8,
            }
        ],
    })

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(no_answer_json)):
            hb = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            hb.do_POST()

    if hb._cap_code != 200:
        errors.append(f"[B] HTTP {hb._cap_code}, expected 200 when 'answer' absent")
    db = hb._cap_data or {}
    if db.get("ok") is not True:
        errors.append(f"[B] ok={db.get('ok')!r}, expected True")
    text_b = db.get("text", "")
    _check_no_internal_exposure(text_b, "[B] missing answer", errors)
    if not text_b or not text_b.strip():
        errors.append("[B] text is empty — must return fallback string when answer key absent")

    # ── Sub-case C: valid JSON with whitespace-only "answer" value ────────────
    # LLM put "answer" key but filled it with whitespace.
    # Expected: same fallback, not an empty/blank user-facing text.
    blank_answer_json = json.dumps({
        "answer": "   \n  ",
        "question_type": "session",
        "candidates": [
            {
                "direction": "Check masking",
                "rationale": "Kick might be masking the vocal",
                "session_facts_used": ["Kick track present"],
                "assumptions": [],
                "source_hints": ["spectrum"],
                "actionable": True,
                "confidence": 0.6,
            }
        ],
    })

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(blank_answer_json)):
            hc = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            hc.do_POST()

    if hc._cap_code != 200:
        errors.append(f"[C] HTTP {hc._cap_code}, expected 200 when answer is blank")
    dc = hc._cap_data or {}
    if dc.get("ok") is not True:
        errors.append(f"[C] ok={dc.get('ok')!r}, expected True")
    text_c = dc.get("text", "")
    if not text_c or not text_c.strip():
        errors.append("[C] text is blank — must return fallback string when answer is whitespace")
    _check_no_internal_exposure(text_c, "[C] blank answer", errors)

    # ── Sub-case D: YAML-style non-JSON with unquoted markers ─────────────────
    # LLM returns YAML-like key:value text — json.loads fails.
    # Internal markers appear unquoted at word boundaries: candidates:, direction:.
    # _STRUCTURAL_RE must detect these via (?i)\b word-boundary matching.
    # Expected: safe fallback string, no raw YAML fragment in user-facing text.
    yaml_like = (
        "candidates: cut low-mid on lead vocals\n"
        "direction: apply EQ around 300Hz\n"
        "rationale: dullness from 200-400Hz buildup"
    )

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(yaml_like)):
            hd = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            hd.do_POST()

    if hd._cap_code != 200:
        errors.append(f"[D] HTTP {hd._cap_code}, expected 200 on YAML-style non-JSON")
    dd = hd._cap_data or {}
    if dd.get("ok") is not True:
        errors.append(f"[D] ok={dd.get('ok')!r}, expected True")
    _check_no_internal_exposure(dd.get("text", ""), "[D] YAML-style non-JSON", errors)

    # ── Sub-case E: markdown-fenced partial schema ─────────────────────────────
    # LLM wraps a truncated JSON schema in a markdown code fence — json.loads fails.
    # raw_stripped.startswith("```") must be True → _looks_structural = True.
    # Also contains internal markers inside the fence as a second line of defence.
    # Expected: safe fallback string, no raw fenced content in user-facing text.
    fenced = (
        "```json\n"
        '{"candidates": [{"direction": "cut EQ around 300Hz",\n'
        '  "rationale": "low-mid buildup causes dullness"'
    )

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(fenced)):
            he = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            he.do_POST()

    if he._cap_code != 200:
        errors.append(f"[E] HTTP {he._cap_code}, expected 200 on fenced partial schema")
    de = he._cap_data or {}
    if de.get("ok") is not True:
        errors.append(f"[E] ok={de.get('ok')!r}, expected True")
    _check_no_internal_exposure(de.get("text", ""), "[E] fenced partial schema", errors)

    # ── Sub-case F: mixed-case internal markers ────────────────────────────────
    # LLM returns plain text with schema keys in various capitalizations — json.loads fails.
    # _STRUCTURAL_RE uses (?i) flag → must catch CANDIDATES:, Direction:, Rationale:.
    # Expected: safe fallback string, no raw schema text in user-facing text.
    mixed_case = (
        "CANDIDATES: reduce low-mid on the vocal\n"
        "Direction: use EQ around 300Hz\n"
        "Rationale: vocal sounds dull due to 200-400Hz buildup\n"
        "Session_Facts_Used: Lead Vocals selected"
    )

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("urllib.request.urlopen",
                         return_value=_gemini_resp(mixed_case)):
            hf = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            hf.do_POST()

    if hf._cap_code != 200:
        errors.append(f"[F] HTTP {hf._cap_code}, expected 200 on mixed-case markers")
    df = hf._cap_data or {}
    if df.get("ok") is not True:
        errors.append(f"[F] ok={df.get('ok')!r}, expected True")
    _check_no_internal_exposure(df.get("text", ""), "[F] mixed-case markers", errors)

    if errors:
        for e in errors: print(f"  {FAIL} [D137] {e}")
        print("  D137: FAIL"); return False

    print(f"  {PASS} [D137] malformed JSON hardening: "
          "[A] truncated+candidate-keys → fallback; "
          "[B] missing answer → fallback; "
          "[C] blank answer → fallback; "
          "[D] YAML-style unquoted markers → fallback; "
          "[E] fenced partial schema → fallback; "
          "[F] mixed-case markers → fallback; "
          "all: no internal schema markers in user-facing text")
    print("  D137: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D138 — Session facts used when session state available
# ══════════════════════════════════════════════════════════════════════════════

@section("D138")
def run_d138():
    print("=== Section D138: session facts used when state available ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    explorer_call_args = {}

    def _capture_explorer(enriched_text, session_available, system_prompt_str,
                          provider, model, api_key, base_url=None):
        explorer_call_args["enriched_text"] = enriched_text
        explorer_call_args["session_available"] = session_available
        return (_CANNED_EXPLORER_ANSWER, _CANNED_EXPLORER_DATA, _CANNED_EXPLORER_TOKENS)

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         side_effect=_capture_explorer):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            h.do_POST()

    d = h._cap_data
    if d is None:
        errors.append("no response data")

    # session_available must be True because _make_bridge returns ok=True state
    if not explorer_call_args.get("session_available"):
        errors.append(
            f"session_available passed to explorer = "
            f"{explorer_call_args.get('session_available')!r}, "
            "expected True when /session/state returned ok=True"
        )

    # enriched_text must contain session context (formatted state block)
    enriched = explorer_call_args.get("enriched_text", "")
    if "Lead Vocals" not in enriched and "Kick" not in enriched:
        errors.append(
            "enriched_text passed to explorer does not contain track names from session state — "
            "session context is not being passed through"
        )
    if "120" not in enriched:
        errors.append(
            "enriched_text does not contain tempo (120) from session state"
        )

    if errors:
        for e in errors: print(f"  {FAIL} [D138] {e}")
        print("  D138: FAIL"); return False

    print(f"  {PASS} [D138] session_available=True; enriched_text contains track names + tempo")
    print("  D138: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D139 — Missing session state handled honestly
# ══════════════════════════════════════════════════════════════════════════════

@section("D139")
def run_d139():
    print("=== Section D139: missing session state handled honestly ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    explorer_call_args = {}

    def _capture_explorer(enriched_text, session_available, system_prompt_str,
                          provider, model, api_key, base_url=None):
        explorer_call_args["session_available"] = session_available
        explorer_call_args["enriched_text"]     = enriched_text
        return (_CANNED_EXPLORER_ANSWER, _CANNED_EXPLORER_DATA, _CANNED_EXPLORER_TOKENS)

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge_no_state(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         side_effect=_capture_explorer):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "my vocal sounds dull"},
            )
            h.do_POST()

    d = h._cap_data

    # Must still return 200
    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200 despite missing state")
    if d and d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")

    # session_available must be False
    if explorer_call_args.get("session_available") is not False:
        errors.append(
            f"session_available={explorer_call_args.get('session_available')!r}, "
            "expected False when /session/state call failed"
        )

    # Enriched text must NOT contain Ableton session block
    enriched = explorer_call_args.get("enriched_text", "")
    if "## LIVE ABLETON SESSION" in enriched:
        errors.append(
            "enriched_text contains '## LIVE ABLETON SESSION' even though "
            "state call failed — stale session block injected"
        )

    if errors:
        for e in errors: print(f"  {FAIL} [D139] {e}")
        print("  D139: FAIL"); return False

    print(f"  {PASS} [D139] missing state → 200 OK, session_available=False, "
          "no stale session block in enriched text")
    print("  D139: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D140 — READ mode → direct answer path (explorer NOT called)
# ══════════════════════════════════════════════════════════════════════════════

@section("D140")
def run_d140():
    print("=== Section D140: READ mode → direct answer; explorer not called ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_read_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer") as mock_explorer:
            with _mock.patch("tools.harness_server.call_knowledge_answer",
                             return_value=(_CANNED_DIRECT_ANSWER, _CANNED_DIRECT_TOKENS)) \
                    as mock_direct:
                h = _make_mock_handler(
                    hs_mod.HarnessHandler,
                    path="/harness/orchestrate",
                    body={"text": "what is a compression ratio"},
                )
                h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if mock_explorer.call_count != 0:
        errors.append(
            f"call_knowledge_explorer called {mock_explorer.call_count}× on READ mode — "
            "explorer must not run for direct factual questions"
        )
    if mock_direct.call_count != 1:
        errors.append(
            f"call_knowledge_answer called {mock_direct.call_count}×, expected 1 for READ mode"
        )

    if d is None:
        errors.append("no response data")
        for e in errors: print(f"  {FAIL} [D140] {e}")
        print("  D140: FAIL"); return False

    if d.get("type") != "answer":
        errors.append(f"type={d.get('type')!r}, expected 'answer'")
    if d.get("text") != _CANNED_DIRECT_ANSWER:
        errors.append(
            f"text={str(d.get('text'))[:80]!r}, expected canned direct answer"
        )
    # 'explorer' key must be absent on direct path
    if "explorer" in d:
        errors.append(
            "'explorer' key present in READ-mode response — "
            "internal explorer data must only appear on MENTOR/FREEFORM responses"
        )

    if errors:
        for e in errors: print(f"  {FAIL} [D140] {e}")
        print("  D140: FAIL"); return False

    print(f"  {PASS} [D140] READ mode → direct answer, explorer not called, "
          "no 'explorer' key in response")
    print("  D140: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D141 — Write/action still returns type:"action" — explorer never reached
# ══════════════════════════════════════════════════════════════════════════════

@section("D141")
def run_d141():
    print("=== Section D141: write mode still returns type:\"action\" ===")

    hs_mod = importlib.import_module("tools.harness_server")
    errors = []

    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_write_safe_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer") as mock_explorer:
            with _mock.patch("tools.harness_server.call_knowledge_answer") as mock_direct:
                with _mock.patch("tools.harness_server.call_gemini",
                                 return_value=(_CANNED_ACTION_PARSED, _CANNED_ACTION_TOKENS)):
                    h = _make_mock_handler(
                        hs_mod.HarnessHandler,
                        path="/harness/orchestrate",
                        body={"text": "mute the kick"},
                    )
                    h.do_POST()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if mock_explorer.call_count != 0:
        errors.append(
            f"call_knowledge_explorer called {mock_explorer.call_count}× on WRITE mode — "
            "explorer must never run on action paths"
        )
    if mock_direct.call_count != 0:
        errors.append(
            f"call_knowledge_answer called {mock_direct.call_count}× on WRITE mode"
        )

    if d is None:
        errors.append("no response data")
        for e in errors: print(f"  {FAIL} [D141] {e}")
        print("  D141: FAIL"); return False

    if d.get("type") != "action":
        errors.append(f"type={d.get('type')!r}, expected 'action'")
    if d.get("action_id") != "mute":
        errors.append(f"action_id={d.get('action_id')!r}, expected 'mute'")
    if "explorer" in d:
        errors.append("'explorer' key must not appear on type:action responses")

    if errors:
        for e in errors: print(f"  {FAIL} [D141] {e}")
        print("  D141: FAIL"); return False

    print(f"  {PASS} [D141] WRITE mode → type:action; explorer not called; 'explorer' key absent")
    print("  D141: PASS"); return True


# ══════════════════════════════════════════════════════════════════════════════
# D142 — Slice 12 regression: MENTOR→answer, WRITE→action, static symbols present
# ══════════════════════════════════════════════════════════════════════════════

@section("D142")
def run_d142():
    print("=== Section D142: Slice 12 regression — orchestrate routing intact ===")

    hs_mod = importlib.import_module("tools.harness_server")
    src = inspect.getsource(hs_mod)
    errors = []

    # ── Part A: static symbols ───────────────────────────────────────────────
    required_symbols = [
        ("/harness/orchestrate",    "/harness/orchestrate defined"),
        ("_handle_orchestrate",     "_handle_orchestrate defined"),
        ("/harness/parse_intent",   "/harness/parse_intent intact"),
        ("_handle_parse_intent",    "_handle_parse_intent intact"),
        ("INTERN_WRITE_SAFE",       "WRITE mode routing present"),
        ("INTERN_WRITE_RISKY",      "WRITE mode routing present"),
        ("_EXPLORER_MODES",         "_EXPLORER_MODES constant defined"),
        ("call_knowledge_explorer", "call_knowledge_explorer function defined"),
        ("call_knowledge_answer",   "call_knowledge_answer function defined"),
        ("_call_bridge_get",        "_call_bridge_get defined"),
        ('"answer"',                'type:"answer" produced'),
        ('"action"',                'type:"action" produced'),
        ("explorer",                "'explorer' key in response"),
    ]
    for symbol, label in required_symbols:
        if symbol not in src:
            errors.append(f"[static] {label}: {symbol!r} not found in harness_server source")

    # ── Part B: MENTOR mode still routes to answer ────────────────────────────
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_mentor_pack)):
        with _mock.patch("tools.harness_server.call_knowledge_explorer",
                         return_value=(_CANNED_EXPLORER_ANSWER, _CANNED_EXPLORER_DATA,
                                       _CANNED_EXPLORER_TOKENS)):
            h = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "what should I do with my mix"},
            )
            h.do_POST()

    if h._cap_code != 200:
        errors.append(f"[B] HTTP {h._cap_code}, expected 200")
    if h._cap_data and h._cap_data.get("type") != "answer":
        errors.append(f"[B] type={h._cap_data.get('type')!r}, expected 'answer'")

    # ── Part C: WRITE mode still routes to action ─────────────────────────────
    with _mock.patch("tools.harness_server._call_bridge_get",
                     side_effect=_make_bridge(_write_safe_pack)):
        with _mock.patch("tools.harness_server.call_gemini",
                         return_value=(_CANNED_ACTION_PARSED, _CANNED_ACTION_TOKENS)):
            h2 = _make_mock_handler(
                hs_mod.HarnessHandler,
                path="/harness/orchestrate",
                body={"text": "mute the kick"},
            )
            h2.do_POST()

    if h2._cap_code != 200:
        errors.append(f"[C] HTTP {h2._cap_code}, expected 200")
    if h2._cap_data and h2._cap_data.get("type") != "action":
        errors.append(f"[C] type={h2._cap_data.get('type')!r}, expected 'action'")

    if errors:
        for e in errors: print(f"  {FAIL} [D142] {e}")
        print("  D142: FAIL"); return False

    print(f"  {PASS} [D142] Slice 12 regression: all symbols present, "
          "MENTOR→answer, WRITE→action")
    print("  D142: PASS"); return True


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
    print(f"Phase D Slice 14 — Knowledge Explorer v1: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
