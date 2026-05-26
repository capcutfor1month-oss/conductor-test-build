"""
Conductor — Context Pack Builder (B1)
──────────────────────────────────────
Three layers. Each has a different lifetime and call frequency.

  LAYER A — System prompt     → app/system_prompt.md
    Sent as `system` param on EVERY Anthropic API call.
    Fetched ONCE at session start. Never changes during a session.
    → bridge: GET /context/system_prompt

  LAYER B — Session pack      → DNA + project state + tool health
    Injected at session start. REFRESHED when tool state changes
    (Ableton connects/disconnects, project opens/closes).
    NOT re-fetched on every message — only when state changes.
    → bridge: GET /context/session

  LAYER C — Message pack      → ChromaDB top 3 + operator card + mode
    Generated FRESH on every user message.
    Specific to the content of that message — memory search, plugin detection.
    → bridge: GET /context/pack?q=message

Final user content sent to Anthropic:
  {session_pack}

  {message_pack}

  ---
  User: {user_text}

System prompt is always in the `system` parameter — separate from user content.
"""

import datetime
import hashlib
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # TEST-BUILD root
sys.path.insert(0, _ROOT)

from rag.request_mode_classifier import classify
from rag.routed_retriever import retrieve as _routed_retrieve
from rag.risk_taxonomy import get_card_file_for_message as _get_card_file

# ── PATHS ─────────────────────────────────────────────────────────────────────

VAULT_ROOT     = os.path.join(_ROOT, "conductor-vault")
PRODUCER_DNA   = os.path.join(VAULT_ROOT, "producer", "producer_dna.md")
PLUGINS_DIR    = os.path.join(VAULT_ROOT, "plugins")
PROJECT_STATE  = os.path.join(_ROOT, "CURRENT PROJECT STATE.md")
CHROMA_PATH    = os.path.join(_ROOT, "memory", "chromadb")

# PLUGIN_CARD_MAP is removed. Plugin detection is now driven by:
#   data/known_plugins.json  (has_card=True entries, natural_names for NL matching)
#   rag/risk_taxonomy.get_card_file_for_message()
# Adding a new plugin with an operator card = add JSON entry, no code change here.

# ── SHARED HELPERS ────────────────────────────────────────────────────────────

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ── LAYER B — SESSION PACK ────────────────────────────────────────────────────

def _compute_state_hash(bridge_status: dict, project_content: str) -> str:
    """
    Compact 12-char MD5 hash of the most state-sensitive fields.
    Changes when: Ableton connects/disconnects, project changes, PluginBridge state changes.

    The UI stores this after every session-pack fetch. If the next bridge poll
    shows a different hash, the session pack is stale — refresh before any RISKY write.
    """
    ableton  = bridge_status.get("ableton", "unknown") if bridge_status else "unknown"
    pb       = bridge_status.get("pluginbridge", "unknown") if bridge_status else "unknown"
    mem      = bridge_status.get("memory", "unknown") if bridge_status else "unknown"
    # First 300 chars of project state covers Name, Stage, BPM, Key
    proj_sig = project_content.strip()[:300] if project_content else ""
    raw = f"{ableton}|{pb}|{mem}|{proj_sig}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _parse_producer_dna(content: str) -> str:
    """Extract compact summary from producer_dna.md. Skip unfilled template lines."""
    if not content.strip():
        return ""
    fields = {}
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("Name:"):             fields["name"]   = line[5:].strip()
        elif line.startswith("Level:"):          fields["level"]  = line[6:].strip()
        elif line.startswith("Primary:") and "genre" not in fields:
            fields["genre"]  = line[8:].strip()
        elif line.startswith("Primary EQ:"):     fields["eq"]     = line[11:].strip()
        elif line.startswith("Primary Compressor:"): fields["comp"] = line[19:].strip()
        elif line.startswith("Primary Reverb:"): fields["reverb"] = line[15:].strip()
        elif line.startswith("Primary Saturator:"): fields["sat"] = line[18:].strip()
        elif line.startswith("Describe your sound in 3 words:"):
            fields["sound"] = line[31:].strip()
        elif line.startswith("Emotional intent"):
            fields["intent"] = line[line.index(":")+1:].strip() if ":" in line else ""

    lines = ["## PRODUCER DNA"]
    if fields.get("name"):   lines.append(f"Producer: {fields['name']}")
    if fields.get("level"):  lines.append(f"Level: {fields['level']}")
    if fields.get("genre"):  lines.append(f"Primary genre: {fields['genre']}")
    if fields.get("sound"):  lines.append(f"Sound: {fields['sound']}")
    if fields.get("intent"): lines.append(f"Intent: {fields['intent']}")
    anchors = [v for k, v in fields.items() if k in ("eq","comp","reverb","sat") and v]
    if anchors: lines.append(f"Anchor plugins: {' · '.join(anchors)}")

    # Drop unfilled template lines
    lines = [l for l in lines
             if not re.match(r"^[^:]+:\s*$", l)
             and "[ ]" not in l
             and l.strip() not in ("", "___________________")]
    return "\n".join(lines) if len(lines) > 1 else ""


