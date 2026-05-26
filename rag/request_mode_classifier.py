"""
Conductor — Request Mode Classifier (B2)
─────────────────────────────────────────
Classifies a user message into one of 5 modes with zero LLM cost.
Pure keyword + pattern matching. Runs in < 1ms.

Modes:
  MENTOR             → advice, education, explanation — no tools needed
  INTERN_READ        → inspect Ableton, session, audio, memory — tools OK
  INTERN_WRITE_SAFE  → small reversible change — execute and verify
  INTERN_WRITE_RISKY → master/delete/export/batch/replace — confirm first
  CLARIFY            → too ambiguous to proceed safely

Design rule (Generalization-First):
  RISKY classification is driven by rag/risk_taxonomy.py — category/config-based.
  FREEFORM_GENERAL patterns live in rag/memory_schema.py — single source of truth.
  Do NOT add individual plugin names or one-off phrases here.
  Add action categories to risk_taxonomy.ACTION_CATEGORIES.
  Add plugins to data/known_plugins.json (risk="high").
"""

import re

# ── FREEFORM_GENERAL — single source of truth is memory_schema.py ─────────────
# Imported here so classify() has one place to check. Never duplicate this list.
from rag.memory_schema import FREEFORM_PATTERNS  # noqa: F401 (re-exported for callers)

# ── RISKY — delegated to risk_taxonomy ────────────────────────────────────────
# classify_risk() returns {"is_risky": bool, "category": str, "reason": str}
from rag.protection_model import (
    AUTO_EXECUTE_ALLOWED,
    BLOCK_UNSUPPORTED,
    CLARIFY_REQUIRED,
    CONFIRM_REQUIRED,
    STATUS_ONLY,
    UNDO_LOG_REQUIRED,
    classify_protection,
)


def _status_protection(category: str = "status_or_advice", rationale: str = "No protected write action detected.") -> dict:
    return {
        "protection_level": STATUS_ONLY,
        "risk_category": category,
        "rationale": rationale,
        "auto_execute_allowed": False,
        "confirmation_required": False,
    }

# WRITE_SAFE
WRITE_PATTERNS = [
    r"\bset\b", r"\bchange\b", r"\badd\b", r"\bcreate\b", r"\brename\b",
    r"\badjust\b", r"\btune\b", r"\btweak\b", r"\bmove\b",
    r"\blower\b", r"\braise\b", r"\bboost\b", r"\bcut\b",
    r"\bfilter\b", r"\bcompress\b", r"\broute\b", r"\bload\b",
    r"\benable\b", r"\bdisable\b", r"\bturn\s+on\b", r"\bturn\s+off\b",
    r"\bmute\b", r"\bunmute\b", r"\bsolo\b", r"\bunsolo\b",
    r"\bset\s+bpm\b", r"\bset\s+tempo\b", r"\bset\s+key\b",
    r"\bprogram\s+midi\b", r"\bwrite\s+midi\b", r"\badd\s+notes\b",
    r"\bsend\s+to\b", r"\bpatch\b", r"\binsert\b", r"\barm\b",
    r"\bpan\b",  # panning a track/bus is a write action (was silently falling to STATUS_ONLY)
]

# READ
READ_PATTERNS = [
    r"\bcheck\b", r"\bshow\b", r"\bget\b", r"\bread\b", r"\blist\b",
    r"\bwhat\s+is\b", r"\bwhat'?s\b", r"\bhow\s+is\b",
    r"\banalyze\b", r"\banalyse\b", r"\bscan\b", r"\binspect\b",
    r"\btell\s+me\b", r"\bwhat\s+are\b", r"\bdo\s+i\s+have\b",
    r"\bcurrent\s+bpm\b", r"\bcurrent\s+key\b", r"\bcurrent\s+tempo\b",
    r"\bcurrent\s+(lufs|level|peak|rms|loudness|stage|mix)\b",  # "current LUFS", "current stage"
    r"\bwhat\s+tracks\b", r"\bwhat\s+plugins\b", r"\bwhat\s+devices\b",
    r"\bwhat\s+stage\b", r"\bam\s+i\s+at\b",  # "what stage am I at"
    r"\bsession\s+state\b", r"\bremind\s+me\b",
    r"\bwhat\s+did\s+i\b", r"\bwhat\s+did\s+we\b",
    r"\bwhat\s+compression\b", r"\bwhat\s+eq\b", r"\bwhat\s+frequency\b",
    r"\bwhat\s+settings\b", r"\bwhat\s+i\s+used\b",
    r"\bstatus\b", r"\bhealth\b",
]

