#!/usr/bin/env python3
"""
phase_d_slice27_eval.py — Build 20: Controlled Memory Writer v1
Tests D266–D280.

All checks are static source analysis + unit-level functional tests.
No browser runtime, no live ChromaDB writes, no live bridge calls.
Bridge calls are mocked via unittest.mock. All live logs are read-only or
not accessed at all.
"""

import importlib.util
import json
import os
import re
import sys
import tempfile
from unittest.mock import MagicMock, patch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_MODULE_PATH   = os.path.join(_ROOT, "rag", "memory_writer.py")
_NEVER_DO_PATH = os.path.join(_ROOT, "conductor-vault", "producer", "never_do_rules.md")
_CHROMA_DIR    = os.path.join(_ROOT, "memory", "chromadb")

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
    spec = importlib.util.spec_from_file_location("memory_writer", _MODULE_PATH)
    mod  = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Test data helpers ─────────────────────────────────────────────────────────

def make_signal(
    candidate_id="cand_001",
    scope="session_project",
    suggested_level=2,
    project_id="TestProject",
    session_id="sess_abc",
    evidence="action:SET_TRACK_VOLUME | target:track:Kick",
    action_type="SET_TRACK_VOLUME",
    target="track:Kick",
    message="",
    feedback_type="KEEP",
    **kwargs,
):
    d = {
        "candidate_id":    candidate_id,
        "source":          "action_feedback",
        "feedback_type":   feedback_type,
        "action_type":     action_type,
        "target":          target,
        "session_id":      session_id,
        "project_id":      project_id,
        "scope":           scope,
        "suggested_level": suggested_level,
        "score":           0.65,
        "evidence":        evidence,
        "message":         message,
    }
    d.update(kwargs)
    return d


def make_reflection(accepted=None, do_not_promote=None):
    acc = accepted or []
    return {
        "reflection_id":      "refl_test001",
        "generated_at":       "2026-05-01T10:00:00Z",
        "session_id":         "",
        "project_id":         "",
        "accepted_signals":   acc,
        "rejected_signals":   [],
        "do_not_promote":     do_not_promote or [],
        "repeated_patterns":  [],
        "project_notes":      [],
        "confidence_reasons": [],
        "counts":             {"accepted": len(acc)},
    }


