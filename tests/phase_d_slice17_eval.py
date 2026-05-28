"""
Phase D Slice 17 — Plugin Knowledge Routing v1
================================================
Tests for Build 10: Deduplication Guard (A) + BM25 Intent Guard (B)
in rag/context_pack_builder.build_message_pack().

All sections are mock-based — no live ChromaDB required.
"""

import os
import sys
import types
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
sys.path.insert(0, _ROOT)

# ── import the module under test ──────────────────────────────────────────────
import rag.context_pack_builder as cpb

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_evidence_item(
    collection="plugin_operator_index",
    id_="vault_plugin_fabfilter_pro_q_4",
    text="# Operator Card — FabFilter Pro-Q 4\n> Loaded when Pro-Q 4 is active.",
    similarity=0.41,
    injected=True,
    rescue_mode=None,
    label="[plugin]",
):
    """Return a minimal EvidenceItem-compatible namespace for testing."""
    from rag.routed_retriever import EvidenceItem
    item = EvidenceItem(
        text=text,
        collection=collection,
        similarity=similarity,
        memory_level=3,
        label=label,
        injected=injected,
        rescue_mode=rescue_mode,
        id=id_,
    )
    return item


def _make_retrieval(items):
    """Return a minimal RetrievalResult-compatible namespace."""
    from rag.routed_retriever import RetrievalResult
    r = RetrievalResult()
    r.retrieved = items
    r.injected  = [i for i in items if i.injected]
    r.freeform  = False
    r.mode      = "MENTOR"
    # Build summary_text from injected items (same format as routed_retriever)
    lines = []
    for i in r.injected:
        snip = (i.text or "")[:200].replace("\n", " ")
        if len(i.text or "") > 200:
            snip += "…"
        lines.append(f"{i.label} {snip}")
    r.summary_text = "\n".join(lines) if lines else ""
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


# ── Section D162 ──────────────────────────────────────────────────────────────

def run_d162():
    """
    Guard A — detected plugin → same-card ChromaDB evidence excluded from
    memory section; file-based ## OPERATOR CARD snippet still appears in pack.
    """
    errors = []
    section = "D162"

    # Mock a retrieval result that includes the Pro-Q 4 card from ChromaDB
    proq4_item = _make_evidence_item(
        id_="vault_plugin_fabfilter_pro_q_4",
        text="# Operator Card — FabFilter Pro-Q 4\n> Full card body.",
        injected=True,
        rescue_mode=None,   # semantic hit — would normally pass
    )
    mock_retrieval = _make_retrieval([proq4_item])

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value="Pro-Q 4 Operator Card.md"), \
         patch.object(cpb, "_get_stable_card_id",
                      return_value="vault_plugin_fabfilter_pro_q_4"), \
         patch.object(cpb, "_load_card_snippet",
                      return_value="## OPERATOR CARD — Pro-Q 4\n\n## Identity\nManufacturer: FabFilter"):
        result = cpb.build_message_pack("set pro-q 4 band 2 to 200hz")

    pack = result["pack"]

    # Guard A must have fired: ChromaDB item's injected flag = False
    if proq4_item.injected:
        errors.append("Guard A did NOT fire: proq4_item.injected is still True")
    if proq4_item.reason != "dedup_file_path_is_authoritative":
        errors.append(f"Guard A reason wrong: {proq4_item.reason!r}")

    # File-based snippet must still appear in the pack
    if "## OPERATOR CARD — Pro-Q 4" not in pack:
        errors.append("File-based ## OPERATOR CARD block missing from pack")

    # ChromaDB full body must NOT appear in the memory section
    # (It was excluded, so "Full card body." should not be in the pack)
    if "Full card body." in pack:
        errors.append("ChromaDB full card body leaked into pack despite Guard A")

    # debug.plugin_card should be set
    if result["debug"]["plugin_card"] != "Pro-Q 4":
        errors.append(f"debug.plugin_card wrong: {result['debug']['plugin_card']!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D162] {e}")
        print(f"  D162: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D162] Guard A: detected card excluded from memory; ## OPERATOR CARD snippet present")
    print(f"  D162: PASS")
    return True


# ── Section D163 ──────────────────────────────────────────────────────────────

