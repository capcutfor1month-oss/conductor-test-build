"""
Build 21 — Taste Context Injection v1.

Reads the most-recent session reflection and returns a compact,
non-user-visible taste context block for the Creative Critic.

Rules enforced here:
  - Only Level 1–2 signals.
  - Only session_only and session_project scopes — never global_taste or unknown.
  - Never includes negative feedback types.
  - If project_id is given, session_project signals are further filtered to that project.
  - Output contains no memory IDs, scores, confidence numbers, or collection names.
  - Returns "" if no safe signals exist or the reflection log is unavailable.
  - Never raises.

Do not write to any log, ChromaDB collection, or runtime file from this module.
"""

import json
import os
import re
from typing import Optional

_HERE       = os.path.dirname(os.path.abspath(__file__))
_ROOT       = os.path.dirname(_HERE)
_MEMORY_DIR = os.path.join(_ROOT, "memory")

DEFAULT_REFLECTION_PATH = os.path.join(_MEMORY_DIR, "session_reflection_log.jsonl")

# Exported so harness_server can add it to the trust-label leak guard.
TASTE_HEADER = "## Taste Context"

_SAFE_SCOPES = frozenset({"session_only", "session_project"})
_NEGATIVE_FEEDBACK_TYPES = frozenset({
    "UNDO", "WRONG_DIRECTION", "NOT_HELPFUL", "WRONG", "OUTDATED",
})
_LEVEL_CAP   = 2
_MAX_SIGNALS = 5
_MAX_CHARS   = 480

# Patterns for internal/debug text that must never appear in a taste line.
# Case-insensitive for field names and labels.
_INTERNAL_LABEL_RE = re.compile(
    r"(?i)("
    # underscore-joined schema field names
    r"\bcandidate_id\b|\bproof_id\b|\brequest_id\b|\baction_id\b"
    r"|\bsource_type\b|\bfeedback_type\b|\bmemory_level\b"
    r"|\bsession_id\b|\bproject_id\b"
    # space-separated ID label variants (e.g. "proof id", "action id")
    r"|\b(?:candidate|proof|request|action)\s+id\b"
    # key:value pairs with no space after colon (schema/action-log style)
    r"|\baction:[A-Za-z\d]"
    r"|\btarget:[A-Za-z\d]"
    # raw target path references: track:Kick, device:Pro-Q 4
    r"|\b(?:track|device|plugin|clip|scene|bus|send|return|master):[A-Za-z\d]"
    # collection/index names
    r"|producer_memory_index|project_session_index|plugin_operator_index"
    r"|failure_cases_index|audio_analysis_index"
    # numeric score/confidence labels
    r"|\bscore\s*[:=]\s*[\d.]+"
    r"|\bconfidence\s*[:=]\s*[\d.]+"
    r"|\bcollection\s*[:=]"
    # existing internal text labels
    r"|KNOWLEDGE\s+STATUS|Operator\s+card"
    # standalone raw ID-looking tokens: long hex strings (12+ hex chars) and UUIDs
    r"|\b[0-9a-f]{12,}\b"
    r"|\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"
    r")"
)
# Case-sensitive: all-caps snake_case action enums (SET_TRACK_VOLUME, INTERN_WRITE_SAFE).
# Kept separate so normal lowercase snake_case (session_only, etc.) is not blocked.
_ALLCAPS_ENUM_RE = re.compile(r"\b[A-Z]{2,}(?:_[A-Z]{2,})+\b")
_JSON_RE = re.compile(r'[{}\[\]]|"[a-z_]+"\s*:')


def _load_latest_reflection(path: str) -> dict:
    """Read the last JSONL record from the reflection log. Returns {} on any error."""
    try:
        last: dict = {}
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        last = json.loads(line)
                    except json.JSONDecodeError:
                        pass
        return last
    except Exception:
        return {}


def _is_clean_text(text: str) -> bool:
    """Return True if text contains no internal/debug labels safe to include in output."""
    if _INTERNAL_LABEL_RE.search(text):
        return False
    if _ALLCAPS_ENUM_RE.search(text):
        return False
    if _JSON_RE.search(text):
        return False
    return True


def _signal_text(signal: dict) -> str:
    """
    Build a short natural-language description of the signal.
    Prefers evidence over message over action_type+target.
    Returns "" if the best available text contains internal/debug labels.
    """
    evidence    = (signal.get("evidence")    or "").strip()
    message     = (signal.get("message")     or "").strip()
    action_type = (signal.get("action_type") or "").strip()
    target      = (signal.get("target")      or "").strip()

    # Prefer evidence, then message — skip if either contains internal labels.
    for candidate in (evidence[:120], message[:120]):
        if candidate and _is_clean_text(candidate):
            return candidate

    # Fallback: action_type+target come from schema fields (safer), still filtered.
    if action_type and target:
        combo = f"{action_type} on {target}"
        if _is_clean_text(combo):
            return combo
    if action_type and _is_clean_text(action_type):
        return action_type
    return ""


def build_taste_context(
    reflection_path: Optional[str] = None,
    project_id: Optional[str] = None,
    reflection: Optional[dict] = None,
) -> str:
    """
    Return a compact, non-user-visible taste context block for the Creative Critic.
    Returns "" if no safe signals are available.

    Filters accepted_signals from the most-recent reflection entry:
      Gate 1 — scope must be session_only or session_project.
      Gate 2 — feedback_type must not be a negative type.
      Gate 3 — suggested_level must be 1 or 2.
      Gate 4 — session_project signals require both the caller's project_id
                and the signal's project_id to be non-empty and identical;
                session_only signals always pass this gate.

    Parameters
    ----------
    reflection_path : path to session_reflection_log.jsonl (default: memory/ location)
    project_id      : optional project scoping filter (MD5 string from /context/session)
    reflection      : pass a dict directly (for tests — skips file I/O)

    Never raises.
    """
    if reflection is None:
        path = reflection_path or DEFAULT_REFLECTION_PATH
        reflection = _load_latest_reflection(path)

    if not reflection:
        return ""

    accepted = reflection.get("accepted_signals") or []
    lines: list = []

    for signal in accepted:
        scope          = (signal.get("scope")          or "").strip()
        feedback_type  = (signal.get("feedback_type")  or "").strip()
        sig_project_id = (signal.get("project_id")     or "").strip()

        try:
            level = int(signal.get("suggested_level", 1))
        except (TypeError, ValueError):
            level = 1

        # Gate 1: safe scopes only
        if scope not in _SAFE_SCOPES:
            continue
        # Gate 2: no negative feedback types
        if feedback_type in _NEGATIVE_FEEDBACK_TYPES:
            continue
        # Gate 3: level cap
        if level > _LEVEL_CAP:
            continue
        # Gate 4: session_project requires both project_ids non-empty and equal.
        # session_only signals bypass this gate entirely.
        if scope == "session_project":
            if not project_id or not sig_project_id or sig_project_id != project_id:
                continue

        text = _signal_text(signal)
        if not text:
            continue

        lines.append(f"- {text}")
        if len(lines) >= _MAX_SIGNALS:
            break

    if not lines:
        return ""

    block = TASTE_HEADER + "\n" + "\n".join(lines)
    if len(block) > _MAX_CHARS:
        # Hard cap: cut at last complete line within budget
        block = block[:_MAX_CHARS].rsplit("\n", 1)[0]
    return block