def make_mock_urlopen(ok=True, mem_id="mem_test_001"):
    """Return a mock suitable for use as urllib.request.urlopen return value."""
    body = json.dumps({"ok": ok, "id": mem_id}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = body
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


# ── D266 — importable, callable, output keys ─────────────────────────────────

def run_d266():
    print("\n[D266] Import + callable + output key contract")
    try:
        mod = load_module()
        ok1 = check("D266a", "write_promoted_memories importable", callable(mod.write_promoted_memories))
        result = mod.write_promoted_memories(reflection=make_reflection(), dry_run=True)
        required_keys = {
            "written", "skipped_negative_feedback", "skipped_do_not_promote",
            "skipped_global_taste", "skipped_level_cap", "skipped_no_project_id",
            "skipped_duplicate", "failed_bridge", "dry_run", "write_details",
        }
        missing = required_keys - set(result.keys())
        ok2 = check("D266b", "all output keys present", not missing, str(missing))
        ok3 = check("D266c", "dry_run=True reflected in result", result["dry_run"] is True)
        return ok1 and ok2 and ok3
    except Exception as exc:
        check("D266", "import + call", False, str(exc))
        return False


# ── D267 — missing reflection file → empty result ────────────────────────────

def run_d267():
    print("\n[D267] Missing reflection file → zero writes, no crash")
    mod = load_module()
    result = mod.write_promoted_memories(
        reflection_path="/tmp/does_not_exist_conductor_b20.jsonl",
        dry_run=True,
    )
    ok1 = check("D267a", "written=0",             result["written"] == 0)
    ok2 = check("D267b", "all skip counters=0",
                all(result[k] == 0 for k in [
                    "skipped_do_not_promote", "skipped_global_taste",
                    "skipped_level_cap", "skipped_no_project_id",
                    "skipped_duplicate", "failed_bridge",
                ]))
    ok3 = check("D267c", "write_details=[]",       result["write_details"] == [])
    return ok1 and ok2 and ok3


# ── D268 — empty accepted_signals → zero writes ───────────────────────────────

def run_d268():
    print("\n[D268] Empty accepted_signals → zero writes")
    mod    = load_module()
    result = mod.write_promoted_memories(reflection=make_reflection(accepted=[]), dry_run=True)
    ok1 = check("D268a", "written=0",       result["written"] == 0)
    ok2 = check("D268b", "write_details=[]", result["write_details"] == [])
    return ok1 and ok2


# ── D269 — do_not_promote skip ────────────────────────────────────────────────

def run_d269():
    print("\n[D269] candidate_id in do_not_promote → skipped")
    mod = load_module()
    sig = make_signal(candidate_id="cand_dnp")
    dnp = [{"candidate_id": "cand_dnp", "feedback_type": "UNDO"}]
    result = mod.write_promoted_memories(
        reflection=make_reflection(accepted=[sig], do_not_promote=dnp),
        dry_run=False,  # dry_run off — gate must fire before bridge
    )
    ok1 = check("D269a", "skipped_do_not_promote=1", result["skipped_do_not_promote"] == 1)
    ok2 = check("D269b", "written=0",                 result["written"] == 0)
    ok3 = check("D269c", "failed_bridge=0",            result["failed_bridge"] == 0)
    detail = result["write_details"][0] if result["write_details"] else {}
    ok4 = check("D269d", "outcome=skipped_do_not_promote",
                detail.get("outcome") == "skipped_do_not_promote")
    return ok1 and ok2 and ok3 and ok4


# ── D270 — global_taste skip ─────────────────────────────────────────────────

def run_d270():
    print("\n[D270] scope==global_taste → skipped")
    mod  = load_module()
    sig  = make_signal(scope="global_taste", candidate_id="cand_gt")
    result = mod.write_promoted_memories(reflection=make_reflection(accepted=[sig]), dry_run=False)
    ok1 = check("D270a", "skipped_global_taste=1", result["skipped_global_taste"] == 1)
    ok2 = check("D270b", "written=0",               result["written"] == 0)
    detail = result["write_details"][0] if result["write_details"] else {}
    ok3 = check("D270c", "outcome=skipped_global_taste",
                detail.get("outcome") == "skipped_global_taste")
    return ok1 and ok2 and ok3


# ── D271 — level cap: suggested_level >= 3 → skip ────────────────────────────

def run_d271():
    print("\n[D271] suggested_level >= 3 → skipped_level_cap")
    mod = load_module()
    sig3 = make_signal(candidate_id="cand_l3", suggested_level=3)
    sig4 = make_signal(candidate_id="cand_l4", suggested_level=4)
    result = mod.write_promoted_memories(
        reflection=make_reflection(accepted=[sig3, sig4]),
        dry_run=False,
    )
    ok1 = check("D271a", "skipped_level_cap=2", result["skipped_level_cap"] == 2)
    ok2 = check("D271b", "written=0",            result["written"] == 0)
    outcomes = [d.get("outcome") for d in result["write_details"]]
    ok3 = check("D271c", "all outcomes=skipped_level_cap",
                all(o == "skipped_level_cap" for o in outcomes))
    return ok1 and ok2 and ok3


# ── D272 — valid session_project → "project" collection ──────────────────────

def run_d272():
    print("\n[D272] Valid session_project → bridge POST to 'project' collection")
    mod = load_module()
    sig = make_signal(
        candidate_id="cand_sp",
        scope="session_project",
        suggested_level=2,
        project_id="SongAlpha",
        session_id="sess_001",
        evidence="action:SET_TRACK_VOLUME | target:track:Kick",
    )
    mock_resp = make_mock_urlopen(ok=True, mem_id="mem_proj_001")

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = mod.write_promoted_memories(
            reflection=make_reflection(accepted=[sig]),
            bridge_url="http://localhost:9999",
            dry_run=False,
            write_log=False,
        )

    ok1 = check("D272a", "written=1",       result["written"] == 1)
    ok2 = check("D272b", "failed_bridge=0", result["failed_bridge"] == 0)
    ok3 = check("D272c", "bridge called",   mock_open.called)

    req  = mock_open.call_args[0][0]
    body = json.loads(req.data.decode("utf-8"))

    ok4 = check("D272d", "collection=project",        body.get("collection") == "project")
    ok5 = check("D272e", "mode=INTERN_WRITE_SAFE",    body.get("mode") == "INTERN_WRITE_SAFE")
    ok6 = check("D272f", "source_type=memory_promotion",
                body.get("metadata", {}).get("source_type") == "memory_promotion")
    ok7 = check("D272g", "memory_level=2",
                body.get("metadata", {}).get("memory_level") == 2)
    ok8 = check("D272h", "project_id in metadata",
                body.get("metadata", {}).get("project_id") == "SongAlpha")
    ok9 = check("D272i", "text non-empty",  bool(body.get("text", "")))
    return all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9])


