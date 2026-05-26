"""
Conductor — Never-Do Preflight Check (Phase D Slice 1)
──────────────────────────────────────────────────────
Deterministic check against never_do_rules.md before any risky Ableton write.

NO LLM calls.  NO fuzzy semantic matching.  NO network access.
Decision is produced by a static action-type table + context-based overrides.
The rules file is parsed to supply matching rule text (for logs/UI), but the
DECISION itself comes from the static table — not from NLP on the markdown.

Decision enum:
    ALLOW                — proceed without interruption
    HARD_BLOCK           — refuse, log NEVER_DO_BLOCKED, do not execute
    REQUIRE_CONFIRMATION — return the decision to the user; wait for "go ahead"
    UNDO_LOG_REQUIRED    — must capture prior_state before executing
    CLARIFY_REQUIRED     — action type not recognised; ask user to clarify

Rules file: conductor-vault/producer/never_do_rules.md
If the file is missing, the static table is still enforced and check() still
returns correct decisions for all known action types.  Rule text returned for
matched ALLOW cases will be "" (empty).

Slice 1 limitations (documented, not silent):
  - Rules are matched by keyword against the action_type string and context dict.
    Semantic NLP is not used.  A rule like "NEVER apply a cut deeper than -6dB"
    is only triggered when context includes plugin (EQ-related name) + value < -6.
  - Quantitative batch threshold: caller must pass context['track_count'] for
    batch rules to fire (e.g. "NEVER modify more than 3 tracks at once").
  - Project-specific overrides in the rules file are not yet parsed.
    They will be added in a later Slice once the override format is stabilised.
  - The parsed rules cache is module-level.  Call _clear_rules_cache() in tests
    that need a clean parser state.
"""

import os
import re
from enum import Enum
from typing import Dict, List, Optional, Tuple

# ── CONFIG ────────────────────────────────────────────────────────────────────

_HERE      = os.path.dirname(os.path.abspath(__file__))
_ROOT      = os.path.dirname(_HERE)
RULES_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")


# ── DECISION ENUM ──────────────────────────────────────────────────────────────

class NeverDoDecision(str, Enum):
    ALLOW                = "ALLOW"
    HARD_BLOCK           = "HARD_BLOCK"
    REQUIRE_CONFIRMATION = "REQUIRE_CONFIRMATION"
    UNDO_LOG_REQUIRED    = "UNDO_LOG_REQUIRED"
    CLARIFY_REQUIRED     = "CLARIFY_REQUIRED"


# ── STATIC DECISION TABLE ─────────────────────────────────────────────────────
# Canonical mapping: exact action_type string → NeverDoDecision.
# Both the literal string and its upper() form are tried.
# Context overrides (see below) can escalate a decision upward (e.g. ALLOW →
# HARD_BLOCK when target is "Master") but never de-escalate.

