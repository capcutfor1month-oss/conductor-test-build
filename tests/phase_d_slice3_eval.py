"""
Phase D Slice 3 — Offline Eval Suite
──────────────────────────────────────
Tests for: POST /feedback — validation, JSONL persistence, log separation,
           reference lookup, promotion_eligible=False contract.

All tests run WITHOUT a live Ableton connection.

Run:
    /Volumes/T7 Shield/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3 \
        tests/phase_d_slice3_eval.py

Sections:
    D23 — Valid feedback writes JSONL with all required fields          (5 checks)
    D24 — Invalid proof/action reference rejected                       (3 checks)
    D25 — Invalid feedback_type rejected                                (3 checks)
    D26 — Feedback links to correct proof — vstat populated             (4 checks)
    D27 — FAILED/UNVERIFIED/VERIFIED all stored; promotion_eligible=F   (3 checks)
    D28 — No ChromaDB write; log paths separate from Phase C            (4 checks)
    D29 — Slice 1 + Slice 2 regressions                                 (1 check)
    D30 — Phase C eval regression                                       (1 check)

Total: 24 checks (22 offline + 2 subprocess)
"""

import os
import subprocess
import sys
import time
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

PASS = "✅"
FAIL = "❌"
SKIP = "⏭️ "


# ── HELPERS ────────────────────────────────────────────────────────────────────

def _make_proof(vstat: str = "VERIFIED") -> object:
    """Create a real ActionProof in the log for tests to reference."""
    from rag.action_proof import create_proof
    return create_proof(
        action_type         = "SET_TRACK_VOLUME",
        target              = "track:TestKick_Slice3",
        intended_value      = 0.85,
        before_state        = {"volume": 0.70},
        after_state         = {"volume": 0.85} if vstat == "VERIFIED" else {},
        verification_status = vstat,
        undo_eligible       = (vstat == "VERIFIED"),
        user_facing_summary = f"Slice 3 test proof ({vstat})",
        action_id           = f"s3act_{uuid.uuid4().hex[:8]}",
        request_id          = "req_s3_helper",
        session_id          = "sess_s3_test",
        project_id          = "TestProjectSlice3",
    )


# ── SECTION D23: Valid feedback writes JSONL ──────────────────────────────────

def run_valid_feedback_checks() -> bool:
    print("\n=== Section D23: Valid feedback writes JSONL with all required fields ===")
    ok = True

    from rag.feedback import (
        create_feedback, read_last_feedback,
        FeedbackRecord, FeedbackType, FEEDBACK_LOG_PATH,
    )

    proof = _make_proof("VERIFIED")

    # A — create_feedback returns FeedbackRecord with non-empty feedback_id
    record = create_feedback(
        "KEEP",
        proof_id   = proof.proof_id,
        session_id = "sess_d23",
        project_id = "TestD23",
        message    = "Kick volume was spot on",
    )
    if not isinstance(record, FeedbackRecord):
        print(f"{FAIL} [D23-A] create_feedback should return FeedbackRecord, "
              f"got {type(record)}")
        ok = False
    elif not record.feedback_id:
        print(f"{FAIL} [D23-A] feedback_id is empty")
        ok = False
    else:
        print(f"{PASS} [D23-A] create_feedback returns FeedbackRecord with feedback_id")

    # B — record written to JSONL (read_last_feedback returns matching record)
    last = read_last_feedback()
    if last is None or last.get("feedback_id") != record.feedback_id:
        print(f"{FAIL} [D23-B] JSONL write failed or feedback_id mismatch: "
              f"{last.get('feedback_id') if last else None!r}")
        ok = False
    else:
        print(f"{PASS} [D23-B] Feedback written to {os.path.basename(FEEDBACK_LOG_PATH)}")

    # C — feedback_type stored as normalised uppercase
    if record.feedback_type != "KEEP":
        print(f"{FAIL} [D23-C] feedback_type should be 'KEEP', got {record.feedback_type!r}")
        ok = False
    else:
        print(f"{PASS} [D23-C] feedback_type stored as uppercase 'KEEP'")

    # D — promotion_eligible is always False in Slice 3
    if record.promotion_eligible is not False:
        print(f"{FAIL} [D23-D] promotion_eligible should be False, "
              f"got {record.promotion_eligible!r}")
        ok = False
    else:
        print(f"{PASS} [D23-D] promotion_eligible=False (Slice 3 — no promotion yet)")

    # E — all required fields present in the serialised record
    REQUIRED_FIELDS = [
        "feedback_id", "proof_id", "action_id", "request_id",
        "session_id", "project_id", "feedback_type", "timestamp",
        "verification_status_at_feedback", "promotion_eligible", "message",
    ]
    d = record.to_dict()
    missing = [f for f in REQUIRED_FIELDS if f not in d]
    if missing:
        print(f"{FAIL} [D23-E] Missing required fields: {missing}")
        ok = False
    else:
        print(f"{PASS} [D23-E] All 11 required fields present in FeedbackRecord")

    return ok


