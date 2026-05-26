"""
Conductor — Memory Schema & Constants (Phase C / P0 + P1)
──────────────────────────────────────────────────────────
Single source of truth for everything that touches ChromaDB.

  Collections (5)         — names, purposes, what routes to each
  Memory levels (1–4)     — retrieval weights, confidence thresholds
  Source types            — valid types per collection
  Metadata schemas        — all fields with types and defaults
  Similarity thresholds   — min score for injection per collection
  Audio freshness         — fresh / stale / old / unknown thresholds
  Retrieval priority      — RISKY_WRITE safety-first ordering
  Validation              — validate_metadata() + make_metadata()

ALL files that read or write ChromaDB import from here.
Never hardcode collection names, field names, or thresholds elsewhere.

ChromaDB metadata rules (enforced here):
  - Values must be: str, int, float, or bool only
  - No None — use "" for empty strings, -1 for unknown ints, 0.0 for unknown floats
  - No nested dicts or lists — everything is flat
"""

import datetime

# ── COLLECTION NAMES ──────────────────────────────────────────────────────────

COLLECTIONS = {
    "producer":  "producer_memory_index",   # taste, preferences, confirmed decisions
    "project":   "project_session_index",   # per-project history (this song only)
    "plugin":    "plugin_operator_index",   # operator cards, plugin quirks
    "failure":   "failure_cases_index",     # LOM failures, routing failures, fixes
    "audio":     "audio_analysis_index",    # LUFS/spectrum snapshots (evidence only)
}

# Reverse map: collection name → short key
COLLECTION_KEYS = {v: k for k, v in COLLECTIONS.items()}

# Legacy single-collection (kept for backward compat during migration)
LEGACY_COLLECTION = "conductor_memory"

ALL_COLLECTION_NAMES = list(COLLECTIONS.values())


# ── MEMORY LEVELS (P1) ────────────────────────────────────────────────────────
#
# Level 4 overrides everything — hardcoded Never-Do rules always float to top.
# Level 1 raw events rarely influence answers — weight them down.

MEMORY_LEVELS = {
    1: {
        "name":             "Raw event",
        "description":      "Single observation. Session-local. Not cross-project.",
        "retrieval_weight": 0.6,    # multiplied against semantic similarity score
        "min_confidence":   0.0,
        "auto_expire":      True,   # eligible for dropping at session end if not promoted
        "cross_project":    False,
    },
    2: {
        "name":             "Session decision",
        "description":      "Applied this session. Project-specific. Kept across sessions.",
        "retrieval_weight": 0.85,
        "min_confidence":   0.5,
        "auto_expire":      False,
        "cross_project":    False,
    },
    3: {
        "name":             "Confirmed preference",
        "description":      "User explicitly approved. Cross-project. Strong signal.",
        "retrieval_weight": 1.0,
        "min_confidence":   0.7,
        "auto_expire":      False,
        "cross_project":    True,
    },
    4: {
        "name":             "Never-Do rule / Producer rule",
        "description":      "Hardcoded rule. Always retrieved. Overrides all scoring.",
        "retrieval_weight": 9999,   # bypasses threshold — always floats to top
        "min_confidence":   1.0,
        "auto_expire":      False,
        "cross_project":    True,
    },
}

LEVEL_4_BYPASSES_THRESHOLD = True  # Level 4 memories are always injected if retrieved


# ── SOURCE TYPES ──────────────────────────────────────────────────────────────
# Valid source_type values per collection. Enforced by validate_metadata().

SOURCE_TYPES = {
    "producer": [
        "session_decision",       # decision made and applied this session
        "confirmed_preference",   # user said "always do this"
        "never_do",               # user said "never do this"
        "taste_note",             # general preference note (genre, style, feel)
    ],
    "project": [
        "raw_event",              # single observation, weak signal
        "session_decision",       # decision tied to this project
        "stage_transition",       # project moved to a new stage
    ],
    "plugin": [
        "operator_card",          # from vault markdown (auto-seeded)
        "plugin_quirk",           # observed bad behaviour with a specific plugin
        "param_override",         # specific param value that worked or failed
    ],
    "failure": [
        "lom_failure",            # Ableton LOM Python error
        "routing_failure",        # bus routing issue
        "plugin_failure",         # plugin crashed or misbehaved
        "confirmed_fix",          # fix was verified and applied
    ],
    "audio": [
        "audio_snapshot",         # LUFS/spectrum/stereo snapshot at a point in time
    ],
}


# ── METADATA SCHEMAS ──────────────────────────────────────────────────────────
# Format: field_name: (python_type, default_value)
# Defaults are used by make_metadata() to build a valid skeleton.

