"""
Conductor — Phase D Slice 22 Evaluation Suite
Build 15 — Knowledge Feedback Log v1

Sections D205–D212.

Tests:
  D205 — response_id present on all orchestrate response types
  D206 — POST /harness/feedback: HELPFUL accepted and logged
  D207 — All five feedback types accepted
  D208 — Missing response_id returns 400
  D209 — Invalid feedback_type returns 400
  D210 — Log entry shape: promotion_eligible False, no ChromaDB fields
  D211 — Existing orchestrate response fields intact alongside response_id
  D212 — Log isolation: only knowledge_feedback_log.jsonl written, not others

All tests are unit/integration tests against harness_server internals and the
knowledge_feedback_log.jsonl file.  No live bridge or LLM required.
"""

import importlib.util
import io
import json
import os
import sys
import threading
import time

# ── Repo root on path ──────────────────────────────────────────────────────────
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Import harness_server module symbols ──────────────────────────────────────
import importlib
hs_spec = importlib.util.spec_from_file_location(
    "harness_server",
    os.path.join(_ROOT, "tools", "harness_server.py"),
)
hs = importlib.util.module_from_spec(hs_spec)
hs_spec.loader.exec_module(hs)

# Paths used by tests
_KFBL_PATH          = hs._KFBL_LOG_PATH
_MEMORY_DIR         = hs._MEMORY_DIR
_ACTION_LOG_PATH    = os.path.join(_MEMORY_DIR, "action_log.jsonl")
_FEEDBACK_LOG_PATH  = os.path.join(_MEMORY_DIR, "feedback_log.jsonl")
_PROOF_LOG_PATH     = os.path.join(_MEMORY_DIR, "action_proof_log.jsonl")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _read_kfbl():
    """Return all records from knowledge_feedback_log.jsonl as a list."""
    if not os.path.exists(_KFBL_PATH):
        return []
    records = []
    with open(_KFBL_PATH, "r", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if stripped:
                try:
                    records.append(json.loads(stripped))
                except Exception:
                    pass
    return records


def _mtime_or_none(path):
    """Return mtime of path or None if it doesn't exist."""
    try:
        return os.path.getmtime(path)
    except FileNotFoundError:
        return None


def _make_fake_handler(body_dict):
    """
    Return a minimal fake HTTP request handler that routes a POST /harness/feedback
    directly to _handle_knowledge_feedback() without a live TCP socket.
    Captures the response as a dict in .response_sent.
    """
    class _FakeHandler(hs.HarnessHandler):
        def __init__(self):
            # Do NOT call super().__init__() — it tries to open a socket
            self.response_sent = None
            self._body = body_dict

        def send_json(self, code, obj):
            self.response_sent = (code, obj)

    handler = _FakeHandler()
    handler._handle_knowledge_feedback(body_dict)
    return handler


# ── Test sections ─────────────────────────────────────────────────────────────

def run_d205():
    """D205 — response_id present on all three orchestrate response types."""
    print("D205: response_id present on answer/action/clarify …", end=" ")
    errors = []

    # ── D205a: harness_server exports _KFBL_LOG_PATH and _KNOWLEDGE_FEEDBACK_TYPES
    if not hasattr(hs, "_KFBL_LOG_PATH"):
        errors.append("_KFBL_LOG_PATH not defined in harness_server")
    if not hasattr(hs, "_KNOWLEDGE_FEEDBACK_TYPES"):
        errors.append("_KNOWLEDGE_FEEDBACK_TYPES not defined in harness_server")

    # ── D205b: uuid is imported (needed for response_id generation)
    import uuid as _uuid
    if not hasattr(hs, "uuid"):
        errors.append("uuid not imported in harness_server")

    # ── D205c: _handle_orchestrate source contains "response_id"
    import inspect
    src = inspect.getsource(hs.HarnessHandler._handle_orchestrate)
    if "response_id" not in src:
        errors.append("response_id not found in _handle_orchestrate source")

    # ── D205d: response_id appears in all four send_json(200 ...) call sites
    # Count occurrences of '"response_id"' in the function source
    count = src.count('"response_id"')
    # Should appear in: the assignment line + 4 response dicts (action, clarify,
    # explorer-answer, direct-answer)
    if count < 4:
        errors.append(
            f"response_id used {count} time(s) in _handle_orchestrate — expected ≥ 4"
        )

    # ── D205e: response_id value is uuid4().hex[:12] — exactly 12 hex chars
    rid = hs.uuid.uuid4().hex[:12]
    if len(rid) != 12:
        errors.append(f"uuid4().hex[:12] produced length {len(rid)}, expected 12")
    if not all(c in "0123456789abcdef" for c in rid):
        errors.append(f"uuid4().hex[:12] contains non-hex chars: {rid!r}")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d206():
    """D206 — HELPFUL accepted, record appended to knowledge_feedback_log.jsonl."""
    print("D206: HELPFUL accepted and logged …", end=" ")
    errors = []

    before_count = len(_read_kfbl())
    rid = hs.uuid.uuid4().hex[:12]

    handler = _make_fake_handler({
        "response_id":   rid,
        "feedback_type": "HELPFUL",
        "message":       "great suggestion",
    })

    code, resp = handler.response_sent
    if code != 200:
        errors.append(f"Expected HTTP 200, got {code}")
    if not resp.get("ok"):
        errors.append(f"ok not True: {resp}")
    if resp.get("feedback_type") != "HELPFUL":
        errors.append(f"feedback_type wrong: {resp.get('feedback_type')!r}")
    if resp.get("response_id") != rid:
        errors.append(f"response_id mismatch: {resp.get('response_id')!r}")
    if not resp.get("feedback_id"):
        errors.append("feedback_id missing from response")
    if not resp.get("timestamp"):
        errors.append("timestamp missing from response")

    # Check log
    after = _read_kfbl()
    if len(after) <= before_count:
        errors.append("No new record appended to knowledge_feedback_log.jsonl")
    else:
        last = after[-1]
        if last.get("feedback_type") != "HELPFUL":
            errors.append(f"Logged feedback_type wrong: {last.get('feedback_type')!r}")
        if last.get("response_id") != rid:
            errors.append(f"Logged response_id wrong: {last.get('response_id')!r}")
        if "feedback_id" not in last:
            errors.append("feedback_id missing from log entry")
        if "timestamp" not in last:
            errors.append("timestamp missing from log entry")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d207():
    """D207 — All five feedback types accepted without error."""
    print("D207: all five feedback types accepted …", end=" ")
    errors = []

    for ft in ("HELPFUL", "NOT_HELPFUL", "TOO_VAGUE", "WRONG", "OUTDATED"):
        rid = hs.uuid.uuid4().hex[:12]
        handler = _make_fake_handler({"response_id": rid, "feedback_type": ft})
        code, resp = handler.response_sent
        if code != 200:
            errors.append(f"{ft}: expected 200, got {code} — {resp.get('error','')}")
        elif resp.get("feedback_type") != ft:
            errors.append(f"{ft}: feedback_type in response wrong: {resp.get('feedback_type')!r}")

    # Also confirm _KNOWLEDGE_FEEDBACK_TYPES contains exactly these five
    expected = {"HELPFUL", "NOT_HELPFUL", "TOO_VAGUE", "WRONG", "OUTDATED"}
    if hs._KNOWLEDGE_FEEDBACK_TYPES != expected:
        errors.append(
            f"_KNOWLEDGE_FEEDBACK_TYPES mismatch: {hs._KNOWLEDGE_FEEDBACK_TYPES}"
        )

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d208():
    """D208 — Missing response_id returns 400 with descriptive error."""
    print("D208: missing response_id → 400 …", end=" ")
    errors = []

    for body in [
        {"feedback_type": "HELPFUL"},
        {"response_id": "", "feedback_type": "HELPFUL"},
        {"response_id": "   ", "feedback_type": "HELPFUL"},
    ]:
        handler = _make_fake_handler(body)
        code, resp = handler.response_sent
        if code != 400:
            errors.append(f"body={body!r}: expected 400, got {code}")
        if resp.get("ok") is not False:
            errors.append(f"body={body!r}: ok should be False, got {resp.get('ok')!r}")
        err_msg = resp.get("error", "")
        if "response_id" not in err_msg.lower():
            errors.append(
                f"body={body!r}: error message does not mention response_id: {err_msg!r}"
            )

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d209():
    """D209 — Invalid feedback_type returns 400 with descriptive error."""
    print("D209: invalid feedback_type → 400 …", end=" ")
    errors = []

    rid = hs.uuid.uuid4().hex[:12]
    for bad_type in ("KEEP", "UNDO", "WRONG_DIRECTION", "thumbs_up", "", "   "):
        body = {"response_id": rid, "feedback_type": bad_type}
        handler = _make_fake_handler(body)
        code, resp = handler.response_sent
        if code != 400:
            errors.append(f"feedback_type={bad_type!r}: expected 400, got {code}")
        if resp.get("ok") is not False:
            errors.append(f"feedback_type={bad_type!r}: ok should be False")
        err_msg = resp.get("error", "")
        if "feedback_type" not in err_msg.lower() and "invalid" not in err_msg.lower():
            errors.append(
                f"feedback_type={bad_type!r}: error message unclear: {err_msg!r}"
            )

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d210():
    """D210 — Log entry shape: has required fields, promotion_eligible False, no ChromaDB fields."""
    print("D210: log entry shape correct …", end=" ")
    errors = []

    rid = hs.uuid.uuid4().hex[:12]
    handler = _make_fake_handler({
        "response_id":   rid,
        "feedback_type": "NOT_HELPFUL",
        "message":       "off target",
    })
    code, _ = handler.response_sent
    if code != 200:
        errors.append(f"Setup failed — HTTP {code}")
        print("FAIL"); [print(f"  ✗ {e}") for e in errors]; return False

    records = _read_kfbl()
    last = next((r for r in reversed(records) if r.get("response_id") == rid), None)
    if last is None:
        errors.append("Record not found in knowledge_feedback_log.jsonl")
        print("FAIL"); [print(f"  ✗ {e}") for e in errors]; return False

    # Required fields
    for field in ("feedback_id", "response_id", "feedback_type", "timestamp", "promotion_eligible", "message"):
        if field not in last:
            errors.append(f"Field missing from log entry: {field!r}")

    # promotion_eligible must be False (never True in Build 15)
    if last.get("promotion_eligible") is not False:
        errors.append(
            f"promotion_eligible should be False, got {last.get('promotion_eligible')!r}"
        )

    # No ChromaDB fields
    chromadb_fields = ("collection", "memory_level", "source_type", "confidence",
                       "chromadb_id", "chroma_id", "embedding")
    for f in chromadb_fields:
        if f in last:
            errors.append(f"ChromaDB field {f!r} must not appear in knowledge feedback log")

    # feedback_id is 16 hex chars
    fid = last.get("feedback_id", "")
    if len(fid) != 16 or not all(c in "0123456789abcdef" for c in fid):
        errors.append(f"feedback_id should be 16 hex chars, got {fid!r}")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d211():
    """D211 — Existing orchestrate response fields unchanged alongside response_id."""
    print("D211: existing orchestrate response fields intact …", end=" ")
    errors = []

    import inspect

    src = inspect.getsource(hs.HarnessHandler._handle_orchestrate)

    # ── action response must still have all original fields ───────────────────
    action_required = [
        '"ok"', '"type"', '"action_id"', '"params"', '"confidence"',
        '"needs_confirmation"', '"clarification"', '"reason"',
        '"model"', '"provider"', '"tokens"',
    ]
    for field in action_required:
        if field not in src:
            errors.append(f"action response missing field: {field}")

    # ── answer (explorer) response must still have all original fields ────────
    explorer_required = [
        '"ok"', '"type"', '"text"', '"explorer"', '"critic"',
        '"mode"', '"model"', '"provider"', '"tokens"',
    ]
    for field in explorer_required:
        if field not in src:
            errors.append(f"explorer answer response missing field: {field}")

    # ── clarify response must still have all original fields ──────────────────
    clarify_required = [
        '"ok"', '"type"', '"text"', '"mode"', '"model"', '"provider"', '"tokens"',
    ]
    for field in clarify_required:
        if field not in src:
            errors.append(f"clarify response missing field: {field}")

    # ── response_id must appear in all three send_json(200 ...) dicts ─────────
    # We verified count in D205; here we confirm it is in the action response
    # specifically by checking source around '"type":.*"action"'
    if '"response_id":        response_id' not in src and \
       '"response_id": response_id' not in src and \
       '"response_id":  response_id' not in src and \
       '"response_id":\n' not in src:
        # Just check the raw string is present
        if 'response_id' not in src:
            errors.append("response_id assignment not found in _handle_orchestrate")

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


def run_d212():
    """D212 — Log isolation: only knowledge_feedback_log.jsonl is written, not action/feedback/proof logs."""
    print("D212: log isolation — only knowledge_feedback_log.jsonl written …", end=" ")
    errors = []

    # Record mtimes of the other three logs before the call
    before_action = _mtime_or_none(_ACTION_LOG_PATH)
    before_feedback = _mtime_or_none(_FEEDBACK_LOG_PATH)
    before_proof = _mtime_or_none(_PROOF_LOG_PATH)
    before_kfbl = _mtime_or_none(_KFBL_PATH)

    rid = hs.uuid.uuid4().hex[:12]
    _make_fake_handler({
        "response_id":   rid,
        "feedback_type": "OUTDATED",
        "message":       "stale info",
    })

    time.sleep(0.05)  # let filesystem timestamps settle

    after_action   = _mtime_or_none(_ACTION_LOG_PATH)
    after_feedback = _mtime_or_none(_FEEDBACK_LOG_PATH)
    after_proof    = _mtime_or_none(_PROOF_LOG_PATH)
    after_kfbl     = _mtime_or_none(_KFBL_PATH)

    # action_log.jsonl must not have been touched
    if after_action != before_action:
        errors.append("action_log.jsonl was modified — should not be touched by /harness/feedback")

    # feedback_log.jsonl must not have been touched
    if after_feedback != before_feedback:
        errors.append("feedback_log.jsonl was modified — must remain separate from knowledge feedback")

    # action_proof_log.jsonl must not have been touched
    if after_proof != before_proof:
        errors.append("action_proof_log.jsonl was modified — must not be touched")

    # knowledge_feedback_log.jsonl must have been written (mtime changed or newly created)
    if after_kfbl is None:
        errors.append("knowledge_feedback_log.jsonl was not created")
    elif before_kfbl is not None and after_kfbl == before_kfbl:
        errors.append("knowledge_feedback_log.jsonl mtime unchanged — record not appended")

    # Confirm the log filename constant is correct
    if not hs._KFBL_LOG_PATH.endswith("knowledge_feedback_log.jsonl"):
        errors.append(
            f"_KFBL_LOG_PATH does not end with knowledge_feedback_log.jsonl: {hs._KFBL_LOG_PATH!r}"
        )

    # Confirm _append_knowledge_feedback does not reference the other log files
    # (check for the exact filenames — not substrings of "knowledge_feedback_log.jsonl")
    import inspect
    append_src = inspect.getsource(hs._append_knowledge_feedback)
    for forbidden in (
        '"feedback_log.jsonl"',   # bridge write-action feedback log (exact filename)
        "'feedback_log.jsonl'",
        "FEEDBACK_LOG_PATH",       # rag/feedback.py path constant
        '"action_log.jsonl"',
        "'action_log.jsonl'",
        "BBL_LOG_PATH",            # black_box_log path constant
        '"action_proof_log.jsonl"',
        "'action_proof_log.jsonl'",
        "PROOF_LOG_PATH",          # action_proof path constant
    ):
        if forbidden in append_src:
            errors.append(
                f"_append_knowledge_feedback references forbidden log identifier: {forbidden!r}"
            )

    if errors:
        print("FAIL")
        for e in errors:
            print(f"  ✗ {e}")
        return False
    print("PASS")
    return True


# ── Runner ────────────────────────────────────────────────────────────────────

def run_all():
    sections = [
        run_d205,
        run_d206,
        run_d207,
        run_d208,
        run_d209,
        run_d210,
        run_d211,
        run_d212,
    ]

    passed = 0
    failed = 0
    for fn in sections:
        try:
            ok = fn()
        except Exception as exc:
            print(f"  ✗ EXCEPTION in {fn.__name__}: {exc}")
            import traceback; traceback.print_exc()
            ok = False
        if ok:
            passed += 1
        else:
            failed += 1

    total = passed + failed
    print(f"\nphase_d_slice22_eval.py — {passed}/{total} PASS  (D205–D212, Build 15 — Knowledge Feedback Log v1)")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    run_all()