# ── SECTION D24: Invalid reference rejected ───────────────────────────────────

def run_invalid_reference_checks() -> bool:
    print("\n=== Section D24: Invalid proof/action reference rejected ===")
    ok = True

    from rag.feedback import create_feedback, FeedbackValidationError
    from rag.bridge_errors import BridgeErrorCode

    # A — neither proof_id nor action_id → FEEDBACK_NO_REFERENCE
    raised = False
    try:
        create_feedback("KEEP", proof_id="", action_id="")
    except FeedbackValidationError as fve:
        raised = True
        if fve.bridge_error_code != BridgeErrorCode.FEEDBACK_NO_REFERENCE:
            print(f"{FAIL} [D24-A] Expected FEEDBACK_NO_REFERENCE, "
                  f"got {fve.bridge_error_code!r}")
            ok = False
        else:
            print(f"{PASS} [D24-A] Empty references → FEEDBACK_NO_REFERENCE")
    except Exception as exc:
        print(f"{FAIL} [D24-A] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
    if not raised:
        print(f"{FAIL} [D24-A] FeedbackValidationError not raised for empty references")
        ok = False

    # B — non-existent proof_id → FEEDBACK_PROOF_NOT_FOUND
    fake_proof_id = "nonexistent_proof_" + uuid.uuid4().hex[:8]
    raised = False
    try:
        create_feedback("KEEP", proof_id=fake_proof_id)
    except FeedbackValidationError as fve:
        raised = True
        if fve.bridge_error_code != BridgeErrorCode.FEEDBACK_PROOF_NOT_FOUND:
            print(f"{FAIL} [D24-B] Expected FEEDBACK_PROOF_NOT_FOUND, "
                  f"got {fve.bridge_error_code!r}")
            ok = False
        else:
            print(f"{PASS} [D24-B] Unknown proof_id → FEEDBACK_PROOF_NOT_FOUND")
    except Exception as exc:
        print(f"{FAIL} [D24-B] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
    if not raised:
        print(f"{FAIL} [D24-B] FeedbackValidationError not raised for unknown proof_id")
        ok = False

    # C — non-existent action_id (no proof_id supplied) → FEEDBACK_ACTION_NOT_FOUND
    fake_action_id = "nonexistent_act_" + uuid.uuid4().hex[:8]
    raised = False
    try:
        create_feedback("UNDO", action_id=fake_action_id)
    except FeedbackValidationError as fve:
        raised = True
        if fve.bridge_error_code != BridgeErrorCode.FEEDBACK_ACTION_NOT_FOUND:
            print(f"{FAIL} [D24-C] Expected FEEDBACK_ACTION_NOT_FOUND, "
                  f"got {fve.bridge_error_code!r}")
            ok = False
        else:
            print(f"{PASS} [D24-C] Unknown action_id → FEEDBACK_ACTION_NOT_FOUND")
    except Exception as exc:
        print(f"{FAIL} [D24-C] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
    if not raised:
        print(f"{FAIL} [D24-C] FeedbackValidationError not raised for unknown action_id")
        ok = False

    return ok


# ── SECTION D25: Invalid feedback_type rejected ───────────────────────────────

def run_invalid_feedback_type_checks() -> bool:
    print("\n=== Section D25: Invalid feedback_type rejected ===")
    ok = True

    from rag.feedback import create_feedback, FeedbackValidationError
    from rag.bridge_errors import BridgeErrorCode

    proof = _make_proof("VERIFIED")

    # A — unknown type "GREAT" → FEEDBACK_INVALID_TYPE
    raised = False
    try:
        create_feedback("GREAT", proof_id=proof.proof_id)
    except FeedbackValidationError as fve:
        raised = True
        if fve.bridge_error_code != BridgeErrorCode.FEEDBACK_INVALID_TYPE:
            print(f"{FAIL} [D25-A] Expected FEEDBACK_INVALID_TYPE, "
                  f"got {fve.bridge_error_code!r}")
            ok = False
        else:
            print(f"{PASS} [D25-A] Unknown type 'GREAT' → FEEDBACK_INVALID_TYPE")
    except Exception as exc:
        print(f"{FAIL} [D25-A] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
    if not raised:
        print(f"{FAIL} [D25-A] FeedbackValidationError not raised for unknown type")
        ok = False

    # B — empty string → FEEDBACK_INVALID_TYPE
    raised = False
    try:
        create_feedback("", proof_id=proof.proof_id)
    except FeedbackValidationError as fve:
        raised = True
        if fve.bridge_error_code != BridgeErrorCode.FEEDBACK_INVALID_TYPE:
            print(f"{FAIL} [D25-B] Expected FEEDBACK_INVALID_TYPE for empty type, "
                  f"got {fve.bridge_error_code!r}")
            ok = False
        else:
            print(f"{PASS} [D25-B] Empty type string → FEEDBACK_INVALID_TYPE")
    except Exception as exc:
        print(f"{FAIL} [D25-B] Wrong exception: {type(exc).__name__}: {exc}")
        ok = False
    if not raised:
        print(f"{FAIL} [D25-B] FeedbackValidationError not raised for empty type")
        ok = False

    # C — valid types accepted: spot-check all five
    valid_types_ok = True
    from rag.feedback import ALLOWED_FEEDBACK_TYPES
    for ft in sorted(ALLOWED_FEEDBACK_TYPES):
        try:
            r = create_feedback(ft, proof_id=proof.proof_id,
                                message=f"D25-C spot-check {ft}")
            if r.feedback_type != ft:
                valid_types_ok = False
        except Exception as exc:
            print(f"{FAIL} [D25-C] Valid type {ft!r} raised: {exc}")
            ok = False
            valid_types_ok = False
            break
    if valid_types_ok:
        print(f"{PASS} [D25-C] All 5 valid feedback types accepted: "
              f"{sorted(ALLOWED_FEEDBACK_TYPES)}")

    return ok


# ── SECTION D26: Feedback links to correct proof ──────────────────────────────

def run_feedback_linkage_checks() -> bool:
    print("\n=== Section D26: Feedback links to correct proof — vstat populated ===")
    ok = True

    from rag.feedback import create_feedback

    # Create a proof with a known vstat
    proof = _make_proof("VERIFIED")

    record = create_feedback(
        "KEEP",
        proof_id   = proof.proof_id,
        session_id = "sess_d26",
        message    = "D26 linkage test",
    )

    # A — feedback.proof_id matches the proof we referenced
    if record.proof_id != proof.proof_id:
        print(f"{FAIL} [D26-A] proof_id mismatch: "
              f"feedback={record.proof_id!r} vs proof={proof.proof_id!r}")
        ok = False
    else:
        print(f"{PASS} [D26-A] feedback.proof_id == referenced proof.proof_id")

    # B — feedback.action_id populated from the proof record
    if not record.action_id:
        print(f"{FAIL} [D26-B] action_id should be populated from proof, got empty")
        ok = False
    elif record.action_id != proof.action_id:
        print(f"{FAIL} [D26-B] action_id mismatch: "
              f"feedback={record.action_id!r} vs proof={proof.action_id!r}")
        ok = False
    else:
        print(f"{PASS} [D26-B] feedback.action_id resolved from proof record")

    # C — verification_status_at_feedback matches proof's vstat
    if record.verification_status_at_feedback != "VERIFIED":
        print(f"{FAIL} [D26-C] verification_status_at_feedback should be 'VERIFIED', "
              f"got {record.verification_status_at_feedback!r}")
        ok = False
    else:
        print(f"{PASS} [D26-C] verification_status_at_feedback='VERIFIED' "
              f"(from proof record)")

    # D — feedback round-trips correctly through JSONL
    from rag.feedback import read_last_feedback
    last = read_last_feedback()
    if last is None or last.get("feedback_id") != record.feedback_id:
        print(f"{FAIL} [D26-D] JSONL round-trip failed: "
              f"last={last.get('feedback_id') if last else None!r}")
        ok = False
    elif last.get("verification_status_at_feedback") != "VERIFIED":
        print(f"{FAIL} [D26-D] verification_status_at_feedback not persisted: "
              f"{last.get('verification_status_at_feedback')!r}")
        ok = False
    else:
        print(f"{PASS} [D26-D] Feedback with vstat persists correctly in JSONL")

    return ok


# ── SECTION D27: FAILED/UNVERIFIED/VERIFIED all stored; promotion_eligible=F ──

def run_promotion_eligible_checks() -> bool:
    print("\n=== Section D27: All vstats stored; promotion_eligible always False ===")
    ok = True

    from rag.feedback import create_feedback

    for vstat in ("VERIFIED", "FAILED", "UNVERIFIED"):
        proof = _make_proof(vstat)
        record = create_feedback(
            "UNDO",
            proof_id  = proof.proof_id,
            message   = f"D27 test for vstat={vstat}",
        )
        label = f"D27-{vstat[0]}"   # D27-V, D27-F, D27-U

        if record.verification_status_at_feedback != vstat:
            print(f"{FAIL} [{label}] vstat_at_feedback wrong: "
                  f"got {record.verification_status_at_feedback!r}, "
                  f"expected {vstat!r}")
            ok = False
        elif record.promotion_eligible is not False:
            print(f"{FAIL} [{label}] promotion_eligible should be False for {vstat}, "
                  f"got {record.promotion_eligible!r}")
            ok = False
        else:
            print(f"{PASS} [{label}] {vstat} proof feedback stored; "
                  f"promotion_eligible=False")

    return ok


# ── SECTION D28: No ChromaDB write; log paths separate from Phase C ───────────

def run_isolation_checks() -> bool:
    print("\n=== Section D28: No ChromaDB write; logs separate from Phase C ===")
    ok = True

    # A — feedback.py does not import chromadb
    feedback_src = os.path.join(_ROOT, "rag", "feedback.py")
    try:
        with open(feedback_src, "r", encoding="utf-8") as f:
            content = f.read()
        if "import chromadb" in content or "from chromadb" in content:
            print(f"{FAIL} [D28-A] feedback.py imports chromadb — must not write to ChromaDB")
            ok = False
        else:
            print(f"{PASS} [D28-A] feedback.py does not import chromadb")
    except Exception as exc:
        print(f"{FAIL} [D28-A] Could not read feedback.py: {exc}")
        ok = False

    # B — feedback.py does not import from context_pack_builder or Phase C modules
    phase_c_imports = [
        "context_pack_builder", "context_pack_logger",
        "corrective_check", "routed_retriever",
    ]
    for mod in phase_c_imports:
        if mod in content:
            print(f"{FAIL} [D28-B] feedback.py references Phase C module: {mod!r}")
            ok = False
            break
    else:
        print(f"{PASS} [D28-B] feedback.py has no Phase C imports")

    # C — FEEDBACK_LOG_PATH is feedback_log.jsonl (not any other log)
    from rag.feedback import FEEDBACK_LOG_PATH
    from rag.action_proof import PROOF_LOG_PATH
    from rag.black_box_log import BBL_LOG_PATH
    try:
        from rag.context_pack_logger import LOG_PATH as PHASE_C_LOG_PATH
    except ImportError:
        PHASE_C_LOG_PATH = None

    fb_name = os.path.basename(FEEDBACK_LOG_PATH)
    if fb_name != "feedback_log.jsonl":
        print(f"{FAIL} [D28-C] FEEDBACK_LOG_PATH should be feedback_log.jsonl, "
              f"got: {fb_name}")
        ok = False
    elif FEEDBACK_LOG_PATH == PROOF_LOG_PATH:
        print(f"{FAIL} [D28-C] FEEDBACK_LOG_PATH must differ from PROOF_LOG_PATH")
        ok = False
    elif FEEDBACK_LOG_PATH == BBL_LOG_PATH:
        print(f"{FAIL} [D28-C] FEEDBACK_LOG_PATH must differ from BBL_LOG_PATH")
        ok = False
    elif PHASE_C_LOG_PATH and FEEDBACK_LOG_PATH == PHASE_C_LOG_PATH:
        print(f"{FAIL} [D28-C] FEEDBACK_LOG_PATH must differ from Phase C log path")
        ok = False
    else:
        print(f"{PASS} [D28-C] feedback_log.jsonl is separate from all other Phase D/C logs")

    # D — FeedbackValidationError carries bridge_error_code from BridgeErrorCode enum
    from rag.feedback import FeedbackValidationError
    from rag.bridge_errors import BridgeErrorCode
    try:
        create_feedback = __import__("rag.feedback", fromlist=["create_feedback"]).create_feedback
        create_feedback("KEEP", proof_id="", action_id="")
    except FeedbackValidationError as fve:
        if not isinstance(fve.bridge_error_code, BridgeErrorCode):
            print(f"{FAIL} [D28-D] bridge_error_code should be BridgeErrorCode enum, "
                  f"got {type(fve.bridge_error_code)}")
            ok = False
        else:
            print(f"{PASS} [D28-D] FeedbackValidationError carries BridgeErrorCode enum")
    except Exception as exc:
        print(f"{FAIL} [D28-D] Unexpected exception: {type(exc).__name__}: {exc}")
        ok = False

    return ok


# ── SECTION D29: Slice 1 + Slice 2 regressions ───────────────────────────────

def run_slice_regression_check() -> bool:
    print("\n=== Section D29: Slice 1 + Slice 2 regressions ===")

    for label, script_name in [
        ("Slice 1", "phase_d_slice1_eval.py"),
        ("Slice 2", "phase_d_slice2_eval.py"),
    ]:
        script = os.path.join(_ROOT, "tests", script_name)
        if not os.path.exists(script):
            print(f"{SKIP} [D29] {script_name} not found — skipped")
            continue
        try:
            result = subprocess.run(
                [sys.executable, script],
                capture_output=True, text=True, timeout=300,
                cwd=_ROOT,
            )
            if result.returncode != 0:
                print(f"{FAIL} [D29] {script_name} FAILED:")
                lines = (result.stdout + result.stderr).strip().splitlines()
                for line in lines[-15:]:
                    print(f"       {line}")
                return False
        except subprocess.TimeoutExpired:
            print(f"{FAIL} [D29] {script_name} timed out")
            return False
        except Exception as exc:
            print(f"{FAIL} [D29] Failed to run {script_name}: {exc}")
            return False

    print(f"{PASS} [D29] Slice 1 + Slice 2 eval suites pass (Slice 1+2 unchanged)")
    return True


# ── SECTION D30: Phase C eval regression ─────────────────────────────────────

def run_phase_c_regression_check() -> bool:
    print("\n=== Section D30: Phase C eval regression ===")

    script = os.path.join(_ROOT, "tests", "phase_c_eval_set.py")
    if not os.path.exists(script):
        print(f"{SKIP} [D30] phase_c_eval_set.py not found — skipped")
        return True

    try:
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True, timeout=120,
            cwd=_ROOT,
        )
        if result.returncode == 0:
            print(f"{PASS} [D30] phase_c_eval_set.py passed (Phase A/B/C unchanged)")
            return True
        else:
            print(f"{FAIL} [D30] phase_c_eval_set.py FAILED:")
            lines = (result.stdout + result.stderr).strip().splitlines()
            for line in lines[-15:]:
                print(f"       {line}")
            return False
    except subprocess.TimeoutExpired:
        print(f"{FAIL} [D30] phase_c_eval_set.py timed out")
        return False
    except Exception as exc:
        print(f"{FAIL} [D30] Failed to run phase_c_eval_set.py: {exc}")
        return False


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Conductor — Phase D Slice 3 Eval Suite")
    print("=" * 60)

    t0 = time.time()

    d23_ok = run_valid_feedback_checks()
    d24_ok = run_invalid_reference_checks()
    d25_ok = run_invalid_feedback_type_checks()
    d26_ok = run_feedback_linkage_checks()
    d27_ok = run_promotion_eligible_checks()
    d28_ok = run_isolation_checks()
    d29_ok = run_slice_regression_check()
    d30_ok = run_phase_c_regression_check()

    elapsed = time.time() - t0

    all_pass = all([
        d23_ok, d24_ok, d25_ok, d26_ok,
        d27_ok, d28_ok, d29_ok, d30_ok,
    ])

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    results = [
        ("D23  Valid feedback writes JSONL (5 checks)",              d23_ok),
        ("D24  Invalid reference rejected (3 checks)",               d24_ok),
        ("D25  Invalid feedback_type rejected (3 checks)",           d25_ok),
        ("D26  Feedback links to correct proof (4 checks)",          d26_ok),
        ("D27  All vstats stored; promotion_eligible=False (3 chk)", d27_ok),
        ("D28  No ChromaDB; logs separate from Phase C (4 checks)",  d28_ok),
        ("D29  Slice 1+2 regressions",                               d29_ok),
        ("D30  Phase C regression",                                   d30_ok),
    ]
    for label, passed in results:
        icon = PASS if passed else FAIL
        print(f"  {icon}  {label}")

    print(f"\n  {'ALL PASS' if all_pass else 'FAILURES DETECTED'}  ({elapsed:.1f}s)")
    print("=" * 60)

    sys.exit(0 if all_pass else 1)