_COMMON = {
    # Identity
    "memory_level":    (int,   1),
    "source_type":     (str,   ""),
    "collection":      (str,   ""),
    # Timestamps
    "created_at":      (str,   ""),     # ISO-8601 UTC
    "updated_at":      (str,   ""),     # ISO-8601 UTC
    "created_session": (str,   ""),     # session timestamp used as session ID
    # Quality signals
    "confidence":      (float, 0.5),    # 0.0–1.0
    "approved":        (bool,  False),  # user explicitly approved this memory
    "rejected":        (bool,  False),  # user explicitly rejected this memory
    "superseded_by":   (str,   ""),     # memory_id of the newer memory that replaces this
    # Context
    "project_id":      (str,   ""),     # hash of project name+BPM+key
    "stage":           (str,   ""),     # vision|production|mixing|mastering|""
    "genre":           (str,   ""),     # "bollywood"|"punjabi"|"cinematic"|""
    "plugin":          (str,   ""),     # "Pro-Q 4"|"Ozone 12"|""
    "track":           (str,   ""),     # track name or ""
}

COLLECTION_SCHEMAS = {
    "producer_memory_index": {
        **_COMMON,
        "cross_project":  (bool, False),  # applies beyond current project
        "tags":           (str,  ""),     # comma-separated: "vocal,eq,high_shelf"
    },
    "project_session_index": {
        **_COMMON,
        "bpm":            (float, 0.0),
        "key":            (str,   ""),
        "session_number": (int,   0),     # which session this was recorded in
    },
    "plugin_operator_index": {
        **_COMMON,
        "card_section":       (str,  ""),    # identity|safe_reads|risky_writes|never_do|param_ids
        "owner_verified":     (bool, False), # confirmed in studio_inventory.md
        "pluginbridge_seen":  (bool, False), # seen in live PluginBridge list_instances()
    },
    "failure_cases_index": {
        **_COMMON,
        "failure_code":    (str,  ""),      # F001, F002, F006, etc.
        "ableton_version": (str,  ""),
        "confirmed_fix":   (bool, False),
        "fix_code":        (str,  ""),      # the Python snippet that resolved it
    },
    "audio_analysis_index": {
        **_COMMON,
        "analysis_time":   (str,   ""),     # ISO-8601 — when the analyzer ran
        "freshness":       (str,   "unknown"), # fresh|stale|old|unknown
        "file_path":       (str,   ""),
        "lufs_integrated": (float, 0.0),
        "lufs_lra":        (float, 0.0),
        "true_peak":       (float, 0.0),
        "bpm":             (float, 0.0),
        "detected_key":    (str,   ""),
        "stereo_width":    (float, 0.0),
    },
}


# ── SIMILARITY THRESHOLDS ─────────────────────────────────────────────────────
# Minimum cosine similarity score for a result to be injected into the prompt.
# Below threshold: logged in debug as "below threshold — skipped", not injected.

SIMILARITY_THRESHOLDS = {
    "producer_memory_index": 0.35,  # general preferences — allow some fuzz
    "project_session_index": 0.40,  # project-specific — needs a closer match
    "plugin_operator_index": 0.30,  # plugin cards — inject if remotely relevant
    "failure_cases_index":   0.30,  # failure cases — better safe than sorry
    "audio_analysis_index":  0.50,  # audio evidence — only strong matches
}

# If no result clears the threshold, inject nothing for that collection.
# Empty retrieval is honest. Weak retrieval is harmful.
NO_STRONG_MEMORY_MSG = "(no strong memory found — threshold not met)"


# ── TEMPORAL SCORING WEIGHTS (C2) ─────────────────────────────────────────────
# final_score = semantic × W_semantic + recency × W_recency + frequency × W_frequency
# Must sum to 1.0. Level 4 memories bypass all scoring (weight = 9999).

SCORING_WEIGHTS = {
    "semantic":   0.60,   # cosine similarity from ChromaDB
    "recency":    0.30,   # exponential decay on created_at timestamp
    "frequency":  0.10,   # access count (stub at 0.5 until C2.1 adds tracking)
}

# Recency decay half-life in days.
# Memory at RECENCY_HALF_LIFE_DAYS old → recency_score = 0.5
# Memory at 0 days old → recency_score = 1.0
# Memory at 14 days old (2× half-life) → recency_score = 0.25
RECENCY_HALF_LIFE_DAYS = 7


# ── AUDIO FRESHNESS ───────────────────────────────────────────────────────────
# Analysis snapshots decay. Only inject with a freshness label.
# If stale/old: inject with warning, not as authoritative fact.