# ── Project state field aliases ───────────────────────────────────────────────
# Maps lowercase variants (including "key / scale:" from the actual file) to
# canonical field names used internally and in the output block.
_PROJECT_FIELD_ALIASES: dict = {
    "project name":         "Project Name",
    "current stage":        "Current Stage",
    "stage":                "Current Stage",   # bare "Stage:" accepted
    "bpm":                  "BPM",
    "key":                  "Key",
    "key / scale":          "Key",             # actual format in CURRENT PROJECT STATE.md
    "key/scale":            "Key",             # no-space variant
    "genre":                "Genre",
    "sub-genre / hybrid":   "Genre",           # hybrid field → Genre
    "tracks":               "Tracks",
    "current issue":        "Current Issue",
    "date saved":           "Date Saved",
}

_EMPTY_VALUES = {"", "-", "—", "TBD", "None"}


def _project_field_canonical(raw_key: str) -> str | None:
    """
    Resolve a raw field name from the markdown to a canonical name.
    Handles bold markdown (strips ** characters) and alias variants.
    Returns None if the key is not recognised.
    """
    # Strip bold markdown: **Key Name** → Key Name; **Key**: → Key
    cleaned = raw_key.strip().strip("*").rstrip(":").strip()
    return _PROJECT_FIELD_ALIASES.get(cleaned.lower())


def _parse_project_fields(content: str) -> dict:
    """
    Parse CURRENT PROJECT STATE.md into a dict of canonical field → value.

    Handles:
      - Plain text: ``Project Name: demo``
      - Bold markdown: ``**Project Name:** demo``
      - Field aliases: ``Key / Scale: C minor`` → key "Key"
      - Strips "(Default)" suffix from BPM values (e.g. "120 (Default)" → "120")
    """
    fields: dict = {}
    for line in content.splitlines():
        line = line.strip()
        if ":" not in line:
            continue
        colon_idx = line.index(":")
        raw_key = line[:colon_idx]
        val     = line[colon_idx + 1:].strip()

        # Strip residual bold-markdown stars from the value.
        # Bold format **Key:** value splits at the first ':' leaving '** value'.
        # Example: "**Project Name:** demo" → raw_key="**Project Name", val="** demo"
        val = val.lstrip("*").strip()

        canonical = _project_field_canonical(raw_key)
        if canonical is None:
            continue
        if not val or val in _EMPTY_VALUES:
            continue

        # Skip bracket placeholder values — e.g. "(Vision / Production / Mixing / Master)"
        # These are option lists from the template, not real selected values.
        if val.startswith("(") and val.endswith(")"):
            continue

        # Strip "(Default)" suffix (common for template BPM values)
        if canonical == "BPM":
            val = re.sub(r"\s*\(Default\)\s*$", "", val, flags=re.IGNORECASE).strip()
            if not val or val in _EMPTY_VALUES:
                continue

        fields[canonical] = val

    return fields


