"""
Conductor — Context Pack Audit Logger (C2)
─────────────────────────────────────────────────
Writes one JSONL entry per /context/pack request so every context build
can be reconstructed offline — what Claude saw and why.

Design rules:
  - Best-effort and non-fatal: logging failure never breaks the inference path.
  - Local / offline-first: plain JSONL, no network, no ChromaDB.
  - Does not log secrets beyond what is already in the debug payload.
  - Thread-safe: uses a module-level lock around file open/write/close.

Log location: memory/context_pack_log.jsonl  (relative to TEST-BUILD root)
Each line: one JSON object, newline-terminated.

Called by conductor_bridge.py GET /context/pack handler after build_message_pack()
returns. Import is lazy so the logger is never a hard dependency.
"""

import datetime
import json
import os
import threading

# ── CONFIG ────────────────────────────────────────────────────────────────────

# Resolved relative to this file's directory (rag/) → one level up is TEST-BUILD root
_HERE    = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_HERE)           # TEST-BUILD/
LOG_DIR  = os.path.join(_ROOT, "memory")   # memory/ — already exists for chromadb
LOG_PATH = os.path.join(LOG_DIR, "context_pack_log.jsonl")

# Module-level write lock — HTTPServer spawns one thread per request
_write_lock = threading.Lock()


# ── PUBLIC API ────────────────────────────────────────────────────────────────

def log_pack(query: str, result: dict) -> str | None:
    """
    Write one JSONL audit record for a /context/pack build.

    Args:
        query:  The raw user message passed to build_message_pack().
        result: The dict returned by build_message_pack().

    Returns:
        Log path string on success, None on failure.

    Never raises. All exceptions are caught and swallowed so the caller's
    response is never affected.
    """
    try:
        record = _build_record(query, result)
        _append_record(record)
        return LOG_PATH
    except Exception:
        return None


def log_pack_error(query: str, error: str) -> None:
    """
    Write a minimal audit record for a /context/pack that failed before
    build_message_pack() could return a result.

    Never raises.
    """
    try:
        record = {
            "timestamp": _now_iso(),
            "query":     query[:500],
            "mode":      "ERROR",
            "error":     str(error)[:300],
        }
        _append_record(record)
    except Exception:
        pass


# ── RECORD BUILDER ─────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_record(query: str, result: dict) -> dict:
    """
    Distil the build_message_pack() result into a compact audit record.
    Evidence items include all completeness fields from C1 Step 1.
    """
    debug = result.get("debug", {}) or {}
    ev_raw = debug.get("evidence", []) or []

    # Compact evidence — keep every field already in the debug payload
    evidence = []
    skipped   = []
    for item in ev_raw:
        ev_entry = {
            "id":                  item.get("id", ""),
            "collection":          item.get("collection", ""),
            "similarity":          item.get("similarity", 0.0),
            "final_score":         item.get("final_score", 0.0),
            "confidence":          item.get("confidence", 0.0),
            "age_days":            item.get("age_days", -1.0),
            "injected":            item.get("injected", False),
            "superseded":          item.get("superseded", False),
            "superseded_by":       item.get("superseded_by", ""),
            "rejected":            item.get("rejected", False),
            "skip_reason":         item.get("skip_reason", ""),
            # C1 Step 1 completeness fields
            "source_type":         item.get("source_type", "unknown"),
            "verification_status": item.get("verification_status", "unknown"),
            "bm25_score":          item.get("bm25_score", 0.0),
            "reason_injected":     item.get("reason_injected", ""),
            "token_count":         item.get("token_count", 0),
            "project_id":          item.get("project_id", ""),
            "session_id":          item.get("session_id", ""),
            "plugin_id":           item.get("plugin_id", ""),
            "freshness":           item.get("freshness", "unknown"),
            "rescue_mode":         item.get("rescue_mode", None),
            "conflict_flag":       item.get("conflict_flag", False),
            # Truncated text for reconstruction (not full to keep log compact)
            "text_preview":        (item.get("text", "") or "")[:80],
        }
        evidence.append(ev_entry)
        if not item.get("injected", True) and item.get("skip_reason"):
            skipped.append({
                "id":          item.get("id", ""),
                "collection":  item.get("collection", ""),
                "skip_reason": item.get("skip_reason", ""),
            })

    record = {
        "timestamp":            _now_iso(),
        "query":                (query or "")[:500],
        "mode":                 result.get("mode", ""),
        "protection_level":     result.get("protection_level", ""),
        "risk_category":        result.get("risk_category", ""),
        "auto_execute_allowed": bool(result.get("auto_execute_allowed", False)),
        "confirmation_required": bool(result.get("confirmation_required", False)),
        "pack_chars":           debug.get("pack_chars", len(result.get("pack", ""))),
        "token_estimate":       debug.get("token_estimate", 0),
        "memory_hits":          debug.get("memory_hits", 0),
        "injected_count":       debug.get("injected_count", 0),
        "plugin_card":          debug.get("plugin_card", ""),
        "freeform":             bool(debug.get("freeform", False)),
        "evidence":             evidence,
        "skipped":              skipped,
    }
    return record


# ── FILE I/O ──────────────────────────────────────────────────────────────────

def _append_record(record: dict) -> None:
    """Append one JSON line to the log file. Thread-safe."""
    os.makedirs(LOG_DIR, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _write_lock:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)


# ── READER HELPERS (for tests and CLI) ────────────────────────────────────────

def read_last_record() -> dict | None:
    """
    Return the last JSONL record from the log, or None if empty / missing.
    Used by tests — never called on the inference path.
    """
    try:
        if not os.path.exists(LOG_PATH):
            return None
        last = None
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        last = json.loads(line)
                    except Exception:
                        pass
        return last
    except Exception:
        return None


def read_all_records() -> list:
    """Return all JSONL records as a list. Used by tests."""
    try:
        if not os.path.exists(LOG_PATH):
            return []
        records = []
        with open(LOG_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except Exception:
                        pass
        return records
    except Exception:
        return []