AUDIO_FRESHNESS_SECONDS = {
    "fresh": 30 * 60,        # < 30 minutes
    "stale": 2 * 60 * 60,    # 30 min – 2 hours
    # > 2 hours = "old"
}

AUDIO_FRESHNESS_WARNINGS = {
    "fresh":   "",
    "stale":   "⚠ Analysis may be stale — taken >30 min ago",
    "old":     "⚠ Analysis is old — may not reflect current mix",
    "unknown": "⚠ Analysis time unknown — treat as approximate",
}


def get_audio_freshness(analysis_time_iso: str) -> str:
    """Return 'fresh' | 'stale' | 'old' | 'unknown' from an ISO-8601 timestamp."""
    if not analysis_time_iso:
        return "unknown"
    try:
        then = datetime.datetime.fromisoformat(analysis_time_iso.replace("Z", "+00:00"))
        now  = datetime.datetime.now(datetime.timezone.utc)
        age_s = (now - then).total_seconds()
        if age_s < AUDIO_FRESHNESS_SECONDS["fresh"]:
            return "fresh"
        elif age_s < AUDIO_FRESHNESS_SECONDS["stale"]:
            return "stale"
        else:
            return "old"
    except Exception:
        return "unknown"


# ── RETRIEVAL PRIORITY FOR RISKY_WRITE ───────────────────────────────────────
# Safety before creativity. This order is enforced in the retriever, not left to scoring.
# First result that clears threshold from each source is injected in this order.

RISKY_WRITE_RETRIEVAL_ORDER = [
    ("failure_cases_index",   "Never-Do rules + confirmed LOM/routing fixes"),
    ("plugin_operator_index", "Risky Writes + Never Do sections from operator card"),
    ("producer_memory_index", "Producer preferences — loudness/taste"),
    ("audio_analysis_index",  "Audio evidence — only if fresh + project matches"),
]

# Collections NOT searched for RISKY_WRITE (project history is noise here)
RISKY_WRITE_SKIP_COLLECTIONS = {"project_session_index"}


# ── REQUEST MODE → COLLECTIONS MAP ───────────────────────────────────────────
# Which collections are searched for each request mode.

MODE_COLLECTION_MAP = {
    # ── MENTOR: advice, education, explanation — no DAW execution ──────────────
    # producer_memory_index  → semantic: producer taste, habits, confirmed preferences
    # plugin_operator_index  → procedural: plugin capability questions
    #                          ("what does Pro-Q 4 Band 2 do?", "what params does Serum have?")
    # failure_cases_index    → procedural: advisory "what went wrong / what to avoid" queries
    #                          ("what happened when I used PluginBridge on the drum bus?")
    #                          No execution risk — MENTOR is retrieval-only advice mode.
    #                          Failure context improves advice without enabling dangerous writes.
    "MENTOR": [
        "producer_memory_index",
        "plugin_operator_index",
        "failure_cases_index",
    ],
    # ── INTERN_READ: inspect Ableton, session, audio, memory ──────────────────
    # project_session_index  → episodic: current-song decisions and history
    #                          ("what EQ did I use this session on the vocal?")
    # producer_memory_index  → semantic: cross-project habits and preferences
    #                          ("what is my usual compression approach?")
    # plugin_operator_index  → procedural: plugin parameter inspection
    #                          ("show me the params for Pro-Q 4")
    # audio_analysis_index   → measurement: LUFS, stereo, spectrum evidence
    #                          ("what was my LUFS reading from the last analysis?")
    "INTERN_READ": [
        "project_session_index",
        "producer_memory_index",
        "plugin_operator_index",
        "audio_analysis_index",
    ],
    # ── INTERN_WRITE_SAFE: small reversible change ─────────────────────────────
    # Safe writes that touch Ableton LOM internals (routing, track creation,
    # clip ops, MIDI edits) still retrieve relevant failure evidence.
    # The 0.30 threshold ensures only matching failure cases inject.
    # project_session_index excluded: session history is not needed before a safe write.
    "INTERN_WRITE_SAFE": [
        "producer_memory_index",
        "plugin_operator_index",
        "failure_cases_index",
    ],
    # ── INTERN_WRITE_RISKY: dangerous write — retrieve safety info first ───────
    # Safety-first ordering enforced by RISKY_WRITE_RETRIEVAL_ORDER below.
    # project_session_index intentionally excluded — session history is noise
    # when confirming a potentially destructive action.
    "INTERN_WRITE_RISKY": [
        "failure_cases_index",
        "plugin_operator_index",
        "producer_memory_index",
        "audio_analysis_index",
    ],
    # ── CLARIFY: too ambiguous to proceed safely — minimal retrieval ───────────
    "CLARIFY":          ["producer_memory_index"],
    # ── FREEFORM_GENERAL: non-music general query ─────────────────────────────
    # project_session_index excluded: DAW/session context must not leak into
    #   off-topic responses.
    # plugin_operator_index, failure_cases_index excluded: procedural/safety
    #   knowledge is session-specific and irrelevant for general queries.
    # audio_analysis_index excluded: measurement evidence is session-specific.
    # producer_memory_index retained: cross-session preferences (taste, workflow
    #   habits) are global and can inform general advice.
    "FREEFORM_GENERAL": ["producer_memory_index"],
}