def _parse_project_state(content: str) -> str:
    """
    Parse CURRENT PROJECT STATE.md into compact session-pack block.

    Returns "" if the file is an unfilled template (all values empty or placeholder).
    A block is only returned when at least one displayable data field is present.
    """
    if not content.strip():
        return ""
    fields = _parse_project_fields(content)
    if not fields:
        return ""
    lines = ["## CURRENT PROJECT STATE"]
    if fields.get("Project Name"):  lines.append(f"Project: {fields['Project Name']}")
    if fields.get("Current Stage"): lines.append(f"Stage: {fields['Current Stage']}")
    if fields.get("BPM"):           lines.append(f"BPM: {fields['BPM']}")
    if fields.get("Key"):           lines.append(f"Key: {fields['Key']}")
    if fields.get("Genre"):         lines.append(f"Genre: {fields['Genre']}")
    if fields.get("Tracks"):        lines.append(f"Tracks: {fields['Tracks']}")
    if fields.get("Current Issue"): lines.append(f"Current issue: {fields['Current Issue']}")
    # If only the header was assembled (all values were empty/placeholder/unparseable),
    # return "" so has_project stays False and nothing is injected into the session pack.
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def _parse_project_freshness(content: str) -> tuple:
    """
    Compute how stale the project state file is from its ``Date Saved`` field.

    Returns (freshness_label: str, date_saved_str: str).
    freshness_label: 'fresh' | 'recent' | 'stale' | 'old' | 'unknown'
      fresh   — saved today
      recent  — saved 1 day ago
      stale   — saved 2–7 days ago
      old     — saved more than 7 days ago
      unknown — no Date Saved field or unparseable date
    """
    if not content.strip():
        return "unknown", ""

    fields = _parse_project_fields(content)
    date_saved = fields.get("Date Saved", "")
    if not date_saved:
        return "unknown", ""

    try:
        then = datetime.datetime.strptime(date_saved, "%Y-%m-%d")
        now  = datetime.datetime.utcnow()
        age_days = (now - then).days
        if age_days == 0:
            label = "fresh"
        elif age_days <= 1:
            label = "recent"
        elif age_days <= 7:
            label = "stale"
        else:
            label = "old"
    except Exception:
        return "unknown", date_saved

    return label, date_saved


def _build_tool_status(bridge_status: dict) -> str:
    """Format tool health block from bridge status dict."""
    if not bridge_status:
        return "## TOOL STATUS\nAll tools: unknown (bridge not polled yet)"
    s = bridge_status
    ableton = "connected" if s.get("ableton") == "connected" else "disconnected"
    nlm     = "connected" if s.get("notebooklm") == "ready" else "not connected"
    aa      = "available" if s.get("audio_analyzer") == "ready" else "not available"
    mem     = "ready"     if s.get("memory") == "ready" else "not installed"
    pb      = s.get("pluginbridge", "unknown")
    lines = [
        "## TOOL STATUS",
        f"Ableton: {ableton}",
        f"Audio Analyzer: {aa}",
        f"NotebookLM: {nlm}",
        f"Memory (ChromaDB): {mem}",
        f"PluginBridge: {pb}",
    ]
    return "\n".join(lines)


