"""
Conductor — Risk Taxonomy (Phase C — category/config-based)
────────────────────────────────────────────────────────────
Single source of truth for risky-action classification.

Used by:
  rag/request_mode_classifier.py  — backend mode classification
  tools/conductor_bridge.py       — GET /risk/rules (frontend sync)

Design rule (Generalization-First):
  Never hardcode a single plugin name or phrase as the trigger.
  Risky actions are defined by CATEGORY (action type + target scope).
  Plugin risk is loaded from data/known_plugins.json.
  Adding a new risky plugin = add it to known_plugins.json, risk="high".
  Adding a new action category = add it to ACTION_CATEGORIES below.

Plugin matching uses name + natural_names + aliases from known_plugins.json.
  Aliases are camelCase compound identifiers (e.g. "FabFilterProL2", "iZotopeOzone12").
  They are added to both risk detection and operator-card detection.

Checked at classify() call time — cheap regex, no LLM, < 1ms.
"""

import os
import json
import re
from typing import List, Dict, Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_PLUGINS_PATH = os.path.join(_ROOT, "data", "known_plugins.json")


# ── ACTION CATEGORIES ─────────────────────────────────────────────────────────
# 7 categories ordered by priority (first match wins in classify_risk()).
# Each entry:
#   keywords    — list of exact phrases/words to match (converted to word-boundary regex)
#   risk_reason — human-readable reason shown to user; {action} replaced with matched term

ACTION_CATEGORIES: Dict[str, dict] = {

    # 1. Destructive — irreversible deletions
    "destructive": {
        "keywords": [
            "delete", "erase", "wipe",
            "clear all", "clear clip", "clear track", "clear notes",
            "remove notes", "delete notes",
            "drop track", "kill track",
        ],
        "risk_reason": "{action} is irreversible without Cmd+Z — confirm before executing",
    },

    # 2. Render / Export — overwrites files or converts audio permanently
    "render_export": {
        "keywords": [
            "export", "stem export", "bounce", "bounce in place",
            "render", "consolidate", "final mix", "release",
        ],
        "risk_reason": "{action} overwrites existing files if version not specified — check path first",
    },

    # 3. Mastering / Output chain — affects final signal path
    "mastering_output": {
        "keywords": [
            "master bus", "master fader", "master volume",
            "master louder", "master quieter", "master level",
            "master gain", "master output", "master ceiling",
            "make the master", "get the master", "set the master",
            "push master", "push the master",
            "lufs target", "true peak", "limiter ceiling", "output ceiling",
        ],
        "risk_reason": "Master output change affects the final signal — confirm LUFS and True Peak targets first",
    },

    # 4. Batch / Global scope — one action hits multiple tracks or the whole project
    "batch_global": {
        "keywords": [
            "all tracks", "every track", "batch",
            "entire project", "all drums", "all vocals", "every vocal",
            "global tempo", "global key",
            "add to all", "apply to all",
        ],
        "risk_reason": "Batch/global operation affects multiple tracks — preview scope before executing",
    },

    # 5. Plugin state replacement — replaces patch/preset/plugin, irreversible
    "plugin_replace": {
        "keywords": [
            "replace plugin", "swap plugin", "remove plugin", "overwrite",
            "replace patch", "new patch", "load patch", "swap preset",
            "flatten synth", "bounce midi",
            "randomize preset", "randomize patch",
            "load preset", "new preset",
        ],
        "risk_reason": "{action} replaces existing plugin state and cannot be undone without a preset snapshot",
    },

    # 6. Freeze / Flatten — converts MIDI/audio, original is not recoverable
    # "freeze" and "flatten" are standalone to catch broad phrasings:
    #   "freeze every midi track", "freeze the lead synth", "flatten the arrangement"
    "freeze_flatten": {
        "keywords": [
            "freeze", "freeze all", "freeze track", "freeze midi", "freeze audio",
            "flatten", "flatten arrangement", "flatten track",
        ],
        "risk_reason": "{action} converts MIDI/audio — original is not recoverable without Undo",
    },

    # 7. Routing changes — wrong order can cause feedback or silence
    "routing_change": {
        "keywords": [
            "reroute", "re-route", "change routing", "change output",
        ],
        "risk_reason": "Routing change may cause feedback loops or silence — confirm No Input before Monitor:In",
    },

    # Note: "remove" is intentionally excluded from destructive above because
    # "remove plugin" is covered by plugin_replace and is less catastrophic than
    # deleting a track. "remove notes" IS in destructive.
}


