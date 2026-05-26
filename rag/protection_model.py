"""
Conductor protection model (v2)
─────────────────────────────────────────────────────────────────────
Assigns a protection level to a user message using five dimensions:

  1. Intent        — additive / write / destructive
  2. Target        — named track/bus, named group, resolved pronoun, ambiguous pronoun
  3. Scope         — single element | named instrument/role group | project-wide
  4. Reversibility — fully reversible | undo-log-recoverable | irreversible
  5. Effect type   — insert (reversible) | patch replace (medium) | destructive

Decision order (first match wins):
  1. BLOCK_UNSUPPORTED   — manual GUI / mouse requests
  2. CLARIFY_REQUIRED    — ambiguous pronoun target (no local referent in same message)
  3. AUTO_EXECUTE_ALLOWED — reversible effect inserts on named/group targets
                            (project-wide effect insert → CONFIRM_REQUIRED)
  4. AUTO_EXECUTE_ALLOWED — additive creates: new track, new bus, device on new target
  5. Risk taxonomy + scope disambiguation:
       scope-dependent category (batch_global, routing_change):
         project-wide  → CONFIRM_REQUIRED
         named group   → UNDO_LOG_REQUIRED
         unclear scope → CLARIFY_REQUIRED
  6. CONFIRM_REQUIRED    — unconditionally high-risk category
  7. UNDO_LOG_REQUIRED   — single-synth patch / preset replacement
  8. AUTO_EXECUTE_ALLOWED — general reversible write intent
  9. STATUS_ONLY         — no write action detected

Generalization-first rule:
  Decisions are driven by CATEGORY, not individual plugin names or single examples.
  Add new risky plugin types → TYPE_RISK_POLICIES in risk_taxonomy.py.
  Add new named-group words  → _NAMED_GROUP_WORDS below.
  Add new effect types       → _EFFECT_INSERT_NOUNS below.
"""

import re
from typing import Dict

from rag.risk_taxonomy import classify_risk


# ── PROTECTION LEVEL CONSTANTS ────────────────────────────────────────────────

STATUS_ONLY           = "STATUS_ONLY"
AUTO_EXECUTE_ALLOWED  = "AUTO_EXECUTE_ALLOWED"
UNDO_LOG_REQUIRED     = "UNDO_LOG_REQUIRED"
CLARIFY_REQUIRED      = "CLARIFY_REQUIRED"
CONFIRM_REQUIRED      = "CONFIRM_REQUIRED"
BLOCK_UNSUPPORTED     = "BLOCK_UNSUPPORTED"


# ── 1. UNSUPPORTED: manual GUI / mouse actions ────────────────────────────────
# Any request to physically operate the plugin GUI, drag sliders by hand,
# move the mouse, or perform actions that require physical UI interaction.

_UNSUPPORTED_RE = re.compile(
    # "open/show/click/drag/touch/move ... plugin gui / gui / window / mouse"
    r"\b(open|show|click|drag|touch|move)\b.{0,50}"
    r"\b(plugin\s+gui|gui|window|by\s+hand|with\s+(the\s+)?mouse)\b"
    r"|\b(plugin\s+gui|gui|window)\b.{0,50}"
    r"\b(open|show|click|drag|by\s+hand|with\s+(the\s+)?mouse)\b"
    # "tweak/drag/adjust the knob/fader/slider/wavetable visually/manually/by hand"
    r"|\b(tweak|drag|adjust|move)\b.{0,40}\b(knob|fader|slider|wavetable)\b.{0,40}"
    r"\b(visually|manually|by\s+hand|with\s+the\s+mouse|with\s+mouse)\b",
    re.IGNORECASE,
)


# ── 2. SCOPE: project-wide vs named instrument/role group ─────────────────────

