"""
Conductor — Memory Scoring (C2)
────────────────────────────────
Temporal-weighted scoring for retrieved ChromaDB evidence.

Replaces the flat similarity × retrieval_weight sort in routed_retriever._sort_by_weight().

final_score = semantic × 0.60 + recency × 0.30 + frequency × 0.10

Weights and decay parameters are config-driven (memory_schema.py).
Level 4 memories bypass all scoring and always float to top (score = 9999).

Generalization rule:
  This scorer applies to ALL 5 collections identically.
  Do not add per-collection special cases here — use per-collection thresholds
  in memory_schema.SIMILARITY_THRESHOLDS for that.

C2.1 TODO — frequency tracking:
  frequency_score is currently stubbed at 0.5 (neutral).
  Real tracking requires incrementing access_count in ChromaDB metadata on
  every successful retrieval — adds a write to the hot read path.
  Deferring until a background-write strategy is designed so retrieval
  latency stays under 50ms.
"""

import math
import datetime
from typing import TYPE_CHECKING

from rag.memory_schema import (
    MEMORY_LEVELS,
    SCORING_WEIGHTS,
    RECENCY_HALF_LIFE_DAYS,
    LEVEL_4_BYPASSES_THRESHOLD,
)

if TYPE_CHECKING:
    from rag.routed_retriever import EvidenceItem


# ── CONSTANTS ─────────────────────────────────────────────────────────────────

# Decay rate λ = ln(2) / half_life  →  score = e^(-λ × age_days)
_LAMBDA = math.log(2) / RECENCY_HALF_LIFE_DAYS

# Neutral frequency score until C2.1 adds real tracking
_FREQUENCY_STUB = 0.5

# Level 4 sentinel — always wins, no matter how old
_LEVEL_4_SCORE = 9999.0


# ── RECENCY SCORING ───────────────────────────────────────────────────────────

def recency_score(created_at_iso: str) -> float:
    """
    Exponential decay on created_at timestamp.

    Returns a value in [0, 1]:
        age = 0 days  →  1.0  (just written)
        age = 7 days  →  0.5  (half-life, configurable via RECENCY_HALF_LIFE_DAYS)
        age = 14 days →  0.25
        age → ∞       →  ~0.0

    Graceful degradation:
        missing or unparseable created_at → 0.5 (neutral — no penalty, no bonus)
    """
    if not created_at_iso:
        return 0.5  # neutral: unknown age

    try:
        # Handle both naive and timezone-aware ISO-8601 strings
        ts = created_at_iso.replace("Z", "+00:00")
        then = datetime.datetime.fromisoformat(ts)
        # Normalise to UTC-aware for comparison
        if then.tzinfo is None:
            then = then.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        age_days = max(0.0, (now - then).total_seconds() / 86400.0)
        return math.exp(-_LAMBDA * age_days)
    except Exception:
        return 0.5  # neutral on any parse error


def frequency_score(access_count: int) -> float:
    """
    Normalised access-count score.

    C2.1 stub — returns _FREQUENCY_STUB (0.5) regardless of access_count.

    Future: log-normalise access_count against collection max so a memory
    accessed 50× doesn't dominate one accessed 5×.
    Signature kept stable so C2.1 only changes the body.

    TODO C2.1: implement log-normalised frequency
        max_count = collection-level max access_count (pass as arg or cache)
        if max_count <= 1: return 0.5
        return math.log1p(access_count) / math.log1p(max_count)
    """
    return _FREQUENCY_STUB


# ── COMPOSITE SCORER ──────────────────────────────────────────────────────────

def score_item(item: "EvidenceItem") -> float:
    """
    Compute the final ranking score for one retrieved EvidenceItem.

    Priority:
        Level 4 (Never-Do / Producer rule) → 9999 — always first
        All others                          → weighted composite

    Formula:
        final = semantic × W_sem + recency × W_rec + frequency × W_freq

    Metadata fields read from item (set by _query_collection):
        item.similarity        — cosine similarity (0–1)
        item.memory_level      — 1–4
        item._meta_created_at  — ISO-8601 string or "" (stashed by retriever)
        item._meta_access_count — int or 0 (stashed by retriever)

    Note: _meta_* fields are stashed by routed_retriever._query_collection()
    using the same pattern as _meta_rejected and _meta_superseded_by.
    """
    # Level 4 always tops — bypasses all scoring
    if item.memory_level == 4 and LEVEL_4_BYPASSES_THRESHOLD:
        return _LEVEL_4_SCORE

    # Semantic component
    sem = item.similarity * SCORING_WEIGHTS["semantic"]

    # Recency component — read created_at from stashed metadata
    created_at = getattr(item, "_meta_created_at", "")
    rec = recency_score(created_at) * SCORING_WEIGHTS["recency"]

    # Frequency component (stub)
    access_count = getattr(item, "_meta_access_count", 0)
    freq = frequency_score(access_count) * SCORING_WEIGHTS["frequency"]

    return sem + rec + freq