# ── TYPE-BASED RISK POLICIES ──────────────────────────────────────────────────
# Driven by the `type` field in known_plugins.json.
# Generalises to any plugin of a given type without requiring risk="high".
#
# always_risky: True  → any mention = risky (mastering/limiter affect final chain)
# always_risky: False → risky only when trigger_words also appear in message
#                       (synth/sampler: safe to tweak params, risky to swap patch)
#
# EQ/compressor are intentionally excluded — param writes are safe by default;
# scope-level risk (master bus) is already caught by mastering_output keywords.

TYPE_RISK_POLICIES: Dict[str, dict] = {
    "mastering": {
        "always_risky": True,
        "risk_reason":  "{plugin} (mastering plugin) — changes affect the final output chain",
    },
    "limiter": {
        "always_risky": True,
        "risk_reason":  "{plugin} (limiter) — ceiling/threshold changes affect release output level",
    },
    "synth": {
        "always_risky":  False,
        "trigger_words": ["patch", "preset", "program", "randomize", "randomise",
                          "replace", "load", "swap", "new"],
        "risk_reason":   "{plugin} patch/preset replacement — save before randomizing or loading",
    },
    "sampler": {
        "always_risky":  False,
        "trigger_words": ["patch", "preset", "sample", "kit", "replace", "load", "swap", "new"],
        "risk_reason":   "{plugin} sample/preset replacement — save before randomizing or loading",
    },
}


# ── COMPOUND PATTERNS (word-order independent) ────────────────────────────────
# Catches risky intent when the verb and its target noun are separated by a
# plugin name or other words — e.g. "randomize Serum patch", "load Omnisphere patch".
#
# Each entry:
#   verb_words  — action verbs that imply risky intent
#   noun_words  — targets that make the action risky
#   category    — the ACTION_CATEGORIES key this maps to
#   risk_reason — human-readable reason; {verb} replaced with matched verb
#
# Applied as Phase 3 AFTER Phases 1 (action keywords) and 2 (high-risk plugins).
# If Phase 1 or 2 already fired, Phase 3 is never reached.

COMPOUND_PATTERNS: List[dict] = [
    {
        # "randomize Serum patch", "load Omnisphere patch", "swap a Kontakt preset"
        # Words separated by plugin name or adjectives — same sentence, any order.
        "category":   "plugin_replace",
        "verb_words": ["randomize", "randomise", "replace", "load", "swap",
                       "shuffle", "morph", "reset", "change"],
        "noun_words": ["patch", "preset", "program", "bank"],
        "risk_reason": "{verb} of plugin state — save preset before {verb}ing",
    },
]


# ── PLUGIN INVENTORY ──────────────────────────────────────────────────────────

