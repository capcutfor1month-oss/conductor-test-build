"""
Conductor — Phase D Slice 5 Eval Suite (D41–D50)
─────────────────────────────────────────────────
Never-do preflight enforcement: comprehensive decision table coverage,
context overrides, rule text matching, convenience wrappers, graceful
degradation, and regressions through Slice 4 + Phase C.

Run:
    python3 tests/phase_d_slice5_eval.py

All tests are offline — no Ableton connection required.
"""

import os
import sys
import subprocess
import tempfile
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "tools"))

PASS = "✅"
FAIL = "❌"


# ── SECTION D41: HARD_BLOCK action types ─────────────────────────────────────

def run_d41() -> bool:
    """All actions that must HARD_BLOCK unconditionally."""
    print("\n=== Section D41: HARD_BLOCK actions ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    # Note: DELETE_TRACK moved to REQUIRE_CONFIRMATION (Action Expansion Slice 1)
    hard_block_actions = [
        "DELETE_CLIP",
        "DELETE_DEVICE",
        "REMOVE_NOTES",
        "CLEAR_NOTES",
        "OVERWRITE_EXPORT",
    ]

    for action in hard_block_actions:
        decision, rule = check(action)
        if decision != NeverDoDecision.HARD_BLOCK:
            print(f"{FAIL} [D41] {action} should HARD_BLOCK, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D41] {action} → HARD_BLOCK")

    n = len(hard_block_actions)
    print(f"\n  D41 HARD_BLOCK table: {n if ok else '< '+str(n)} pass")
    return ok


# ── SECTION D42: REQUIRE_CONFIRMATION action types ───────────────────────────

def run_d42() -> bool:
    """All actions that must REQUIRE_CONFIRMATION unconditionally."""
    print("\n=== Section D42: REQUIRE_CONFIRMATION actions ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    confirm_actions = [
        "DELETE_TRACK",      # Moved from HARD_BLOCK — requires confirm=True in body
        "SET_TEMPO",
        "SET_KEY",
        "SET_SCALE",
        "WARP_AUDIO",
        "EXPORT_AUDIO",
        "EXPORT_STEMS",
        "BATCH_RENAME_TRACKS",
        "BATCH_MODIFY_TRACKS",
        "SET_OUTPUT_ROUTING",
        "SET_INPUT_ROUTING",
        "CHANGE_MONITOR_MODE",
        "SAVE_MEMORY",
        "PROMOTE_MEMORY",
    ]

    for action in confirm_actions:
        decision, rule = check(action)
        if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
            print(f"{FAIL} [D42] {action} should REQUIRE_CONFIRMATION, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D42] {action} → REQUIRE_CONFIRMATION")

    n = len(confirm_actions)
    print(f"\n  D42 REQUIRE_CONFIRMATION table: {n if ok else '< '+str(n)} pass")
    return ok


# ── SECTION D43: ALLOW action types ──────────────────────────────────────────

def run_d43() -> bool:
    """All safe mixer actions that must ALLOW (no context override)."""
    print("\n=== Section D43: ALLOW actions ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    allow_cases = [
        ("SET_TRACK_VOLUME", {"target": "Kick"}),
        ("SET_TRACK_PAN",    {"target": "Snare"}),
        ("SET_TRACK_MUTE",   {"target": "Hi-Hat"}),
        ("SET_TRACK_SOLO",   {"target": "Lead Vox"}),
        ("SET_SEND_LEVEL",   {"target": "Reverb"}),
        ("SET_PLUGIN_PARAM", {"target": "Compressor", "plugin": "compressor"}),
        ("ARM_TRACK",        {"target": "Vocals"}),
        ("RENAME_TRACK",     {"target": "Guitar"}),
    ]

    for action, ctx in allow_cases:
        decision, rule = check(action, ctx)
        if decision != NeverDoDecision.ALLOW:
            print(f"{FAIL} [D43] {action}({ctx.get('target')}) should ALLOW, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D43] {action}({ctx.get('target')}) → ALLOW")

    n = len(allow_cases)
    print(f"\n  D43 ALLOW table: {n if ok else '< '+str(n)} pass")
    return ok


# ── SECTION D44: UNDO_LOG_REQUIRED action types ───────────────────────────────

def run_d44() -> bool:
    """Actions requiring prior_state capture (UNDO_LOG_REQUIRED)."""
    print("\n=== Section D44: UNDO_LOG_REQUIRED actions ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    undo_log_actions = [
        "MODIFY_MASTER_BUS",
        "ADD_MASTER_DEVICE",
        "REMOVE_MASTER_DEVICE",
        "APPLY_MASTER_PROCESSING",
    ]

    for action in undo_log_actions:
        decision, rule = check(action)
        if decision != NeverDoDecision.UNDO_LOG_REQUIRED:
            print(f"{FAIL} [D44] {action} should UNDO_LOG_REQUIRED, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D44] {action} → UNDO_LOG_REQUIRED")

    n = len(undo_log_actions)
    print(f"\n  D44 UNDO_LOG_REQUIRED table: {n if ok else '< '+str(n)} pass")
    return ok


# ── SECTION D45: Context overrides ───────────────────────────────────────────

def run_d45() -> bool:
    """
    Context-based escalation:
      - Master bus targeting escalates ALLOW → HARD_BLOCK
      - REQUIRE_CONFIRMATION targeting master → HARD_BLOCK
      - Batch threshold: track_count ≤ 3 = ALLOW, ≥ 4 = REQUIRE_CONFIRMATION
      - EQ cut below -6 dB on EQ plugin → REQUIRE_CONFIRMATION
      - EQ cut on non-EQ plugin → unescalated
    """
    print("\n=== Section D45: Context overrides ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    # ── Master bus variants ───────────────────────────────────────────────────
    master_cases = [
        ("SET_TRACK_VOLUME", {"target": "master"},          "master (lowercase)"),
        ("SET_TRACK_VOLUME", {"target": "Master Bus"},      "'Master Bus'"),
        ("SET_TRACK_VOLUME", {"target": "master_bus"},      "'master_bus'"),
        ("SET_TRACK_VOLUME", {"target": "1/2"},             "'1/2' (Ableton routing)"),
        ("SET_TRACK_VOLUME", {"track_name": "Master"},      "track_name=Master alias"),
        ("SET_TRACK_PAN",    {"target": "master"},          "pan targeting master"),
        ("SET_TRACK_MUTE",   {"target": "Master Bus"},      "mute targeting master bus"),
    ]
    for action, ctx, label in master_cases:
        decision, rule = check(action, ctx)
        if decision != NeverDoDecision.HARD_BLOCK:
            print(f"{FAIL} [D45] Master override ({label}): expected HARD_BLOCK, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D45] Master override ({label}) → HARD_BLOCK")

    # ── Batch threshold boundary ──────────────────────────────────────────────
    # 3 tracks → ALLOW (at threshold — not over)
    decision, _ = check("SET_TRACK_VOLUME", {"target": "Kick", "track_count": 3})
    if decision != NeverDoDecision.ALLOW:
        print(f"{FAIL} [D45] track_count=3 should stay ALLOW, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D45] Batch boundary: track_count=3 → ALLOW (at threshold)")

    # 4 tracks → REQUIRE_CONFIRMATION (one over threshold)
    decision, rule = check("SET_TRACK_VOLUME", {"target": "Kick", "track_count": 4})
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D45] track_count=4 should be REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D45] Batch boundary: track_count=4 → REQUIRE_CONFIRMATION")

    # ── EQ cut threshold ──────────────────────────────────────────────────────
    # Deep cut on EQ plugin → REQUIRE_CONFIRMATION
    decision, rule = check("SET_PLUGIN_PARAM",
                           {"target": "Vocal Bus", "plugin": "Pro-Q 4", "value": -7.0})
    if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
        print(f"{FAIL} [D45] Pro-Q 4 cut -7dB should REQUIRE_CONFIRMATION, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D45] EQ cut -7dB (Pro-Q 4) → REQUIRE_CONFIRMATION")

    # Just above threshold → ALLOW
    decision, _ = check("SET_PLUGIN_PARAM",
                        {"target": "Vocal Bus", "plugin": "eq eight", "value": -5.9})
    if decision != NeverDoDecision.ALLOW:
        print(f"{FAIL} [D45] EQ cut -5.9dB should stay ALLOW, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D45] EQ cut -5.9dB (just above threshold) → ALLOW")

    # Deep cut but not an EQ plugin → ALLOW (no escalation)
    decision, _ = check("SET_PLUGIN_PARAM",
                        {"target": "Kick Bus", "plugin": "compressor", "value": -7.0})
    if decision != NeverDoDecision.ALLOW:
        print(f"{FAIL} [D45] Non-EQ plugin deep cut should stay ALLOW, got {decision}")
        ok = False
    else:
        print(f"{PASS} [D45] Deep cut on non-EQ plugin (compressor) → ALLOW (no escalation)")

    # EQ plugin alias variants
    for alias in ["proq", "pro q", "fabfilter", "equalizer"]:
        decision, _ = check("SET_PLUGIN_PARAM",
                            {"target": "Track", "plugin": alias, "value": -8.0})
        if decision != NeverDoDecision.REQUIRE_CONFIRMATION:
            print(f"{FAIL} [D45] EQ alias '{alias}' cut -8dB should REQUIRE_CONFIRMATION, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D45] EQ alias '{alias}' cut -8dB → REQUIRE_CONFIRMATION")

    print(f"\n  D45 context overrides: {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D46: Rule text matching ──────────────────────────────────────────

def run_d46() -> bool:
    """
    Rule text:
      - HARD_BLOCK actions return non-empty rule_text (matched from file or
        from override description)
      - ALLOW on normal track returns "" (no matching rule)
      - Context override always returns non-empty rule_text
    """
    print("\n=== Section D46: Rule text returned from check() ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    # A — HARD_BLOCK action returns non-empty rule_text
    _, rule = check("DELETE_TRACK")
    if not rule:
        print(f"{FAIL} [D46-A] DELETE_TRACK should return non-empty rule_text, got {rule!r}")
        ok = False
    else:
        print(f"{PASS} [D46-A] DELETE_TRACK → rule_text: {rule[:60]!r}")

    # B — ALLOW on normal track returns ""
    _, rule = check("SET_TRACK_VOLUME", {"target": "Kick"})
    if rule != "":
        print(f"{FAIL} [D46-B] SET_TRACK_VOLUME(Kick) should return rule_text='', got {rule!r}")
        ok = False
    else:
        print(f"{PASS} [D46-B] SET_TRACK_VOLUME normal track → rule_text=''")

    # C — context override (master bus) returns non-empty rule_text
    _, rule = check("SET_TRACK_VOLUME", {"target": "master"})
    if not rule:
        print(f"{FAIL} [D46-C] Master override should return non-empty rule_text")
        ok = False
    else:
        print(f"{PASS} [D46-C] Master override → rule_text: {rule[:60]!r}")

    # D — REQUIRE_CONFIRMATION action returns rule text or empty (file match best-effort)
    _, rule = check("DELETE_CLIP")
    if not rule:
        print(f"{FAIL} [D46-D] DELETE_CLIP should return non-empty rule_text, got {rule!r}")
        ok = False
    else:
        print(f"{PASS} [D46-D] DELETE_CLIP → rule_text: {rule[:60]!r}")

    # E — context batch override rule_text contains track count
    _, rule = check("SET_TRACK_VOLUME", {"target": "Kick", "track_count": 5})
    if "5" not in rule and "3" not in rule:
        print(f"{FAIL} [D46-E] Batch override rule_text should mention count, got: {rule!r}")
        ok = False
    else:
        print(f"{PASS} [D46-E] Batch override rule_text includes track threshold: {rule[:60]!r}")

    print(f"\n  D46 rule text: {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D47: Convenience wrappers ────────────────────────────────────────

def run_d47() -> bool:
    """check_allows() and is_hard_block() convenience functions."""
    print("\n=== Section D47: Convenience wrappers ===")
    ok = True

    from rag.never_do_check import (
        check_allows, is_hard_block, NeverDoDecision, _clear_rules_cache
    )
    _clear_rules_cache()

    # A — check_allows: ALLOW → True
    if not check_allows("SET_TRACK_VOLUME", {"target": "Kick"}):
        print(f"{FAIL} [D47-A] check_allows(SET_TRACK_VOLUME, Kick) should be True")
        ok = False
    else:
        print(f"{PASS} [D47-A] check_allows(SET_TRACK_VOLUME, Kick) → True")

    # B — check_allows: HARD_BLOCK → False
    if check_allows("DELETE_TRACK"):
        print(f"{FAIL} [D47-B] check_allows(DELETE_TRACK) should be False")
        ok = False
    else:
        print(f"{PASS} [D47-B] check_allows(DELETE_TRACK) → False")

    # C — check_allows: REQUIRE_CONFIRMATION → False
    if check_allows("SET_TEMPO"):
        print(f"{FAIL} [D47-C] check_allows(SET_TEMPO) should be False")
        ok = False
    else:
        print(f"{PASS} [D47-C] check_allows(SET_TEMPO) → False")

    # D — is_hard_block: HARD_BLOCK → True
    if not is_hard_block("DELETE_CLIP"):
        print(f"{FAIL} [D47-D] is_hard_block(DELETE_CLIP) should be True")
        ok = False
    else:
        print(f"{PASS} [D47-D] is_hard_block(DELETE_CLIP) → True")

    # E — is_hard_block: ALLOW → False
    if is_hard_block("SET_TRACK_PAN", {"target": "Snare"}):
        print(f"{FAIL} [D47-E] is_hard_block(SET_TRACK_PAN, Snare) should be False")
        ok = False
    else:
        print(f"{PASS} [D47-E] is_hard_block(SET_TRACK_PAN, Snare) → False")

    # F — is_hard_block: master context escalation → True
    if not is_hard_block("SET_TRACK_VOLUME", {"target": "master"}):
        print(f"{FAIL} [D47-F] is_hard_block(SET_TRACK_VOLUME, master) should be True")
        ok = False
    else:
        print(f"{PASS} [D47-F] is_hard_block(SET_TRACK_VOLUME, master) → True (context escalated)")

    print(f"\n  D47 convenience wrappers: {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D48: Case-insensitive lookup ──────────────────────────────────────

def run_d48() -> bool:
    """
    check() accepts lowercase, uppercase, and mixed-case action_type strings.
    Unknown strings still return CLARIFY_REQUIRED regardless of case.
    """
    print("\n=== Section D48: Case-insensitive action_type lookup ===")
    ok = True

    from rag.never_do_check import check, NeverDoDecision, _clear_rules_cache
    _clear_rules_cache()

    cases = [
        ("set_track_volume", {"target": "Kick"}, NeverDoDecision.ALLOW,
         "lowercase"),
        ("SET_TRACK_VOLUME", {"target": "Kick"}, NeverDoDecision.ALLOW,
         "uppercase (canonical)"),
        ("Set_Track_Volume", {"target": "Kick"}, NeverDoDecision.ALLOW,
         "mixed case"),
        ("delete_clip",      {},                 NeverDoDecision.HARD_BLOCK,
         "lowercase HARD_BLOCK"),
        ("DELETE_CLIP",      {},                 NeverDoDecision.HARD_BLOCK,
         "uppercase HARD_BLOCK"),
        ("unknown_action_xyz_999", {},           NeverDoDecision.CLARIFY_REQUIRED,
         "unknown → CLARIFY_REQUIRED"),
    ]

    for action, ctx, expected, label in cases:
        decision, _ = check(action, ctx)
        if decision != expected:
            print(f"{FAIL} [D48] {label}: expected {expected}, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D48] {label} → {decision}")

    print(f"\n  D48 case-insensitive: {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D49: Missing rules file — graceful degradation ───────────────────

def run_d49() -> bool:
    """
    When never_do_rules.md is absent, check() still returns the correct
    decisions from the static table.  No crash.  rule_text may be "" for
    cases that depended only on file matching — that is acceptable.
    Context overrides still fire (they don't need the file).
    """
    print("\n=== Section D49: Missing rules file — graceful degradation ===")
    ok = True

    import rag.never_do_check as ndc
    _orig_path = ndc.RULES_PATH
    ndc._clear_rules_cache()

    # Temporarily redirect RULES_PATH to a non-existent file
    ndc.RULES_PATH = "/tmp/conductor_test_nonexistent_rules_d49.md"
    ndc._clear_rules_cache()

    try:
        # Static decisions must still work
        decision, _ = ndc.check("DELETE_CLIP")
        if decision != ndc.NeverDoDecision.HARD_BLOCK:
            print(f"{FAIL} [D49-A] DELETE_CLIP should HARD_BLOCK even without rules file, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D49-A] DELETE_CLIP → HARD_BLOCK (no rules file)")

        decision, _ = ndc.check("SET_TRACK_VOLUME", {"target": "Kick"})
        if decision != ndc.NeverDoDecision.ALLOW:
            print(f"{FAIL} [D49-B] SET_TRACK_VOLUME should ALLOW even without rules file, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D49-B] SET_TRACK_VOLUME normal track → ALLOW (no rules file)")

        decision, _ = ndc.check("SET_TEMPO")
        if decision != ndc.NeverDoDecision.REQUIRE_CONFIRMATION:
            print(f"{FAIL} [D49-C] SET_TEMPO should REQUIRE_CONFIRMATION without rules file, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D49-C] SET_TEMPO → REQUIRE_CONFIRMATION (no rules file)")

        # Context override must still escalate
        decision, rule = ndc.check("SET_TRACK_VOLUME", {"target": "master"})
        if decision != ndc.NeverDoDecision.HARD_BLOCK:
            print(f"{FAIL} [D49-D] Master override should HARD_BLOCK without rules file, got {decision}")
            ok = False
        else:
            print(f"{PASS} [D49-D] Master context override fires without rules file")

        # check_allows convenience must work
        if not ndc.check_allows("SET_TRACK_PAN", {"target": "Snare"}):
            print(f"{FAIL} [D49-E] check_allows should be True without rules file")
            ok = False
        else:
            print(f"{PASS} [D49-E] check_allows works without rules file")

    finally:
        # Always restore
        ndc.RULES_PATH = _orig_path
        ndc._clear_rules_cache()

    print(f"\n  D49 missing rules file: {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D51: Endpoint-level gate tests ────────────────────────────────────

def run_d51() -> bool:
    """
    Bridge endpoint gate:
      1. Monkeypatches never_do_check.check to each of 5 decision types and
         verifies the endpoint refuses BEFORE any Ableton call:
           - response fields: ok=False, error_code, decision, rule_text,
             action_id, request_id, session_id, http status
           - no-write proof: ableton_execute + ableton_connected call count = 0
      2. Verifies ALLOW passes the gate and calls ableton_connected (≥1).
      3. Tests that an unknown/non-enum decision fails closed without crash.

    Coverage: 4 endpoints × 5 decision types = 20 refusal cases
              + 4 ALLOW pass-throughs.
    """
    print("\n=== Section D51: Endpoint-level gate enforcement ===")
    ok = True

    import io
    import json as _json
    sys.path.insert(0, os.path.join(_ROOT, "tools"))

    import rag.never_do_check as ndc_mod
    import conductor_bridge   as _cb_mod
    from rag.never_do_check import NeverDoDecision
    from conductor_bridge import ConductorHandler

    # ── Minimal mock handler — bypasses BaseHTTPRequestHandler.__init__ ───────
    class _MockHandler(ConductorHandler):
        def __init__(self, path_str: str, body_dict: dict):
            # Intentionally skip super().__init__ to avoid socket setup.
            self.path = path_str
            body_bytes = _json.dumps(body_dict).encode()
            self.headers   = {"Content-Length": str(len(body_bytes))}
            self.rfile     = io.BytesIO(body_bytes)
            self._cap_data = None
            self._cap_code = None

        def _send_json(self, data, code=200):
            # Capture and suppress all HTTP output
            self._cap_data = data
            self._cap_code = code

    # ── Endpoints under test ──────────────────────────────────────────────────
    endpoints = [
        ("/action/track_volume", {"track": "TestKick",  "volume": 0.5},  "volume"),
        ("/action/track_pan",    {"track": "TestSnare", "pan":    0.5},  "pan"),
        ("/action/track_mute",   {"track": "TestHiHat", "mute":   True}, "mute"),
        ("/action/track_solo",   {"track": "TestVox",   "solo":   True}, "solo"),
    ]

    # ── 5 gate cases ──────────────────────────────────────────────────────────
    # 5th case: bare string — no .value attribute — proves the bridge does not
    # crash at log_never_do_blocked() or error_response() and still fails closed.
    # This is the true unknown/non-enum test (prior version used a fake class
    # with .value, which could not expose the crash).

    gate_cases = [
        (NeverDoDecision.HARD_BLOCK,
         "SECURITY_NEVER_DO_BLOCK",         403, "HARD_BLOCK"),
        (NeverDoDecision.REQUIRE_CONFIRMATION,
         "SECURITY_CONFIRMATION_REQUIRED",  403, "REQUIRE_CONFIRMATION"),
        (NeverDoDecision.CLARIFY_REQUIRED,
         "SECURITY_CLARIFY_REQUIRED",       400, "CLARIFY_REQUIRED"),
        (NeverDoDecision.UNDO_LOG_REQUIRED,
         "SECURITY_NEVER_DO_BLOCK",         403, "UNDO_LOG_REQUIRED (fail-closed)"),
        ("UNKNOWN_DECISION_D51",
         "SECURITY_NEVER_DO_BLOCK",         403, "bare-string unknown (fail-closed, no crash)"),
    ]
    _TEST_RULE = "test-rule-text-d51"

    # ── Call-count trackers — prove write executor never called on gate block ─
    execute_calls   = [0]
    connected_calls = [0]
    _orig_execute   = _cb_mod.ableton_execute
    _orig_connected = _cb_mod.ableton_connected
    original_check  = ndc_mod.check

    def _tracking_execute(code, timeout=10.0):
        execute_calls[0] += 1
        return {"ok": False, "error": "test-sentinel", "data": {},
                "verified": False, "source": "test"}

    def _tracking_connected():
        connected_calls[0] += 1
        return False  # always not connected (simulates offline Ableton)

    _cb_mod.ableton_execute   = _tracking_execute
    _cb_mod.ableton_connected = _tracking_connected

    try:
        # ── Non-ALLOW: response checks + no-write proof ───────────────────────
        for path, body, ep_label in endpoints:
            ep_ok = True
            for decision, exp_ec, exp_http, case_label in gate_cases:
                execute_calls[0]   = 0
                connected_calls[0] = 0

                ndc_mod.check = lambda a, ctx=None, _d=decision: (_d, _TEST_RULE)
                try:
                    h = _MockHandler(path, body)
                    h.do_POST()
                finally:
                    ndc_mod.check = original_check

                resp = h._cap_data
                code = h._cap_code
                fail_msgs = []

                if resp is None:
                    fail_msgs.append("handler produced no response")
                else:
                    if resp.get("ok") is not False:
                        fail_msgs.append(f"ok={resp.get('ok')!r} (expected False)")
                    if resp.get("error_code") != exp_ec:
                        fail_msgs.append(f"error_code={resp.get('error_code')!r} expected {exp_ec!r}")
                    # bare-string decisions have no .value; NeverDoDecision enums do
                    exp_decision = decision if isinstance(decision, str) else decision.value
                    if resp.get("decision") != exp_decision:
                        fail_msgs.append(f"decision={resp.get('decision')!r} expected {exp_decision!r}")
                    if resp.get("rule_text") != _TEST_RULE:
                        fail_msgs.append(f"rule_text={resp.get('rule_text')!r} expected {_TEST_RULE!r}")
                    if not resp.get("action_id"):
                        fail_msgs.append("action_id missing")
                    if not resp.get("request_id"):
                        fail_msgs.append("request_id missing")
                    if "session_id" not in resp:
                        fail_msgs.append("session_id missing")
                    if code != exp_http:
                        fail_msgs.append(f"http={code} expected {exp_http}")

                # No-write proof: gate must fire before any Ableton call
                if execute_calls[0] != 0:
                    fail_msgs.append(
                        f"ableton_execute called {execute_calls[0]}x (must be 0 — gate should block before write)"
                    )
                if connected_calls[0] != 0:
                    fail_msgs.append(
                        f"ableton_connected called {connected_calls[0]}x (must be 0 — gate should block before connectivity check)"
                    )

                if fail_msgs:
                    for m in fail_msgs:
                        print(f"{FAIL} [D51] {ep_label}/{case_label}: {m}")
                    ok = False
                    ep_ok = False

            print(f"{PASS if ep_ok else FAIL} [D51] {ep_label}: "
                  f"all gate cases {'pass' if ep_ok else 'see failures above'}")

        # ── ALLOW: gate passes, ableton_connected called (≥1), no security err ─
        _SECURITY_CODES = {
            "SECURITY_NEVER_DO_BLOCK",
            "SECURITY_CONFIRMATION_REQUIRED",
            "SECURITY_CLARIFY_REQUIRED",
        }
        for path, body, ep_label in endpoints:
            execute_calls[0]   = 0
            connected_calls[0] = 0
            ndc_mod.check = lambda a, ctx=None: (NeverDoDecision.ALLOW, "")
            try:
                h = _MockHandler(path, body)
                h.do_POST()
            finally:
                ndc_mod.check = original_check

            resp = h._cap_data
            fail_msgs = []

            if resp is None:
                fail_msgs.append("handler produced no response")
            else:
                ec = resp.get("error_code", "")
                if ec in _SECURITY_CODES:
                    fail_msgs.append(f"ALLOW was blocked by gate (error_code={ec!r})")
                # Connectivity check must have been reached (called ≥1)
                if connected_calls[0] == 0:
                    fail_msgs.append("ableton_connected not called — gate may have fired on ALLOW")
                # Write executor must NOT be called (connectivity returned False → no write)
                if execute_calls[0] != 0:
                    fail_msgs.append(
                        f"ableton_execute called {execute_calls[0]}x before connectivity confirmed"
                    )

            if fail_msgs:
                for m in fail_msgs:
                    print(f"{FAIL} [D51] {ep_label}/ALLOW: {m}")
                ok = False
            else:
                ec = resp.get("error_code", "")
                print(f"{PASS} [D51] {ep_label}/ALLOW: gate passed → "
                      f"ableton_connected called ({connected_calls[0]}x), error_code={ec!r}")

    finally:
        ndc_mod.check             = original_check
        _cb_mod.ableton_execute   = _orig_execute
        _cb_mod.ableton_connected = _orig_connected

    total_gate  = len(endpoints) * len(gate_cases)
    total_allow = len(endpoints)
    print(f"\n  D51 endpoint gate: {total_gate} refusal cases + {total_allow} ALLOW pass-throughs — {'pass' if ok else 'FAIL'}")
    return ok


# ── SECTION D50: Slice 4 + Phase C regressions ────────────────────────────────

def run_d50() -> bool:
    """Run Slice 4 eval + Phase C eval — must still pass after D5 additions."""
    print("\n=== Section D50: Slice 4 + Phase C regressions ===")

    py = sys.executable
    results = []
    for suite, label in [
        ("phase_d_slice4_eval.py", "Slice 4"),
        ("phase_c_eval_set.py",    "Phase C"),
    ]:
        try:
            path = os.path.join(_HERE, suite)
            r = subprocess.run(
                [py, path],
                capture_output=True, text=True,
                timeout=600,
                cwd=_ROOT,
            )
            success = r.returncode == 0
            last = [l.strip() for l in r.stdout.splitlines() if l.strip()]
            summary = last[-1] if last else "(no output)"
            print(f"  {'✅' if success else '❌'} [{label}] {summary}")
            if not success:
                for l in last[-8:]:
                    print(f"       {l}")
            results.append(success)
        except subprocess.TimeoutExpired:
            print(f"  ❌ [{label}] TIMEOUT")
            results.append(False)
        except Exception as exc:
            print(f"  ❌ [{label}] ERROR: {exc}")
            results.append(False)

    all_ok = all(results)
    print(f"\n  Slice 4 + Phase C regressions: {'pass' if all_ok else 'FAIL'}")
    return all_ok


# ── MAIN ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Conductor — Phase D Slice 5 Eval Suite")
    print("  Never-Do Preflight Enforcement")
    print("=" * 60)

    results = {
        "D41": run_d41(),
        "D42": run_d42(),
        "D43": run_d43(),
        "D44": run_d44(),
        "D45": run_d45(),
        "D46": run_d46(),
        "D47": run_d47(),
        "D48": run_d48(),
        "D49": run_d49(),
        "D51": run_d51(),
        "D50": run_d50(),
    }

    print("\n" + "=" * 60)
    print("  RESULTS")
    print("=" * 60)
    labels = {
        "D41": "HARD_BLOCK actions (6 checks)",
        "D42": "REQUIRE_CONFIRMATION actions (13 checks)",
        "D43": "ALLOW actions (8 checks)",
        "D44": "UNDO_LOG_REQUIRED actions (4 checks)",
        "D45": "Context overrides: master/batch/EQ cut",
        "D46": "Rule text matching from file",
        "D47": "check_allows() + is_hard_block() wrappers",
        "D48": "Case-insensitive action_type lookup",
        "D49": "Missing rules file — graceful degradation",
        "D51": "Endpoint gate: 4 endpoints × 5 decisions, no-write proof",
        "D50": "Slice 4 + Phase C regressions",
    }
    all_pass = all(results.values())
    for k, v in results.items():
        icon = PASS if v else FAIL
        print(f"  {icon}  {k}  {labels[k]}")

    print()
    if all_pass:
        print(f"  ALL PASS")
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"  FAILED: {failed}")
        sys.exit(1)