def build_session_pack(bridge_status: dict = None) -> dict:
    """
    LAYER B — Build the session context pack.

    Contents: Producer DNA + current project state + tool health.
    Call at session start and whenever tool state changes.
    Do NOT call on every message.

    Returns:
        {
          "ok": True,
          "pack": str,
          "session_pack_version": str,   # ISO-8601 UTC — when this pack was built
          "state_hash": str,             # 12-char MD5 — changes on Ableton/project drift
          "ableton": str,
          "project": str,
          "project_id": str,             # stable MD5 of project name+BPM+key
          "project_freshness": str,      # fresh|recent|stale|old|unknown
          "project_date_saved": str,     # YYYY-MM-DD from Date Saved field
          "has_dna": bool,
          "has_project": bool,
          "session_valid": bool,         # True if the pack was built without error
          "block_risky": bool,           # True when risky writes should be blocked
          "block_reason": str,           # human-readable reason if block_risky=True
          "pack_chars": int,
          "token_estimate": int,
        }

    Risky-action safety gate (block_risky):
      A RISKY write executes DAW commands that are hard to undo.
      The pre-risky hook refreshes this pack and the UI checks block_risky.
      If Ableton is disconnected the session state cannot be verified —
      block_risky=True forces the UI to show an error instead of the confirm gate.
      Normal MENTOR / READ / SAFE_WRITE actions are NOT affected.
    """
    parts = []

    dna = _parse_producer_dna(_read_file(PRODUCER_DNA))
    if dna:
        parts.append(dna)

    project_raw = _read_file(PROJECT_STATE)
    project     = _parse_project_state(project_raw)
    if project:
        parts.append(project)

    status = _build_tool_status(bridge_status)
    parts.append(status)

    pack = "\n\n".join(parts)

    # Version = UTC ISO timestamp of this build (for freshness tracking in the UI)
    version    = datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    state_hash = _compute_state_hash(bridge_status, project_raw)

    # Project identity / freshness
    project_id        = _get_project_id()
    proj_freshness, proj_date_saved = _parse_project_freshness(project_raw)

    # Risky-action gate: RISKY writes require Ableton to be connected so the
    # session state (track list, routing, bus state) can be read before execution.
    # Any other tool outage does NOT block risky writes by default.
    ableton_ok   = bool(bridge_status and bridge_status.get("ableton") == "connected")
    block_risky  = not ableton_ok
    block_reason = (
        "Ableton not connected — session state cannot be verified. "
        "Reconnect Ableton before executing a risky action."
    ) if block_risky else ""

    return {
        "ok":                   True,
        "pack":                 pack,
        "session_pack_version": version,
        "state_hash":           state_hash,
        "ableton":              bridge_status.get("ableton", "unknown") if bridge_status else "unknown",
        "project":              project_raw[:60] if os.path.exists(PROJECT_STATE) else "",
        "project_id":           project_id,
        "project_freshness":    proj_freshness,
        "project_date_saved":   proj_date_saved,
        "has_dna":              bool(dna),
        "has_project":          bool(project),
        "session_valid":        True,            # pack built without exception
        "block_risky":          block_risky,
        "block_reason":         block_reason,
        "pack_chars":           len(pack),
        "token_estimate":       len(pack) // 4,
    }


# ── LAYER C — MESSAGE PACK ────────────────────────────────────────────────────

def _get_project_id() -> str:
    """
    Derive a stable project ID from the current project state file.
    Used as a ChromaDB WHERE filter for project_session_index queries.
    Returns a short MD5 hash, or "" if no project is loaded.
    Uses the same alias-aware parser as _parse_project_state().
    """
    content = _read_file(PROJECT_STATE)
    if not content.strip():
        return ""
    fields = _parse_project_fields(content)
    name = fields.get("Project Name", "")
    bpm  = fields.get("BPM",          "")
    key  = fields.get("Key",           "")
    if not name and not bpm and not key:
        return ""
    raw = f"{name}|{bpm}|{key}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def _detect_plugin(message: str) -> str:
    """
    Return operator card filename if a known plugin is mentioned in the message.
    Driven by data/known_plugins.json (has_card=True, natural_names) via risk_taxonomy.
    No hardcoded keywords here — add new plugins to known_plugins.json.
    """
    return _get_card_file(message)


def _load_card_snippet(card_file: str) -> str:
    """
    Load compact snippet from operator card: Identity + Risky Writes + Never Do.
    Full card omitted — too large for every prompt.
    """
    path = os.path.join(PLUGINS_DIR, card_file)
    content = _read_file(path)
    if not content:
        return ""

    keep = {"Identity", "Risky Writes", "Never Do"}
    plugin_name = card_file.replace(" Operator Card.md", "").replace(".md", "")
    out = [f"## OPERATOR CARD — {plugin_name}"]
    capturing = False

    for line in content.splitlines():
        if line.startswith("## "):
            section = line[3:].strip()
            capturing = any(s.lower() in section.lower() for s in keep)
            if capturing:
                out.append("")
                out.append(line)
        elif capturing:
            if line.startswith("---"):
                capturing = False
            else:
                out.append(line)

    return "\n".join(out) if len(out) > 1 else ""


_RISK_LEVEL = {
    "INTERN_WRITE_RISKY": "HIGH",
    "INTERN_WRITE_SAFE":  "MEDIUM",
    "INTERN_READ":        "LOW",
    "MENTOR":             "LOW",
    "CLARIFY":            "MEDIUM",
}