# Project-wide scope: unambiguously means every track/element in the session.
# These ALWAYS require confirmation regardless of the action type.
_PROJECT_WIDE_RE = re.compile(
    r"\ball\s+tracks\b"
    r"|\bevery\s+track\b"
    r"|\bentire\s+project\b"
    r"|\bwhole\s+project\b"
    r"|\ball\s+(?:the\s+)?clips\b"
    r"|\badd\s+to\s+all\b"
    r"|\bapply\s+to\s+all\b"
    r"|\bglobal\s+tempo\b"
    r"|\bglobal\s+key\b"
    r"|\breplace\s+plugins?\s+on\s+all\b"
    r"|\ball\s+plugins\b",
    re.IGNORECASE,
)

# Named instrument/role group — "all backing vocals", "every guitar track", etc.
# These are clear limited groups: a specific instrument family or mix role.
# Config-driven: add new group words here to extend coverage.
_NAMED_GROUP_WORDS = (
    # Vocals
    r"backing\s+vocal|lead\s+vocal|ad[- ]?lib|adlib|vocal|voice|vox|"
    # Guitar family
    r"guitar|gtr|acoustic\s+guitar|electric\s+guitar|bass\s+guitar|"
    # Strings
    r"string|violin|viola|cello|double\s+bass|contrabass|"
    # Brass / woodwinds
    r"brass|woodwind|trumpet|horn|french\s+horn|trombone|tuba|flute|oboe|clarinet|bassoon|"
    # Keys / pads
    r"pad|synth\s+pad|piano|keys?|keyboard|organ|"
    # Drums / percussion
    r"kick|snare|hi[- ]?hat|overhead|tom|drum|cymbal|percussion|perc|"
    # Bass
    r"bass|sub|808|"
    # Generic mix groups
    r"sample|loop|layer|effect|fx|instrument|stem"
)
_NAMED_GROUP_RE = re.compile(
    r"\b(?:all|every)\s+(?:" + _NAMED_GROUP_WORDS + r")\w*"
    r"(?:\s+(?:track|bus|channel|group|stem|part))?\b",
    re.IGNORECASE,
)


# ── 3. EFFECT INSERT: reversible inserts on any named target ──────────────────
# Effect inserts are always removable → reversible by definition.
# Even inserting on "all backing vocals" is UNDO-safe: each device can be removed.
# Config-driven: add new effect type names to _EFFECT_INSERT_NOUNS.

_EFFECT_INSERT_VERBS_PAT = r"(?:put|add|insert|load|apply|place|chain)"
_EFFECT_INSERT_NOUNS_PAT = (
    r"compressor|compression|"
    r"eq\b|equalizer|equaliser|"
    r"reverb\b|"
    r"delay\b|"
    r"saturation|saturator|tape\s+saturation|"
    r"chorus\b|"
    r"widener|stereo\s+widener|"
    r"de[- ]?esser|"
    r"distortion|tape\s+distortion|clipper|"
    r"phaser|flanger|tremolo|enhancer|exciter|transient\s+shaper|"
    r"limiter(?!\s+ceiling)(?!\s+on\s+the\s+master)"  # limiter inserts on tracks are fine
)

_EFFECT_INSERT_RE = re.compile(
    # Insert verb followed by effect type name (up to 80 chars apart).
    # Verb-first requirement prevents questions ("what's the best EQ for…")
    # from triggering this check — those have no insert verb.
    r"\b(?:" + _EFFECT_INSERT_VERBS_PAT + r")\b.{0,80}\b(?:" + _EFFECT_INSERT_NOUNS_PAT + r")\b",
    re.IGNORECASE,
)


# ── 4. ADDITIVE CREATES: new tracks, buses, device inserts on new targets ─────
# Creates are always reversible (Ctrl+Z removes them).

