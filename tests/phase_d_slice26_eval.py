#!/usr/bin/env python3
"""
phase_d_slice26_eval.py — Build 19: Session Reflection / Feedback Summary v1
Tests D249–D265.

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
_MODULE_PATH     = os.path.join(_ROOT, "rag", "session_reflection.py")
_LIVE_CANDIDATES = os.path.join(_ROOT, "memory", "promotion_candidates.jsonl")
_NEVER_DO_PATH   = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")

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
    spec = importlib.util.spec_from_file_location("session_reflection", _MODULE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Test data helpers ─────────────────────────────────────────────────────────

def make_candidate(
    candidate_id="cand_001",
    source="action_feedback",
    feedback_type="KEEP",
    action_type="SET_TRACK_VOLUME",
    target="track:Kick",
    session_id="sess_test",
    project_id="TestProject",
    scope="session_project",
    suggested_level=2,
    score=0.65,
    evidence="action:SET_TRACK_VOLUME | target:track:Kick",
    message="",
    **kwargs,
):
    rec = {
        "candidate_id":       candidate_id,
        "source":             source,
        "feedback_type":      feedback_type,
        "action_type":        action_type,
        "target":             target,
        "session_id":         session_id,
        "project_id":         project_id,
        "scope":              scope,
        "suggested_level":    suggested_level,
        "score":              score,
        "evidence":           evidence,
        "message":            message,
        "generated_at":       "2026-05-01T10:00:00Z",
        "timestamp_original": "2026-05-01T09:59:00Z",
    }
    rec.update(kwargs)
    return rec


def make_feedback(
    feedback_id="fb_001",
    feedback_type="UNDO",
    session_id="sess_test",
    project_id="TestProject",
    action_type="",
    target="",
    timestamp="2026-05-01T10:05:00Z",
    **kwargs,
):
    rec = {
        "feedback_id":   feedback_id,
        "feedback_type": feedback_type,
        "session_id":    session_id,
        "project_id":    project_id,
        "action_type":   action_type,
        "target":        target,
        "timestamp":     timestamp,
        "proof_id":      "",
        "action_id":     "",
        "message":       "",
    }
    rec.update(kwargs)
    return rec


def make_kfeedback(
    feedback_id="kfb_001",
    feedback_type="NOT_HELPFUL",
    session_id="",
    project_id="",
    timestamp="2026-05-01T10:05:00Z",
    **kwargs,
):
    rec = {
        "feedback_id":   feedback_id,
        "feedback_type": feedback_type,
        "session_id":    session_id,
        "project_id":    project_id,
        "response_id":   "resp_001",
        "message":       "",
        "timestamp":     timestamp,
    }
    rec.update(kwargs)
    return rec


def run_with_cands(
    mod,
    cand_records,
    fb_records=None,
    kfb_records=None,
    dry_run=True,
    write_log=False,
):
    """
    Write temp files, call run_reflection, clean up, return result.
    Files are closed before run_reflection is called (avoids flush issues).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in cand_records:
            f.write(json.dumps(r) + "\n")
        cand_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in (fb_records or []):
            f.write(json.dumps(r) + "\n")
        fb_path = f.name
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for r in (kfb_records or []):
            f.write(json.dumps(r) + "\n")
        kfb_path = f.name

    # All file handles closed before calling the module
    try:
        result = mod.run_reflection(
            candidates_path     = cand_path,
            feedback_log_path   = fb_path,
            knowledge_log_path  = kfb_path,
            reflection_log_path = "/tmp/__no_refl_log_slice26__.jsonl",
            dry_run             = dry_run,
            write_log           = write_log,
        )
    finally:
        os.unlink(cand_path)
        os.unlink(fb_path)
        os.unlink(kfb_path)
    return result


# ─────────────────────────────────────────────────────────────────────────────

print("=" * 64)
print("D249–D265  Build 19: Session Reflection / Feedback Summary v1")
print("=" * 64)

module_src = read_src(_MODULE_PATH)

# ── D249  module importable + run_reflection callable ────────────────────────
print("\n[D249] module importable and run_reflection is callable")

try:
    mod = load_module()
    check("D249a", "rag/session_reflection.py imports without error", True)
except Exception as exc:
    check("D249a", "rag/session_reflection.py imports without error", False, str(exc))
    mod = None

if mod is not None:
    has_fn = hasattr(mod, "run_reflection") and callable(mod.run_reflection)
    check("D249b", "run_reflection is a callable", has_fn)
else:
    check("D249b", "run_reflection is a callable", False, "module not loaded")