_STATIC_DECISIONS: Dict[str, NeverDoDecision] = {

    # ── Safe mixer actions — ALLOW ────────────────────────────────────────────
    "SET_TRACK_VOLUME":      NeverDoDecision.ALLOW,
    "SET_TRACK_PAN":         NeverDoDecision.ALLOW,
    "SET_TRACK_MUTE":        NeverDoDecision.ALLOW,
    "SET_TRACK_SOLO":        NeverDoDecision.ALLOW,
    "SET_SEND_LEVEL":        NeverDoDecision.ALLOW,
    "SET_PLUGIN_PARAM":      NeverDoDecision.ALLOW,
    "ARM_TRACK":             NeverDoDecision.ALLOW,
    "RENAME_TRACK":          NeverDoDecision.ALLOW,   # single track — OK

    # ── Destructive — HARD BLOCK ──────────────────────────────────────────────
    # These are non-negotiable.  No confirmation is sufficient.
    "DELETE_CLIP":           NeverDoDecision.HARD_BLOCK,
    "DELETE_DEVICE":         NeverDoDecision.HARD_BLOCK,
    "REMOVE_NOTES":          NeverDoDecision.HARD_BLOCK,
    "CLEAR_NOTES":           NeverDoDecision.HARD_BLOCK,
    "OVERWRITE_EXPORT":      NeverDoDecision.HARD_BLOCK,
    # Master bus actions require UNDO_LOG_REQUIRED — not HARD_BLOCK — because
    # they are sometimes valid (e.g. adding a limiter to master intentionally).
    # BUT context-based override escalates to HARD_BLOCK if action is flagged
    # as destructive (see _context_override).

    # ── Requires explicit user confirmation ───────────────────────────────────
    # DELETE_TRACK: destructive and NOT reversible via Conductor.
    # No compensating LOM call can restore a deleted track's content.
    # Requires explicit confirm=True in the request body.  undo_eligible=False always.
    "DELETE_TRACK":          NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_TEMPO":             NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_KEY":               NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_SCALE":             NeverDoDecision.REQUIRE_CONFIRMATION,
    "WARP_AUDIO":            NeverDoDecision.REQUIRE_CONFIRMATION,
    "EXPORT_AUDIO":          NeverDoDecision.REQUIRE_CONFIRMATION,
    "EXPORT_STEMS":          NeverDoDecision.REQUIRE_CONFIRMATION,
    "EXPORT_BOUNCE":         NeverDoDecision.REQUIRE_CONFIRMATION,
    "BATCH_RENAME_TRACKS":   NeverDoDecision.REQUIRE_CONFIRMATION,
    "BATCH_MODIFY_TRACKS":   NeverDoDecision.REQUIRE_CONFIRMATION,
    "BATCH_CREATE_TRACKS":   NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_OUTPUT_ROUTING":    NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_INPUT_ROUTING":     NeverDoDecision.REQUIRE_CONFIRMATION,
    "CHANGE_MONITOR_MODE":   NeverDoDecision.REQUIRE_CONFIRMATION,
    "SET_TRACK_ROUTE":       NeverDoDecision.REQUIRE_CONFIRMATION,
    "TRANSPORT_RECORD":      NeverDoDecision.REQUIRE_CONFIRMATION,
    "STOP_ALL_CLIPS":        NeverDoDecision.REQUIRE_CONFIRMATION,
    "LOAD_PLUGIN":           NeverDoDecision.REQUIRE_CONFIRMATION,
    "SAVE_MEMORY":           NeverDoDecision.REQUIRE_CONFIRMATION,
    "PROMOTE_MEMORY":        NeverDoDecision.REQUIRE_CONFIRMATION,

    # ── High risk — must capture prior_state first ────────────────────────────
    "MODIFY_MASTER_BUS":     NeverDoDecision.UNDO_LOG_REQUIRED,
    "ADD_MASTER_DEVICE":     NeverDoDecision.UNDO_LOG_REQUIRED,
    "REMOVE_MASTER_DEVICE":  NeverDoDecision.UNDO_LOG_REQUIRED,
    "APPLY_MASTER_PROCESSING": NeverDoDecision.UNDO_LOG_REQUIRED,

    # ── Action Expansion (Slice 1 — Track / Recording) ───────────────────────
    "CREATE_TRACK":          NeverDoDecision.ALLOW,
    "CREATE_AUDIO_TRACK":    NeverDoDecision.ALLOW,
    "CREATE_RETURN_TRACK":   NeverDoDecision.ALLOW,
    "DUPLICATE_TRACK":       NeverDoDecision.ALLOW,
    # ARM_TRACK already defined above as ALLOW
    "SET_TRACK_MONITOR":     NeverDoDecision.ALLOW,
    # RENAME_TRACK already defined above as ALLOW
    "SET_TRACK_COLOR":       NeverDoDecision.ALLOW,

    # ── Action Expansion (Slice 2 — Routing / Sends / Transport) ─────────────
    "SET_TRACK_SEND":        NeverDoDecision.ALLOW,
    "TRANSPORT_PLAY":        NeverDoDecision.ALLOW,
    "TRANSPORT_STOP":        NeverDoDecision.ALLOW,
    "TRANSPORT_LOOP":        NeverDoDecision.ALLOW,
    "TRANSPORT_METRONOME":   NeverDoDecision.ALLOW,

    # ── Action Expansion (Slice 3A — Plugin bypass) ───────────────────────────
    "PLUGIN_BYPASS":         NeverDoDecision.ALLOW,
}