_SAFE_ADDITIVE_RE = re.compile(
    # New track creation (MIDI, audio, instrument, or just "track")
    r"\b(?:create|add|load|insert)\b.{0,50}\bnew\b.{0,30}\b(?:midi|audio|instrument|track)\b"
    r"|\b(?:create|add)\b.{0,30}\btrack\b"
    r"|\bload\b.{0,40}\bon\s+a\s+new\s+track\b"
    # Bus creation: "create guitar bus", "create pad bus, bass bus, string bus"
    r"|\b(?:create|add|set\s+up|make)\b.{0,80}\b\w+\s+bus\b"
    # Named plugin/device insert on a specific named track (not "all tracks")
    r"|\b(?:load|insert|add)\b.{0,40}\b(?:on|to)\s+(?:the|a)\s+\w+\s+track\b",
    re.IGNORECASE,
)


# ── 5. AMBIGUOUS PRONOUN TARGET ───────────────────────────────────────────────
# When the action target is a bare pronoun (it/this/that/them) and there is no
# clear referent in the same message, ask one clarifying question.
# Category-based: covers all action verbs that need a specific named target.

_PRONOUN_ACTION_RE = re.compile(
    # Action verb immediately followed by it/this/that
    r"\b(?:lower|raise|boost|cut|turn\s+up|turn\s+down|turn|"
    r"route|send|move|set|change|adjust|compress|pan|mute|solo|"
    r"rename|delete|freeze|flatten|export)\s+(?:it|this|that)\b"
    # route/send [pronoun] to [destination]
    r"|\b(?:route|send)\s+(?:it|this|that|them)\s+to\b"
    # "make it/this/that [quality]" — e.g. "make it warmer", "make this brighter"
    r"|\bmake\s+(?:it|this|that)\s+(?:warmer|brighter|darker|louder|softer|"
    r"heavier|thinner|punchier|wider|narrower|bigger|smaller|"
    r"smoother|crispier|crisper|punchier|rounder|tighter|fatter)\b"
    # Short action + bare pronoun
    r"|\b(?:pan|compress|eq|tune|tweak)\s+(?:it|this|that)\b"
    # "turn it down/up/off/on"
    r"|\bturn\s+(?:it|this|that)\s+(?:up|down|off|on)\b"
    # "load a patch" with no named plugin target
    r"|\bload\s+a\s+patch\b(?!\s+(?:for|from|into|on)\s+\w)",
    re.IGNORECASE,
)


def _has_local_referent_for_them(msg: str) -> bool:
    """
    Return True when "them" in the message refers back to a list of named
    items (buses, tracks, channels) explicitly created or listed in the same message.

    Heuristic: the message contains ≥2 named things (word + bus/track/channel)
    BEFORE the word "them".

    Examples that resolve:
      "Create guitar bus, pad bus, bass bus and route them to Music Bus."
      "Create guitar bus, pad bus, bass bus, string bus, route matching tracks
       to them, then route all those buses to Music Bus."
    """
    # Extract the part of the message before the first "them"
    them_pos = msg.lower().find("them")
    if them_pos < 0:
        return False
    pre_them = msg[:them_pos]

    # Count named "X bus", "X track", "X channel" occurrences before "them"
    named_items = re.findall(
        r"\b\w+\s+(?:bus|track|channel|group)\b",
        pre_them,
        re.IGNORECASE,
    )
    # Two or more named items = sufficient to resolve "them"
    if len(named_items) >= 2:
        return True

    # Alternative: message has a comma-separated creation list
    # e.g. "guitar bus, pad bus, bass bus"
    comma_list = re.findall(r"\w+\s+bus\b", pre_them, re.IGNORECASE)
    return len(comma_list) >= 2


# ── 6. MEDIUM PATCH / PRESET REPLACEMENT ─────────────────────────────────────
# Replacing or randomizing a patch/preset on a single synth is reversible
# with an undo log entry — medium protection, not destructive.

_MEDIUM_PATCH_RE = re.compile(
    r"\b(?:replace|randomize|randomise|swap|change|reset)\b.{0,40}"
    r"\b(?:patch|preset|program|bank)\b"
    r"|\b(?:patch|preset|program|bank)\b.{0,40}"
    r"\b(?:replace|randomize|randomise|swap|change|reset)\b",
    re.IGNORECASE,
)