# ── D273 — valid session_only → "producer" collection ────────────────────────

def run_d273():
    print("\n[D273] Valid session_only → bridge POST to 'producer' collection")
    mod = load_module()
    sig = make_signal(
        candidate_id="cand_so",
        scope="session_only",
        suggested_level=1,
        project_id="",
        session_id="sess_002",
        evidence="knowledge_feedback:HELPFUL",
    )
    mock_resp = make_mock_urlopen(ok=True, mem_id="mem_prod_001")

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_open:
        result = mod.write_promoted_memories(
            reflection=make_reflection(accepted=[sig]),
            bridge_url="http://localhost:9999",
            dry_run=False,
        )

    ok1 = check("D273a", "written=1",            result["written"] == 1)
    ok2 = check("D273b", "bridge called",         mock_open.called)
    req  = mock_open.call_args[0][0]
    body = json.loads(req.data.decode("utf-8"))
    ok3 = check("D273c", "collection=producer",   body.get("collection") == "producer")
    ok4 = check("D273d", "memory_level=1",
                body.get("metadata", {}).get("memory_level") == 1)
    # no project_id in metadata (empty)
    ok5 = check("D273e", "no project_id key when empty",
                "project_id" not in body.get("metadata", {}))
    return ok1 and ok2 and ok3 and ok4 and ok5


# ── D274 — session_project + empty project_id → skip ─────────────────────────

def run_d274():
    print("\n[D274] session_project + empty project_id → skipped_no_project_id")
    mod = load_module()
    sig = make_signal(scope="session_project", project_id="")
    result = mod.write_promoted_memories(
        reflection=make_reflection(accepted=[sig]),
        dry_run=False,
    )
    ok1 = check("D274a", "skipped_no_project_id=1", result["skipped_no_project_id"] == 1)
    ok2 = check("D274b", "written=0",                result["written"] == 0)
    detail = result["write_details"][0] if result["write_details"] else {}
    ok3 = check("D274c", "outcome=skipped_no_project_id",
                detail.get("outcome") == "skipped_no_project_id")
    return ok1 and ok2 and ok3


# ── D275 — dry_run=True → zero bridge calls ───────────────────────────────────

def run_d275():
    print("\n[D275] dry_run=True → no urlopen calls, even with valid candidates")
    mod = load_module()
    sigs = [
        make_signal(candidate_id="cand_dr1"),
        make_signal(candidate_id="cand_dr2", scope="session_only", project_id=""),
    ]

    with patch("urllib.request.urlopen") as mock_open:
        result = mod.write_promoted_memories(
            reflection=make_reflection(accepted=sigs),
            dry_run=True,
        )

    ok1 = check("D275a", "urlopen not called",  not mock_open.called)
    ok2 = check("D275b", "written=0",            result["written"] == 0)
    ok3 = check("D275c", "dry_run=True in result", result["dry_run"] is True)
    dry_outcomes = [d.get("outcome") for d in result["write_details"]]
    ok4 = check("D275d", "all outcomes=dry_run",
                all(o == "dry_run" for o in dry_outcomes))
    return ok1 and ok2 and ok3 and ok4


# ── D276 — bridge failure → non-fatal ────────────────────────────────────────

