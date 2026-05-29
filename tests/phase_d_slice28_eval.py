#!/usr/bin/env python3
"""
phase_d_slice28_eval.py — Build 21: Taste Context Injection v1
Tests D282–D297.

All checks are static source analysis + unit-level functional tests.
No browser runtime, no live ChromaDB writes, no live bridge calls.
LLM calls are not exercised — only module-level functions are tested directly.
"""

import importlib
import importlib.util
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)

# Ensure rag/ and tools/ are importable
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

_TASTE_MODULE_PATH   = os.path.join(_ROOT, "rag", "taste_context.py")
_HARNESS_MODULE_PATH = os.path.join(_ROOT, "tools", "harness_server.py")

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(id_, desc, ok, detail=""):
    status = PASS if ok else FAIL
    results.append((id_, status, desc, detail))
    suffix = f"\n         → {detail}" if (not ok and detail) else ""
    print(f"  [{status}] {id_}: {desc}{suffix}")
    return ok


def read_src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_taste_module():
    spec = importlib.util.spec_from_file_location("taste_context", _TASTE_MODULE_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_signal(
    scope="session_only",
    feedback_type="KEEP",
    suggested_level=1,
    project_id="proj_abc123",
    session_id="sess_001",
    evidence="Heavy sidechain on kick worked well",
    message="",
    action_type="compress",
    target="kick",
    candidate_id="cand_001",
):
    return {
        "candidate_id":   candidate_id,
        "scope":          scope,
        "feedback_type":  feedback_type,
        "suggested_level": suggested_level,
        "project_id":     project_id,
        "session_id":     session_id,
        "evidence":       evidence,
        "message":        message,
        "action_type":    action_type,
        "target":         target,
    }


def make_reflection(accepted, do_not_promote=None):
    return {
        "accepted_signals": accepted,
        "do_not_promote":   do_not_promote or [],
    }


# ── D282: module importable, constants present ───────────────────────────────

def run_d282():
    print("=== Section D282: taste_context.py — importable, constants ===")
    errors = []
    try:
        tc = load_taste_module()

        if not callable(getattr(tc, "build_taste_context", None)):
            errors.append("build_taste_context not callable")

        header = getattr(tc, "TASTE_HEADER", None)
        if not header:
            errors.append("TASTE_HEADER constant missing")
        elif not isinstance(header, str) or not header.startswith("##"):
            errors.append(f"TASTE_HEADER has unexpected format: {header!r}")

        level_cap = getattr(tc, "_LEVEL_CAP", None)
        if level_cap != 2:
            errors.append(f"_LEVEL_CAP should be 2, got {level_cap!r}")

        max_signals = getattr(tc, "_MAX_SIGNALS", None)
        if not isinstance(max_signals, int) or max_signals < 1:
            errors.append(f"_MAX_SIGNALS invalid: {max_signals!r}")

        check("D282a", "build_taste_context importable and callable",
              callable(getattr(tc, "build_taste_context", None)))
        check("D282b", "TASTE_HEADER constant present and starts with ##",
              bool(header and isinstance(header, str) and header.startswith("##")))
        check("D282c", "_LEVEL_CAP == 2 and _MAX_SIGNALS >= 1",
              level_cap == 2 and isinstance(max_signals, int) and max_signals >= 1)

    except Exception as exc:
        check("D282a", "import + constants", False, str(exc))


# ── D283: no signals → returns "" ────────────────────────────────────────────

def run_d283():
    print("=== Section D283: no signals → '' ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # Missing file
        result_missing = fn(reflection_path="/nonexistent/path.jsonl")
        check("D283a", "missing reflection file → ''",
              result_missing == "")

        # Empty dict
        result_empty = fn(reflection={})
        check("D283b", "empty reflection dict → ''",
              result_empty == "")

        # Empty accepted_signals list
        result_no_accepted = fn(reflection=make_reflection([]))
        check("D283c", "empty accepted_signals → ''",
              result_no_accepted == "")

    except Exception as exc:
        check("D283a", "no-signals tests", False, str(exc))


# ── D284: scope filtering ─────────────────────────────────────────────────────

def run_d284():
    print("=== Section D284: scope filtering ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # session_only included
        r = fn(reflection=make_reflection([make_signal(scope="session_only")]))
        check("D284a", "session_only scope included",
              bool(r))

        # session_project included (both project_ids non-empty and matching)
        r = fn(
            reflection=make_reflection([make_signal(scope="session_project", project_id="proj_abc123")]),
            project_id="proj_abc123",
        )
        check("D284b", "session_project scope included (matching project_ids)",
              bool(r))

        # global_taste excluded
        r = fn(reflection=make_reflection([make_signal(scope="global_taste")]))
        check("D284c", "global_taste scope excluded → ''",
              r == "")

        # unknown scope excluded
        r = fn(reflection=make_reflection([make_signal(scope="unknown_scope")]))
        check("D284d", "unknown scope excluded → ''",
              r == "")

    except Exception as exc:
        check("D284a", "scope filtering tests", False, str(exc))


# ── D285: level filtering ─────────────────────────────────────────────────────

def run_d285():
    print("=== Section D285: level filtering ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # Level 1 included
        r = fn(reflection=make_reflection([make_signal(suggested_level=1)]))
        check("D285a", "Level 1 signal included",
              bool(r))

        # Level 2 included
        r = fn(reflection=make_reflection([make_signal(suggested_level=2)]))
        check("D285b", "Level 2 signal included",
              bool(r))

        # Level 3 excluded
        r = fn(reflection=make_reflection([make_signal(suggested_level=3)]))
        check("D285c", "Level 3 signal excluded → ''",
              r == "")

        # Level 4 excluded
        r = fn(reflection=make_reflection([make_signal(suggested_level=4)]))
        check("D285d", "Level 4 signal excluded → ''",
              r == "")

    except Exception as exc:
        check("D285a", "level filtering tests", False, str(exc))


# ── D286: negative feedback type filtering ────────────────────────────────────

def run_d286():
    print("=== Section D286: negative feedback filtering ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        negative_types = ["UNDO", "WRONG_DIRECTION", "NOT_HELPFUL", "WRONG", "OUTDATED"]
        for ftype in negative_types:
            r = fn(reflection=make_reflection([make_signal(feedback_type=ftype)]))
            label = f"D286-{ftype}"
            check(label, f"feedback_type={ftype} excluded → ''",
                  r == "")

    except Exception as exc:
        check("D286-UNDO", "negative feedback tests", False, str(exc))


# ── D287: project_id filtering ────────────────────────────────────────────────

def run_d287():
    print("=== Section D287: project_id filtering ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # session_project with matching project_id → included
        r = fn(
            reflection=make_reflection([make_signal(scope="session_project", project_id="abc")]),
            project_id="abc",
        )
        check("D287a", "session_project with matching project_id → included",
              bool(r))

        # session_project with non-matching project_id → excluded
        r = fn(
            reflection=make_reflection([make_signal(scope="session_project", project_id="abc")]),
            project_id="xyz",
        )
        check("D287b", "session_project with non-matching project_id → excluded",
              r == "")

        # session_only always included regardless of project_id
        r = fn(
            reflection=make_reflection([make_signal(scope="session_only", project_id="abc")]),
            project_id="xyz",
        )
        check("D287c", "session_only always included regardless of project_id",
              bool(r))

        # session_project when caller has no project_id → excluded (Gate 4 strict)
        r = fn(
            reflection=make_reflection([make_signal(scope="session_project", project_id="abc")]),
            project_id=None,
        )
        check("D287d", "session_project when caller has no project_id → excluded",
              r == "")

        # session_project with empty signal project_id → excluded even if caller has one
        r = fn(
            reflection=make_reflection([make_signal(scope="session_project", project_id="")]),
            project_id="abc",
        )
        check("D287e", "session_project with empty signal project_id → excluded",
              r == "")

    except Exception as exc:
        check("D287a", "project_id filtering tests", False, str(exc))


# ── D288: output format safety ────────────────────────────────────────────────

def run_d288():
    print("=== Section D288: output format safety ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # Block with one safe signal
        r = fn(reflection=make_reflection([make_signal(
            evidence="Velocity layering on strings was effective",
            scope="session_only",
            suggested_level=1,
        )]))

        check("D288a", "non-empty result starts with TASTE_HEADER",
              r.startswith(tc.TASTE_HEADER))

        # No hex memory IDs (16+ char hex strings that look like candidate_ids)
        hex_pattern = re.compile(r"\b[0-9a-f]{12,}\b")
        check("D288b", "no hex memory IDs in output",
              not hex_pattern.search(r))

        # No collection names
        bad_terms = ["producer_memory_index", "project_session_index",
                     "plugin_operator_index", "failure_cases_index", "audio_analysis_index"]
        check("D288c", "no collection names in output",
              not any(term in r for term in bad_terms))

        # No score/confidence float patterns (e.g. 0.857, score: 0.9)
        score_pattern = re.compile(r"\bscore\s*[:=]\s*[\d.]+|\bconfidence\s*[:=]\s*[\d.]+")
        check("D288d", "no score/confidence labels in output",
              not score_pattern.search(r))

        # _MAX_SIGNALS cap
        many_signals = [make_signal(evidence=f"Signal {i}", candidate_id=f"cand_{i:03d}")
                        for i in range(20)]
        r_many = fn(reflection=make_reflection(many_signals))
        bullet_count = r_many.count("\n-")
        check("D288e", f"output capped at _MAX_SIGNALS ({tc._MAX_SIGNALS}) bullets",
              bullet_count <= tc._MAX_SIGNALS)

        # _MAX_CHARS cap
        long_evidence = "X" * 200
        long_signals = [make_signal(evidence=long_evidence, candidate_id=f"c{i}")
                        for i in range(10)]
        r_long = fn(reflection=make_reflection(long_signals))
        check("D288f", f"output capped at _MAX_CHARS ({tc._MAX_CHARS})",
              len(r_long) <= tc._MAX_CHARS)

    except Exception as exc:
        check("D288a", "output format tests", False, str(exc))


# ── D289: empty result is "" not TASTE_HEADER ─────────────────────────────────

def run_d289():
    print("=== Section D289: empty result is strictly '' ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # All signals at Level 3 → nothing passes → strict ""
        r = fn(reflection=make_reflection([
            make_signal(suggested_level=3),
            make_signal(scope="global_taste"),
        ]))
        check("D289a", "all-filtered signals → strictly '' (not just header alone)",
              r == "")

        # Single signal with empty evidence AND empty message AND empty action_type → ""
        empty_signal = make_signal(evidence="", message="", action_type="", target="",
                                   scope="session_only", suggested_level=1)
        r2 = fn(reflection=make_reflection([empty_signal]))
        check("D289b", "signal with no textual content → ''",
              r2 == "")

    except Exception as exc:
        check("D289a", "empty result tests", False, str(exc))


# ── D290: harness_server wiring ───────────────────────────────────────────────

def run_d290():
    print("=== Section D290: harness_server — taste_context wiring ===")
    try:
        hs = importlib.import_module("tools.harness_server")

        # _build_critic_prompt accepts taste_context kwarg
        import inspect
        sig = inspect.signature(hs._build_critic_prompt)
        check("D290a", "_build_critic_prompt has taste_context param",
              "taste_context" in sig.parameters)

        # Critic prompt includes taste_context when non-empty
        taste_block = "## Taste Context\n- Heavy sidechain on kick"
        prompt = hs._build_critic_prompt(
            candidates=[],
            question_text="How should I mix the kick?",
            session_context="",
            taste_context=taste_block,
        )
        check("D290b", "taste_context appears in critic prompt when non-empty",
              "Taste Context" in prompt)

        # Empty taste_context → no Taste Context in critic prompt
        prompt_empty = hs._build_critic_prompt(
            candidates=[],
            question_text="test",
            session_context="",
            taste_context="",
        )
        check("D290c", "empty taste_context → no Taste Context in critic prompt",
              "Taste Context" not in prompt_empty)

        # call_creative_critic accepts taste_context kwarg
        sig_cc = inspect.signature(hs.call_creative_critic)
        check("D290d", "call_creative_critic has taste_context param",
              "taste_context" in sig_cc.parameters)

        # _TRUST_LABEL_RE matches "Taste Context"
        trust_re = getattr(hs, "_TRUST_LABEL_RE", None)
        check("D290e", "_TRUST_LABEL_RE matches 'Taste Context'",
              bool(trust_re and trust_re.search("## Taste Context")))

        # _TRUST_LABEL_RE matches lowercase variant
        check("D290f", "_TRUST_LABEL_RE matches 'taste context' (case-insensitive)",
              bool(trust_re and trust_re.search("taste context")))

    except Exception as exc:
        check("D290a", "harness_server wiring tests", False, str(exc))


# ── D291: _compose_final_answer taste label guard ─────────────────────────────

def run_d291():
    print("=== Section D291: _compose_final_answer rejects taste label contamination ===")
    try:
        hs = importlib.import_module("tools.harness_server")

        # Synthesise a critic-selected candidate whose direction echoes the taste label.
        # _compose_final_answer should fall back to explorer_answer (trust-label guard).
        explorer_data_with_taste = {
            "candidates": [
                {
                    "direction": "## Taste Context echoed from critic prompt",
                    "rationale": "Use sidechain compression",
                    "session_facts_used": [],
                    "assumptions": [],
                }
            ]
        }
        critic_data_valid = {"selected": 0, "kept": [0], "rejected": [], "reasons": {}}
        explorer_fallback = "Explorer fallback answer."

        result = hs._compose_final_answer(
            explorer_fallback,
            explorer_data_with_taste,
            critic_data_valid,
        )
        check("D291a", "_compose_final_answer falls back when direction echoes taste label",
              result == explorer_fallback)

        # Sanity: normal direction (no label) → composed normally
        explorer_data_clean = {
            "candidates": [
                {
                    "direction": "Use heavier sidechain",
                    "rationale": "Frees up low end in the mix",
                    "session_facts_used": [],
                    "assumptions": [],
                }
            ]
        }
        result_clean = hs._compose_final_answer(
            explorer_fallback,
            explorer_data_clean,
            critic_data_valid,
        )
        check("D291b", "normal direction without taste label → composed (not fallback)",
              result_clean != explorer_fallback)

    except Exception as exc:
        check("D291a", "_compose_final_answer tests", False, str(exc))


# ── D292: static analysis ─────────────────────────────────────────────────────

def run_d292():
    print("=== Section D292: static source analysis ===")
    taste_src   = read_src(_TASTE_MODULE_PATH)
    harness_src = read_src(_HARNESS_MODULE_PATH)

    # No direct chromadb client instantiation in taste_context.py
    check("D292a", "taste_context.py: no chromadb.Client / PersistentClient call",
          not re.search(r"chromadb\.(Persistent)?Client\s*\(", taste_src))

    # No circular import of memory_writer or session_reflection
    check("D292b", "taste_context.py: no import of memory_writer or session_reflection",
          not re.search(r"(from|import)\s+.*memory_writer", taste_src) and
          not re.search(r"(from|import)\s+.*session_reflection", taste_src))

    # No Level 3+ bypass in taste_context.py (LEVEL_CAP must be 2)
    check("D292c", "taste_context.py: _LEVEL_CAP is 2 (no bypass of level gate)",
          "_LEVEL_CAP   = 2" in taste_src or "_LEVEL_CAP = 2" in taste_src)

    # harness_server.py imports from rag.taste_context
    check("D292d", "harness_server.py: imports from rag.taste_context",
          "rag.taste_context" in harness_src)

    # harness_server.py: taste_context wired to call_creative_critic
    check("D292e", "harness_server.py: taste_context passed to call_creative_critic",
          "taste_context=taste_context" in harness_src)

    # harness_server.py: Taste Context added to _TRUST_LABEL_RE
    check("D292f", "harness_server.py: Taste.*Context in _TRUST_LABEL_RE definition",
          bool(re.search(r"Taste\\s\+Context", harness_src)))

    # harness_server.py: action execution path not changed
    # Verify write-mode branch still routes via call_gemini / call_openai (unchanged)
    check("D292g", "harness_server.py: write-mode action path intact",
          "_WRITE_MODES" in harness_src and "call_gemini" in harness_src)

    # taste_context.py: no writes to runtime log files
    check("D292h", "taste_context.py: no open(..., 'a') / 'w' log writes",
          not re.search(r"open\(.*[\"'](a|w)[\"']", taste_src))

    # taste_context.py: no never_do_rules reference
    check("D292i", "taste_context.py: no never_do_rules reference",
          "never_do_rules" not in taste_src)

    # harness_server.py: taste context call is AFTER _EXPLORER_MODES check (not in WRITE path)
    explorer_idx   = harness_src.find("if mode in _EXPLORER_MODES:")
    taste_call_idx = harness_src.find("_load_taste_context(", explorer_idx if explorer_idx > 0 else 0)
    write_modes_idx = harness_src.find("_WRITE_MODES = {")
    # taste call must come after both the EXPLORER_MODES check and the WRITE_MODES definition
    check("D292j", "harness_server.py: _load_taste_context() call is inside Explorer branch",
          explorer_idx > 0 and taste_call_idx > explorer_idx)


# ── D293: full-stack taste context flow — mock reflection, verify critic prompt ─

def run_d293():
    print("=== Section D293: full-stack flow — mock reflection → taste in critic prompt ===")
    try:
        tc = load_taste_module()
        hs = importlib.import_module("tools.harness_server")

        # Build a valid reflection and get taste block from taste_context.py
        reflection = make_reflection([
            make_signal(evidence="Velocity layering on strings effective",
                        scope="session_only", suggested_level=1),
            make_signal(evidence="Sidechain on kick improved clarity",
                        scope="session_only", suggested_level=2),
        ])
        taste_block = tc.build_taste_context(reflection=reflection)

        # Taste block should be non-empty
        check("D293a", "taste block built from session reflection is non-empty",
              bool(taste_block))

        # Inject into critic prompt
        prompt = hs._build_critic_prompt(
            candidates=[{"direction": "Try heavier sidechain", "rationale": "Cleans up low end",
                          "session_facts_used": [], "assumptions": []}],
            question_text="How should I mix the kick?",
            session_context="",
            taste_context=taste_block,
        )

        # Taste block content appears in the critic prompt
        check("D293b", "taste block content appears in critic prompt",
              "Velocity layering" in prompt or "Sidechain" in prompt)

        # Internal instruction present
        check("D293c", "critic prompt contains 'do not surface' instruction for taste block",
              "do not surface" in prompt.lower() or "do not expose" in prompt.lower())

        # Taste header is in the prompt (not stripped)
        check("D293d", "TASTE_HEADER appears in critic prompt",
              tc.TASTE_HEADER in prompt)

    except Exception as exc:
        check("D293a", "full-stack flow tests", False, str(exc))


# ── D295: adversarial internal-label text dropped from taste output ───────────

def run_d295():
    print("=== Section D295: adversarial text — internal labels dropped ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        # candidate_id in evidence → line dropped; action_type/target cleared → no fallback
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence="candidate_id: abc123efgh — sidechain worked",
            message="", action_type="", target="",
        )]))
        check("D295a", "evidence with 'candidate_id' label → line dropped → ''",
              r == "")

        # score label in evidence → dropped; no fallback
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence="score: 0.92 sidechain compress",
            message="", action_type="", target="",
        )]))
        check("D295b", "evidence with 'score: 0.X' → line dropped → ''",
              r == "")

        # collection name in evidence → dropped; no fallback
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence="from producer_memory_index: heavy sidechain on kick",
            message="", action_type="", target="",
        )]))
        check("D295c", "evidence with collection name → line dropped → ''",
              r == "")

        # JSON-looking evidence → dropped; no fallback
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence='{"action_type": "compress", "target": "kick"}',
            message="", action_type="", target="",
        )]))
        check("D295d", "evidence with JSON text → line dropped → ''",
              r == "")

        # proof_id in message → dropped (falls back to clean action_type+target)
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence="proof_id: abc — heavy compression worked",
            message="proof_id: abc — also in message",
            action_type="compress",
            target="kick",
        )]))
        check("D295e", "adversarial evidence+message → fallback to clean action_type+target",
              bool(r) and "compress" in r and "kick" in r)

        # Clean evidence → included normally (sanity check)
        r = fn(reflection=make_reflection([make_signal(
            scope="session_only", suggested_level=1,
            evidence="Velocity layering on strings sounded more natural",
            message="",
        )]))
        check("D295f", "clean evidence → included normally",
              bool(r) and "Velocity" in r)

    except Exception as exc:
        check("D295a", "adversarial text tests", False, str(exc))