# ── 7. GENERAL WRITE INTENT ───────────────────────────────────────────────────
# Any message with a write-intent verb that cleared all checks above.

_WRITE_INTENT_RE = re.compile(
    r"\b(?:set|change|add|create|rename|adjust|tune|tweak|move|lower|raise|boost|cut|"
    r"filter|compress|route|load|enable|disable|turn\s+on|turn\s+off|mute|unmute|"
    r"solo|unsolo|program|write|send|patch|insert|arm|replace|randomize|randomise|"
    r"export|delete|flatten|freeze|push|pan)\b",
    re.IGNORECASE,
)


# ── HIGH-RISK CATEGORIES (unconditional) ─────────────────────────────────────
# These ALWAYS require explicit confirmation — irreversible or affect the
# final output chain / entire session structure.

_HIGH_RISK_CATEGORIES = {
    "destructive",       # delete, erase, clear, drop track
    "render_export",     # export, bounce, render, consolidate
    "mastering_output",  # master/output chain, LUFS, True Peak, ceiling
    "freeze_flatten",    # freeze/flatten (converts MIDI, original lost)
    "high_risk_plugin",  # explicitly flagged risk="high" plugins
    "type_mastering",    # mastering plugin type
    "type_limiter",      # limiter plugin type
}

# batch_global and routing_change are scope-dependent.
# They escalate to CONFIRM_REQUIRED only for project-wide scope.
_SCOPE_DEPENDENT_CATEGORIES = {"batch_global", "routing_change"}


# ── HELPERS ───────────────────────────────────────────────────────────────────

def _base(level: str, category: str, rationale: str,
          auto: bool, confirm: bool) -> Dict[str, object]:
    return {
        "protection_level":     level,
        "risk_category":        category,
        "rationale":            rationale,
        "auto_execute_allowed": auto,
        "confirmation_required": confirm,
    }


# ── MAIN CLASSIFIER ───────────────────────────────────────────────────────────