def run_d276():
    print("\n[D276] Bridge failure → non-fatal; failed_bridge increments; others continue")
    mod = load_module()
    sig_fail = make_signal(candidate_id="cand_fail")
    sig_ok   = make_signal(candidate_id="cand_ok2", scope="session_only", project_id="")

    call_count = [0]

    def side_effect(*args, **kwargs):
        call_count[0] += 1
        if call_count[0] == 1:
            raise Exception("connection refused")
        return make_mock_urlopen(ok=True, mem_id="mem_ok2")

    with patch("urllib.request.urlopen", side_effect=side_effect):
        result = mod.write_promoted_memories(
            reflection=make_reflection(accepted=[sig_fail, sig_ok]),
            dry_run=False,
        )

    ok1 = check("D276a", "failed_bridge=1", result["failed_bridge"] == 1)
    ok2 = check("D276b", "written=1",        result["written"] == 1)
    outcomes = [d.get("outcome") for d in result["write_details"]]
    ok3 = check("D276c", "both candidates processed",
                "failed_bridge" in outcomes and "written" in outcomes)
    return ok1 and ok2 and ok3


# ── D277 — idempotency: second run → skipped_duplicate ───────────────────────

def run_d277():
    print("\n[D277] Idempotency — write_log=True, second run → skipped_duplicate")
    mod = load_module()
    sig = make_signal(candidate_id="cand_idem")

    with tempfile.TemporaryDirectory() as tmpdir:
        wl_path = os.path.join(tmpdir, "write_log.jsonl")

        # Patch DEFAULT_WRITE_LOG_PATH to our temp file
        original_wl = mod.DEFAULT_WRITE_LOG_PATH
        mod.DEFAULT_WRITE_LOG_PATH = wl_path

        try:
            mock_resp = make_mock_urlopen(ok=True, mem_id="mem_idem_001")

            # First run
            with patch("urllib.request.urlopen", return_value=mock_resp):
                r1 = mod.write_promoted_memories(
                    reflection=make_reflection(accepted=[sig]),
                    dry_run=False,
                    write_log=True,
                )

            ok1 = check("D277a", "first run: written=1",      r1["written"] == 1)
            ok2 = check("D277b", "first run: no duplicates",  r1["skipped_duplicate"] == 0)

            # Write log must exist
            ok3 = check("D277c", "write_log.jsonl created",   os.path.exists(wl_path))

            # Second run — same candidate
            with patch("urllib.request.urlopen") as mock_open2:
                r2 = mod.write_promoted_memories(
                    reflection=make_reflection(accepted=[sig]),
                    dry_run=False,
                    write_log=True,
                )
            ok4 = check("D277d", "second run: written=0",       r2["written"] == 0)
            ok5 = check("D277e", "second run: skipped_duplicate=1",
                        r2["skipped_duplicate"] == 1)
            ok6 = check("D277f", "second run: no bridge call",  not mock_open2.called)

        finally:
            mod.DEFAULT_WRITE_LOG_PATH = original_wl

    return ok1 and ok2 and ok3 and ok4 and ok5 and ok6


# ── D278 — level cap enforced in payload ─────────────────────────────────────

def run_d278():
    print("\n[D278] Level cap: memory_level in payload always 1–2")
    mod = load_module()

    # L1 and L2 are valid; make two candidates that pass all other gates
    sig1 = make_signal(candidate_id="cand_l1v", suggested_level=1,
                       scope="session_only", project_id="")
    sig2 = make_signal(candidate_id="cand_l2v", suggested_level=2,
                       scope="session_project", project_id="ProjB")

    call_bodies = []

    def capture(*args, **kwargs):
        req  = args[0]
        body = json.loads(req.data.decode("utf-8"))
        call_bodies.append(body)
        return make_mock_urlopen(ok=True, mem_id=f"mem_{len(call_bodies)}")

    with patch("urllib.request.urlopen", side_effect=capture):
        result = mod.write_promoted_memories(
            reflection=make_reflection(accepted=[sig1, sig2]),
            dry_run=False,
        )

    ok1 = check("D278a", "written=2", result["written"] == 2)
    levels = [b.get("metadata", {}).get("memory_level") for b in call_bodies]
    ok2 = check("D278b", "all memory_levels >= 1", all(l >= 1 for l in levels))
    ok3 = check("D278c", "all memory_levels <= 2", all(l <= 2 for l in levels))
    ok4 = check("D278d", "L1 candidate → level=1", 1 in levels)
    ok5 = check("D278e", "L2 candidate → level=2", 2 in levels)
    return ok1 and ok2 and ok3 and ok4 and ok5