def run_d163():
    """
    Guard A — a DIFFERENT plugin card (not the detected one) is NOT excluded.
    Only the exact detected card's stable ID is removed.
    """
    errors = []

    proq4_item = _make_evidence_item(
        id_="vault_plugin_fabfilter_pro_q_4",
        text="# Operator Card — Pro-Q 4",
        injected=True,
    )
    ozone_item = _make_evidence_item(
        id_="vault_plugin_izotope_ozone_12",
        text="# Operator Card — Ozone 12",
        injected=True,
    )
    mock_retrieval = _make_retrieval([proq4_item, ozone_item])

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value="Pro-Q 4 Operator Card.md"), \
         patch.object(cpb, "_get_stable_card_id",
                      return_value="vault_plugin_fabfilter_pro_q_4"), \
         patch.object(cpb, "_load_card_snippet",
                      return_value="## OPERATOR CARD — Pro-Q 4\n\n## Identity\nTest"):
        cpb.build_message_pack("set pro-q 4 band 2")

    # Pro-Q 4 must be excluded (Guard A)
    if proq4_item.injected:
        errors.append("Pro-Q 4 (detected card) was NOT excluded — Guard A missed it")
    # Ozone must NOT be excluded (different plugin)
    if not ozone_item.injected:
        errors.append("Ozone 12 (different card) was wrongly excluded by Guard A")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D163] {e}")
        print(f"  D163: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D163] Guard A: only detected card excluded; other plugin card preserved")
    print(f"  D163: PASS")
    return True


# ── Section D164 ──────────────────────────────────────────────────────────────

def run_d164():
    """
    Guard B — no plugin detected + BM25-rescued plugin card is excluded.
    """
    errors = []

    bm25_item = _make_evidence_item(
        id_="vault_plugin_fabfilter_pro_q_4",
        text="# Operator Card — Pro-Q 4\n> mix EQ filter band",
        injected=True,
        rescue_mode="bm25",   # BM25 rescue — must be blocked
    )
    mock_retrieval = _make_retrieval([bm25_item])

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""):
        result = cpb.build_message_pack("how do I mix a sitar")

    pack = result["pack"]

    if bm25_item.injected:
        errors.append("Guard B did NOT fire: BM25-rescued item is still injected")
    if bm25_item.reason != "no_plugin_detected_bm25_rescue_blocked":
        errors.append(f"Guard B reason wrong: {bm25_item.reason!r}")
    if "## OPERATOR CARD" in pack:
        errors.append("## OPERATOR CARD block appeared despite no plugin detected")
    if result["debug"]["plugin_card"] != "":
        errors.append(f"debug.plugin_card should be '' got: {result['debug']['plugin_card']!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D164] {e}")
        print(f"  D164: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D164] Guard B: BM25-rescued plugin card excluded when no plugin detected")
    print(f"  D164: PASS")
    return True


# ── Section D165 ──────────────────────────────────────────────────────────────

def run_d165():
    """
    Guard B — no plugin detected + semantic plugin card (rescue_mode=None)
    remains injected. Guard B must not block semantic hits.
    """
    errors = []

    semantic_item = _make_evidence_item(
        id_="vault_plugin_fabfilter_pro_q_4",
        text="# Operator Card — Pro-Q 4\n> EQ for mixing",
        injected=True,
        rescue_mode=None,   # semantic hit — must NOT be blocked
        similarity=0.38,
    )
    mock_retrieval = _make_retrieval([semantic_item])

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""):
        cpb.build_message_pack("which EQ should I use for harshness")

    if not semantic_item.injected:
        errors.append("Guard B wrongly excluded a semantic plugin hit (rescue_mode=None)")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D165] {e}")
        print(f"  D165: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D165] Guard B: semantic plugin card (rescue_mode=None) still injected when no plugin detected")
    print(f"  D165: PASS")
    return True


# ── Section D166 ──────────────────────────────────────────────────────────────

def run_d166():
    """
    No plugin detected → debug.plugin_card == "" and no ## OPERATOR CARD block in pack.
    """
    errors = []

    mock_retrieval = _make_retrieval([])

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""):
        result = cpb.build_message_pack("how do I write a string melody")

    if result["debug"]["plugin_card"] != "":
        errors.append(f"debug.plugin_card should be '' got: {result['debug']['plugin_card']!r}")
    if "## OPERATOR CARD" in result["pack"]:
        errors.append("## OPERATOR CARD appeared in pack when no plugin was detected")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D166] {e}")
        print(f"  D166: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D166] No plugin detected → plugin_card='' and no OPERATOR CARD block in pack")
    print(f"  D166: PASS")
    return True


