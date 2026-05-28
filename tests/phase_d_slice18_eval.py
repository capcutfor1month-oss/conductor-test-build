"""
Phase D Slice 18 — Plugin Knowledge Trust Signals
===================================================
Tests for Build 11: KNOWLEDGE STATUS block injection in build_message_pack(),
Explorer knowledge_gap rule, and Critic knowledge_evidence criterion.

All sections are mock-based — no live ChromaDB required.
"""

import os
import sys
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
sys.path.insert(0, _ROOT)

import rag.context_pack_builder as cpb


# ── shared helpers ─────────────────────────────────────────────────────────────

def _make_empty_retrieval():
    from rag.routed_retriever import RetrievalResult
    r = RetrievalResult()
    r.retrieved    = []
    r.injected     = []
    r.freeform     = False
    r.mode         = "MENTOR"
    r.summary_text = ""
    return r


def _minimal_classify(mode="MENTOR"):
    return {
        "mode": mode,
        "risk_reason": "",
        "protection_level": "STATUS_ONLY",
        "risk_category": "status_or_advice",
        "rationale": "",
        "auto_execute_allowed": False,
        "confirmation_required": False,
    }


# ── Section D169 ───────────────────────────────────────────────────────────────

def run_d169():
    """
    _check_plugin_knowledge_status("set diva filter cutoff", "") returns
    ("missing", "Diva") when _get_known_plugin_name is mocked to "Diva".
    card_file="" → not verified. Inventory recognizes "Diva" → missing.
    """
    errors = []

    with patch.object(cpb, "_get_known_plugin_name", return_value="Diva"):
        status, plugin_name = cpb._check_plugin_knowledge_status(
            "set diva filter cutoff", ""
        )

    if status != "missing":
        errors.append(f"expected status 'missing', got {status!r}")
    if plugin_name != "Diva":
        errors.append(f"expected plugin_name 'Diva', got {plugin_name!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D169] {e}")
        print("  D169: FAIL")
        return False
    print("  \033[92m✅\033[0m [D169] _check_plugin_knowledge_status: recognized-but-no-card → ('missing', 'Diva')")
    print("  D169: PASS")
    return True


# ── Section D170 ───────────────────────────────────────────────────────────────

def run_d170():
    """
    _check_plugin_knowledge_status("set pro-q 4 band 2", "Pro-Q 4 Operator Card.md")
    returns ("verified", "Pro-Q 4") — card_file is non-empty, no _get_known_plugin_name call.
    """
    errors = []

    # card_file non-empty → short-circuits before _get_known_plugin_name
    status, plugin_name = cpb._check_plugin_knowledge_status(
        "set pro-q 4 band 2", "Pro-Q 4 Operator Card.md"
    )

    if status != "verified":
        errors.append(f"expected status 'verified', got {status!r}")
    if plugin_name != "Pro-Q 4":
        errors.append(f"expected plugin_name 'Pro-Q 4', got {plugin_name!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D170] {e}")
        print("  D170: FAIL")
        return False
    print("  \033[92m✅\033[0m [D170] _check_plugin_knowledge_status: card present → ('verified', 'Pro-Q 4')")
    print("  D170: PASS")
    return True


# ── Section D171 ───────────────────────────────────────────────────────────────

def run_d171():
    """
    _check_plugin_knowledge_status("how do I write a string melody", "") returns
    ("none", "") when _get_known_plugin_name is mocked to "" — no plugin recognized.
    """
    errors = []

    with patch.object(cpb, "_get_known_plugin_name", return_value=""):
        status, plugin_name = cpb._check_plugin_knowledge_status(
            "how do I write a string melody", ""
        )

    if status != "none":
        errors.append(f"expected status 'none', got {status!r}")
    if plugin_name != "":
        errors.append(f"expected plugin_name '', got {plugin_name!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D171] {e}")
        print("  D171: FAIL")
        return False
    print("  \033[92m✅\033[0m [D171] _check_plugin_knowledge_status: no plugin → ('none', '')")
    print("  D171: PASS")
    return True


# ── Section D172 ───────────────────────────────────────────────────────────────