# ── D279 — live source log mtimes unchanged ───────────────────────────────────

def run_d279():
    print("\n[D279] Live source logs mtimes unchanged after write_promoted_memories call")
    mod = load_module()

    # Paths that must NOT be modified
    guarded = {
        "promotion_candidates.jsonl": os.path.join(_ROOT, "memory", "promotion_candidates.jsonl"),
        "session_reflection_log.jsonl": os.path.join(_ROOT, "memory", "session_reflection_log.jsonl"),
        "feedback_log.jsonl":         os.path.join(_ROOT, "memory", "feedback_log.jsonl"),
        "knowledge_feedback_log.jsonl": os.path.join(_ROOT, "memory", "knowledge_feedback_log.jsonl"),
        "never_do_rules.md":          _NEVER_DO_PATH,
    }

    before = {name: (os.path.getmtime(p) if os.path.exists(p) else None)
              for name, p in guarded.items()}

    sig = make_signal(candidate_id="cand_mtime")
    mod.write_promoted_memories(
        reflection=make_reflection(accepted=[sig]),
        dry_run=True,  # dry_run — no writes to any file
    )

    after = {name: (os.path.getmtime(p) if os.path.exists(p) else None)
             for name, p in guarded.items()}

    all_ok = True
    for name in guarded:
        ok = check(f"D279-{name[:20]}", f"{name} mtime unchanged", before[name] == after[name])
        if not ok:
            all_ok = False
    return all_ok


# ── D280 — static source analysis ────────────────────────────────────────────

def run_d280():
    print("\n[D280] Static source analysis")
    src = read_src(_MODULE_PATH)

    # No direct chromadb import
    ok1 = check("D280a", "no 'import chromadb'",
                not re.search(r"\bimport chromadb\b", src))

    # No direct chroma write (e.g. col.add, collection.add)
    ok2 = check("D280b", "no direct col.add / .upsert ChromaDB calls",
                not re.search(r"\bcol\.(?:add|upsert)\b", src))

    # No never_do_rules.md open for writing
    ok3 = check("D280c", "never_do_rules.md not opened for write",
                not re.search(r'open\([^)]*never_do_rules', src))

    # No confirmed_preferences.md open for writing
    ok4 = check("D280d", "confirmed_preferences.md not opened for write",
                not re.search(r'open\([^)]*confirmed_preferences', src))

    # No memory_level >= 3 in any payload construction
    ok5 = check("D280e", "no hardcoded memory_level >= 3 in source",
                not re.search(r'"memory_level"\s*:\s*[34]', src))

    # mode is INTERN_WRITE_SAFE
    ok6 = check("D280f", "_MODE = INTERN_WRITE_SAFE",
                re.search(r'_MODE\s*=\s*["\']INTERN_WRITE_SAFE["\']', src))

    # Level cap constant = 2
    ok7 = check("D280g", "_LEVEL_CAP = 2",
                re.search(r'_LEVEL_CAP\s*=\s*2\b', src))

    # global_taste in _SKIP_SCOPES
    ok8 = check("D280h", "global_taste in _SKIP_SCOPES",
                re.search(r'_SKIP_SCOPES\s*=.*global_taste', src, re.DOTALL))

    # __main__ guard present
    ok9 = check("D280i", "__main__ guard present",
                'if __name__ == "__main__"' in src or "if __name__ == '__main__'" in src)

    # Default reflection path points to session_reflection_log.jsonl
    ok10 = check("D280j", "DEFAULT_REFLECTION_PATH references session_reflection_log",
                 "session_reflection_log.jsonl" in src)

    # Default write log path points to write_log.jsonl
    ok11 = check("D280k", "DEFAULT_WRITE_LOG_PATH references write_log.jsonl",
                 "write_log.jsonl" in src)

    # No direct ChromaDB client instantiation (PersistentClient / Client())
    ok12 = check("D280l", "no chromadb client instantiation",
                 not re.search(r'chromadb\.(Persistent)?Client\s*\(', src))

    # _NEGATIVE_FEEDBACK_TYPES covers all 5 required types
    required_neg = {"UNDO", "WRONG_DIRECTION", "NOT_HELPFUL", "WRONG", "OUTDATED"}
    ok14 = check("D280n", "_NEGATIVE_FEEDBACK_TYPES covers all 5 negative types",
                 all(t in src for t in required_neg))

    # No import of memory_promotion or session_reflection (no circular dep)
    ok13 = check("D280m", "no import of memory_promotion or session_reflection",
                 not re.search(r'from rag\.(memory_promotion|session_reflection)', src) and
                 not re.search(r'import rag\.(memory_promotion|session_reflection)', src))

    return all([ok1, ok2, ok3, ok4, ok5, ok6, ok7, ok8, ok9, ok10, ok11, ok12, ok13, ok14])


