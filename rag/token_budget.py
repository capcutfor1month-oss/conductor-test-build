"""
Conductor — Token Budget Policy (C3 Layer C)
─────────────────────────────────────────────
Applied AFTER evidence labeling (C1) and corrective RAG, before building
the injected set that goes into the prompt.

Drops lowest-priority injected items when total token_count exceeds
DEFAULT_BUDGET_TOKENS. Non-injected items are never touched (they are already
out of the pack).

Priority order (highest = protected):
  P0: memory_level == 4               (Never-Do — always keep regardless of budget)
  P1: collection == failure_cases_index  (failure/safety patterns — never drop)
  P2: memory_level == 3
  P3: memory_level == 2
  P4: memory_level == 1 or unknown

Within the same priority tier, items with higher final_score are kept first.

Dropped items:
    item.injected        = False
    item.reason          = "token_budget_exceeded"
    item.reason_injected = "not_injected"

The item REMAINS in debug.evidence so the UI can show why it was dropped.
"""

from typing import List

# ── CONFIG ────────────────────────────────────────────────────────────────────

DEFAULT_BUDGET_TOKENS = 2000   # ~8 000 chars; sensible default for Layer C evidence

# Collections whose items are safety-critical and must never be token-dropped
PROTECTED_COLLECTIONS = frozenset({"failure_cases_index"})


# ── PRIORITY ──────────────────────────────────────────────────────────────────

def _priority(item) -> int:
    """
    Return drop-priority: lower number = higher priority = protected last.
    Item with highest priority number is dropped first.
    """
    if getattr(item, "memory_level", 1) == 4:
        return 0   # Never-Do: absolutely protected
    col = getattr(item, "collection", "")
    if col in PROTECTED_COLLECTIONS:
        return 1   # safety / failure evidence: protected
    level = getattr(item, "memory_level", 1)
    if level == 3:
        return 2
    if level == 2:
        return 3
    return 4       # level 1 or unknown: dropped first


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def apply_token_budget(items: list, budget_tokens: int = DEFAULT_BUDGET_TOKENS) -> list:
    """
    Drop lowest-priority injected items until total token_count ≤ budget_tokens.

    Modifies items in-place. Returns the same list for chaining.

    Args:
        items:         Full retrieved list (EvidenceItem objects or duck-typed).
        budget_tokens: Max allowed token_count sum for injected items.

    Side effects on dropped items:
        .injected        = False
        .reason          = "token_budget_exceeded"
        .reason_injected = "not_injected"
    """
    injected = [i for i in items if getattr(i, "injected", False)]
    total = sum(getattr(i, "token_count", 0) for i in injected)

    if total <= budget_tokens:
        return items   # within budget — nothing to drop

    # Sort injected by drop-priority: lowest priority (drop first) at end.
    # Within same tier, lowest final_score dropped first.
    def _sort_key(item):
        score = getattr(item, "final_score", None)
        if score is None:
            score = getattr(item, "similarity", 0.0)
        return (_priority(item), -score)

    ordered = sorted(injected, key=_sort_key)

    # Drop from the end (lowest priority, lowest score) until within budget.
    # HARD STOP: never drop items whose priority < 2 (Level 4 or protected collections).
    # If all remaining candidates are protected, accept the budget overrun gracefully.
    while total > budget_tokens and ordered:
        # Peek: if next victim is protected (priority 0 or 1), stop dropping
        if _priority(ordered[-1]) < 2:
            break
        victim = ordered.pop()
        victim_tokens = getattr(victim, "token_count", 0)
        victim.injected        = False
        victim.reason          = "token_budget_exceeded"
        victim.reason_injected = "not_injected"
        total -= victim_tokens

    return items