def run_d172():
    """
    build_message_pack for a recognized-but-no-card plugin:
    - ## KNOWLEDGE STATUS block present in pack
    - "Plugin recognized: Diva" in pack
    - "Operator card: not available" in pack
    - ## OPERATOR CARD absent from pack
    """
    errors = []

    mock_retrieval = _make_empty_retrieval()

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""), \
         patch.object(cpb, "_get_known_plugin_name", return_value="Diva"):
        result = cpb.build_message_pack("set diva filter cutoff")

    pack = result["pack"]

    if "## KNOWLEDGE STATUS" not in pack:
        errors.append("## KNOWLEDGE STATUS block missing from pack")
    if "Plugin recognized: Diva" not in pack:
        errors.append("'Plugin recognized: Diva' missing from pack")
    if "Operator card: not available" not in pack:
        errors.append("'Operator card: not available' missing from pack")
    if "## OPERATOR CARD" in pack:
        errors.append("## OPERATOR CARD block appeared despite no card detected")
    if result["debug"]["plugin_card"] != "":
        errors.append(f"debug.plugin_card should be '' got {result['debug']['plugin_card']!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D172] {e}")
        print("  D172: FAIL")
        return False
    print("  \033[92m✅\033[0m [D172] KNOWLEDGE STATUS injected for recognized-but-no-card plugin")
    print("  D172: PASS")
    return True


# ── Section D173 ───────────────────────────────────────────────────────────────

def run_d173():
    """
    build_message_pack for a plugin with a card (Pro-Q 4):
    - ## OPERATOR CARD present in pack
    - ## KNOWLEDGE STATUS absent from pack
    Guard A dedup not triggered here (empty retrieval), card snippet injected normally.
    """
    errors = []

    mock_retrieval = _make_empty_retrieval()

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value="Pro-Q 4 Operator Card.md"), \
         patch.object(cpb, "_get_stable_card_id",
                      return_value="vault_plugin_fabfilter_pro_q_4"), \
         patch.object(cpb, "_load_card_snippet",
                      return_value="## OPERATOR CARD — Pro-Q 4\n\n## Identity\nOK"):
        result = cpb.build_message_pack("set pro-q 4 band 2 to 200hz")

    pack = result["pack"]

    if "## OPERATOR CARD" not in pack:
        errors.append("## OPERATOR CARD missing from pack when card is present")
    if "## KNOWLEDGE STATUS" in pack:
        errors.append("## KNOWLEDGE STATUS appeared despite card being present")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D173] {e}")
        print("  D173: FAIL")
        return False
    print("  \033[92m✅\033[0m [D173] Card present → OPERATOR CARD in pack; no KNOWLEDGE STATUS")
    print("  D173: PASS")
    return True


# ── Section D174 ───────────────────────────────────────────────────────────────

def run_d174():
    """
    _build_explorer_instructions(True) contains the knowledge_gap rule
    referencing '## KNOWLEDGE STATUS' and 'Operator card: not available'.
    """
    errors = []

    import importlib
    hs = importlib.import_module("harness_server")
    text = hs._build_explorer_instructions(True)

    if "knowledge_gap" not in text:
        errors.append("'knowledge_gap' not found in explorer instructions")
    if "KNOWLEDGE STATUS" not in text:
        errors.append("'KNOWLEDGE STATUS' not found in explorer instructions")
    if "Operator card: not available" not in text:
        errors.append("'Operator card: not available' not found in explorer instructions")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D174] {e}")
        print("  D174: FAIL")
        return False
    print("  \033[92m✅\033[0m [D174] Explorer instructions contain knowledge_gap rule")
    print("  D174: PASS")
    return True


# ── Section D175 ───────────────────────────────────────────────────────────────

def run_d175():
    """
    _build_critic_prompt() contains the knowledge_evidence criterion
    referencing missing Operator Card.
    """
    errors = []

    import importlib
    hs = importlib.import_module("harness_server")

    dummy_candidate = {
        "direction":          "Use general EQ principles",
        "rationale":          "No card available",
        "session_facts_used": [],
        "assumptions":        ["No card — general advice only"],
    }
    prompt = hs._build_critic_prompt([dummy_candidate], "test question", "")

    if "knowledge_evidence" not in prompt:
        errors.append("'knowledge_evidence' criterion not found in critic prompt")
    # Check that the criterion references missing Operator Card context
    if "KNOWLEDGE STATUS" not in prompt and "no Operator Card" not in prompt:
        errors.append("Critic criterion does not reference missing Operator Card")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D175] {e}")
        print("  D175: FAIL")
        return False
    print("  \033[92m✅\033[0m [D175] Critic prompt contains knowledge_evidence criterion")
    print("  D175: PASS")
    return True