# ── D281 — negative feedback_type in accepted_signals → always skipped ────────

def run_d281():
    print("\n[D281] Negative feedback_type in accepted_signals → skipped, zero bridge calls")
    mod = load_module()

    negative_types = ["UNDO", "WRONG_DIRECTION", "NOT_HELPFUL", "WRONG", "OUTDATED"]
    all_ok = True

    for ftype in negative_types:
        sig = make_signal(
            candidate_id=f"cand_{ftype.lower()}",
            feedback_type=ftype,
            scope="session_project",
            suggested_level=2,
            project_id="ProjX",
        )
        with patch("urllib.request.urlopen") as mock_open:
            result = mod.write_promoted_memories(
                reflection=make_reflection(accepted=[sig]),
                dry_run=False,
            )
        ok_written  = check(f"D281-{ftype}-written=0",
                            f"{ftype}: written=0",
                            result["written"] == 0)
        ok_skipped  = check(f"D281-{ftype}-skipped=1",
                            f"{ftype}: skipped_negative_feedback=1",
                            result["skipped_negative_feedback"] == 1)
        ok_no_call  = check(f"D281-{ftype}-no_bridge",
                            f"{ftype}: no bridge call",
                            not mock_open.called)
        detail = result["write_details"][0] if result["write_details"] else {}
        ok_outcome  = check(f"D281-{ftype}-outcome",
                            f"{ftype}: outcome=skipped_negative_feedback",
                            detail.get("outcome") == "skipped_negative_feedback")
        # No payload was built for this candidate
        ok_no_pay   = check(f"D281-{ftype}-no_payload",
                            f"{ftype}: no payload key in detail",
                            "payload" not in detail)
        if not all([ok_written, ok_skipped, ok_no_call, ok_outcome, ok_no_pay]):
            all_ok = False

    return all_ok


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("phase_d_slice27_eval — Build 20: Controlled Memory Writer v1")
    print("=" * 60)

    runners = [
        run_d266,
        run_d267,
        run_d268,
        run_d269,
        run_d270,
        run_d271,
        run_d272,
        run_d273,
        run_d274,
        run_d275,
        run_d276,
        run_d277,
        run_d278,
        run_d279,
        run_d280,
        run_d281,
    ]

    for runner in runners:
        try:
            runner()
        except Exception as exc:
            check(runner.__name__, "unexpected exception", False, str(exc))

    print()
    print("=" * 60)
    passed = sum(1 for _, s, _, _ in results if s == PASS)
    failed = sum(1 for _, s, _, _ in results if s == FAIL)
    print(f"  TOTAL: {passed} PASS / {failed} FAIL  (of {len(results)} checks)")
    print("=" * 60)

    if failed:
        print("\nFAILED checks:")
        for id_, status, desc, detail in results:
            if status == FAIL:
                print(f"  {id_}: {desc}" + (f"\n    → {detail}" if detail else ""))

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