# ── Section D167 ──────────────────────────────────────────────────────────────

def run_d167():
    """
    Guard rebuild — after Guard A fires, retrieval.injected and
    retrieval.summary_text reflect the updated state, not the stale pre-guard state.
    """
    errors = []

    proq4_item = _make_evidence_item(
        id_="vault_plugin_fabfilter_pro_q_4",
        text="Pro-Q 4 full body text that should not appear in summary",
        injected=True,
        rescue_mode=None,
    )
    other_item = _make_evidence_item(
        collection="producer_memory_index",
        id_="mem_123",
        text="I prefer a high-pass filter at 80Hz on all non-bass tracks",
        injected=True,
        rescue_mode=None,
        label="[producer]",
    )
    mock_retrieval = _make_retrieval([proq4_item, other_item])

    captured_retrieval = {}

    original_routed = cpb._routed_retrieve

    def _capture_and_return(msg, mode, **kw):
        captured_retrieval["obj"] = mock_retrieval
        return mock_retrieval

    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", side_effect=_capture_and_return), \
         patch.object(cpb, "_detect_plugin", return_value="Pro-Q 4 Operator Card.md"), \
         patch.object(cpb, "_get_stable_card_id",
                      return_value="vault_plugin_fabfilter_pro_q_4"), \
         patch.object(cpb, "_load_card_snippet",
                      return_value="## OPERATOR CARD — Pro-Q 4\n\n## Identity\nOK"):
        result = cpb.build_message_pack("set pro-q 4 gain")

    r = captured_retrieval.get("obj")
    if r is None:
        errors.append("retrieval object not captured")
    else:
        # retrieval.injected must NOT contain the excluded proq4_item
        injected_ids = [i.id for i in r.injected]
        if "vault_plugin_fabfilter_pro_q_4" in injected_ids:
            errors.append("retrieval.injected still contains excluded item after guard rebuild")
        # retrieval.injected must still contain the other item
        if "mem_123" not in injected_ids:
            errors.append("retrieval.injected lost the non-excluded item")
        # summary_text must not contain the excluded Pro-Q 4 full body
        if "Pro-Q 4 full body text" in r.summary_text:
            errors.append("retrieval.summary_text still contains excluded card text")
        # summary_text must contain the other item
        if "high-pass filter" not in r.summary_text:
            errors.append("retrieval.summary_text lost non-excluded item text")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D167] {e}")
        print(f"  D167: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D167] Guard rebuild: retrieval.injected and summary_text reflect guard changes")
    print(f"  D167: PASS")
    return True


# ── Section D168 ──────────────────────────────────────────────────────────────

def run_d168():
    """
    Regression — Slice 14-16 behavior intact:
    - _detect_plugin and _get_stable_card_id are importable and callable
    - _load_card_snippet signature unchanged
    - _extract_operator_card_context in harness_server is unchanged
    - build_message_pack returns the expected top-level keys
    """
    errors = []

    # ── Static symbol checks ──────────────────────────────────────────────────
    for sym in ("_detect_plugin", "_load_card_snippet", "_get_stable_card_id",
                "build_message_pack", "build_session_pack", "build_context_pack"):
        if not hasattr(cpb, sym):
            errors.append(f"context_pack_builder missing symbol: {sym}")

    # ── harness_server symbols (Build 8 / Slice 16 regression) ───────────────
    try:
        import importlib, types as _types
        hs_spec = importlib.util.spec_from_file_location(
            "harness_server",
            os.path.join(_ROOT, "tools", "harness_server.py"),
        )
        hs_mod = importlib.util.module_from_spec(hs_spec)
        hs_spec.loader.exec_module(hs_mod)
        for sym in ("_extract_operator_card_context", "_build_critic_prompt",
                    "call_creative_critic", "_compose_final_answer"):
            if not hasattr(hs_mod, sym):
                errors.append(f"harness_server missing symbol: {sym}")
        # _extract_operator_card_context basic smoke test
        pack_with_card = (
            "## MESSAGE PACK\nMode: MENTOR\n\n"
            "## OPERATOR CARD — Pro-Q 4\n"
            "## Identity\nManufacturer: FabFilter\n\n"
            "## Risky Writes\n- Deep cuts.\n\n"
            "## Never Do\n- Never bypass.\n"
        )
        extracted = hs_mod._extract_operator_card_context(pack_with_card)
        if "OPERATOR CARD — Pro-Q 4" not in extracted:
            errors.append("_extract_operator_card_context did not extract Pro-Q 4 card")
    except Exception as exc:
        errors.append(f"harness_server import/smoke failed: {exc}")

    # ── build_message_pack return shape ──────────────────────────────────────
    mock_retrieval = _make_retrieval([])
    with patch.object(cpb, "classify", return_value=_minimal_classify()), \
         patch.object(cpb, "_get_project_id", return_value=""), \
         patch.object(cpb, "_routed_retrieve", return_value=mock_retrieval), \
         patch.object(cpb, "_detect_plugin", return_value=""), \
         patch.object(cpb, "_get_stable_card_id", return_value=None), \
         patch.object(cpb, "_load_card_snippet", return_value=""):
        result = cpb.build_message_pack("how do I compress a dhol")

    for key in ("ok", "pack", "mode", "risk_reason", "debug"):
        if key not in result:
            errors.append(f"build_message_pack missing key: {key}")
    for dkey in ("plugin_card", "memory_hits", "injected_count", "evidence"):
        if dkey not in result.get("debug", {}):
            errors.append(f"build_message_pack debug missing key: {dkey}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D168] {e}")
        print(f"  D168: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D168] Regression: Slice 14-16 symbols intact; build_message_pack shape correct")
    print(f"  D168: PASS")
    return True