def classify_protection(message: str) -> Dict[str, object]:
    """
    Classify the protection level for a user message.

    Returns a dict with protection_level, risk_category, rationale,
    auto_execute_allowed, and confirmation_required.
    """
    msg = message.strip()

    # ── Step 1: Unsupported manual GUI / mouse action ─────────────────────────
    if _UNSUPPORTED_RE.search(msg):
        return _base(
            BLOCK_UNSUPPORTED, "unsupported_manual_gui",
            "Manual GUI/mouse actions cannot be automated; "
            "explain the limitation and suggest the MCP-accessible alternative.",
            False, False,
        )

    # ── Step 2: Ambiguous pronoun target ──────────────────────────────────────
    # Only fires when the action target is a bare pronoun with no clear referent.
    # "them" with a local list (buses/tracks named earlier) is resolved and skipped.
    has_lone_pronoun = bool(_PRONOUN_ACTION_RE.search(msg))
    if has_lone_pronoun:
        # Resolve "them" when a named list precedes it in the same message
        if re.search(r"\bthem\b", msg, re.IGNORECASE) and _has_local_referent_for_them(msg):
            has_lone_pronoun = False
    if has_lone_pronoun:
        return _base(
            CLARIFY_REQUIRED, "unclear_target",
            "Action target is a pronoun without a clear referent; "
            "ask one clarifying question (which track/bus/plugin?) before proceeding.",
            False, False,
        )

    # ── Step 3: Reversible effect inserts ────────────────────────────────────
    # Compressor / EQ / reverb / delay / etc. inserts are always removable.
    # Intercept BEFORE the risk taxonomy so "add reverb to all drums" doesn't
    # escalate to CONFIRM_REQUIRED just because batch_global fires.
    if _EFFECT_INSERT_RE.search(msg):
        if _PROJECT_WIDE_RE.search(msg):
            return _base(
                CONFIRM_REQUIRED, "batch_global_effect_insert",
                "Effect insert targeting all tracks / entire project — "
                "confirm scope before applying.",
                False, True,
            )
        return _base(
            AUTO_EXECUTE_ALLOWED, "effect_insert",
            "Reversible effect insert on named target or group; "
            "execute and report insertion point.",
            True, False,
        )

    # ── Step 4: Additive creates ──────────────────────────────────────────────
    # New tracks, buses, and device inserts on new/named targets are
    # fully reversible. Never interrupt producer flow for these.
    # Exception: additive phrasing with project-wide scope ("for all tracks",
    # "across every track") still requires confirmation — the implied routing
    # or assignment touches every element in the session.
    if _SAFE_ADDITIVE_RE.search(msg):
        if _PROJECT_WIDE_RE.search(msg):
            return _base(
                CONFIRM_REQUIRED, "batch_global",
                "Additive action targets all tracks / entire project — "
                "confirm scope before applying.",
                False, True,
            )
        return _base(
            AUTO_EXECUTE_ALLOWED, "safe_additive",
            "Additive track/bus/device creation — "
            "fully reversible, no confirmation needed.",
            True, False,
        )

    # ── Step 5: Risk taxonomy + scope disambiguation ─────────────────────────
    risk     = classify_risk(msg)
    category = risk.get("category", "")

    if category in _SCOPE_DEPENDENT_CATEGORIES:
        # Project-wide: every track, entire session → always confirm
        if _PROJECT_WIDE_RE.search(msg):
            return _base(
                CONFIRM_REQUIRED, category,
                risk.get("reason") or
                "Project-wide operation — confirm scope before proceeding.",
                False, True,
            )
        # Named instrument/role group: "all backing vocals", "every guitar track"
        # These are clear limited groups → reversible with an undo log entry.
        if _NAMED_GROUP_RE.search(msg):
            return _base(
                UNDO_LOG_REQUIRED, f"{category}_named_group",
                "Operation on a named instrument/role group — "
                "reversible; log the action and execute.",
                True, False,
            )
        # Ambiguous scope (no project-wide signal, no named group)
        return _base(
            CLARIFY_REQUIRED, f"{category}_unclear_scope",
            "Scope of this operation is unclear; "
            "ask which tracks or buses are the target before proceeding.",
            False, False,
        )

    # ── Step 6: Unconditionally high-risk categories ──────────────────────────
    if category in _HIGH_RISK_CATEGORIES:
        return _base(
            CONFIRM_REQUIRED, category,
            risk.get("reason") or
            "Irreversible or final-output action — confirm before proceeding.",
            False, True,
        )

    # ── Step 7: Single-synth patch / preset replacement ──────────────────────
    # Randomizing or replacing a patch on one synth is medium-risk:
    # reversible if Conductor logs the previous preset path before executing.
    if _MEDIUM_PATCH_RE.search(msg) or category in {"plugin_replace", "type_synth", "type_sampler"}:
        return _base(
            UNDO_LOG_REQUIRED, category or "plugin_state_change",
            risk.get("reason") or
            "Patch/preset replacement — reversible with an undo log entry.",
            True, False,
        )

    # ── Step 8: General write intent ─────────────────────────────────────────
    if _WRITE_INTENT_RE.search(msg):
        return _base(
            AUTO_EXECUTE_ALLOWED, category or "safe_write",
            "Clear reversible edit; execute and report status.",
            True, False,
        )

    # ── Step 9: No write action detected ─────────────────────────────────────
    return _base(
        STATUS_ONLY, category or "status_or_advice",
        "No protected write action detected.",
        False, False,
    )


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [
        # (description, message, expected_level)
        # Rule 1: safe/additive
        ("new track",           "Create a new Omnisphere track with a warm pad.", AUTO_EXECUTE_ALLOWED),
        ("load on new track",   "Load Omnisphere on a new track.",                AUTO_EXECUTE_ALLOWED),
        ("named param write",   "Lower the kick by 1 dB.",                        AUTO_EXECUTE_ALLOWED),
        ("batch rename group",  "Rename all guitar tracks cleanly.",              AUTO_EXECUTE_ALLOWED),
        ("create buses + route","Create guitar bus, pad bus, bass bus and route them to Music Bus.", AUTO_EXECUTE_ALLOWED),
        # Rule 2: medium reversible
        ("patch replace",       "Replace the current lead patch with Omnisphere.", UNDO_LOG_REQUIRED),
        ("randomize patch",     "Randomize this Serum patch.",                    UNDO_LOG_REQUIRED),
        ("plugin insert",       "Add Pro-Q to the vocal track.",                  AUTO_EXECUTE_ALLOWED),
        ("routing safe",        "Route violin to the strings bus.",               AUTO_EXECUTE_ALLOWED),
        # Rule 3: effect inserts on groups
        ("fx on group",         "Put compressor on all backing vocal tracks.",    AUTO_EXECUTE_ALLOWED),
        ("reverb on adlibs",    "Add reverb to all ad-lib tracks.",               AUTO_EXECUTE_ALLOWED),
        ("delay on bus",        "Put delay on the lead vocal throw bus.",         AUTO_EXECUTE_ALLOWED),
        ("saturation on bus",   "Add saturation to guitar bus.",                  AUTO_EXECUTE_ALLOWED),
        ("eq on group",         "Put EQ on all string tracks.",                   AUTO_EXECUTE_ALLOWED),
        # Rule 5: high-risk
        ("destructive batch",   "Delete all muted tracks.",                       CONFIRM_REQUIRED),
        ("freeze flatten",      "Flatten every MIDI track.",                      CONFIRM_REQUIRED),
        ("master output",       "Push master to -7 LUFS.",                        CONFIRM_REQUIRED),
        ("replace on all",      "Replace plugins on all tracks.",                 CONFIRM_REQUIRED),
        ("export",              "Export final master.",                           CONFIRM_REQUIRED),
        ("global tempo",        "Change global tempo to 128.",                    CONFIRM_REQUIRED),
        # Rule 6: pronouns
        ("pronoun lower",       "Lower it by 1 dB.",                             CLARIFY_REQUIRED),
        ("pronoun route",       "Route it to the bus.",                          CLARIFY_REQUIRED),
        ("pronoun turn down",   "Turn it down.",                                 CLARIFY_REQUIRED),
        ("pronoun compress",    "Compress it.",                                  CLARIFY_REQUIRED),
        ("pronoun make warmer", "Make it warmer.",                               CLARIFY_REQUIRED),
        ("pronoun pan",         "Pan it right.",                                 CLARIFY_REQUIRED),
        ("bare load patch",     "Load a patch.",                                 CLARIFY_REQUIRED),
        # Rule 7: local referent (NOT clarify)
        ("local referent them", "Create guitar bus, pad bus, bass bus, string bus and route them to Music Bus.",
         AUTO_EXECUTE_ALLOWED),
        # Rule 8: unsupported GUI
        ("gui drag",            "Open the plugin GUI and drag the wavetable by hand.", BLOCK_UNSUPPORTED),
        ("mouse tweak",         "Move the mouse and tweak the knob visually.",  BLOCK_UNSUPPORTED),
    ]

    passed = failed = 0
    for desc, msg, expected in cases:
        result = classify_protection(msg)
        got = result["protection_level"]
        ok = got == expected
        sym = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"  {sym} [{got:22}] {desc}")
        if not ok:
            print(f"       expected: {expected}")
            print(f"       rationale: {result['rationale']}")
            print(f"       category: {result['risk_category']}")

    print(f"\n  {passed}/{len(cases)} correct")