def build_message_pack(message: str) -> dict:
    """
    LAYER C — Build the per-message context pack.

    ORDER (intentional): mode/risk FIRST, then memories, then operator card.
    Claude must see the risk classification before reading any retrieved context.

    Contents: Mode header + ChromaDB top 3 + operator card (if plugin mentioned).
    Called FRESH on every user message.

    Returns:
        {
            "ok": True,
            "pack": str,              — text injected into user content
            "mode": str,
            "risk_reason": str,
            "debug": {                — structured metadata for the UI debug view
                "memory_hits": int,
                "memories": [str],    — actual memory strings (top 3)
                "plugin_card": str,   — card name loaded, or ""
                "pack_chars": int,    — character count of pack
                "token_estimate": int — rough token count (chars / 4)
            }
        }
    """
    parts = []
    debug_memories = []
    debug_card = ""

    # ── Classify FIRST — mode leads the pack so Claude sees risk before context ──
    result      = classify(message)
    mode        = result["mode"]
    risk_reason = result.get("risk_reason", "")
    protection_level = result.get("protection_level", "STATUS_ONLY")
    risk_category = result.get("risk_category", "")
    rationale = result.get("rationale", risk_reason)
    auto_execute_allowed = bool(result.get("auto_execute_allowed", False))
    confirmation_required = bool(result.get("confirmation_required", mode == "INTERN_WRITE_RISKY"))
    confirm     = "yes" if confirmation_required else "no"
    risk_level  = _RISK_LEVEL.get(mode, "LOW")

    mode_lines = [
        "## MESSAGE PACK",
        f"Mode: {mode}",
        f"Risk: {risk_level}",
        f"Risk category: {risk_category or 'none'}",
        f"Protection level: {protection_level}",
        f"Auto execute allowed: {'YES' if auto_execute_allowed else 'NO'}",
        f"Confirmation required: {confirm.upper()}",
    ]
    if rationale:
        mode_lines.append(f"Reason: {rationale}")
    if protection_level == "UNDO_LOG_REQUIRED":
        mode_lines.append("Protection: log the action and preserve an undo path before executing.")
    if protection_level == "CLARIFY_REQUIRED":
        mode_lines.append("Protection: ask exactly one clarifying question before any action.")
    if protection_level == "BLOCK_UNSUPPORTED":
        mode_lines.append("Protection: block/explain; do not pretend to operate unsupported UI.")
    mode_lines.append("\nRelevant retrieved context:")
    parts.append("\n".join(mode_lines))

    # ── Memory search — routed retrieval (C1) ────────────────────────────────
    # Routes to correct collection(s) by mode, enforces similarity thresholds.
    # Returns both .retrieved (debug) and .injected (what goes into prompt).
    project_id     = _get_project_id()
    retrieval      = _routed_retrieve(message, mode, project_id=project_id)
    debug_memories = [i.text for i in retrieval.retrieved]   # everything retrieved
    debug_injected = [i.text for i in retrieval.injected]    # only what cleared threshold

    mem_lines = ["### Memory"]
    if retrieval.freeform:
        # Strict FREEFORM — no collections in map, all retrieval skipped
        mem_lines.append("(non-music query — retrieval skipped)")
    elif mode == "FREEFORM_GENERAL":
        # FREEFORM with partial retrieval (producer_memory_index only)
        mem_lines.append("(general query — project/session context excluded; producer preferences available)")
        if retrieval.summary_text:
            mem_lines.append(retrieval.summary_text)
    elif retrieval.summary_text:
        mem_lines.append(retrieval.summary_text)
    else:
        mem_lines.append("(none yet — builds over sessions)")
    parts.append("\n".join(mem_lines))

    # ── Operator card — only if this message mentions a known plugin ──────────
    card_file = _detect_plugin(message)
    if card_file:
        snippet = _load_card_snippet(card_file)
        if snippet:
            parts.append(snippet)
            debug_card = card_file.replace(" Operator Card.md", "").replace(".md", "")

    pack = "\n\n".join(parts)

    return {
        "ok":          True,
        "pack":        pack,
        "mode":        mode,
        "risk_reason": risk_reason,
        "risk_category": risk_category,
        "protection_level": protection_level,
        "auto_execute_allowed": auto_execute_allowed,
        "rationale": rationale,
        "confirmation_required": confirmation_required,
        "debug": {
            # retrieved = everything ChromaDB returned (shown in debug view)
            # injected  = subset that cleared the similarity threshold (went into prompt)
            # These can differ: e.g. 3 retrieved, 1 injected (2 below threshold)
            "memory_hits":       len(debug_memories),
            "memories":          debug_memories,       # raw retrieved texts
            "injected_count":    len(debug_injected),
            "injected_memories": debug_injected,       # only what cleared threshold
            "freeform":          retrieval.freeform,
            "plugin_card":       debug_card,
            "risk_category":     risk_category,
            "protection_level":  protection_level,
            "auto_execute_allowed": auto_execute_allowed,
            "rationale":         rationale,
            "confirmation_required": confirmation_required,
            "pack_chars":        len(pack),
            "token_estimate":    len(pack) // 4,
            # Structured evidence items (C4 — full labels for debug transparency)
            # Every retrieved item appears here, injected=True/False tells you
            # whether it made it into the prompt.
            "evidence": [
                {
                    # ── existing C4 fields (never removed) ──────────────────
                    "id":              e.id,
                    "text":            (e.text or "")[:120],
                    "collection":      e.collection,
                    "similarity":      round(e.similarity, 3),
                    "confidence":      round(e.confidence, 2),
                    "level":           e.memory_level,
                    "age_days":        round(e.age_days, 1),
                    "final_score":     e.final_score,
                    "label":           e.label,
                    "injected":        e.injected,
                    "superseded":      bool(e.superseded_by),
                    "superseded_by":   e.superseded_by,
                    "rejected":        e.rejected,
                    "skip_reason":     e.reason,
                    # ── C1 Step 1 — completeness fields ─────────────────────
                    "source_type":         e.source_type,
                    "verification_status": e.verification_status,
                    "bm25_score":          round(e.bm25_score, 4),
                    "reason_injected":     e.reason_injected,
                    "token_count":         e.token_count,
                    "project_id":          e.project_id,
                    "session_id":          e.session_id,
                    "plugin_id":           e.plugin_id,
                    "freshness":           e.freshness,
                    "rescue_mode":         e.rescue_mode,
                    "conflict_flag":       e.conflict_flag,
                }
                for e in retrieval.retrieved
            ],
        },
    }