def _load_plugins() -> List[dict]:
    """Load plugin list from data/known_plugins.json. Returns [] on any error."""
    try:
        with open(_PLUGINS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("plugins", [])
    except Exception:
        return []


def get_high_risk_plugin_terms() -> List[str]:
    """
    Return sorted list of lowercase terms for plugins with risk == 'high'.
    Includes: canonical name + natural_names + aliases (camelCase identifiers).

    These are used for the emergency risky detector — any HIGH-risk plugin mentioned
    in a write action should trigger INTERN_WRITE_RISKY regardless of action category.

    Aliases like "FabFilterProL2", "iZotopeOzone12" are included so users who paste
    plugin identifiers from API calls or drag-n-drop still get the safety check.
    """
    terms = set()
    for p in _load_plugins():
        if p.get("risk") != "high":
            continue
        terms.add(p["name"].lower())
        for a in p.get("natural_names", []):
            if a:
                terms.add(a.lower())
        for a in p.get("aliases", []):
            if a:
                terms.add(a.lower())
    return sorted(terms)


def get_card_file_for_message(message: str) -> str:
    """
    Return operator card filename (e.g. 'Ozone 12 Operator Card.md') if any known
    plugin with has_card=True is mentioned in the message.

    Uses canonical name + natural_names + aliases from plugin inventory.
    Aliases (e.g. "FabFilterProQ4", "XferSerum2") let users reference plugins
    via DAW identifiers without needing spaces or canonical spelling.
    First match wins (ordered by inventory order).
    Returns "" if no matching plugin with a card is found.
    """
    msg = message.lower()
    for p in _load_plugins():
        if not p.get("has_card") or not p.get("card_file"):
            continue
        # Check canonical name + natural_names + aliases
        search_terms = (
            [p["name"].lower()]
            + [a.lower() for a in p.get("natural_names", []) if a]
            + [a.lower() for a in p.get("aliases", []) if a]
        )
        if any(term in msg for term in search_terms):
            return p["card_file"]
    return ""


def get_known_plugin_name_for_message(message: str) -> str:
    """
    Return canonical plugin name if ANY known plugin (has_card=True or False)
    is mentioned in the message. Returns "" if none recognized.

    Unlike get_card_file_for_message() this does NOT require has_card=True —
    it catches all 61 inventory entries.

    Build 11: used by context_pack_builder to detect the "recognized plugin
    with no operator card" case so a ## KNOWLEDGE STATUS block can be injected.
    """
    msg = message.lower()
    for p in _load_plugins():
        terms = (
            [p["name"].lower()]
            + [a.lower() for a in p.get("natural_names", []) if a]
            + [a.lower() for a in p.get("aliases", []) if a]
        )
        if any(t in msg for t in terms):
            return p["name"]
    return ""


def get_plugin_by_natural_name(name: str) -> Optional[dict]:
    """
    Return plugin dict for a given name, natural_name, or alias (case-insensitive).
    None if not found.
    """
    name_lower = name.lower().strip()
    for p in _load_plugins():
        if p["name"].lower() == name_lower:
            return p
        if any(a.lower() == name_lower for a in p.get("natural_names", [])):
            return p
        if any(a.lower() == name_lower for a in p.get("aliases", [])):
            return p
    return None


# ── RISK CLASSIFIER ───────────────────────────────────────────────────────────

# Phase 1: action-category patterns compiled once at module load.
_COMPILED_CATEGORIES: Optional[Dict[str, re.Pattern]] = None

# Phase 2b: type-policy patterns — one compiled regex per plugin type.
# {type_name: (compiled_re, [{plugin_dict, terms}])}
_TYPE_PATTERNS: Dict[str, tuple] = {}


def _get_compiled_categories() -> Dict[str, re.Pattern]:
    global _COMPILED_CATEGORIES
    if _COMPILED_CATEGORIES is not None:
        return _COMPILED_CATEGORIES

    _COMPILED_CATEGORIES = {}
    for cat, data in ACTION_CATEGORIES.items():
        parts = []
        for kw in data["keywords"]:
            # Convert multi-word keyword to \s+-joined regex, then wrap in word boundaries
            escaped = re.escape(kw).replace(r"\ ", r"\s+")
            parts.append(r"\b" + escaped + r"\b")
        _COMPILED_CATEGORIES[cat] = re.compile("|".join(parts), re.IGNORECASE)
    return _COMPILED_CATEGORIES


def _get_type_patterns() -> Dict[str, tuple]:
    """
    Build one compiled regex per TYPE_RISK_POLICIES key.
    Groups all plugins of that type into a single alternation for fast matching.
    Lazy-built and cached.
    """
    global _TYPE_PATTERNS
    if _TYPE_PATTERNS:
        return _TYPE_PATTERNS

    plugins_by_type: Dict[str, list] = {}
    for p in _load_plugins():
        ptype = p.get("type", "")
        if ptype not in TYPE_RISK_POLICIES:
            continue
        terms = (
            [p["name"].lower()]
            + [a.lower() for a in p.get("natural_names", []) if a]
            + [a.lower() for a in p.get("aliases", []) if a]
        )
        if ptype not in plugins_by_type:
            plugins_by_type[ptype] = []
        plugins_by_type[ptype].append({"plugin": p, "terms": terms})

    for ptype, plugin_list in plugins_by_type.items():
        parts = []
        for entry in plugin_list:
            for t in entry["terms"]:
                esc = re.escape(t).replace(r"\ ", r"\s+")
                parts.append(r"\b" + esc + r"\b")
        if parts:
            _TYPE_PATTERNS[ptype] = (
                re.compile("|".join(parts), re.IGNORECASE),
                plugin_list,
            )
    return _TYPE_PATTERNS


def _find_matched_plugin(message: str, plugin_list: list) -> str:
    """Return the canonical name of the first plugin in plugin_list mentioned in message."""
    msg = message.lower()
    for entry in plugin_list:
        for t in entry["terms"]:
            if re.search(r"\b" + re.escape(t) + r"\b", msg, re.IGNORECASE) or t in msg:
                return entry["plugin"]["name"]
    return ""


def classify_risk(message: str) -> dict:
    """
    Classify whether a message contains a risky action.

    Returns:
        {
          "is_risky":  bool,
          "category":  str,   # e.g. "destructive", "mastering_output", "type_mastering"
          "reason":    str,   # human-readable explanation for the UI
          "matched":   str,   # the keyword/term that triggered the match
        }

    Checks in order:
      Phase 1 — Action categories     (exact keyword phrases)
      Phase 2 — High-risk plugins     (risk="high" in known_plugins.json)
      Phase 2b— Type-based policy     (mastering/limiter=always; synth/sampler=with patch/preset)
      Phase 3 — Compound intent       (risky verb + risky noun anywhere, word-order independent)

    If no match: {"is_risky": False, "category": "", "reason": "", "matched": ""}
    """
    patterns = _get_compiled_categories()

    # Phase 1: action categories (exact phrases, word-boundary matched)
    for cat, pattern in patterns.items():
        m = pattern.search(message)
        if m:
            matched = m.group(0)
            reason_tpl = ACTION_CATEGORIES[cat]["risk_reason"]
            reason = reason_tpl.replace("{action}", matched.title())
            return {
                "is_risky": True,
                "category": cat,
                "reason":   reason,
                "matched":  matched,
            }

    # Phase 2: high-risk plugins (risk="high", includes aliases)
    for term in get_high_risk_plugin_terms():
        if re.search(r"\b" + re.escape(term) + r"\b", message, re.IGNORECASE):
            plugin = get_plugin_by_natural_name(term) or {}
            pname = plugin.get("name", term)
            return {
                "is_risky": True,
                "category": "high_risk_plugin",
                "reason":   f"{pname} — HIGH risk plugin on this action",
                "matched":  term,
            }

    # Phase 2b: type-based policy — generalises beyond explicit risk="high"
    # mastering/limiter: always risky (any mention); synth/sampler: risky with patch/preset words
    type_patterns = _get_type_patterns()
    for ptype, (type_re, plugin_list) in type_patterns.items():
        if not type_re.search(message):
            continue
        policy = TYPE_RISK_POLICIES[ptype]
        if policy["always_risky"]:
            pname = _find_matched_plugin(message, plugin_list) or ptype
            reason = policy["risk_reason"].replace("{plugin}", pname)
            return {
                "is_risky": True,
                "category": f"type_{ptype}",
                "reason":   reason,
                "matched":  pname,
            }
        # Not always risky — only trigger when trigger_words also present
        trigger_words = policy.get("trigger_words", [])
        for tw in trigger_words:
            if re.search(r"\b" + re.escape(tw) + r"\b", message, re.IGNORECASE):
                pname = _find_matched_plugin(message, plugin_list) or ptype
                reason = policy["risk_reason"].replace("{plugin}", pname)
                return {
                    "is_risky": True,
                    "category": f"type_{ptype}",
                    "reason":   reason,
                    "matched":  f"{pname} + {tw}",
                }

    # Phase 3: compound intent — risky VERB + risky NOUN anywhere in message
    # Catches word-order variants: "randomize Serum patch", "load Omnisphere patch"
    for cp in COMPOUND_PATTERNS:
        verb_m = None
        for v in cp["verb_words"]:
            vm = re.search(r"\b" + re.escape(v) + r"\b", message, re.IGNORECASE)
            if vm:
                verb_m = vm.group(0)
                break
        if not verb_m:
            continue
        for n in cp["noun_words"]:
            nm = re.search(r"\b" + re.escape(n) + r"\b", message, re.IGNORECASE)
            if nm:
                reason = cp["risk_reason"].replace("{verb}", verb_m.lower())
                return {
                    "is_risky": True,
                    "category": cp["category"],
                    "reason":   reason,
                    "matched":  f"{verb_m} + {nm.group(0)}",
                }

    return {"is_risky": False, "category": "", "reason": "", "matched": ""}


# ── /risk/rules EXPORT ────────────────────────────────────────────────────────
# Used by the bridge's GET /risk/rules endpoint so the frontend stays in sync
# with the backend taxonomy without duplicating logic.

def get_risk_rules_payload() -> dict:
    """
    Return a serialisable dict for GET /risk/rules.
    Frontend uses this to generate its emergency risky-action regex.

    Structure:
      action_categories:      {cat_name: [keyword, ...], ...}
      high_risk_plugin_terms: ["ozone", "ozone 12", "fabfilterprol2", ...]
      type_risk_policies:     {type: {always_risky, trigger_words?, risk_reason}}
      compound_patterns:      [{category, verb_words, noun_words, risk_reason}, ...]
      freeform_patterns:      [...regex strings...]
    """
    from rag.memory_schema import FREEFORM_PATTERNS  # avoid circular at module level

    categories_export = {
        cat: data["keywords"]
        for cat, data in ACTION_CATEGORIES.items()
    }

    # Compound patterns without compiled re objects (not JSON-serialisable)
    compound_export = [
        {k: v for k, v in cp.items() if not isinstance(v, re.Pattern)}
        for cp in COMPOUND_PATTERNS
    ]

    return {
        "action_categories":      categories_export,
        "high_risk_plugin_terms": get_high_risk_plugin_terms(),
        "type_risk_policies":     TYPE_RISK_POLICIES,
        "compound_patterns":      compound_export,
        "freeform_patterns":      FREEFORM_PATTERNS,
    }


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    cases = [
        # (phrase, expected_risky, expected_category)
        ("delete the kick drum track",            True,  "destructive"),
        ("erase the vocal clip",                  True,  "destructive"),
        ("bounce the whole session to audio",     True,  "render_export"),
        ("stem export drums",                     True,  "render_export"),
        ("make the master louder",                True,  "mastering_output"),
        ("set true peak to -1.0 dBTP",            True,  "mastering_output"),
        ("change lufs target to -14",             True,  "mastering_output"),
        ("apply reverb to all tracks",            True,  "batch_global"),
        ("global tempo to 120",                   True,  "batch_global"),
        ("replace patch in Serum",                True,  "plugin_replace"),
        ("flatten arrangement",                   True,  "freeze_flatten"),
        # "limiter ceiling" fires mastering_output before the high_risk_plugin check — correct.
        # Action category wins because it is more specific and gives a better reason.
        ("set Ozone 12 limiter ceiling to -1",    True,  "mastering_output"),
        ("set Pro-L 2 ceiling",                   True,  "high_risk_plugin"),  # no action keyword, plugin fires
        ("load god particle on master bus",       True,  "mastering_output"),  # "master bus" fires first
        # ── Broadened freeze/flatten ─────────────────────────────────────────
        ("freeze every midi track",               True,  "freeze_flatten"),   # new: "freeze" standalone
        ("flatten the lead synth",                True,  "freeze_flatten"),   # new: "flatten" standalone
        # ── Broadened plugin_replace ─────────────────────────────────────────
        ("remove plugin from kick channel",       True,  "plugin_replace"),   # new: "remove plugin"
        ("load a new patch in Omnisphere",        True,  "plugin_replace"),   # new: "new patch"
        ("load preset into the synth",            True,  "plugin_replace"),   # new: "load preset"
        # ── Alias-based high-risk detection ──────────────────────────────────
        ("set FabFilterProL2 ceiling to -1",      True,  "high_risk_plugin"), # alias: Pro-L 2
        ("adjust iZotopeOzone12 settings",        True,  "high_risk_plugin"), # alias: Ozone 12
        # Safe — must NOT trigger
        ("how do I EQ a dhol",                   False, ""),
        ("what is the current BPM",              False, ""),
        ("compress the snare at 4:1",            False, ""),
        ("route violin to strings bus",          False, ""),   # "route" alone not risky
        ("set Pro-Q 4 band 2 to 3.4kHz",         False, ""),
        ("what should I eat for lunch",           False, ""),
        ("set FabFilterProQ4 band 2 to 3.4kHz",  False, ""),  # medium-risk plugin, safe action
    ]

    print("\n── Risk Taxonomy self-test ──────────────────────────────────")
    passed = failed = 0
    for phrase, exp_risky, exp_cat in cases:
        r = classify_risk(phrase)
        cat_ok  = (exp_cat == "" or r["category"] == exp_cat or
                   (exp_cat == "high_risk_plugin" and r["category"] == "high_risk_plugin") or
                   (exp_cat == "mastering_output" and r["category"] == "mastering_output"))
        risky_ok = r["is_risky"] == exp_risky
        ok = risky_ok and cat_ok
        sym = "✅" if ok else "❌"
        if ok:
            passed += 1
        else:
            failed += 1
        label = f"[{r['category'] or 'safe':20}]"
        print(f"  {sym} {label} {phrase[:55]}")
        if not ok:
            print(f"       expected: risky={exp_risky} cat={exp_cat}")
            print(f"       got:      risky={r['is_risky']} cat={r['category']} matched={r['matched']!r}")

    n_high = len(get_high_risk_plugin_terms())
    print(f"\n  {passed}/{passed+failed} correct  |  {n_high} high-risk plugin terms loaded")
    print(f"  Card lookup: 'ozone' → {get_card_file_for_message('set ozone 12 limiter ceiling')!r}")
    print(f"  Card lookup: 'serum 2' → {get_card_file_for_message('randomize preset in serum 2')!r}")
    print(f"  Card lookup: 'valhalla' → {get_card_file_for_message('add valhalla room to strings')!r}")
    # Alias-based lookups
    print(f"  Card lookup: 'XferSerum2' (alias) → {get_card_file_for_message('set XferSerum2 filter cutoff')!r}")
    print(f"  Card lookup: 'FabFilterProQ4' (alias) → {get_card_file_for_message('FabFilterProQ4 band 2 cut')!r}")