# ── FREEFORM_GENERAL DETECTION ────────────────────────────────────────────────
# Conservative guardrail — only fires when the request is CLEARLY non-music,
# non-Ableton, and non-project-related.
#
# Rule: if the prompt is ambiguous, do NOT force FREEFORM.
# Ambiguous prompts fall through to CLARIFY or MENTOR so Conductor context
# is never bypassed accidentally.
#
# Safety test for every pattern:
#   ✗ "write a bassline"              → must NOT match (music term)
#   ✗ "write a short hook"            → must NOT match (music term)
#   ✗ "translate this feeling to chords" → must NOT match (music context)
#   ✗ "make it warmer"                → must NOT match (production instruction)
#   ✗ "what should I make next"       → must NOT match (ambiguous: music or food)
#   ✗ "what should I do next"         → must NOT match (ambiguous)
#   ✗ "translate this"                → must NOT match (ambiguous)
#
# When adding a new pattern: confirm it passes ALL safety tests above.

FREEFORM_PATTERNS = [

    # ── Food / cooking ────────────────────────────────────────────────────────
    # "make", "order", "watch", "buy" intentionally EXCLUDED — ambiguous in music context.
    # "what should I make next" could be "what track should I make next this session".
    # Only "eat" and "cook" are unambiguously non-music verbs.
    r"\bwhat (should i|do i) (eat|cook)\b",
    r"\bwhat (should i|do i) have for (breakfast|lunch|dinner|a snack)\b",
    r"\brecipe (for|to make)\b",   # "recipe for X" has zero music meaning
    r"\bhow (do i|to) cook\b",

    # ── Weather / current events ──────────────────────────────────────────────
    r"\bwhat('?s| is) the weather\b",
    r"\bweather (in|for|today|tomorrow)\b",

    # ── Writing — explicit non-music document formats only ────────────────────
    # email, story, essay, letter — no music production meaning.
    # "poem" intentionally excluded — too close to song lyrics.
    # "hook", "riff", "melody", "bassline" are NOT in this list.
    # Allow 0-3 intervening adjectives: "write a short email", "write me a quick letter".
    r"\bwrite (\w+\s+){0,3}(email|story|essay|letter|blog post|cover letter|resignation letter|apology letter)\b",
    r"\b(can you|help me|please) write (\w+\s+){0,3}(email|story|essay|letter)\b",

    # ── Translation — MUST name a spoken human language ──────────────────────
    # Bare "translate" is AMBIGUOUS: "translate this feeling into chords" is music work.
    # "translate this to Hindi" and "translate the text into Japanese" are clearly non-music.
    # Language name is required. 0-3 intervening words allowed before (to|into|from).
    # Safety: language list is exhaustive — "chords", "a chord voicing", etc. never match.
    r"\btranslate (\w+\s+){0,3}(to|into|from) "
    r"(hindi|tamil|telugu|punjabi|urdu|bengali|marathi|"
    r"french|spanish|german|arabic|chinese|japanese|korean|"
    r"portuguese|italian|russian|dutch|turkish|english|swahili|"
    r"greek|hebrew|thai|vietnamese|indonesian|malay|persian|"
    r"polish|ukrainian|swedish|norwegian|danish|finnish|czech)\b",

    # ── Small talk ────────────────────────────────────────────────────────────
    r"\btell me a joke\b",
    r"\bwhat time is it\b",
    r"\bwhat('?s| is) today('?s date| the date)?\b",

    # ── Named-person / factual knowledge ─────────────────────────────────────
    # Role queries: must include "of/in" to prevent "who is the singer" (music context)
    r"\bwho (is|was) (the )?(prime minister|president|king|queen|chancellor|"
    r"pope|governor|emperor) (of|in)\b",
    # Geography / trivia
    r"\bwhat('?s| is) the (capital|currency|population|official language) of \w",

    # ── Life / admin ──────────────────────────────────────────────────────────
    r"\bhow (do i|to) (file|apply for|submit a|renew a|get a|pay for|register for|cancel a) \w",
]


