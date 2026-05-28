"""
Build 9 — Seeder Safety Tests
==============================
Proves that seed_operator_cards() never calls delete() on plugin_operator_index,
so unrelated IDs (e.g. user_plugin_note_123) are never touched.

Uses unittest.mock only — no live ChromaDB required.
"""

import os
import sys
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "tools"))
sys.path.insert(0, _ROOT)

import conductor_bridge as _cb  # noqa: E402


def run_seeder_safety():
    passed = 0
    failed = 0

    def ok(label):
        nonlocal passed
        passed += 1
        print(f"  ✅ {label}")

    def fail(label, detail=""):
        nonlocal failed
        failed += 1
        msg = f"  ❌ {label}"
        if detail:
            msg += f"\n       {detail}"
        print(msg)

    # ── B9-S1: unrelated IDs are NOT deleted ─────────────────────────────────
    print("\n── B9-S1: seed_operator_cards() does not delete unrelated IDs ──")

    # Mock collection already contains one unrelated ID and one stable card ID.
    mock_col = MagicMock()
    mock_col.get.return_value = {
        "ids": ["user_plugin_note_123", "vault_plugin_pro_q_4"]
    }
    mock_col.upsert.return_value = None

    _dummy_meta = {
        "collection": "plugin_operator_index",
        "memory_level": 3,
        "source_type": "operator_card",
        "created_at": "",
        "updated_at": "",
    }

    with patch.object(_cb, "get_collection", return_value=mock_col), \
         patch.object(_cb, "CHROMA_AVAILABLE", True), \
         patch.object(_cb, "make_metadata", return_value=_dummy_meta):
        try:
            result = _cb.seed_operator_cards()
        except Exception as exc:
            fail("seed_operator_cards() raised an unexpected exception", str(exc))
            print(f"\n  Seeder safety: {passed} pass / {failed} fail")
            return False

    # delete() must never have been called.
    if mock_col.delete.called:
        fail(
            "delete() was called — unrelated IDs are at risk",
            f"calls: {mock_col.delete.call_args_list}",
        )
    else:
        ok("delete() was NOT called — unrelated IDs in plugin_operator_index are safe")

    # upsert() should have been called (seeder still does its job).
    if mock_col.upsert.called:
        ok(f"upsert() was called {mock_col.upsert.call_count} time(s) — cards seeded normally")
    else:
        # Warn only — vault_dir may genuinely have no .md files in some CI envs.
        print("  ⚠️  upsert() not called — vault_dir may be empty or unreachable")

    # ── B9-S2: empty collection — delete() still never called ────────────────
    print("\n── B9-S2: delete() not called even when collection is empty ──")

    mock_col2 = MagicMock()
    mock_col2.get.return_value = {"ids": []}
    mock_col2.upsert.return_value = None

    with patch.object(_cb, "get_collection", return_value=mock_col2), \
         patch.object(_cb, "CHROMA_AVAILABLE", True), \
         patch.object(_cb, "make_metadata", return_value=_dummy_meta):
        try:
            _cb.seed_operator_cards()
        except Exception as exc:
            fail("seed_operator_cards() raised on empty collection", str(exc))

    if mock_col2.delete.called:
        fail(
            "delete() called on empty collection",
            f"calls: {mock_col2.delete.call_args_list}",
        )
    else:
        ok("delete() NOT called on empty collection")

    print(f"\n  Seeder safety: {passed} pass / {failed} fail")
    return failed == 0


if __name__ == "__main__":
    print("=" * 60)
    print("  Build 9 — Seeder Safety Tests")
    print("=" * 60)
    ok = run_seeder_safety()
    print("\n" + "=" * 60)
    if ok:
        print("  ✅ All seeder safety checks passed")
    else:
        print("  ❌ Some seeder safety checks failed")
    print("=" * 60)
    sys.exit(0 if ok else 1)
