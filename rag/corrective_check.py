"""
Conductor — Corrective RAG (C3)
────────────────────────────────
Two-layer contradiction and supersession protection.

Layer 1 — Write-time (called by conductor_bridge.py POST /memory):
    When a new memory is saved, similar existing memories in the same
    collection are automatically marked superseded_by=new_id in ChromaDB.
    These are then filtered at read time by routed_retriever._apply_threshold().

Layer 2 — Read-time in-flight check (called by routed_retriever.retrieve()):
    After retrieval and threshold filtering, scan the injected set for pairs
    that weren't caught at write time (e.g. pre-existing data). Newer wins;
    older gets injected=False and a C3 skip_reason.

Algorithm:
    Contradiction = two memories in the same collection with Jaccard token
    similarity ≥ CONTRADICTION_OVERLAP_THRESHOLD. Newer (lower age_days) wins.
    On equal age, higher final_score wins. On tie: first item wins.

Design rule (Generalization-First):
    Thresholds live here. Do not add per-topic special cases.
    Add new stopwords to _STOPWORDS, not new branches.
"""

import re
from typing import List


# ── CONFIG ────────────────────────────────────────────────────────────────────

# Minimum Jaccard overlap to treat two memories as "about the same thing"
CONTRADICTION_OVERLAP_THRESHOLD = 0.40

# Write-time: minimum cosine similarity to even consider write-time suppression
WRITE_TIME_SIM_THRESHOLD = 0.70

# Write-time: how many existing items to check when a new memory is saved
WRITE_TIME_N_CHECK = 5

_MIN_TOKEN_LEN = 3
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "this", "that", "from", "into", "have",
    "was", "are", "not", "but", "can", "use", "set", "get", "its", "our",
    "you", "all", "had", "has", "his", "her", "they", "than", "then",
    "when", "will", "been", "also", "very", "its",
})


# ── TOKEN HELPERS ─────────────────────────────────────────────────────────────

