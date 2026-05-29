#!/usr/bin/env python3
"""
tools/read_feedback.py — Build 17: Feedback Signal Reader v1

Reads memory/knowledge_feedback_log.jsonl and returns a summary dict.
Read-only — no writes, no ChromaDB, no rag imports, no memory promotion.

Usage:
    python3 tools/read_feedback.py
    python3 tools/read_feedback.py /path/to/other.jsonl

Importable:
    from tools.read_feedback import summarize_feedback
    summary = summarize_feedback()          # default path
    summary = summarize_feedback(path)      # explicit path
"""

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_DEFAULT_LOG = os.path.join(_ROOT, "memory", "knowledge_feedback_log.jsonl")

_KNOWN_TYPES = {"HELPFUL", "NOT_HELPFUL", "TOO_VAGUE", "WRONG", "OUTDATED"}
_MAX_SAMPLE = 5


def summarize_feedback(path=None):
    """Read knowledge_feedback_log.jsonl and return a summary dict.

    Returns:
        {
            "total": int,
            "malformed_count": int,
            "period_start": str | None,   # earliest ISO-8601 timestamp
            "period_end": str | None,     # latest ISO-8601 timestamp
            "type_counts": {
                "HELPFUL": int,
                "NOT_HELPFUL": int,
                "TOO_VAGUE": int,
                "WRONG": int,
                "OUTDATED": int,
                "OTHER": int,
            },
            "messages_with_content": int,  # records where message != ""
            "sample_messages": [str, ...], # up to 5 non-empty messages
        }
    """
    log_path = path if path is not None else _DEFAULT_LOG

    # Initialise counters — all known types + OTHER always present
    type_counts = {t: 0 for t in _KNOWN_TYPES}
    type_counts["OTHER"] = 0

    total = 0
    malformed = 0
    timestamps = []
    messages_with_content = 0
    sample_messages = []

    # Missing or empty file → return zeroed summary
    if not os.path.exists(log_path):
        return _build_result(0, 0, None, None, type_counts, 0, [])

    try:
        with open(log_path, encoding="utf-8") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    malformed += 1
                    continue

                if not isinstance(record, dict):
                    malformed += 1
                    continue

                total += 1

                # feedback_type
                ftype = record.get("feedback_type", "")
                if ftype in _KNOWN_TYPES:
                    type_counts[ftype] += 1
                else:
                    type_counts["OTHER"] += 1

                # timestamp
                ts = record.get("timestamp")
                if ts and isinstance(ts, str):
                    timestamps.append(ts)

                # message
                msg = record.get("message", "")
                if not isinstance(msg, str):
                    msg = ""
                if msg:
                    messages_with_content += 1
                    if len(sample_messages) < _MAX_SAMPLE:
                        sample_messages.append(msg)

    except OSError:
        # Unreadable file — treat as empty
        return _build_result(0, 0, None, None, type_counts, 0, [])

    period_start = min(timestamps) if timestamps else None
    period_end = max(timestamps) if timestamps else None

    return _build_result(
        total, malformed, period_start, period_end,
        type_counts, messages_with_content, sample_messages
    )


def _build_result(total, malformed, period_start, period_end,
                  type_counts, messages_with_content, sample_messages):
    return {
        "total": total,
        "malformed_count": malformed,
        "period_start": period_start,
        "period_end": period_end,
        "type_counts": dict(type_counts),
        "messages_with_content": messages_with_content,
        "sample_messages": list(sample_messages),
    }


def _print_summary(summary):
    print("=" * 52)
    print("Knowledge Feedback Summary")
    print("=" * 52)
    print(f"  Total records     : {summary['total']}")
    print(f"  Malformed lines   : {summary['malformed_count']}")
    print(f"  Period start      : {summary['period_start'] or '—'}")
    print(f"  Period end        : {summary['period_end'] or '—'}")
    print()
    print("  Type counts:")
    for ftype in ("HELPFUL", "NOT_HELPFUL", "TOO_VAGUE", "WRONG", "OUTDATED", "OTHER"):
        print(f"    {ftype:<16}: {summary['type_counts'].get(ftype, 0)}")
    print()
    print(f"  Messages with text: {summary['messages_with_content']}")
    if summary["sample_messages"]:
        print("  Sample messages:")
        for msg in summary["sample_messages"]:
            print(f"    • {msg}")
    print("=" * 52)


if __name__ == "__main__":
    log_path = sys.argv[1] if len(sys.argv) > 1 else None
    result = summarize_feedback(log_path)
    _print_summary(result)