# ── D296: expanded internal-label filtering (Codex fix) ──────────────────────

def run_d296():
    print("=== Section D296: expanded internal-label patterns ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        def _dropped(evidence):
            """Helper: signal with only this evidence (no fallback text)."""
            return fn(reflection=make_reflection([make_signal(
                scope="session_only", suggested_level=1,
                evidence=evidence, message="", action_type="", target="",
            )]))

        # action:SET_TRACK_VOLUME | target:track:Kick (schema pair style)
        check("D296a", "action:SET_TRACK_VOLUME | target:track:Kick → dropped",
              _dropped("action:SET_TRACK_VOLUME | target:track:Kick") == "")

        # space-separated ID labels
        check("D296b", "'proof id' label → dropped",
              _dropped("proof id: abc123 — compression used") == "")

        check("D296c", "'request id' label → dropped",
              _dropped("request id: xyz789") == "")

        check("D296d", "'action id' label → dropped",
              _dropped("action id: compress_kick") == "")

        check("D296e", "'candidate id' label → dropped",
              _dropped("candidate id: 9f3a1b2c") == "")

        # all-caps snake_case action enum
        check("D296f", "SET_TRACK_VOLUME all-caps enum → dropped",
              _dropped("SET_TRACK_VOLUME action applied to kick") == "")

        # schema field names
        check("D296g", "'source_type' schema field → dropped",
              _dropped("source_type: memory_promotion") == "")

        check("D296h", "'feedback_type' schema field → dropped",
              _dropped("feedback_type: KEEP") == "")

        check("D296i", "'memory_level' schema field → dropped",
              _dropped("memory_level: 2") == "")

        check("D296j", "'session_id' schema field → dropped",
              _dropped("session_id: sess_abc123") == "")

        check("D296k", "'project_id' schema field → dropped",
              _dropped("project_id: proj_xyz789") == "")

        # clean studio language must still pass
        check("D296l", "clean studio language → included normally",
              bool(_dropped("Heavy sidechain compression on kick cleared the low end")) and
              "sidechain" in _dropped("Heavy sidechain compression on kick cleared the low end"))

    except Exception as exc:
        check("D296a", "expanded internal-label tests", False, str(exc))


# ── D297: raw ID-looking token guard (Codex fix 3) ───────────────────────────

def run_d297():
    print("=== Section D297: raw ID-looking token guard ===")
    try:
        tc = load_taste_module()
        fn = tc.build_taste_context

        def _dropped(evidence):
            return fn(reflection=make_reflection([make_signal(
                scope="session_only", suggested_level=1,
                evidence=evidence, message="", action_type="", target="",
            )]))

        # long hex strings must be blocked
        check("D297a", "standalone long hex token abcdef1234567890 → dropped",
              _dropped("Heavy compression abcdef1234567890 worked") == "")

        # UUID format must be blocked
        check("D297b", "UUID 550e8400-e29b-41d4-a716-446655440000 → dropped",
              _dropped("Signal 550e8400-e29b-41d4-a716-446655440000 was promoted") == "")

        # musical numbers must NOT be blocked
        r_bpm = _dropped("Tempo at 120 BPM felt right for the groove")
        check("D297c", "120 BPM → passes (not blocked)",
              bool(r_bpm) and "120 BPM" in r_bpm)

        r_lufs = _dropped("-8 LUFS integrated loudness target")
        check("D297d", "-8 LUFS → passes (not blocked)",
              bool(r_lufs) and "LUFS" in r_lufs)

        r_db = _dropped("3 dB boost on presence shelf added clarity")
        check("D297e", "3 dB → passes (not blocked)",
              bool(r_db) and "3 dB" in r_db)

        r_808 = _dropped("808 bass needed low-pass filter at 200 Hz")
        check("D297f", "808 bass → passes (not blocked)",
              bool(r_808) and "808" in r_808)

    except Exception as exc:
        check("D297a", "raw ID-looking token guard tests", False, str(exc))


# ── D294: regression — py_compile passes for harness_server ──────────────────

def run_d294():
    print("=== Section D294: py_compile regression ===")
    import py_compile
    errors_hs = []
    errors_tc = []
    try:
        py_compile.compile(_HARNESS_MODULE_PATH, doraise=True)
    except py_compile.PyCompileError as exc:
        errors_hs.append(str(exc))
    try:
        py_compile.compile(_TASTE_MODULE_PATH, doraise=True)
    except py_compile.PyCompileError as exc:
        errors_tc.append(str(exc))

    check("D294a", "py_compile: tools/harness_server.py passes",
          not errors_hs, str(errors_hs))
    check("D294b", "py_compile: rag/taste_context.py passes",
          not errors_tc, str(errors_tc))


# ── runner ────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 60)
    print("  phase_d_slice28_eval.py — Build 21: Taste Context Injection v1")
    print("=" * 60)

    run_d282()
    run_d283()
    run_d284()
    run_d285()
    run_d286()
    run_d287()
    run_d288()
    run_d289()
    run_d290()
    run_d291()
    run_d292()
    run_d293()
    run_d294()
    run_d295()
    run_d296()
    run_d297()

    passed = sum(1 for _, s, _, _ in results if s == PASS)
    failed = sum(1 for _, s, _, _ in results if s == FAIL)
    total  = len(results)

    print()
    print("=" * 60)
    print(f"  TOTAL: {passed} PASS / {failed} FAIL  (of {total} checks)")
    print("=" * 60)

    if failed:
        print("\nFailed checks:")
        for id_, status, desc, detail in results:
            if status == FAIL:
                print(f"  {id_}: {desc}")
                if detail:
                    print(f"    → {detail}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