# ── VALIDATION ────────────────────────────────────────────────────────────────

def validate_metadata(collection: str, metadata: dict) -> tuple:
    """
    Validate a metadata dict against the schema for a given collection.

    Returns:
        (is_valid: bool, errors: list[str])

    Errors = wrong types (hard failure).
    Missing fields are warnings only — make_metadata() handles defaults.
    """
    schema = COLLECTION_SCHEMAS.get(collection, {field: spec for field, spec in _COMMON.items()})
    errors = []

    for field, (expected_type, _) in schema.items():
        if field not in metadata:
            continue  # missing field — make_metadata() fills defaults
        val = metadata[field]
        if not isinstance(val, expected_type):
            errors.append(
                f"'{field}': expected {expected_type.__name__}, "
                f"got {type(val).__name__} = {val!r}"
            )

    # source_type must be valid for this collection
    coll_key = COLLECTION_KEYS.get(collection)
    if coll_key and "source_type" in metadata:
        st = metadata["source_type"]
        valid = SOURCE_TYPES.get(coll_key, [])
        if st and st not in valid:
            errors.append(
                f"'source_type' = '{st}' not valid for {collection}. "
                f"Valid: {valid}"
            )

    # memory_level must be 1–4
    if "memory_level" in metadata:
        lvl = metadata["memory_level"]
        if lvl not in MEMORY_LEVELS:
            errors.append(f"'memory_level' = {lvl} invalid — must be 1, 2, 3, or 4")

    # confidence must be 0.0–1.0
    if "confidence" in metadata:
        c = metadata["confidence"]
        if isinstance(c, float) and not (0.0 <= c <= 1.0):
            errors.append(f"'confidence' = {c} out of range — must be 0.0–1.0")

    return len(errors) == 0, errors


def make_metadata(collection: str, overrides: dict = None) -> dict:
    """
    Build a complete metadata dict with all defaults for a given collection.
    Stamps created_at and updated_at automatically.
    Pass overrides= to set specific fields.

    Usage:
        meta = make_metadata("producer_memory_index", {
            "memory_level": 2,
            "source_type":  "session_decision",
            "project_id":   "abc123",
            "plugin":       "Pro-Q 4",
            "stage":        "mixing",
            "confidence":   0.8,
        })
    """
    schema = COLLECTION_SCHEMAS.get(collection, {f: s for f, s in _COMMON.items()})
    meta = {field: default for field, (_, default) in schema.items()}
    meta["collection"] = collection
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta["created_at"] = now
    meta["updated_at"] = now
    if overrides:
        meta.update(overrides)
    return meta


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("── Collections ──")
    for k, v in COLLECTIONS.items():
        print(f"  {k:10} → {v}")

    print("\n── Memory Levels ──")
    for lvl, info in MEMORY_LEVELS.items():
        print(f"  Level {lvl}: {info['name']:30} weight={info['retrieval_weight']}")

    print("\n── Similarity Thresholds ──")
    for col, thresh in SIMILARITY_THRESHOLDS.items():
        print(f"  {col}: {thresh}")

    print("\n── make_metadata() test ──")
    meta = make_metadata("producer_memory_index", {
        "memory_level": 3,
        "source_type":  "confirmed_preference",
        "project_id":   "abc123",
        "plugin":       "Pro-Q 4",
        "stage":        "mixing",
        "confidence":   0.9,
        "approved":     True,
    })
    ok, errs = validate_metadata("producer_memory_index", meta)
    print(f"  Valid: {ok} | Errors: {errs or 'none'}")
    print(f"  Fields: {list(meta.keys())}")

    print("\n── validate_metadata() — bad input ──")
    bad = make_metadata("plugin_operator_index", {
        "memory_level": 7,          # invalid level
        "source_type":  "bad_type", # invalid source type
        "confidence":   1.5,        # out of range
        "owner_verified": "yes",    # wrong type (should be bool)
    })
    ok2, errs2 = validate_metadata("plugin_operator_index", bad)
    print(f"  Valid: {ok2}")
    for e in errs2:
        print(f"  ✗ {e}")

    print("\n── Audio Freshness ──")
    import time
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_iso = "2026-01-01T00:00:00Z"
    print(f"  Now  → {get_audio_freshness(now_iso)}")
    print(f"  Old  → {get_audio_freshness(old_iso)}")
    print(f"  ''   → {get_audio_freshness('')}")

    print("\n── Mode → Collection Map ──")
    for mode, cols in MODE_COLLECTION_MAP.items():
        print(f"  {mode:22} → {cols or ['(none — FREEFORM)']}")

    print("\n  All checks complete.")
