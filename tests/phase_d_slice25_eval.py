#!/usr/bin/env python3
"""
phase_d_slice25_eval.py — Build 18: Memory Promotion v1 / Promotion Candidate Generator
Tests D229–D248.

All checks are static source analysis + unit-level functional tests.
No browser runtime, no ChromaDB runtime writes, no network calls required.
All live logs are opened read-only or not at all.
"""

import importlib.util
import json
import os
import re
import sys
import tempfile

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MODULE_PATH      = os.path.join(_ROOT, "rag", "memory_promotion.py")
_LIVE_FB_LOG      = os.path.join(_ROOT, "memory", "feedback_log.jsonl")
_LIVE_KFB_LOG     = os.path.join(_ROOT, "memory", "knowledge_feedback_log.jsonl")
_LIVE_PROOF_LOG   = os.path.join(_ROOT, "memory", "action_proof_log.jsonl")
_NEVER_DO_PATH    = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")

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


def load_module():
    spec = importlib.util.spec_from_file_location("memory_promotion", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_action_feedback_record(**kwargs):
    base = {
        "feedback_id":                      "test_fb_001",
        "proof_id":                         "test_proof_001",
        "action_id":                        "test_act_001",
        "request_id":                       "",
        "session_id":                       "sess_test",
        "project_id":                       "TestProject",
        "feedback_type":                    "KEEP",
        "timestamp":                        "2026-05-01T10:00:00Z",
        "verification_status_at_feedback":  "VERIFIED",
        "promotion_eligible":               False,
        "message":                          "",
    }
    base.update(kwargs)
    return base


def make_knowledge_feedback_record(**kwargs):
    base = {
        "feedback_id":       "test_kfb_001",
        "response_id":       "abc123def456",
        "feedback_type":     "HELPFUL",
        "timestamp":         "2026-05-01T10:00:00Z",
        "promotion_eligible": False,
        "message":           "",
    }
    base.update(kwargs)
    return base


def make_proof_record(**kwargs):
    base = {
        "proof_id":           "test_proof_001",
        "action_id":          "test_act_001",
        "action_type":        "SET_TRACK_VOLUME",
        "target":             "track:Kick",
        "session_id":         "sess_test",
        "project_id":         "TestProject",
        "timestamp":          "2026-05-01T09:59:00Z",
        "before_state":       {"volume": 0.7},
        "after_state":        {"volume": 0.85},
        "verification_status": "VERIFIED",
        "undo_eligible":      True,
        "user_facing_summary": "Volume set to 0.85 — confirmed.",
    }
    base.update(kwargs)
    return base


def write_jsonl(path, records):
    with open(path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


print("=" * 64)
print("D229–D248  Build 18: Memory Promotion v1 / Candidate Generator")
print("=" * 64)

module_src = read_src(_MODULE_PATH)

# ── D229  module importable + run_promotion callable ─────────────────────────
print("\n[D229] module importable and run_promotion is callable")

try:
    mod = load_module()
    check("D229a", "rag/memory_promotion.py imports without error", True)
except Exception as exc:
    check("D229a", "rag/memory_promotion.py imports without error", False, str(exc))
    mod = None

if mod is not None:
    has_fn = hasattr(mod, "run_promotion") and callable(mod.run_promotion)
    check("D229b", "run_promotion is a callable", has_fn)
else:
    check("D229b", "run_promotion is a callable", False, "module not loaded")

# ── D230  missing logs → safe zero result ────────────────────────────────────
print("\n[D230] missing logs return safe zero result")

if mod:
    result = mod.run_promotion(
        feedback_log_path   = "/tmp/__nonexistent_feedback__.jsonl",
        proof_log_path      = "/tmp/__nonexistent_proof__.jsonl",
        knowledge_log_path  = "/tmp/__nonexistent_kfb__.jsonl",
        ledger_path         = "/tmp/__nonexistent_ledger__.jsonl",
        dry_run             = True,
    )
    check("D230a", "missing logs: total_candidates == 0",
          result["total_candidates"] == 0, f"got {result['total_candidates']}")
    check("D230b", "missing logs: total_processed == 0",
          result["total_processed"] == 0, f"got {result['total_processed']}")
    check("D230c", "missing logs: candidates list is empty",
          result["candidates"] == [], str(result["candidates"][:2]))
else:
    for sub in ("D230a", "D230b", "D230c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D231  empty logs → safe zero result ──────────────────────────────────────
print("\n[D231] empty logs return safe zero result")

if mod:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        empty_fb = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        empty_kfb = f.name
    try:
        result = mod.run_promotion(
            feedback_log_path   = empty_fb,
            knowledge_log_path  = empty_kfb,
            proof_log_path      = "/tmp/__no_proof__.jsonl",
            ledger_path         = "/tmp/__no_ledger__.jsonl",
            dry_run             = True,
        )
        check("D231a", "empty logs: total_candidates == 0",
              result["total_candidates"] == 0, f"got {result['total_candidates']}")
        check("D231b", "empty logs: total_processed == 0",
              result["total_processed"] == 0, f"got {result['total_processed']}")
    finally:
        os.unlink(empty_fb)
        os.unlink(empty_kfb)
else:
    check("D231a", "empty logs: total_candidates == 0", False, "module not loaded")
    check("D231b", "empty logs: total_processed == 0", False, "module not loaded")

# ── D232  positive signals create candidates ──────────────────────────────────
print("\n[D232] KEEP and HELPFUL create promotion candidates")

if mod:
    # KEEP action feedback
    fb_rec = make_action_feedback_record(
        feedback_id="d232_fb_keep", feedback_type="KEEP",
        session_id="sess_232", project_id="Proj232",
    )
    pf_rec = make_proof_record(proof_id="d232_proof_001")
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(fb_rec) + "\n")
        fb_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(pf_rec) + "\n")
        prf_path = f.name
    try:
        result = mod.run_promotion(
            feedback_log_path   = fb_path,
            proof_log_path      = prf_path,
            knowledge_log_path  = "/tmp/__no_kfb__.jsonl",
            ledger_path         = "/tmp/__no_ledger232__.jsonl",
            dry_run             = True,
        )
        check("D232a", "KEEP → at least 1 candidate generated",
              result["total_candidates"] >= 1, f"got {result['total_candidates']}")
        if result["candidates"]:
            c = result["candidates"][0]
            check("D232b", "KEEP candidate score >= 0.50",
                  c["score"] >= 0.50, f"got {c['score']}")
            check("D232c", "KEEP candidate source == 'action_feedback'",
                  c["source"] == "action_feedback", f"got {c['source']}")
    finally:
        os.unlink(fb_path)
        os.unlink(prf_path)

    # HELPFUL knowledge feedback
    kfb_rec = make_knowledge_feedback_record(
        feedback_id="d232_kfb_helpful", feedback_type="HELPFUL",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(kfb_rec) + "\n")
        kfb_path = f.name
    try:
        result2 = mod.run_promotion(
            feedback_log_path   = "/tmp/__no_fb232__.jsonl",
            proof_log_path      = "/tmp/__no_proof232__.jsonl",
            knowledge_log_path  = kfb_path,
            ledger_path         = "/tmp/__no_ledger232b__.jsonl",
            dry_run             = True,
        )
        check("D232d", "HELPFUL → at least 1 candidate generated",
              result2["total_candidates"] >= 1, f"got {result2['total_candidates']}")
        if result2["candidates"]:
            ck = result2["candidates"][0]
            check("D232e", "HELPFUL candidate source == 'knowledge_feedback'",
                  ck["source"] == "knowledge_feedback", f"got {ck['source']}")
    finally:
        os.unlink(kfb_path)
else:
    for sub in ("D232a", "D232b", "D232c", "D232d", "D232e"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D233  negative signals do not promote ────────────────────────────────────
print("\n[D233] negative feedback types create no candidates")

NEGATIVE_PAIRS = [
    ("action",    "UNDO"),
    ("action",    "WRONG_DIRECTION"),
    ("knowledge", "NOT_HELPFUL"),
    ("knowledge", "WRONG"),
    ("knowledge", "OUTDATED"),
]

if mod:
    for i, (source, ftype) in enumerate(NEGATIVE_PAIRS):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            if source == "action":
                rec = make_action_feedback_record(
                    feedback_id=f"d233_fb_{i}", feedback_type=ftype,
                )
                f.write(json.dumps(rec) + "\n")
                fb_p = f.name
                kfb_p = "/tmp/__no_kfb233__.jsonl"
            else:
                rec = make_knowledge_feedback_record(
                    feedback_id=f"d233_kfb_{i}", feedback_type=ftype,
                )
                f.write(json.dumps(rec) + "\n")
                kfb_p = f.name
                fb_p = "/tmp/__no_fb233__.jsonl"
        try:
            result = mod.run_promotion(
                feedback_log_path   = fb_p,
                proof_log_path      = "/tmp/__no_proof233__.jsonl",
                knowledge_log_path  = kfb_p,
                ledger_path         = "/tmp/__no_ledger233__.jsonl",
                dry_run             = True,
            )
            check(f"D233-{ftype}", f"{ftype} → total_candidates == 0",
                  result["total_candidates"] == 0,
                  f"got {result['total_candidates']}")
        finally:
            os.unlink(f.name)
else:
    for _, ftype in NEGATIVE_PAIRS:
        check(f"D233-{ftype}", f"{ftype} → no candidate", False, "module not loaded")

# ── D234  TOO_MUCH / NOT_ENOUGH / TOO_VAGUE below threshold ──────────────────
print("\n[D234] below-threshold types (TOO_MUCH, NOT_ENOUGH, TOO_VAGUE) skipped")

BELOW_THRESHOLD_TYPES = [
    ("action",    "TOO_MUCH"),
    ("action",    "NOT_ENOUGH"),
    ("knowledge", "TOO_VAGUE"),
]

if mod:
    for i, (source, ftype) in enumerate(BELOW_THRESHOLD_TYPES):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            if source == "action":
                rec = make_action_feedback_record(
                    feedback_id=f"d234_fb_{i}", feedback_type=ftype, message="",
                )
                f.write(json.dumps(rec) + "\n")
                fb_p = f.name
                kfb_p = "/tmp/__no_kfb234__.jsonl"
            else:
                rec = make_knowledge_feedback_record(
                    feedback_id=f"d234_kfb_{i}", feedback_type=ftype, message="",
                )
                f.write(json.dumps(rec) + "\n")
                kfb_p = f.name
                fb_p = "/tmp/__no_fb234__.jsonl"
        try:
            result = mod.run_promotion(
                feedback_log_path   = fb_p,
                proof_log_path      = "/tmp/__no_proof234__.jsonl",
                knowledge_log_path  = kfb_p,
                ledger_path         = "/tmp/__no_ledger234__.jsonl",
                dry_run             = True,
            )
            check(f"D234-{ftype}", f"{ftype} without message → no candidate",
                  result["total_candidates"] == 0,
                  f"got {result['total_candidates']} (score below threshold 0.50)")
        finally:
            os.unlink(f.name)
else:
    for _, ftype in BELOW_THRESHOLD_TYPES:
        check(f"D234-{ftype}", f"{ftype} below threshold", False, "module not loaded")

# ── D235  message bonus ───────────────────────────────────────────────────────
print("\n[D235] message bonus increases score")

if mod:
    def _score_for(ftype, message, source="action"):
        # Write temp file and close the handle before calling run_promotion.
        # (File must be closed/flushed before it can be read on all platforms.)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            if source == "action":
                rec = make_action_feedback_record(
                    feedback_id=f"d235_{ftype}_{len(message)}", feedback_type=ftype,
                    message=message,
                )
            else:
                rec = make_knowledge_feedback_record(
                    feedback_id=f"d235_{ftype}_{len(message)}", feedback_type=ftype,
                    message=message,
                )
            f.write(json.dumps(rec) + "\n")
            p = f.name
        # File handle is now closed — safe to read
        try:
            if source == "action":
                r = mod.run_promotion(
                    feedback_log_path=p,
                    knowledge_log_path="/tmp/__no__.jsonl",
                    proof_log_path="/tmp/__no__.jsonl",
                    ledger_path="/tmp/__no__.jsonl",
                    dry_run=True,
                )
            else:
                r = mod.run_promotion(
                    feedback_log_path="/tmp/__no__.jsonl",
                    knowledge_log_path=p,
                    proof_log_path="/tmp/__no__.jsonl",
                    ledger_path="/tmp/__no__.jsonl",
                    dry_run=True,
                )
        finally:
            os.unlink(p)
        return r["candidates"][0]["score"] if r["candidates"] else None

    score_keep_no_msg  = _score_for("KEEP", "")
    score_keep_msg     = _score_for("KEEP", "This was perfect for the track")
    score_help_no_msg  = _score_for("HELPFUL", "", source="knowledge")
    score_help_msg     = _score_for("HELPFUL", "Great answer helped my mix", source="knowledge")

    check("D235a", "KEEP with message has higher score than KEEP without",
          score_keep_msg is not None and score_keep_no_msg is not None
          and score_keep_msg > score_keep_no_msg,
          f"no_msg={score_keep_no_msg} msg={score_keep_msg}")
    check("D235b", "HELPFUL with message has higher score than HELPFUL without",
          score_help_msg is not None and score_help_no_msg is not None
          and score_help_msg > score_help_no_msg,
          f"no_msg={score_help_no_msg} msg={score_help_msg}")
    check("D235c", "KEEP no message score == 0.65",
          score_keep_no_msg == 0.65, f"got {score_keep_no_msg}")
    check("D235d", "KEEP with message score == 0.75",
          score_keep_msg == 0.75, f"got {score_keep_msg}")
    check("D235e", "HELPFUL no message score == 0.55",
          score_help_no_msg == 0.55, f"got {score_help_no_msg}")
else:
    for sub in ("D235a", "D235b", "D235c", "D235d", "D235e"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D236  scope — action feedback ────────────────────────────────────────────
print("\n[D236] scope: session_project when project_id set; session_only when not")

if mod:
    # With project_id
    rec_with = make_action_feedback_record(
        feedback_id="d236_with", feedback_type="KEEP",
        project_id="MyProject", session_id="sess_236",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec_with) + "\n")
        p_with = f.name
    try:
        r = mod.run_promotion(
            feedback_log_path=p_with, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path="/tmp/__no__.jsonl",
            dry_run=True,
        )
        c = r["candidates"][0] if r["candidates"] else {}
        check("D236a", "KEEP with project_id → scope == 'session_project'",
              c.get("scope") == "session_project", f"got {c.get('scope')}")
        check("D236b", "KEEP with project_id → suggested_level == 2",
              c.get("suggested_level") == 2, f"got {c.get('suggested_level')}")
    finally:
        os.unlink(p_with)

    # Without project_id
    rec_without = make_action_feedback_record(
        feedback_id="d236_without", feedback_type="KEEP",
        project_id="", session_id="sess_236b",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec_without) + "\n")
        p_without = f.name
    try:
        r2 = mod.run_promotion(
            feedback_log_path=p_without, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path="/tmp/__no__.jsonl",
            dry_run=True,
        )
        c2 = r2["candidates"][0] if r2["candidates"] else {}
        check("D236c", "KEEP without project_id → scope == 'session_only'",
              c2.get("scope") == "session_only", f"got {c2.get('scope')}")
        check("D236d", "KEEP without project_id → suggested_level == 1",
              c2.get("suggested_level") == 1, f"got {c2.get('suggested_level')}")
    finally:
        os.unlink(p_without)
else:
    for sub in ("D236a", "D236b", "D236c", "D236d"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D237  scope — knowledge feedback always session_only ─────────────────────
print("\n[D237] knowledge feedback scope always session_only")

if mod:
    kfb = make_knowledge_feedback_record(
        feedback_id="d237_kfb", feedback_type="HELPFUL",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(kfb) + "\n")
        p = f.name
    try:
        r = mod.run_promotion(
            feedback_log_path="/tmp/__no__.jsonl", knowledge_log_path=p,
            proof_log_path="/tmp/__no__.jsonl", ledger_path="/tmp/__no__.jsonl",
            dry_run=True,
        )
        ck = r["candidates"][0] if r["candidates"] else {}
        check("D237a", "HELPFUL → scope == 'session_only'",
              ck.get("scope") == "session_only", f"got {ck.get('scope')}")
        check("D237b", "HELPFUL → suggested_level == 1",
              ck.get("suggested_level") == 1, f"got {ck.get('suggested_level')}")
        check("D237c", "HELPFUL → project_id == ''",
              ck.get("project_id") == "", f"got {ck.get('project_id')!r}")
    finally:
        os.unlink(p)
else:
    for sub in ("D237a", "D237b", "D237c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D238  no global_taste scope from single KEEP ─────────────────────────────
print("\n[D238] single KEEP does not generate global_taste scope")

if mod:
    rec = make_action_feedback_record(
        feedback_id="d238_keep", feedback_type="KEEP",
        project_id="SomeProject", message="Great sound",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec) + "\n")
        p = f.name
    try:
        r = mod.run_promotion(
            feedback_log_path=p, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path="/tmp/__no__.jsonl",
            dry_run=True,
        )
        global_taste_count = sum(
            1 for c in r["candidates"] if c.get("scope") == "global_taste"
        )
        check("D238a", "single KEEP: no global_taste candidates",
              global_taste_count == 0,
              f"found {global_taste_count} global_taste candidates")
        check("D238b", "single KEEP: suggested_level <= 2",
              all(c["suggested_level"] <= 2 for c in r["candidates"]),
              str([c["suggested_level"] for c in r["candidates"]]))
    finally:
        os.unlink(p)
else:
    check("D238a", "no global_taste from single KEEP", False, "module not loaded")
    check("D238b", "suggested_level <= 2", False, "module not loaded")

# ── D239  idempotency — no duplicate candidates across repeated runs ──────────
print("\n[D239] idempotency: second run with same log produces no new candidates")

if mod:
    rec = make_action_feedback_record(
        feedback_id="d239_keep_idem", feedback_type="KEEP",
        project_id="IdemProject",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec) + "\n")
        fb_p = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        ledger_p = f.name
    try:
        r1 = mod.run_promotion(
            feedback_log_path=fb_p, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path=ledger_p,
            dry_run=False,   # write ledger
        )
        r2 = mod.run_promotion(
            feedback_log_path=fb_p, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path=ledger_p,
            dry_run=False,   # same ledger — should detect duplicate
        )
        check("D239a", "first run: at least 1 candidate generated",
              r1["total_candidates"] >= 1, f"got {r1['total_candidates']}")
        check("D239b", "second run: total_candidates == 0",
              r2["total_candidates"] == 0, f"got {r2['total_candidates']}")
        check("D239c", "second run: duplicates_skipped == first run candidates",
              r2["duplicates_skipped"] == r1["total_candidates"],
              f"r1={r1['total_candidates']} r2_dupes={r2['duplicates_skipped']}")
    finally:
        os.unlink(fb_p)
        try:
            os.unlink(ledger_p)
        except OSError:
            pass
else:
    for sub in ("D239a", "D239b", "D239c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D240  dry_run does not write ledger ───────────────────────────────────────
print("\n[D240] dry_run=True does not create or modify ledger")

if mod:
    rec = make_action_feedback_record(
        feedback_id="d240_dry", feedback_type="KEEP",
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(rec) + "\n")
        fb_p = f.name
    ledger_dry = "/tmp/__d240_ledger_never_created__.jsonl"
    # Remove if somehow exists
    if os.path.exists(ledger_dry):
        os.unlink(ledger_dry)
    try:
        r = mod.run_promotion(
            feedback_log_path=fb_p, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path=ledger_dry,
            dry_run=True,
        )
        check("D240a", "dry_run=True: ledger file NOT created",
              not os.path.exists(ledger_dry),
              "ledger file was created despite dry_run=True")
        check("D240b", "dry_run=True: candidates still returned in result",
              r["total_candidates"] >= 1, f"got {r['total_candidates']}")
    finally:
        os.unlink(fb_p)
        if os.path.exists(ledger_dry):
            os.unlink(ledger_dry)
else:
    check("D240a", "dry_run doesn't write ledger", False, "module not loaded")
    check("D240b", "dry_run still returns candidates", False, "module not loaded")

# ── D241  Level 4 / Never-Do guard ───────────────────────────────────────────
print("\n[D241] no candidate ever has suggested_level == 4")

if mod:
    recs = [
        make_action_feedback_record(feedback_id=f"d241_{i}", feedback_type="KEEP",
                                     message="top signal")
        for i in range(5)
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
        p = f.name
    try:
        result = mod.run_promotion(
            feedback_log_path=p, knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl", ledger_path="/tmp/__no__.jsonl",
            dry_run=True,
        )
        bad_levels = [c["suggested_level"] for c in result["candidates"] if c["suggested_level"] >= 3]
        check("D241a", "no candidate has suggested_level >= 3",
              len(bad_levels) == 0, f"found levels {bad_levels}")
        check("D241b", "no candidate has suggested_level == 4",
              all(c["suggested_level"] != 4 for c in result["candidates"]),
              str([c["suggested_level"] for c in result["candidates"]]))
    finally:
        os.unlink(p)
else:
    check("D241a", "no level 3+ candidates", False, "module not loaded")
    check("D241b", "no level 4 candidates", False, "module not loaded")

# ── D242  source logs mtime unchanged ─────────────────────────────────────────
print("\n[D242] live source logs mtime unchanged after run_promotion")

if mod:
    live_logs = [
        ("feedback_log",           _LIVE_FB_LOG),
        ("knowledge_feedback_log", _LIVE_KFB_LOG),
        ("action_proof_log",       _LIVE_PROOF_LOG),
    ]
    for name, path in live_logs:
        if os.path.exists(path):
            before = os.path.getmtime(path)
            mod.run_promotion(
                feedback_log_path=path if name == "feedback_log" else "/tmp/__no__.jsonl",
                knowledge_log_path=path if name == "knowledge_feedback_log" else "/tmp/__no__.jsonl",
                proof_log_path=path if name == "action_proof_log" else "/tmp/__no__.jsonl",
                ledger_path="/tmp/__d242_ledger__.jsonl",
                dry_run=True,
            )
            # Clean up temp ledger
            if os.path.exists("/tmp/__d242_ledger__.jsonl"):
                os.unlink("/tmp/__d242_ledger__.jsonl")
            after = os.path.getmtime(path)
            check(f"D242-{name}", f"{name} mtime unchanged",
                  before == after, f"before={before} after={after}")
        else:
            check(f"D242-{name}", f"{name} mtime unchanged (skipped — not present)",
                  True, "live log absent; read-only check skipped")
else:
    for name, _ in [("feedback_log", ""), ("knowledge_feedback_log", ""), ("action_proof_log", "")]:
        check(f"D242-{name}", "mtime unchanged", False, "module not loaded")

# ── D243  never_do_rules.md not written ───────────────────────────────────────
print("\n[D243] never_do_rules.md mtime unchanged after run_promotion")

if mod:
    if os.path.exists(_NEVER_DO_PATH):
        before = os.path.getmtime(_NEVER_DO_PATH)
        mod.run_promotion(
            feedback_log_path="/tmp/__no__.jsonl",
            knowledge_log_path="/tmp/__no__.jsonl",
            proof_log_path="/tmp/__no__.jsonl",
            ledger_path="/tmp/__d243_ledger__.jsonl",
            dry_run=True,
        )
        if os.path.exists("/tmp/__d243_ledger__.jsonl"):
            os.unlink("/tmp/__d243_ledger__.jsonl")
        after = os.path.getmtime(_NEVER_DO_PATH)
        check("D243a", "never_do_rules.md mtime unchanged",
              before == after, f"before={before} after={after}")
    else:
        check("D243a", "never_do_rules.md mtime unchanged (skipped — file absent)",
              True, "never_do_rules.md not present; guard check skipped")
else:
    check("D243a", "never_do_rules.md not written", False, "module not loaded")

# ── D244  static source analysis ─────────────────────────────────────────────
print("\n[D244] source has no forbidden imports or references")

forbidden_patterns = {
    "harness_server import":    r'\bimport\s+harness_server\b|from\s+harness_server\b',
    "conductor_bridge import":  r'\bimport\s+conductor_bridge\b|from\s+conductor_bridge\b',
    "chromadb import":          r'\bimport\s+chromadb\b|from\s+chromadb\b',
    "app/ reference":           r'["\']app/',
    "voice mode":               r'\bvoice_mode\b|\bvoice_reaction\b',
    "PluginBridge":             r'\bPluginBridge\b|\bpluginbridge\b',
    "Auto Execute":             r'\bauto_execute\b|\bAutoExecute\b',
    "open for write":           r'\bopen\s*\(.*["\'][wa]["\']',
    "Level 4 write":            r'\bmemory_level\s*[=:]\s*4\b',
}

for label, pattern in forbidden_patterns.items():
    # Exclude the open-for-write check from the ledger write helper itself
    # (which legitimately uses open(path, "a") for the ledger only)
    if label == "open for write":
        # Allow only _append_to_ledger; fail if any other write open exists
        # Strip the helper function body and re-check
        src_stripped = re.sub(
            r'def _append_to_ledger.*?(?=\ndef |\nif __name__)',
            '', module_src, flags=re.DOTALL
        )
        found = bool(re.search(pattern, src_stripped, re.IGNORECASE))
    else:
        found = bool(re.search(pattern, module_src, re.IGNORECASE))
    check(f"D244-{label.replace(' ', '_')}",
          f"no '{label}' in memory_promotion.py",
          not found, "pattern found in source" if found else "")

# CLI guard present
has_main = "__name__" in module_src and "__main__" in module_src
check("D244-has_main_guard", "if __name__ == '__main__' guard present", has_main)

# Default paths reference correct log files
check("D244-default_feedback_path",
      "DEFAULT_FEEDBACK_LOG references feedback_log.jsonl",
      "feedback_log.jsonl" in module_src)
check("D244-default_knowledge_path",
      "DEFAULT_KNOWLEDGE_LOG references knowledge_feedback_log.jsonl",
      "knowledge_feedback_log.jsonl" in module_src)
check("D244-default_ledger_path",
      "DEFAULT_LEDGER_PATH references promotion_candidates.jsonl",
      "promotion_candidates.jsonl" in module_src)

# Never-Do path guard is documented
check("D244-never_do_guard",
      "_NEVER_DO_PATH or never_do_rules.md referenced in source",
      "never_do_rules.md" in module_src)

# ── Summary ───────────────────────────────────────────────────────────────────
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
