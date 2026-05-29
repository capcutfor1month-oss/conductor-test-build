"""
Phase D Slice 20 — Critic Composer Polish / Final Answer Polish
===============================================================
Tests for Build 13: improved _compose_final_answer() prose joining,
session_facts_used weaving, and all safety guards.

All sections are mock-based — no live ChromaDB or LLM calls.
"""

import importlib
import os
import sys

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

_EXPLORER_FALLBACK = "The Explorer synthesised a safe fallback answer."


def _make_explorer_data(direction, rationale="", session_facts_used=None):
    return {
        "question_type": "creative",
        "candidates": [
            {
                "direction":          direction,
                "rationale":          rationale,
                "session_facts_used": session_facts_used or [],
                "assumptions":        [],
                "source_hints":       [],
                "actionable":         True,
                "confidence":         0.8,
            }
        ],
    }


def _make_critic(selected=0):
    return {
        "selected":       selected,
        "kept":           [selected],
        "rejected":       [],
        "reasons":        {},
        "critic_summary": "test",
    }


# ── Section D187 ──────────────────────────────────────────────────────────────

@section("D187")
def run_d187():
    """
    Clean direction (≤ 8 words) + rationale → composed text uses em-dash
    connector for natural one-sentence flow. Not the old plain ". " join.
    Both direction and rationale content are present in the output.
    """
    print("=== Section D187: short direction+rationale → em-dash prose ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Cut the low-mid buildup on Lead Vocals"   # 7 words ≤ 8
    rationale = "Boost presence between 3–5kHz with a gentle shelf"
    explorer_data = _make_explorer_data(direction, rationale)
    critic_data   = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    # Must not be the fallback
    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")

    # Must contain em-dash connector (natural flow)
    if " — " not in result:
        errors.append(f"em-dash connector missing; got: {result!r}")

    # Direction content must be present
    if "low-mid" not in result.lower():
        errors.append(f"direction content missing from output: {result!r}")

    # Rationale content must be present
    if "3–5kHz" not in result and "3-5" not in result.lower():
        errors.append(f"rationale content missing from output: {result!r}")

    # Must not contain raw schema join ". " between direction and rationale
    # (the whole direction phrase followed by ". " followed by the rationale start)
    if "Lead Vocals. Boost" in result:
        errors.append(f"old plain-join format detected: {result!r}")

    # Must end with "." cleanly
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

    return errors


# ── Section D188 ──────────────────────────────────────────────────────────────

@section("D188")
def run_d188():
    """
    Direction-only (empty rationale) → composed text is clean prose ending
    with '.'. No trailing em-dash, no '()', no artifact from the absent rationale.
    """
    print("=== Section D188: direction-only (no rationale) → clean, no artifact ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use a gentle low-pass on the synth pad"
    explorer_data = _make_explorer_data(direction, rationale="")
    critic_data   = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")

    # Direction content present
    if "low-pass" not in result.lower():
        errors.append(f"direction content missing: {result!r}")

    # No em-dash artifact (no rationale to join)
    if " — " in result:
        errors.append(f"unexpected em-dash in direction-only output: {result!r}")

    # No empty parenthetical artifact
    if "()" in result:
        errors.append(f"empty parenthetical '()' in output: {result!r}")

    # Ends cleanly with "."
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

    # No double period
    if ".." in result:
        errors.append(f"double period in output: {result!r}")

    return errors


# ── Section D189 ──────────────────────────────────────────────────────────────

@section("D189")
def run_d189():
    """
    Useful session_facts_used (specific measurements) → facts woven into
    the composed output naturally. Content of the fact appears in the result.
    """
    print("=== Section D189: useful session_facts_used woven naturally ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use parallel compression on the drums"   # 7 words ≤ 8
    rationale = "Push the parallel chain hard without killing transients"
    facts     = ["Kick at -8 LUFS", "Snare at -12 LUFS"]

    explorer_data = _make_explorer_data(direction, rationale, session_facts_used=facts)
    critic_data   = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")

    # At least one of the safe facts must appear in the output
    if "Kick at -8 LUFS" not in result and "Snare at -12 LUFS" not in result:
        errors.append(
            f"no session fact found in output; got: {result!r}"
        )

    # Core content still present
    if "parallel" not in result.lower():
        errors.append(f"direction content missing from output: {result!r}")

    # No raw JSON or internal markers
    if result.strip().startswith("{"):
        errors.append("output starts with raw JSON brace")

    # Ends with "."
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

    return errors


# ── Section D190 ──────────────────────────────────────────────────────────────

@section("D190")
def run_d190():
    """
    Empty session_facts_used → composed text has no fact-weaving artifact:
    no empty parenthetical '()', no " · ", no trailing comma, no orphaned separator.
    """
    print("=== Section D190: empty session_facts_used → no artifact ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use gentle EQ on the mix"      # 6 words ≤ 8
    rationale = "Aim for clarity in the midrange"
    facts     = []

    explorer_data = _make_explorer_data(direction, rationale, session_facts_used=facts)
    critic_data   = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")

    # No empty parenthetical
    if "()" in result:
        errors.append(f"empty parenthetical '()' in output: {result!r}")

    # No separator artifacts from fact joining
    for artifact in [" · ", " (,", "(, ", "( )"]:
        if artifact in result:
            errors.append(f"fact-join artifact {artifact!r} in output: {result!r}")

    # Core content present
    if "EQ" not in result and "eq" not in result.lower():
        errors.append(f"direction content missing from output: {result!r}")

    # Ends cleanly
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

    return errors


# ── Section D191 ──────────────────────────────────────────────────────────────

@section("D191")
def run_d191():
    """
    Internal/debug-like session_facts_used is never exposed in output.
    Covers: Operator Card labels, snake_case keys, KNOWLEDGE STATUS markers,
    markdown headers.
    """
    print("=== Section D191: internal/debug session_facts not exposed ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use gentle EQ on the mix"
    rationale = "Aim for clarity in the midrange"
    debug_facts = [
        "Operator Card — Ozone 12",       # operator card reference
        "session_facts_used",             # snake_case internal key
        "## KNOWLEDGE STATUS — Diva",     # markdown header with trust label
        "KNOWLEDGE STATUS block",         # trust label
        "knowledge_evidence criterion",   # trust label (knowledge_evidence)
        "source_hints applied",           # structural schema key embedded
    ]

    explorer_data = _make_explorer_data(direction, rationale,
                                        session_facts_used=debug_facts)
    critic_data = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    # None of the internal labels must appear in the output
    forbidden = [
        "Operator Card",
        "session_facts_used",
        "KNOWLEDGE STATUS",
        "knowledge_evidence",
        "source_hints",
        "## ",
    ]
    for label in forbidden:
        if label.lower() in result.lower():
            errors.append(
                f"internal label {label!r} leaked into output: {result!r}"
            )

    # Core content still present (composition ran normally)
    if result == _EXPLORER_FALLBACK:
        # Fallback is acceptable here — but also check that if it did compose,
        # it did so cleanly. Either way, no labels.
        pass  # fallback = guards fired on contaminated text — acceptable

    # If output is composed (not fallback), must end cleanly
    if result != _EXPLORER_FALLBACK and not result.strip().endswith("."):
        errors.append(f"composed output does not end with '.': {result!r}")

    return errors


# ── Section D192 ──────────────────────────────────────────────────────────────

@section("D192")
def run_d192():
    """
    Regression: _STRUCTURAL_RE guard still fires when direction or rationale
    contains an internal schema marker — falls back to explorer_answer.
    """
    print("=== Section D192: _STRUCTURAL_RE guard regression ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    structural_cases = [
        # direction contains a structural marker
        ("confidence: 0.85 is why this approach works", "Use a soft limiter."),
        ("This direction has candidates embedded",       "Solid rationale here."),
        ("Use rationale-driven approach",                "Good reasoning."),
    ]

    for dirty_dir, rat in structural_cases:
        explorer_data = _make_explorer_data(dirty_dir, rat)
        result = hs._compose_final_answer(_EXPLORER_FALLBACK,
                                          explorer_data, _make_critic(0))
        if result != _EXPLORER_FALLBACK:
            errors.append(
                f"_STRUCTURAL_RE did not fire for direction {dirty_dir!r}; "
                f"got: {result!r}"
            )

    # Rationale with structural marker
    explorer_data = _make_explorer_data(
        "Use gentle compression",
        "This boosts the assumptions of the mix",
    )
    result = hs._compose_final_answer(_EXPLORER_FALLBACK,
                                      explorer_data, _make_critic(0))
    if result != _EXPLORER_FALLBACK:
        errors.append(
            f"_STRUCTURAL_RE did not fire for rationale with 'assumptions'; "
            f"got: {result!r}"
        )

    return errors


# ── Section D193 ──────────────────────────────────────────────────────────────

@section("D193")
def run_d193():
    """
    Regression: _TRUST_LABEL_RE guard still fires when direction or rationale
    contains a Build 11/12 internal trust label — falls back to explorer_answer.
    """
    print("=== Section D193: _TRUST_LABEL_RE guard regression ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    trust_cases = [
        ("## KNOWLEDGE STATUS — Diva recognized",    "Use general principles."),
        ("Use Diva filter",  "Operator card: not available — answer from general knowledge only"),
        ("Plugin Knowledge Context: check this",     "Apply knowledge_evidence here."),
        ("Use compression",  "confidence <= 0.5 for this approach"),
        ("Use compression",  "confidence ≤ 0.5 because no card"),
    ]

    for dirty_dir, rat in trust_cases:
        explorer_data = _make_explorer_data(dirty_dir, rat)
        result = hs._compose_final_answer(_EXPLORER_FALLBACK,
                                          explorer_data, _make_critic(0))
        if result != _EXPLORER_FALLBACK:
            errors.append(
                f"_TRUST_LABEL_RE did not fire for "
                f"direction={dirty_dir!r}, rationale={rat!r}; got: {result!r}"
            )

    return errors


# ── Section D194 ──────────────────────────────────────────────────────────────

@section("D194")
def run_d194():
    """
    Regression: empty/invalid critic_data always falls back to explorer_answer.
    Covers: {}, selected=None, selected out-of-range, direction="".
    """
    print("=== Section D194: empty/invalid critic_data → fallback regression ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    explorer_data = _make_explorer_data(
        "Cut the low-mid buildup on Lead Vocals",
        "Boost presence between 3–5kHz",
    )

    # A: empty critic_data
    result_a = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, {})
    if result_a != _EXPLORER_FALLBACK:
        errors.append(f"[A] empty critic_data: expected fallback, got {result_a!r}")

    # B: selected = None
    result_b = hs._compose_final_answer(
        _EXPLORER_FALLBACK, explorer_data,
        {"selected": None, "kept": [], "rejected": [], "reasons": {},
         "critic_summary": ""},
    )
    if result_b != _EXPLORER_FALLBACK:
        errors.append(f"[B] selected=None: expected fallback, got {result_b!r}")

    # C: selected out-of-range (only 1 candidate)
    result_c = hs._compose_final_answer(
        _EXPLORER_FALLBACK, explorer_data,
        {"selected": 5, "kept": [5], "rejected": [], "reasons": {},
         "critic_summary": ""},
    )
    if result_c != _EXPLORER_FALLBACK:
        errors.append(f"[C] out-of-range index: expected fallback, got {result_c!r}")

    # D: direction="" — should fall back
    empty_dir_data = _make_explorer_data("", "Some rationale here")
    result_d = hs._compose_final_answer(_EXPLORER_FALLBACK, empty_dir_data, _make_critic(0))
    if result_d != _EXPLORER_FALLBACK:
        errors.append(f"[D] empty direction: expected fallback, got {result_d!r}")

    # E: critic_data=None
    result_e = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, None)
    if result_e != _EXPLORER_FALLBACK:
        errors.append(f"[E] None critic_data: expected fallback, got {result_e!r}")

    return errors


# ── Section D195 ──────────────────────────────────────────────────────────────

@section("D195")
def run_d195():
    """
    Internal/debug metadata facts are never woven into the final answer.
    Covers:
      - key:value metadata (mode:, risk:, score:, selected:, kept:, rejected:)
      - JSON-looking facts starting with { or [
      - ID references (proof id, request id, action id — space form)
    """
    print("=== Section D195: internal/debug metadata facts not woven ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use parallel compression on the drums"   # 7 words ≤ 8
    rationale = "Push the parallel chain hard without killing transients"
    dirty_facts = [
        "Mode: MENTOR",
        "Risk: LOW",
        "score: 0.91",
        "scores: [0.9, 0.7]",
        "selected: 0",
        "kept: [0]",
        "rejected: [1]",
        '{"mode":"MENTOR"}',
        '["candidate", "list"]',
        "proof id abc123",
        "request id xyz-99",
        "action id 007",
    ]

    explorer_data = _make_explorer_data(direction, rationale,
                                        session_facts_used=dirty_facts)
    critic_data = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")
        return errors

    # None of the internal metadata values should appear in the output
    forbidden_fragments = [
        "Mode: MENTOR",
        "Risk: LOW",
        "score: 0.91",
        "scores:",
        "selected: 0",
        "kept:",
        "rejected:",
        '{"mode"',
        '["candidate"',
        "proof id",
        "request id",
        "action id",
    ]
    for fragment in forbidden_fragments:
        if fragment.lower() in result.lower():
            errors.append(
                f"internal metadata fragment {fragment!r} leaked into output: {result!r}"
            )

    # Core content still present
    if "parallel" not in result.lower():
        errors.append(f"direction content missing from output: {result!r}")

    # Ends cleanly
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

    return errors


# ── Section D196 ──────────────────────────────────────────────────────────────

@section("D196")
def run_d196():
    """
    Clean musical/session facts (e.g. 'Kick at -8 LUFS', 'Tempo: 120 BPM')
    are still woven into the output after the new metadata filters are applied.
    Verifies the new checks do not over-filter useful musical context.
    """
    print("=== Section D196: clean musical facts still woven after new filters ===")
    hs = importlib.import_module("tools.harness_server")
    errors = []

    direction = "Use parallel compression on the drums"   # 7 words ≤ 8
    rationale = "Push the parallel chain without killing transients"
    clean_facts = [
        "Kick at -8 LUFS",
        "Tempo: 120 BPM",
    ]

    explorer_data = _make_explorer_data(direction, rationale,
                                        session_facts_used=clean_facts)
    critic_data = _make_critic(0)

    result = hs._compose_final_answer(_EXPLORER_FALLBACK, explorer_data, critic_data)

    if result == _EXPLORER_FALLBACK:
        errors.append("fell back to explorer_answer — composition did not run")
        return errors

    # At least one clean fact must be woven in
    if "Kick at -8 LUFS" not in result and "Tempo: 120 BPM" not in result:
        errors.append(
            f"no clean musical fact woven into output; got: {result!r}"
        )

    # Core content present
    if "parallel" not in result.lower():
        errors.append(f"direction content missing from output: {result!r}")

    # Ends cleanly
    if not result.strip().endswith("."):
        errors.append(f"output does not end with '.': {result!r}")

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
        print(f"{FAIL} Phase D Slice 20: {failed}/{total} sections failed")
        raise SystemExit(1)
    print(f"{PASS} Phase D Slice 20: {total}/{total} sections passed")


if __name__ == "__main__":
    main()