# MENTOR — education, explanation, advice
MENTOR_PATTERNS = [
    r"\bhow\s+do\s+i\b", r"\bhow\s+should\s+i\b", r"\bhow\s+to\b",
    r"\bwhat\s+is\b", r"\bwhat\s+are\b", r"\bexplain\b", r"\bteach\b",
    r"\bwhy\s+does\b", r"\bwhy\s+is\b", r"\bwhy\s+do\b",
    r"\bshould\s+i\b", r"\bwhat'?s\s+the\s+best\b",
    r"\bbest\s+way\b", r"\brecommend\b", r"\bdifference\s+between\b",
    r"\bwhen\s+to\b", r"\bwhen\s+should\b", r"\bhow\s+does\b",
    r"\badvice\b", r"\btips\b", r"\btechnique\b", r"\bapproach\b",
    r"\bwhat\s+plugin\b", r"\bwhich\s+plugin\b",
    r"\bfor\s+punjabi\b", r"\bfor\s+hindi\b", r"\bfor\s+bollywood\b",
    r"\bhow\s+ar\s+rahman\b", r"\bhow\s+does\s+diljit\b",
]

# ── CLASSIFIER ────────────────────────────────────────────────────────────────

def classify(message: str) -> dict:
    """
    Classify a user message into a request mode.

    Returns:
        {
            "mode": "MENTOR|INTERN_READ|INTERN_WRITE_SAFE|INTERN_WRITE_RISKY|CLARIFY|FREEFORM_GENERAL",
            "risk_reason": str  (only set for RISKY — explains why confirmation needed)
        }

    RISKY classification is delegated to rag/risk_taxonomy.py (category/config-based).
    FREEFORM patterns are imported from rag/memory_schema.py (single source of truth).
    """
    msg = message.lower().strip()

    # FREEFORM_GENERAL — non-music query, skip all retrieval
    for pattern in FREEFORM_PATTERNS:
        if re.search(pattern, msg):
            return {
                "mode": "FREEFORM_GENERAL",
                "risk_reason": "",
                **_status_protection("freeform_general", "Non-music query; skip project context and retrieval."),
            }

    # Too short to classify safely
    if len(msg.split()) < 2:
        protection = {
            "protection_level": CLARIFY_REQUIRED,
            "risk_category": "too_short",
            "rationale": "Message too short to determine intent safely.",
            "auto_execute_allowed": False,
            "confirmation_required": False,
        }
        return {"mode": "CLARIFY", "risk_reason": protection["rationale"], **protection}

    # Protection layer first. Risk is no longer the same thing as confirmation.
    protection = classify_protection(message)
    level = protection["protection_level"]
    if level == BLOCK_UNSUPPORTED:
        return {
            "mode": "CLARIFY",
            "risk_reason": protection["rationale"],
            **protection,
        }
    if level == CLARIFY_REQUIRED:
        return {
            "mode": "CLARIFY",
            "risk_reason": protection["rationale"],
            **protection,
        }
    if level == CONFIRM_REQUIRED:
        return {
            "mode": "INTERN_WRITE_RISKY",
            "risk_reason": protection["rationale"],
            **protection,
        }
    if level == UNDO_LOG_REQUIRED:
        return {
            "mode": "INTERN_WRITE_SAFE",
            "risk_reason": "",
            **protection,
        }
    # Protection model confirmed a definitive write action via effect-insert or
    # additive-create checks. These are never questions — early-return as WRITE_SAFE.
    # "safe_write" (from the _WRITE_INTENT_RE fallback) still falls through to
    # pattern matching so that questions like "how should I compress…" route to MENTOR.
    if level == AUTO_EXECUTE_ALLOWED and protection.get("risk_category") in (
        "effect_insert", "safe_additive",
    ):
        return {
            "mode": "INTERN_WRITE_SAFE",
            "risk_reason": "",
            **protection,
        }

    # WRITE_SAFE — has clear write intent, not risky
    # Reached only when protection model returned STATUS_ONLY (no write confirmed).
    # Pattern matching then determines mode and upgrades STATUS_ONLY → AUTO_EXECUTE.
    write_hits = sum(1 for p in WRITE_PATTERNS if re.search(p, msg))
    read_hits  = sum(1 for p in READ_PATTERNS  if re.search(p, msg))
    mentor_hits = sum(1 for p in MENTOR_PATTERNS if re.search(p, msg))

    # MENTOR — educational question
    # "how do I X" wins even if X is a write-action word
    is_how_question   = bool(re.search(r"\bhow\s+(do\s+i|should\s+i|to|does|can\s+i)\b", msg))
    is_what_question  = bool(re.search(r"\bwhat\s+(is|are|'?s\s+the|plugin|should)\b", msg))
    # "should I use/try/choose" — advice-seeking even if a write-action word appears (e.g. "cut")
    is_advice_question = bool(re.search(r"\bshould\s+i\s+(use|try|do|go|pick|choose|consider|apply|start)\b", msg))
    # Inspection queries — "what is the current X" or "current LUFS/stage/BPM" → READ, not MENTOR
    is_inspection_query = bool(re.search(
        r"\bcurrent\s+(lufs|bpm|key|tempo|stage|level|peak|rms|loudness|mix)\b"
        r"|\bwhat\s+is\s+the\s+current\b"
        r"|\bwhat\s+(tracks|plugins|devices)\b",
        msg
    ))

    if mentor_hits > 0 and not is_inspection_query and (
        write_hits == 0 or is_how_question or is_what_question or is_advice_question
    ):
        return {"mode": "MENTOR", "risk_reason": "", **protection}

    # READ — inspection request
    if read_hits > 0 and write_hits == 0:
        return {"mode": "INTERN_READ", "risk_reason": "", **protection}
    # Inspection query overrides write hits (e.g. "what is the current mix" contains no write words
    # but READ should still win if explicitly asking for current state)
    if is_inspection_query and read_hits > 0:
        return {"mode": "INTERN_READ", "risk_reason": "", **protection}

    # WRITE_SAFE — write intent, no risky signals
    if write_hits > 0:
        if level == STATUS_ONLY:
            protection = {
                **protection,
                "protection_level": AUTO_EXECUTE_ALLOWED,
                "risk_category": protection.get("risk_category") or "safe_write",
                "rationale": "Clear reversible edit; execute directly when Auto Execute is on and report status.",
                "auto_execute_allowed": True,
                "confirmation_required": False,
            }
        return {"mode": "INTERN_WRITE_SAFE", "risk_reason": "", **protection}

    # Mixed signals with no clear winner — default to MENTOR (safer)
    if mentor_hits > 0:
        return {"mode": "MENTOR", "risk_reason": "", **protection}

    # Fallback — treat as MENTOR (advice) rather than guessing a write
    return {"mode": "MENTOR", "risk_reason": "", **protection}