# ── _get_stable_card_id unit tests ────────────────────────────────────────────

def run_d162b():
    """
    Unit test for _get_stable_card_id:
    - Returns correct stable ID when frontmatter card_id is present
    - Returns None when card_file is empty
    - Returns None when frontmatter is absent
    - Returns None when card_id field is missing from frontmatter
    """
    errors = []

    # Sub-case A: card with frontmatter card_id
    card_with_fm = (
        '---\ncard_id: "fabfilter_pro_q_4"\ndisplay_name: "Pro-Q 4"\n---\n'
        "# Operator Card — FabFilter Pro-Q 4\n"
    )
    with patch.object(cpb, "_read_file", return_value=card_with_fm):
        result = cpb._get_stable_card_id("Pro-Q 4 Operator Card.md")
    if result != "vault_plugin_fabfilter_pro_q_4":
        errors.append(f"[A] expected 'vault_plugin_fabfilter_pro_q_4', got {result!r}")

    # Sub-case B: empty card_file → None
    if cpb._get_stable_card_id("") is not None:
        errors.append("[B] expected None for empty card_file")

    # Sub-case C: card without frontmatter → None
    with patch.object(cpb, "_read_file", return_value="# Operator Card — Ozone 12\n"):
        result = cpb._get_stable_card_id("Ozone 12 Operator Card.md")
    if result is not None:
        errors.append(f"[C] expected None for card without frontmatter, got {result!r}")

    # Sub-case D: frontmatter without card_id → None
    card_no_cid = '---\ndisplay_name: "Ozone 12"\n---\n# Operator Card\n'
    with patch.object(cpb, "_read_file", return_value=card_no_cid):
        result = cpb._get_stable_card_id("Ozone 12 Operator Card.md")
    if result is not None:
        errors.append(f"[D] expected None for frontmatter without card_id, got {result!r}")

    if errors:
        for e in errors:
            print(f"  \033[91m✗\033[0m [D162b] _get_stable_card_id: {e}")
        print(f"  D162b: FAIL")
        return False
    print(f"  \033[92m✅\033[0m [D162b] _get_stable_card_id: correct stable ID; fails closed on missing/absent frontmatter")
    print(f"  D162b: PASS")
    return True


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    sections = [
        ("D162",  run_d162),
        ("D162b", run_d162b),
        ("D163",  run_d163),
        ("D164",  run_d164),
        ("D165",  run_d165),
        ("D166",  run_d166),
        ("D167",  run_d167),
        ("D168",  run_d168),
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
        print(f"\033[92m✅\033[0m Phase D Slice 17 — Plugin Knowledge Routing v1: {passed}/{total} sections passed")
        print("OVERALL: PASS")
    else:
        print(f"\033[91m❌\033[0m Phase D Slice 17 — Plugin Knowledge Routing v1: {passed}/{total} sections passed")
        print("OVERALL: FAIL")
    print('=' * 60)
    return passed == total


if __name__ == "__main__":
    ok = run_all()
    sys.exit(0 if ok else 1)