# ── BACKWARD COMPAT ───────────────────────────────────────────────────────────
# Keep build_context_pack() so existing bridge code still works during transition.

def build_context_pack(message: str, bridge_status: dict = None) -> dict:
    """
    Combines session + message pack into one response.
    Used by GET /context/pack (bridge). UI should prefer using
    /context/session and /context/pack separately for correct caching.
    """
    session = build_session_pack(bridge_status)
    message_pack = build_message_pack(message)

    combined = session["pack"] + "\n\n" + message_pack["pack"] if session["pack"] else message_pack["pack"]

    return {
        "ok":          True,
        "pack":        combined,
        "mode":        message_pack["mode"],
        "risk_reason": message_pack["risk_reason"],
        "risk_category": message_pack.get("risk_category", ""),
        "protection_level": message_pack.get("protection_level", "STATUS_ONLY"),
        "auto_execute_allowed": message_pack.get("auto_execute_allowed", False),
        "rationale": message_pack.get("rationale", message_pack["risk_reason"]),
        "confirmation_required": message_pack.get("confirmation_required", False),
        "session_pack": session["pack"],
        "message_pack": message_pack["pack"],
    }


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    status = {
        "ableton": "connected", "notebooklm": "ready",
        "audio_analyzer": "ready", "memory": "ready",
        "pluginbridge": "detected on Vocal Bus",
    }

    print("── LAYER B: Session Pack ──")
    s = build_session_pack(status)
    print(s["pack"] or "(no project state yet — template unfilled)")

    print("\n── LAYER C: Message Pack ──")
    tests = [
        ("how do I compress a dhol", "MENTOR"),
        ("set Pro-Q 4 band 2 to cut 3.4kHz", "INTERN_WRITE_SAFE"),
        ("delete the scratch vocal", "INTERN_WRITE_RISKY"),
        ("what's the current BPM", "INTERN_READ"),
    ]
    all_pass = True
    for msg, expected in tests:
        r = build_message_pack(msg)
        ok = r["mode"] == expected
        if not ok: all_pass = False
        print(f"  {'✅' if ok else '❌'} [{r['mode']:22}] {msg}")
        if r["risk_reason"]: print(f"       Risk: {r['risk_reason']}")

    print(f"\n  All pass: {all_pass}")