# ── QUICK TEST ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    tests = [
        ("how do I layer strings for a cinematic feel",   "MENTOR"),
        ("what's the current BPM",                        "INTERN_READ"),
        ("set track 1 volume to -6dB",                    "INTERN_WRITE_SAFE"),
        ("delete the kick track",                         "INTERN_WRITE_RISKY"),
        ("export the final mix",                          "INTERN_WRITE_RISKY"),
        ("remind me what I used on the vocals",           "INTERN_READ"),
        ("boost the low end a bit",                       "INTERN_WRITE_SAFE"),
        ("make the master bus louder",                    "INTERN_WRITE_RISKY"),
        ("clear all notes on track 2",                    "INTERN_WRITE_RISKY"),
        ("what compression did I use last time",          "INTERN_READ"),
        ("ok",                                            "CLARIFY"),
        ("batch rename all tracks",                       "INTERN_WRITE_RISKY"),
        ("mute the hi-hat",                               "INTERN_WRITE_SAFE"),
    ]

    passed = 0
    for msg, expected in tests:
        result = classify(msg)
        status = "✅" if result["mode"] == expected else "❌"
        if result["mode"] == expected:
            passed += 1
        print(f"  {status} [{result['mode']:22}] {msg}")
        if result["mode"] != expected:
            print(f"       expected: {expected}")

    print(f"\n  {passed}/{len(tests)} correct")