# ── D250  missing logs → safe empty reflection ───────────────────────────────
print("\n[D250] missing logs return safe empty reflection")

if mod:
    r = mod.run_reflection(
        candidates_path     = "/tmp/__no_cands_d250__.jsonl",
        feedback_log_path   = "/tmp/__no_fb_d250__.jsonl",
        knowledge_log_path  = "/tmp/__no_kfb_d250__.jsonl",
        reflection_log_path = "/tmp/__no_refl_d250__.jsonl",
        dry_run=True,
    )
    check("D250a", "missing logs: counts.accepted == 0",
          r["counts"]["accepted"] == 0, f"got {r['counts']['accepted']}")
    check("D250b", "missing logs: counts.rejected == 0",
          r["counts"]["rejected"] == 0, f"got {r['counts']['rejected']}")
    all_empty = (
        r["accepted_signals"]   == []
        and r["rejected_signals"]   == []
        and r["repeated_patterns"]  == []
        and r["project_notes"]      == []
        and r["do_not_promote"]     == []
        and r["confidence_reasons"] == []
    )
    check("D250c", "missing logs: all list fields empty", all_empty,
          str({k: len(v) for k, v in r.items() if isinstance(v, list)}))
else:
    for sub in ("D250a", "D250b", "D250c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D251  empty logs → safe empty reflection ─────────────────────────────────
print("\n[D251] empty logs return safe empty reflection")

if mod:
    r = run_with_cands(mod, [], [], [])
    check("D251a", "empty candidates: counts.accepted == 0",
          r["counts"]["accepted"] == 0, f"got {r['counts']['accepted']}")
    check("D251b", "empty feedback: counts.rejected == 0",
          r["counts"]["rejected"] == 0, f"got {r['counts']['rejected']}")
else:
    check("D251a", "empty candidates: counts.accepted == 0", False, "module not loaded")
    check("D251b", "empty feedback: counts.rejected == 0",   False, "module not loaded")

# ── D252  candidates populate accepted_signals ───────────────────────────────
print("\n[D252] candidates populate accepted_signals fields")

if mod:
    c = make_candidate(candidate_id="d252_c1", feedback_type="KEEP", project_id="ProjA")
    r = run_with_cands(mod, [c])
    check("D252a", "1 KEEP candidate → accepted_signals has 1 entry",
          len(r["accepted_signals"]) == 1, f"got {len(r['accepted_signals'])}")
    if r["accepted_signals"]:
        sig = r["accepted_signals"][0]
        required_keys = {
            "candidate_id", "feedback_type", "scope", "suggested_level",
            "score", "evidence", "action_type", "target", "project_id", "session_id",
        }
        missing = required_keys - set(sig.keys())
        check("D252b", "accepted entry has all required fields",
              not missing, f"missing: {missing}")
        check("D252c", "accepted entry candidate_id matches source",
              sig["candidate_id"] == "d252_c1", f"got {sig.get('candidate_id')}")
    else:
        check("D252b", "accepted entry has all required fields",    False, "no accepted_signals")
        check("D252c", "accepted entry candidate_id matches source", False, "no accepted_signals")
else:
    for sub in ("D252a", "D252b", "D252c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D253  rejected_signals from negative feedback ────────────────────────────
print("\n[D253] rejected_signals from negative feedback logs")

if mod:
    fb_undo = make_feedback(feedback_id="d253_fb_undo", feedback_type="UNDO")
    r = run_with_cands(mod, [], [fb_undo], [])
    check("D253a", "UNDO in feedback_log → rejected_signals has 1 entry",
          len(r["rejected_signals"]) == 1, f"got {len(r['rejected_signals'])}")

    fb_wd = make_feedback(feedback_id="d253_fb_wd", feedback_type="WRONG_DIRECTION")
    r2 = run_with_cands(mod, [], [fb_wd], [])
    check("D253b", "WRONG_DIRECTION in feedback_log → in rejected_signals",
          len(r2["rejected_signals"]) == 1, f"got {len(r2['rejected_signals'])}")

    kfb = make_kfeedback(feedback_id="d253_kfb", feedback_type="NOT_HELPFUL")
    r3 = run_with_cands(mod, [], [], [kfb])
    check("D253c", "NOT_HELPFUL in knowledge_log → in rejected_signals",
          len(r3["rejected_signals"]) == 1, f"got {len(r3['rejected_signals'])}")
else:
    for sub in ("D253a", "D253b", "D253c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D254  counts match source records ────────────────────────────────────────
print("\n[D254] accepted/rejected counts match source records")

if mod:
    c1 = make_candidate(candidate_id="d254_c1", action_type="SET_TRACK_VOLUME")
    c2 = make_candidate(candidate_id="d254_c2", action_type="SET_TRACK_PAN")
    r = run_with_cands(mod, [c1, c2])
    check("D254a", "2 candidates → counts.accepted == 2",
          r["counts"]["accepted"] == 2, f"got {r['counts']['accepted']}")

    fb1 = make_feedback(feedback_id="d254_fb1", feedback_type="UNDO")
    fb2 = make_feedback(feedback_id="d254_fb2", feedback_type="UNDO")
    r2 = run_with_cands(mod, [], [fb1, fb2])
    check("D254b", "2 UNDO records → counts.rejected == 2",
          r2["counts"]["rejected"] == 2, f"got {r2['counts']['rejected']}")
else:
    check("D254a", "2 candidates → counts.accepted == 2", False, "module not loaded")
    check("D254b", "2 UNDO records → counts.rejected == 2", False, "module not loaded")

# ── D255  repeated pattern detection ─────────────────────────────────────────
print("\n[D255] repeated pattern detection from action_type metadata")

if mod:
    # Two candidates with the same action_type → should be a repeated pattern
    c1 = make_candidate(candidate_id="d255_c1", action_type="SET_TRACK_VOLUME")
    c2 = make_candidate(candidate_id="d255_c2", action_type="SET_TRACK_VOLUME")
    r = run_with_cands(mod, [c1, c2])
    check("D255a", "2 candidates with same action_type → 1 repeated pattern",
          len(r["repeated_patterns"]) == 1, f"got {len(r['repeated_patterns'])}")
    if r["repeated_patterns"]:
        check("D255b", "pattern count == 2",
              r["repeated_patterns"][0]["count"] == 2,
              f"got count={r['repeated_patterns'][0].get('count')}")
    else:
        check("D255b", "pattern count == 2", False, "no repeated_patterns")

    # Two candidates with different action_types → each appears once → no pattern
    c3 = make_candidate(candidate_id="d255_c3", action_type="SET_TRACK_VOLUME")
    c4 = make_candidate(candidate_id="d255_c4", action_type="SET_TRACK_PAN")
    r2 = run_with_cands(mod, [c3, c4])
    check("D255c", "2 candidates with different action_types → 0 repeated patterns",
          len(r2["repeated_patterns"]) == 0, f"got {len(r2['repeated_patterns'])}")
else:
    for sub in ("D255a", "D255b", "D255c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D256  project_notes only when project_id present ─────────────────────────
print("\n[D256] project_notes only when project_id is present")

if mod:
    c_proj   = make_candidate(candidate_id="d256_c1", project_id="ProjX",
                               scope="session_project")
    c_noproj = make_candidate(candidate_id="d256_c2", project_id="",
                               scope="session_only")
    r = run_with_cands(mod, [c_proj, c_noproj])
    check("D256a", "candidate with project_id → project_notes has 1 entry",
          len(r["project_notes"]) == 1, f"got {len(r['project_notes'])}")
    proj_ids_in_notes = [n["project_id"] for n in r["project_notes"]]
    check("D256b", "empty project_id candidate not in project_notes",
          "" not in proj_ids_in_notes, f"ids in notes: {proj_ids_in_notes}")
    if r["project_notes"]:
        note = next((n for n in r["project_notes"] if n["project_id"] == "ProjX"), None)
        check("D256c", "project note accepted_count == 1 for ProjX",
              note is not None and note["accepted_count"] == 1,
              f"note={note}")
    else:
        check("D256c", "project note accepted_count == 1 for ProjX",
              False, "no project_notes")
else:
    for sub in ("D256a", "D256b", "D256c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D257  scope field preserved from candidate record ────────────────────────
print("\n[D257] scope field preserved from candidate record")

if mod:
    c_no_proj   = make_candidate(candidate_id="d257_c1", project_id="",
                                  scope="session_only",   suggested_level=1)
    c_with_proj = make_candidate(candidate_id="d257_c2", project_id="ProjY",
                                  scope="session_project", suggested_level=2)
    r = run_with_cands(mod, [c_no_proj, c_with_proj])
    sigs_by_id = {s["candidate_id"]: s for s in r["accepted_signals"]}
    check("D257a", "no project_id candidate scope == 'session_only'",
          sigs_by_id.get("d257_c1", {}).get("scope") == "session_only",
          f"got {sigs_by_id.get('d257_c1', {}).get('scope')}")
    check("D257b", "project_id candidate scope == 'session_project'",
          sigs_by_id.get("d257_c2", {}).get("scope") == "session_project",
          f"got {sigs_by_id.get('d257_c2', {}).get('scope')}")
else:
    check("D257a", "no project_id → scope session_only",  False, "module not loaded")
    check("D257b", "project_id → scope session_project",  False, "module not loaded")

# ── D258  only negative types go to do_not_promote ───────────────────────────
print("\n[D258] only negative feedback types appear in do_not_promote")

if mod:
    fb_too_much = make_feedback(feedback_id="d258_fb_tm",   feedback_type="TOO_MUCH")
    fb_keep     = make_feedback(feedback_id="d258_fb_keep", feedback_type="KEEP")
    fb_undo     = make_feedback(feedback_id="d258_fb_undo", feedback_type="UNDO")
    r = run_with_cands(mod, [], [fb_too_much, fb_keep, fb_undo])
    dtp_types = [e["feedback_type"] for e in r["do_not_promote"]]
    check("D258a", "TOO_MUCH not in do_not_promote",
          "TOO_MUCH" not in dtp_types, f"do_not_promote types: {dtp_types}")
    check("D258b", "KEEP not in do_not_promote",
          "KEEP" not in dtp_types, f"do_not_promote types: {dtp_types}")
    check("D258c", "UNDO in do_not_promote",
          "UNDO" in dtp_types, f"do_not_promote types: {dtp_types}")
else:
    for sub in ("D258a", "D258b", "D258c"):
        check(sub, f"sub-check {sub}", False, "module not loaded")

# ── D259  dry_run and write_log=False write nothing ──────────────────────────
print("\n[D259] dry_run / output-only mode writes nothing")

if mod:
    # dry_run=True must override write_log=True
    refl_log_a = "/tmp/__d259a_refl_log__.jsonl"
    if os.path.exists(refl_log_a):
        os.unlink(refl_log_a)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(make_candidate(candidate_id="d259_c1")) + "\n")
        cp = f.name
    try:
        mod.run_reflection(
            candidates_path     = cp,
            feedback_log_path   = "/tmp/__no_fb_d259__.jsonl",
            knowledge_log_path  = "/tmp/__no_kfb_d259__.jsonl",
            reflection_log_path = refl_log_a,
            dry_run=True,
            write_log=True,
        )
    finally:
        os.unlink(cp)
    check("D259a", "dry_run=True overrides write_log=True → log not created",
          not os.path.exists(refl_log_a),
          f"log unexpectedly created at {refl_log_a}")

    # write_log=False (default) must not create log either
    refl_log_b = "/tmp/__d259b_refl_log__.jsonl"
    if os.path.exists(refl_log_b):
        os.unlink(refl_log_b)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        f.write(json.dumps(make_candidate(candidate_id="d259_c2")) + "\n")
        cp2 = f.name
    try:
        mod.run_reflection(
            candidates_path     = cp2,
            feedback_log_path   = "/tmp/__no_fb_d259b__.jsonl",
            knowledge_log_path  = "/tmp/__no_kfb_d259b__.jsonl",
            reflection_log_path = refl_log_b,
            dry_run=False,
            write_log=False,
        )
    finally:
        os.unlink(cp2)
    check("D259b", "write_log=False → reflection log not created",
          not os.path.exists(refl_log_b),
          f"log unexpectedly created at {refl_log_b}")
else:
    check("D259a", "dry_run=True → reflection log not created", False, "module not loaded")
    check("D259b", "write_log=False → reflection log not created", False, "module not loaded")

# ── D260  promotion_candidates.jsonl mtime unchanged ─────────────────────────
print("\n[D260] live promotion_candidates.jsonl mtime unchanged after run")

if mod and os.path.exists(_LIVE_CANDIDATES):
    import time
    mtime_before = os.path.getmtime(_LIVE_CANDIDATES)
    time.sleep(0.05)
    mod.run_reflection(
        candidates_path     = _LIVE_CANDIDATES,
        feedback_log_path   = "/tmp/__no_fb_d260__.jsonl",
        knowledge_log_path  = "/tmp/__no_kfb_d260__.jsonl",
        reflection_log_path = "/tmp/__no_refl_d260__.jsonl",
        dry_run=True,
    )
    mtime_after = os.path.getmtime(_LIVE_CANDIDATES)
    check("D260a", "promotion_candidates.jsonl mtime unchanged",
          mtime_before == mtime_after,
          f"before={mtime_before}  after={mtime_after}")
else:
    check("D260a", "promotion_candidates.jsonl mtime unchanged (file absent — skip)",
          True, "file absent — skipped")

# ── D261  never_do_rules.md mtime unchanged ──────────────────────────────────
print("\n[D261] never_do_rules.md mtime unchanged after run")

if mod and os.path.exists(_NEVER_DO_PATH):
    mtime_before = os.path.getmtime(_NEVER_DO_PATH)
    mod.run_reflection(
        candidates_path     = "/tmp/__no_cands_d261__.jsonl",
        feedback_log_path   = "/tmp/__no_fb_d261__.jsonl",
        knowledge_log_path  = "/tmp/__no_kfb_d261__.jsonl",
        reflection_log_path = "/tmp/__no_refl_d261__.jsonl",
        dry_run=True,
    )
    mtime_after = os.path.getmtime(_NEVER_DO_PATH)
    check("D261a", "never_do_rules.md mtime unchanged",
          mtime_before == mtime_after,
          f"before={mtime_before}  after={mtime_after}")
else:
    check("D261a", "never_do_rules.md mtime unchanged (file absent — skip)",
          True, "file absent — skipped")

# ── D262  no ChromaDB import or reference ────────────────────────────────────
print("\n[D262] no ChromaDB import or reference in source")

no_chromadb_import = not re.search(r"import chromadb|from chromadb", module_src)
check("D262a", "no chromadb import in source", no_chromadb_import,
      "found chromadb import" if not no_chromadb_import else "")

no_chromadb_ref = "chromadb" not in module_src
check("D262b", "no 'chromadb' reference anywhere in source", no_chromadb_ref,
      "found 'chromadb' in source" if not no_chromadb_ref else "")

# ── D263  no forbidden imports or references ─────────────────────────────────
print("\n[D263] no forbidden imports or references in source")

forbidden = [
    ("harness_server",   r"harness_server"),
    ("conductor_bridge", r"conductor_bridge"),
    ("app/",             r"""['"]app/"""),
    ("PluginBridge",     r"PluginBridge"),
    ("Auto Execute",     r"Auto Execute"),
    ("requests/httpx",   r"\b(import requests|import httpx|from requests|from httpx)\b"),
]

for label, pattern in forbidden:
    found = bool(re.search(pattern, module_src))
    safe_label = label.replace("/", "_").replace(" ", "_")
    check(
        f"D263-{safe_label}",
        f"no '{label}' reference in source",
        not found,
        f"found '{label}' in source" if found else "",
    )

# ── D264  CLI guard present ───────────────────────────────────────────────────
print("\n[D264] CLI guard present in source")

cli_guard = (
    'if __name__ == "__main__"' in module_src
    or "if __name__ == '__main__'" in module_src
)
check("D264a", 'if __name__ == "__main__" guard present', cli_guard,
      "not found" if not cli_guard else "")

# ── D265  confidence_reasons populated for accepted signals ──────────────────
print("\n[D265] confidence_reasons populated for accepted signals")

if mod:
    c = make_candidate(
        candidate_id="d265_c1",
        feedback_type="KEEP",
        score=0.75,
        evidence="action:SET_TRACK_VOLUME | user_note:sounded right",
        suggested_level=2,
    )
    r = run_with_cands(mod, [c])
    check("D265a", "1 accepted candidate → 1 confidence_reason",
          len(r["confidence_reasons"]) == 1, f"got {len(r['confidence_reasons'])}")
    if r["confidence_reasons"]:
        cr = r["confidence_reasons"][0]
        required = {"candidate_id", "feedback_type", "score", "suggested_level", "evidence"}
        missing = required - set(cr.keys())
        check("D265b", "confidence_reason has all required fields",
              not missing, f"missing: {missing}")
    else:
        check("D265b", "confidence_reason has all required fields",
              False, "no confidence_reasons")
else:
    check("D265a", "1 accepted candidate → 1 confidence_reason", False, "module not loaded")
    check("D265b", "confidence_reason has required fields",       False, "module not loaded")


# ── Summary ───────────────────────────────────────────────────────────────────

print()
print("=" * 64)
total  = len(results)
passed = sum(1 for r in results if r[1] == PASS)
failed = total - passed

if failed == 0:
    print(f"Result: {total}/{total} PASS")
    print("All checks PASS.")
else:
    print(f"Result: {passed}/{total} PASS  ({failed} FAIL)")
    print("FAILURES:")
    for id_, status, desc, detail in results:
        if status == FAIL:
            d = f"  → {detail}" if detail else ""
            print(f"  [{FAIL}] {id_}: {desc}{d}")
    sys.exit(1)
