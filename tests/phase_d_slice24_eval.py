#!/usr/bin/env python3
"""
phase_d_slice24_eval.py — Build 17: Feedback Signal Reader v1
Tests D221–D228.

All checks are static source analysis + unit-level functional tests.
No browser runtime, no ChromaDB, no network calls required.
"""

import importlib.util
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_TOOL_PATH = os.path.join(_ROOT, "tools", "read_feedback.py")
_LIVE_LOG   = os.path.join(_ROOT, "memory", "knowledge_feedback_log.jsonl")

PASS = "PASS"
FAIL = "FAIL"
results = []


def check(id_, desc, ok, detail=""):
    status = PASS if ok else FAIL
    results.append((id_, status, desc, detail))
    suffix = f"\n         → {detail}" if (not ok and detail) else ""
    print(f"  [{status}] {id_}: {desc}{suffix}")
    return ok


def read_src(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_read_feedback():
    """Import tools/read_feedback as a module without modifying sys.path."""
    spec = importlib.util.spec_from_file_location("read_feedback", _TOOL_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


print("=" * 64)
print("D221–D228  Build 17: Feedback Signal Reader v1")
print("=" * 64)

tool_src = read_src(_TOOL_PATH)

# ── D221  summarize_feedback is importable and returns dict ──────
print("\n[D221] summarize_feedback importable and returns dict")

try:
    mod = load_read_feedback()
    check("D221a", "tools/read_feedback.py imports without error", True)
except Exception as exc:
    check("D221a", "tools/read_feedback.py imports without error", False, str(exc))
    mod = None

if mod is not None:
    has_fn = hasattr(mod, "summarize_feedback") and callable(mod.summarize_feedback)
    check("D221b", "summarize_feedback is a callable", has_fn)
else:
    check("D221b", "summarize_feedback is a callable", False, "module not loaded")

# ── D222  missing / empty file returns total 0 ───────────────────
print("\n[D222] missing file returns total=0; empty file returns total=0")

if mod:
    # Non-existent path
    missing = summarize_missing = mod.summarize_feedback("/tmp/__nonexistent_conductor_log__.jsonl")
    check("D222a", "missing file: total == 0", missing["total"] == 0,
          f"got {missing['total']}")
    check("D222b", "missing file: malformed_count == 0", missing["malformed_count"] == 0)
    check("D222c", "missing file: period_start is None", missing["period_start"] is None)
    check("D222d", "missing file: all type_counts == 0",
          all(v == 0 for v in missing["type_counts"].values()),
          str(missing["type_counts"]))

    # Empty file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
        empty_path = tf.name
    try:
        empty = mod.summarize_feedback(empty_path)
        check("D222e", "empty file: total == 0", empty["total"] == 0, f"got {empty['total']}")
    finally:
        os.unlink(empty_path)
else:
    for sub in ("D222a", "D222b", "D222c", "D222d", "D222e"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D223  malformed lines skipped, valid lines counted ───────────
print("\n[D223] malformed lines skipped; valid lines counted correctly")

if mod:
    records = [
        {"feedback_id": "aaa", "response_id": "bbb", "feedback_type": "HELPFUL",
         "timestamp": "2026-05-01T10:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "ccc", "response_id": "ddd", "feedback_type": "WRONG",
         "timestamp": "2026-05-02T10:00:00Z", "promotion_eligible": False, "message": ""},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
        tf.write(json.dumps(records[0]) + "\n")
        tf.write("NOT JSON AT ALL {\n")          # malformed
        tf.write(json.dumps(records[1]) + "\n")
        mixed_path = tf.name
    try:
        result = mod.summarize_feedback(mixed_path)
        check("D223a", "total == 2 (malformed skipped)", result["total"] == 2,
              f"got {result['total']}")
        check("D223b", "malformed_count == 1", result["malformed_count"] == 1,
              f"got {result['malformed_count']}")
        check("D223c", "HELPFUL count == 1", result["type_counts"]["HELPFUL"] == 1,
              str(result["type_counts"]))
        check("D223d", "WRONG count == 1", result["type_counts"]["WRONG"] == 1,
              str(result["type_counts"]))
    finally:
        os.unlink(mixed_path)
else:
    for sub in ("D223a", "D223b", "D223c", "D223d"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D224  type counts correct across known types ─────────────────
print("\n[D224] type counts correct — all known types + OTHER")

if mod:
    rows = [
        {"feedback_id": "01", "response_id": "r1", "feedback_type": "HELPFUL",
         "timestamp": "2026-05-01T00:00:00Z", "promotion_eligible": False, "message": "nice"},
        {"feedback_id": "02", "response_id": "r2", "feedback_type": "HELPFUL",
         "timestamp": "2026-05-02T00:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "03", "response_id": "r3", "feedback_type": "NOT_HELPFUL",
         "timestamp": "2026-05-03T00:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "04", "response_id": "r4", "feedback_type": "TOO_VAGUE",
         "timestamp": "2026-05-04T00:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "05", "response_id": "r5", "feedback_type": "WRONG",
         "timestamp": "2026-05-05T00:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "06", "response_id": "r6", "feedback_type": "OUTDATED",
         "timestamp": "2026-05-06T00:00:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "07", "response_id": "r7", "feedback_type": "UNKNOWN_FUTURE_TYPE",
         "timestamp": "2026-05-07T00:00:00Z", "promotion_eligible": False, "message": ""},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
        for row in rows:
            tf.write(json.dumps(row) + "\n")
        typed_path = tf.name
    try:
        result = mod.summarize_feedback(typed_path)
        check("D224a", "HELPFUL == 2",      result["type_counts"]["HELPFUL"] == 2,      str(result["type_counts"]))
        check("D224b", "NOT_HELPFUL == 1",  result["type_counts"]["NOT_HELPFUL"] == 1,  str(result["type_counts"]))
        check("D224c", "TOO_VAGUE == 1",    result["type_counts"]["TOO_VAGUE"] == 1,    str(result["type_counts"]))
        check("D224d", "WRONG == 1",        result["type_counts"]["WRONG"] == 1,        str(result["type_counts"]))
        check("D224e", "OUTDATED == 1",     result["type_counts"]["OUTDATED"] == 1,     str(result["type_counts"]))
        check("D224f", "OTHER == 1 (unknown type → OTHER)", result["type_counts"]["OTHER"] == 1,
              str(result["type_counts"]))
        check("D224g", "total == 7", result["total"] == 7, f"got {result['total']}")
    finally:
        os.unlink(typed_path)
else:
    for sub in ("D224a", "D224b", "D224c", "D224d", "D224e", "D224f", "D224g"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D225  all known types + OTHER always present in type_counts ──
print("\n[D225] all known types + OTHER always present in result dict")

if mod:
    # Even on an empty file all keys must exist
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
        empty_path2 = tf.name
    try:
        result = mod.summarize_feedback(empty_path2)
        required_keys = {"HELPFUL", "NOT_HELPFUL", "TOO_VAGUE", "WRONG", "OUTDATED", "OTHER"}
        present_keys = set(result["type_counts"].keys())
        check("D225a", "all 6 type keys present even on empty file",
              required_keys.issubset(present_keys),
              f"missing: {required_keys - present_keys}")
    finally:
        os.unlink(empty_path2)

    # And on a missing file
    missing2 = mod.summarize_feedback("/tmp/__conductor_missing2__.jsonl")
    present2 = set(missing2["type_counts"].keys())
    check("D225b", "all 6 type keys present on missing file",
          required_keys.issubset(present2),
          f"missing: {required_keys - present2}")
else:
    check("D225a", "all 6 type keys present (empty)", False, "module not loaded")
    check("D225b", "all 6 type keys present (missing)", False, "module not loaded")

# ── D226  period_start / period_end correctness + messages ───────
print("\n[D226] period_start, period_end, messages_with_content, sample_messages")

if mod:
    rows = [
        {"feedback_id": "p1", "response_id": "r1", "feedback_type": "HELPFUL",
         "timestamp": "2026-01-15T09:00:00Z", "promotion_eligible": False, "message": "first msg"},
        {"feedback_id": "p2", "response_id": "r2", "feedback_type": "WRONG",
         "timestamp": "2026-03-22T14:30:00Z", "promotion_eligible": False, "message": ""},
        {"feedback_id": "p3", "response_id": "r3", "feedback_type": "OUTDATED",
         "timestamp": "2026-06-01T00:00:00Z", "promotion_eligible": False, "message": "last msg"},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf:
        for row in rows:
            tf.write(json.dumps(row) + "\n")
        period_path = tf.name
    try:
        result = mod.summarize_feedback(period_path)
        check("D226a", "period_start == earliest timestamp",
              result["period_start"] == "2026-01-15T09:00:00Z",
              f"got {result['period_start']}")
        check("D226b", "period_end == latest timestamp",
              result["period_end"] == "2026-06-01T00:00:00Z",
              f"got {result['period_end']}")
        check("D226c", "messages_with_content == 2",
              result["messages_with_content"] == 2,
              f"got {result['messages_with_content']}")
        check("D226d", "sample_messages has both non-empty messages",
              "first msg" in result["sample_messages"] and "last msg" in result["sample_messages"],
              str(result["sample_messages"]))
        # sample_messages capped at 5
        rows_many = [
            {"feedback_id": f"m{i}", "response_id": f"r{i}", "feedback_type": "HELPFUL",
             "timestamp": "2026-05-01T00:00:00Z", "promotion_eligible": False,
             "message": f"msg {i}"}
            for i in range(8)
        ]
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as tf2:
            for row in rows_many:
                tf2.write(json.dumps(row) + "\n")
            many_path = tf2.name
        try:
            result2 = mod.summarize_feedback(many_path)
            check("D226e", "sample_messages capped at 5",
                  len(result2["sample_messages"]) <= 5,
                  f"got {len(result2['sample_messages'])}")
        finally:
            os.unlink(many_path)
    finally:
        os.unlink(period_path)
else:
    for sub in ("D226a", "D226b", "D226c", "D226d", "D226e"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D227  read-only: live log mtime unchanged ────────────────────
print("\n[D227] read-only — live log mtime unchanged after summarize_feedback")

if mod and os.path.exists(_LIVE_LOG):
    mtime_before = os.path.getmtime(_LIVE_LOG)
    _ = mod.summarize_feedback(_LIVE_LOG)
    mtime_after = os.path.getmtime(_LIVE_LOG)
    check("D227a", "live log mtime unchanged after summarize_feedback",
          mtime_before == mtime_after,
          f"before={mtime_before} after={mtime_after}")
elif not os.path.exists(_LIVE_LOG):
    check("D227a", "live log mtime unchanged (skipped — log not present)",
          True, "live log absent; read-only check skipped")
else:
    check("D227a", "live log mtime unchanged", False, "module not loaded")

# ── D228  source has no forbidden imports or write operations ─────
print("\n[D228] source has no ChromaDB / rag / promotion / write / frequency_score")

forbidden_patterns = {
    "chromadb import":    r'\bimport\s+chromadb\b|from\s+chromadb\b',
    "rag import":         r'\bfrom\s+rag\b|\bimport\s+rag\b',
    # Guard actual promotion code references, not the word in comments/docstrings.
    # Matches: memory_promotion module, promote_memory(), run_promotion()
    "promotion code":     r'\bmemory_promotion\b|\bpromote_memory\b|\brun_promotion\b|\bdo_promotion\b',
    "frequency_score":    r'\bfrequency_score\b',
    "open for write":     r'\bopen\s*\(.*["\'][wa]["\']',
}
for label, pattern in forbidden_patterns.items():
    found = bool(re.search(pattern, tool_src, re.IGNORECASE))
    check(f"D228-{label.replace(' ', '_')}", f"no '{label}' in read_feedback.py",
          not found, "pattern found in source" if found else "")

# No harness_server.py modifications
server_src = read_src(os.path.join(_ROOT, "tools", "harness_server.py"))
check("D228-server_untouched",
      "harness_server.py has no Build 17 read_feedback references",
      "read_feedback" not in server_src and "summarize_feedback" not in server_src)

# Guard: if __name__ == '__main__' block must be present (CLI entry)
has_main = '__name__' in tool_src and '__main__' in tool_src
check("D228-has_main_guard", "if __name__ == '__main__' guard present", has_main)

# Default path points to memory/knowledge_feedback_log.jsonl
has_default_path = "knowledge_feedback_log.jsonl" in tool_src
check("D228-default_path", "default log path references knowledge_feedback_log.jsonl",
      has_default_path)

# ── Summary ───────────────────────────────────────────────────────
print("\n" + "=" * 64)
passed = sum(1 for _, s, _, _ in results if s == PASS)
failed = sum(1 for _, s, _, _ in results if s == FAIL)
print(f"Result: {passed}/{passed + failed} PASS")

if failed:
    print("\nFailed checks:")
    for id_, s, desc, detail in results:
        if s == FAIL:
            print(f"  ✗ {id_}: {desc}" + (f"\n    detail: {detail}" if detail else ""))
    sys.exit(1)
else:
    print("All checks PASS.")