def _tokens(text: str) -> frozenset:
    """Significant lowercase tokens from text."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return frozenset(w for w in words if len(w) >= _MIN_TOKEN_LEN and w not in _STOPWORDS)


def _jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _item_age(item) -> float:
    """Age in days; unknown (-1) → treated as very old (999) so newer item wins."""
    age = getattr(item, "age_days", -1.0)
    return 999.0 if age < 0 else age


# ── LAYER 2 — READ-TIME IN-FLIGHT CHECK ───────────────────────────────────────

def apply_corrective_check(items: list) -> list:
    """
    In-flight contradiction check on retrieved EvidenceItems.

    Groups by collection, compares every injected pair using Jaccard token
    overlap. When two items in the same collection are about the same thing
    (overlap ≥ threshold), the older one is suppressed in-memory:
        item.injected = False
        item.reason   = "in-flight superseded by <id> (C3 contradiction: Jaccard=…)"

    Does NOT write to ChromaDB — modifies items in-place.
    Called by routed_retriever.retrieve() after _apply_threshold().
    """
    # Group by collection — contradictions only matter within the same collection
    by_coll: dict = {}
    for item in items:
        by_coll.setdefault(item.collection, []).append(item)

    for coll_items in by_coll.values():
        # Only compare currently-injected items
        injected = [i for i in coll_items if i.injected]
        for i in range(len(injected)):
            for j in range(i + 1, len(injected)):
                a, b = injected[i], injected[j]
                # Skip pairs already suppressed in an earlier iteration
                if not a.injected or not b.injected:
                    continue

                # ── C4: Scope-aware guards ────────────────────────────────────
                # Guard 1 — Different project scope: same text in different
                # projects is NOT a contradiction.  Only check when both items
                # carry a non-empty project_id AND they differ.
                proj_a = str(getattr(a, "project_id", "") or "")
                proj_b = str(getattr(b, "project_id", "") or "")
                if proj_a and proj_b and proj_a != proj_b:
                    continue   # different projects — never supersede

                # Guard 2 — Different plugin scope: same-topic memories for
                # different plugins (e.g. Pro-Q vs Neutron) should flag conflict
                # but NOT auto-suppress — the memories are both valid.
                plug_a = str(getattr(a, "plugin_id", "") or "")
                plug_b = str(getattr(b, "plugin_id", "") or "")
                if plug_a and plug_b and plug_a != plug_b:
                    # Set conflict_flag on both but do not suppress
                    if hasattr(a, "conflict_flag"): a.conflict_flag = True
                    if hasattr(b, "conflict_flag"): b.conflict_flag = True
                    continue

                tok_a = _tokens(a.text or "")
                tok_b = _tokens(b.text or "")
                jac   = _jaccard(tok_a, tok_b)
                if jac < CONTRADICTION_OVERLAP_THRESHOLD:
                    continue

                # Same topic — newer wins
                age_a, age_b = _item_age(a), _item_age(b)
                if age_a < age_b:
                    # a is newer → suppress b
                    b.injected = False
                    b.reason = (
                        f"in-flight superseded by {a.id or 'newer memory'} "
                        f"(C3 contradiction: Jaccard={jac:.2f})"
                    )
                    # C1 Step 1 — flag both items involved in a conflict
                    if hasattr(b, "conflict_flag"): b.conflict_flag = True
                    if hasattr(a, "conflict_flag"): a.conflict_flag = True
                elif age_b < age_a:
                    # b is newer → suppress a
                    a.injected = False
                    a.reason = (
                        f"in-flight superseded by {b.id or 'newer memory'} "
                        f"(C3 contradiction: Jaccard={jac:.2f})"
                    )
                    if hasattr(a, "conflict_flag"): a.conflict_flag = True
                    if hasattr(b, "conflict_flag"): b.conflict_flag = True
                else:
                    # Same age → suppress lower final_score
                    score_a = getattr(a, "final_score", a.similarity)
                    score_b = getattr(b, "final_score", b.similarity)
                    if score_a >= score_b:
                        b.injected = False
                        b.reason = (
                            f"in-flight superseded by {a.id or 'higher-scored memory'} "
                            f"(C3 contradiction: Jaccard={jac:.2f}, same age)"
                        )
                        if hasattr(b, "conflict_flag"): b.conflict_flag = True
                        if hasattr(a, "conflict_flag"): a.conflict_flag = True
                    else:
                        a.injected = False
                        a.reason = (
                            f"in-flight superseded by {b.id or 'higher-scored memory'} "
                            f"(C3 contradiction: Jaccard={jac:.2f}, same age)"
                        )
                        if hasattr(a, "conflict_flag"): a.conflict_flag = True
                        if hasattr(b, "conflict_flag"): b.conflict_flag = True

    return items


# ── LAYER 1 — WRITE-TIME SUPPRESSION ─────────────────────────────────────────

def find_superseded_by_new(col, new_text: str, new_id: str) -> List[str]:
    """
    Write-time check: find existing memories in col that are semantically
    AND lexically similar to new_text. Mark them superseded_by=new_id in
    ChromaDB so they are filtered at retrieval time.

    Returns list of old IDs that were updated.
    Called by conductor_bridge.py after col.add().

    Safety guards:
    - Only runs if collection has >1 item (can't supersede if this is first)
    - Requires both cosine similarity ≥ WRITE_TIME_SIM_THRESHOLD AND
      Jaccard ≥ CONTRADICTION_OVERLAP_THRESHOLD before marking
    - Skips items already marked as superseded_by (don't double-mark)
    """
    try:
        count = col.count() - 1   # exclude the just-written item
        if count <= 0:
            return []

        results = col.query(
            query_texts=[new_text],
            n_results=min(WRITE_TIME_N_CHECK, count),
            include=["documents", "metadatas", "distances"],
        )
        old_ids   = results.get("ids",       [[]])[0]
        old_docs  = results.get("documents", [[]])[0]
        old_metas = results.get("metadatas", [[]])[0]
        old_dists = results.get("distances", [[]])[0]

        tok_new = _tokens(new_text)
        updated: List[str] = []

        for old_id, old_doc, old_meta, dist in zip(
            old_ids, old_docs, old_metas, old_dists
        ):
            if old_id == new_id:
                continue
            meta = old_meta or {}
            if meta.get("superseded_by"):
                continue   # already superseded — don't chain

            # Require both semantic AND lexical similarity
            cosine_sim = max(0.0, 1.0 - dist)
            if cosine_sim < WRITE_TIME_SIM_THRESHOLD:
                continue
            tok_old = _tokens(old_doc or "")
            if _jaccard(tok_new, tok_old) < CONTRADICTION_OVERLAP_THRESHOLD:
                continue

            # Mark as superseded (write to ChromaDB)
            col.update(ids=[old_id], metadatas=[{**meta, "superseded_by": new_id}])
            updated.append(old_id)

        return updated

    except Exception:
        return []


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Corrective Check (C3) self-test ──")

    class _Item:
        def __init__(self, id_, text, age, score=0.7, col="producer_memory_index"):
            self.id          = id_
            self.text        = text
            self.age_days    = age
            self.final_score = score
            self.similarity  = score   # fallback used by apply_corrective_check
            self.collection  = col
            self.injected    = True
            self.reason      = ""

    def _check_jaccard(t1, t2):
        j = _jaccard(_tokens(t1), _tokens(t2))
        print(f"    Jaccard({t1[:40]!r}, {t2[:40]!r}) = {j:.3f}")
        return j

    # Scenario 1: two contradictory items — older should be suppressed.
    # Both texts share: compress, snare, fast, attack, slow, release, parallel,
    # compression → Jaccard ≥ 0.70 → well above threshold.
    old_txt = "compress snare fast attack slow release parallel compression punch technique"
    new_txt = "compress snare fast attack slow release parallel compression punch corrected improved"
    old = _Item("old_001", old_txt, age=14)
    new = _Item("new_001", new_txt, age=1)
    j1 = _check_jaccard(old_txt, new_txt)
    assert j1 >= CONTRADICTION_OVERLAP_THRESHOLD, f"expected Jaccard ≥ {CONTRADICTION_OVERLAP_THRESHOLD}, got {j1:.3f}"
    items = apply_corrective_check([old, new])
    assert new.injected,      "newer should stay injected"
    assert not old.injected,  "older should be suppressed"
    assert "C3 contradiction" in old.reason, f"reason should mention C3: {old.reason}"
    print("  ✅ older contradictory memory suppressed")

    # Scenario 2: unrelated items — both stay injected.
    a = _Item("a_001", "Use saturation drum bus warmth analog",         age=5)
    b = _Item("b_001", "Set reverb pre-delay vocal clarity presence",   age=5)
    j2 = _check_jaccard(a.text, b.text)
    apply_corrective_check([a, b])
    assert a.injected, "unrelated item a should stay injected"
    assert b.injected, "unrelated item b should stay injected"
    print("  ✅ unrelated memories both stay injected")

    # Scenario 3: same age — higher score wins.
    # Both about compress/snare/fast/attack/slow/release/ratio → high Jaccard.
    x_txt = "compress snare fast attack slow release ratio punch parallel bus glue"
    y_txt = "compress snare fast attack slow release ratio punch parallel bus thick"
    x = _Item("x_001", x_txt, age=3, score=0.8)
    y = _Item("y_001", y_txt, age=3, score=0.6)
    j3 = _check_jaccard(x_txt, y_txt)
    assert j3 >= CONTRADICTION_OVERLAP_THRESHOLD, f"test setup error: Jaccard={j3:.3f}"
    apply_corrective_check([x, y])
    assert x.injected,     "higher-score item should win"
    assert not y.injected, "lower-score item should be suppressed"
    print("  ✅ same age: higher-scored memory wins")

    # Scenario 4: cross-collection items never suppress each other.
    same_txt = "compress snare fast attack slow release ratio punch parallel bus"
    p = _Item("p_001", same_txt, age=14, col="producer_memory_index")
    f = _Item("f_001", same_txt, age=1,  col="failure_cases_index")
    apply_corrective_check([p, f])
    assert p.injected, "cross-collection: producer item should stay injected"
    assert f.injected, "cross-collection: failure item should stay injected"
    print("  ✅ cross-collection items never suppress each other")

    print("\n  All C3 self-tests passed")