# ── CONTEXT OVERRIDE RULES ────────────────────────────────────────────────────

# Any target string containing one of these keywords triggers master-bus escalation
_MASTER_KEYWORDS: frozenset = frozenset({
    "master", "master bus", "master_bus", "1/2",
})

# Batch threshold — if track_count > this and base decision is ALLOW,
# escalate to REQUIRE_CONFIRMATION
_BATCH_THRESHOLD = 3

# EQ cut depth that triggers REQUIRE_CONFIRMATION for EQ plugins
_EQ_CUT_THRESHOLD_DB = -6.0

# Plugin name fragments that identify EQ tools
_EQ_PLUGIN_FRAGMENTS: frozenset = frozenset({
    "eq", "pro-q", "proq", "pro q", "equalizer", "equaliser",
    "fabfilter", "ssl eq",
})


# ── PARSED RULE CACHE ─────────────────────────────────────────────────────────

_parsed_rules_cache: "Optional[List[str]]" = None


def _get_parsed_rules() -> "List[str]":
    """
    Parse never_do_rules.md and return a list of NEVER rule strings.
    Result is module-level cached after the first call.
    Returns [] if the file is missing or unreadable — decisions still work.
    Call _clear_rules_cache() to reset (tests only).
    """
    global _parsed_rules_cache
    if _parsed_rules_cache is not None:
        return _parsed_rules_cache
    try:
        with open(RULES_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        rules: List[str] = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped.startswith("- NEVER"):
                rules.append(stripped[2:].strip())   # strip leading "- "
        _parsed_rules_cache = rules
        return rules
    except FileNotFoundError:
        _parsed_rules_cache = []
        return []
    except Exception:
        _parsed_rules_cache = []
        return []


def _clear_rules_cache() -> None:
    """Reset the parsed-rules cache.  For test isolation only."""
    global _parsed_rules_cache
    _parsed_rules_cache = None


# ── PUBLIC API ─────────────────────────────────────────────────────────────────

def check(
    action_type: str,
    context: "Optional[Dict]" = None,
) -> "Tuple[NeverDoDecision, str]":
    """
    Check one action against never-do rules.

    Args:
        action_type:   Canonical action string, e.g. "SET_TRACK_VOLUME".
                       Case-insensitive via upper() fallback.
        context:       Optional dict with additional information:
                         target      (str)   — what is being modified
                         track_name  (str)   — track name (alias for target)
                         track_count (int)   — number of tracks in a batch op
                         plugin      (str)   — plugin name (plugin-specific rules)
                         value       (float) — parameter value (e.g. EQ gain in dB)
                         project_id  (str)   — project name (future: per-project rules)

    Returns:
        (NeverDoDecision, rule_text: str)

        rule_text is the matching NEVER rule from the rules file, or a
        description of the override that triggered the decision.
        rule_text is "" for pure ALLOW cases with no rule match.

    Guarantees:
        - Deterministic: same inputs always produce the same output.
        - No LLM calls.  No network.  No Ableton connection required.
        - Never raises.  Returns CLARIFY_REQUIRED for unknown action types.
    """
    ctx = context or {}

    # ── 1. Static table lookup ─────────────────────────────────────────────────
    base_decision = (
        _STATIC_DECISIONS.get(action_type)
        or _STATIC_DECISIONS.get(action_type.upper())
    )

    if base_decision is None:
        return (
            NeverDoDecision.CLARIFY_REQUIRED,
            f"Action type {action_type!r} is not in the known action table. "
            "Clarify intent before executing.",
        )

    # ── 2. Context-based escalation ────────────────────────────────────────────
    escalation = _context_override(action_type, base_decision, ctx)
    if escalation is not None:
        escalated_decision, rule_text = escalation
        return escalated_decision, rule_text

    # ── 3. Match rule text from file for audit/UI (does not change decision) ───
    rule_text = _match_rule_text(action_type, ctx)

    return base_decision, rule_text


def check_allows(action_type: str, context: "Optional[Dict]" = None) -> bool:
    """Convenience: True only if decision is ALLOW."""
    decision, _ = check(action_type, context)
    return decision == NeverDoDecision.ALLOW


def is_hard_block(action_type: str, context: "Optional[Dict]" = None) -> bool:
    """Convenience: True only if decision is HARD_BLOCK."""
    decision, _ = check(action_type, context)
    return decision == NeverDoDecision.HARD_BLOCK


# ── INTERNALS ─────────────────────────────────────────────────────────────────

def _context_override(
    action_type: str,
    base_decision: NeverDoDecision,
    ctx: dict,
) -> "Optional[Tuple[NeverDoDecision, str]]":
    """
    Check context-based escalation rules.  Returns (decision, rule_text) if an
    override applies, or None if base_decision stands unchanged.
    """
    target      = (ctx.get("target") or ctx.get("track_name") or "").lower().strip()
    track_count = int(ctx.get("track_count") or 1)
    plugin      = (ctx.get("plugin") or "").lower().strip()
    value       = ctx.get("value")

    # ── Master-bus escalation ──────────────────────────────────────────────────
    # Any write action targeting "master" (or "Master Bus", "1/2", etc.)
    # escalates to HARD_BLOCK.  The never-do rule requires explicit "go ahead"
    # confirmation for destructive master-bus processing — we block by default
    # and let the never-do review gate allow through if confirmed.
    if target and any(kw in target for kw in _MASTER_KEYWORDS):
        if base_decision in (NeverDoDecision.ALLOW, NeverDoDecision.REQUIRE_CONFIRMATION):
            return (
                NeverDoDecision.HARD_BLOCK,
                "NEVER apply destructive processing to master bus without "
                "explicit 'go ahead' confirmation",
            )

    # ── Batch escalation ───────────────────────────────────────────────────────
    if track_count > _BATCH_THRESHOLD and base_decision == NeverDoDecision.ALLOW:
        return (
            NeverDoDecision.REQUIRE_CONFIRMATION,
            f"NEVER run a for-loop that modifies more than {_BATCH_THRESHOLD} "
            f"tracks without showing the plan first ({track_count} tracks requested)",
        )

    # ── EQ deep-cut escalation ─────────────────────────────────────────────────
    if plugin and any(frag in plugin for frag in _EQ_PLUGIN_FRAGMENTS):
        if value is not None:
            try:
                val_f = float(value)
                if val_f < _EQ_CUT_THRESHOLD_DB:
                    if base_decision == NeverDoDecision.ALLOW:
                        return (
                            NeverDoDecision.REQUIRE_CONFIRMATION,
                            f"NEVER apply a cut deeper than {_EQ_CUT_THRESHOLD_DB}dB "
                            f"without explaining why (requested: {val_f}dB)",
                        )
            except (TypeError, ValueError):
                pass

    return None   # base_decision stands


def _match_rule_text(action_type: str, ctx: dict) -> str:
    """
    Search the parsed rules file for a line that matches action_type or context.
    Returns the first matching rule string, or "" if none match.
    Decision is NOT affected by this function — it is used only for logging/UI.
    """
    rules = _get_parsed_rules()
    if not rules:
        return ""

    # Build search tokens from action_type and context
    search_terms: set = set()
    for token in re.split(r"[_\s]+", action_type.lower()):
        if token:
            search_terms.add(token)

    target = (ctx.get("target") or ctx.get("track_name") or "").lower()
    if target:
        for token in target.split():
            if token:
                search_terms.add(token)

    # Remove overly common tokens that would match every rule
    search_terms.discard("set")
    search_terms.discard("track")
    search_terms.discard("get")

    for rule in rules:
        rule_lower = rule.lower()
        for term in search_terms:
            if len(term) > 2 and term in rule_lower:
                return rule
    return ""