def score_items_debug(item: "EvidenceItem") -> dict:
    """
    Same as score_item() but returns a breakdown dict for debug views.
    Used by tests and the debug evidence panel.
    """
    if item.memory_level == 4 and LEVEL_4_BYPASSES_THRESHOLD:
        return {
            "final":     _LEVEL_4_SCORE,
            "semantic":  item.similarity,
            "recency":   1.0,
            "frequency": 1.0,
            "override":  "level_4",
        }

    created_at   = getattr(item, "_meta_created_at",   "")
    access_count = getattr(item, "_meta_access_count", 0)
    r_score = recency_score(created_at)
    f_score = frequency_score(access_count)

    return {
        "final":     item.similarity * SCORING_WEIGHTS["semantic"]
                     + r_score       * SCORING_WEIGHTS["recency"]
                     + f_score       * SCORING_WEIGHTS["frequency"],
        "semantic":  item.similarity,
        "recency":   round(r_score, 4),
        "frequency": round(f_score, 4),
        "age_days":  _age_days(created_at),
        "override":  "",
    }


def _age_days(created_at_iso: str) -> float:
    """Return age in days for debug display. -1 if unknown."""
    if not created_at_iso:
        return -1.0
    try:
        ts   = created_at_iso.replace("Z", "+00:00")
        then = datetime.datetime.fromisoformat(ts)
        if then.tzinfo is None:
            then = then.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        return round((now - then).total_seconds() / 86400.0, 2)
    except Exception:
        return -1.0


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__file__)))

    print("\n── Memory Scoring (C2) self-test ────────────────────────────────")

    # Recency decay checks
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    week_ago = (datetime.datetime.now(datetime.timezone.utc)
                - datetime.timedelta(days=7)).isoformat()
    month_ago = (datetime.datetime.now(datetime.timezone.utc)
                 - datetime.timedelta(days=30)).isoformat()

    r_now   = recency_score(now_iso)
    r_week  = recency_score(week_ago)
    r_month = recency_score(month_ago)
    r_none  = recency_score("")

    print(f"\n  Recency decay (half-life={RECENCY_HALF_LIFE_DAYS} days):")
    print(f"    now      → {r_now:.4f}  (expect ~1.0)")
    print(f"    7 days   → {r_week:.4f}  (expect ~0.5)")
    print(f"    30 days  → {r_month:.4f}  (expect ~0.09)")
    print(f"    missing  → {r_none:.4f}  (expect 0.5 — neutral)")

    cases = [
        (r_now   > 0.95,   "recent memory → high recency score"),
        (0.45 < r_week < 0.55, "7-day memory → ~0.5 (half-life)"),
        (r_month < 0.15,   "30-day memory → low recency score"),
        (r_none  == 0.5,   "missing created_at → neutral 0.5"),
    ]

    # Composite scoring simulation
    class _MockItem:
        def __init__(self, sim, level, created_at, access_count=0):
            self.similarity         = sim
            self.memory_level       = level
            self._meta_created_at   = created_at
            self._meta_access_count = access_count
            self.injected           = True

    recent_item = _MockItem(0.6, 2, now_iso)
    old_item    = _MockItem(0.6, 2, month_ago)
    level4_item = _MockItem(0.3, 4, month_ago)  # old but Level 4

    s_recent = score_item(recent_item)
    s_old    = score_item(old_item)
    s_l4     = score_item(level4_item)

    print(f"\n  Composite score (same similarity=0.6):")
    print(f"    recent (now)    → {s_recent:.4f}")
    print(f"    old (30 days)   → {s_old:.4f}")
    print(f"    level-4 (old)   → {s_l4:.4f}  (expect 9999)")

    cases += [
        (s_recent > s_old, "recent beats same-similarity old memory"),
        (s_l4 == _LEVEL_4_SCORE, "level-4 always returns 9999"),
        (s_recent < 1.0, "score bounded (not trivially 1)"),
    ]

    passed = failed = 0
    print(f"\n  Assertions:")
    for ok, desc in cases:
        sym = "✅" if ok else "❌"
        print(f"    {sym} {desc}")
        if ok:
            passed += 1
        else:
            failed += 1

    print(f"\n  {passed}/{passed+failed} pass")
    sys.exit(0 if failed == 0 else 1)