# ── Section D176 ───────────────────────────────────────────────────────────────

def run_d176():
    """
    Regression / import checks:
    - _check_plugin_knowledge_status importable from context_pack_builder
    - _get_known_plugin_name alias importable from context_pack_builder
    - get_known_plugin_name_for_message importable from rag.risk_taxonomy
    - Live inventory lookups (no mock):
        "use diva on strings"     → "Diva"
        "set pro-q 4 band 2"      → "Pro-Q 4"
        "how do I mic a tabla"    → ""
    - build_message_pack return shape unchanged
    """
    errors = []

    # ── Symbol checks ─────────────────────────────────────────────────────────
    for sym in ("_check_plugin_knowledge_status", "_get_known_plugin_name"):
        if not hasattr(cpb, sym):
            errors.append(f"context_pack_builder missing symbol: {sym}")

    try:
        from rag.risk_taxonomy import get_known_plugin_name_for_message
    except ImportError as exc:
        errors.append(f"get_known_plugin_name_for_message not importable: {exc}")
        get_known_plugin_name_for_message = None

    # ── Live inventory lookups (no mock — tests actual known_plugins.json) ────
    if get_known_plugin_name_for_message is not None:
        cases = [
            ("use diva on strings",    "Diva"),
            ("set pro-q 4 band 2",     "Pro-Q 4"),
            ("how do I mic a tabla",   ""),
        ]
        for msg, expected in cases:
            got = get_known_plugin_name_for_message(msg)
            if got != expected:
                errors.append(
                    f"get_known_plugin_name_for_message({msg!r}): "
                    f"expected {expected!r}, got {got!r}"
                )

    # ── build_message_pack return shape ───────────────────────────────────────
    mock_retrieval = _make_empty_retrieval()
    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""), \
         patch.object(cpb, "_get_known_plugin_name", return_value=""):
        result = cpb.build_message_pack("how do I compress a dhol")

    for key in ("ok", "pack", "mode", "risk_reason", "debug"):
        if key not in result:
            errors.append(f"build_message_pack missing top-level key: {key}")
    for dkey in ("plugin_card", "memory_hits", "injected_count", "evidence"):
        if dkey not in result.get("debug", {}):
            errors.append(f"build_message_pack debug missing key: {dkey}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D176] {e}")
        print("  D176: FAIL")
        return False
    print("  \033[92m✅\033[0m [D176] Regression: symbols importable; live lookups correct; return shape unchanged")
    print("  D176: PASS")
    return True


# ── Runner ─────────────────────────────────────────────────────────────────────

def run_all():
    sections = [
        ("D169", run_d169),
        ("D170", run_d170),
        ("D171", run_d171),
        ("D172", run_d172),
        ("D173", run_d173),
        ("D174", run_d174),
        ("D175", run_d175),
        ("D176", run_d176),
    ]
    total  = len(sections)
    passed = 0
    for label, fn in sections:
        print(f"\n=== Section {label}: {fn.__doc__.strip().splitlines()[0]} ===")
        try:
            ok = fn()
        except Exception as exc:
            print(f"  \033[91m✗\033[0m [{label}] EXCEPTION: {exc}")
            import traceback
            traceback.print_exc()
            ok = False
        if ok:
            passed += 1

    print(f"\n{'=' * 60}")
    if passed == total:
        print(f"\033[92m✅\033[0m Phase D Slice 18 — Plugin Knowledge Trust Signals: {passed}/{total} sections passed")
        print("OVERALL: PASS")
    else:
        print(f"\033[91m❌\033[0m Phase D Slice 18 — Plugin Knowledge Trust Signals: {passed}/{total} sections passed")
        print("OVERALL: FAIL")
    print("=" * 60)
    return passed == total


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
