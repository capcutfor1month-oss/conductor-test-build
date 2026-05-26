"""
Phase D — Slice 11: Natural Replies
Eval sections D115–D120

What this tests:
  D115  node --check app/harness.js passes
  D116  Forbidden wording absent from user-visible code paths
  D117  composeReply function present; translateResponse gone
  D118  composeReply pure-function contract (via node subprocess)
  D119  Proposal card: endpoint/model/tokens NOT visible outside <details>
  D120  Unsupported-action and not-in-registry messages are natural

No bridge changes in this slice — no Python compile check needed.
No bridge endpoint mock needed — all tests are JS source analysis
or node subprocess execution of the pure composeReply function.
"""

import os
import re
import sys
import json
import subprocess
import unittest

TEST_BUILD = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
HARNESS_JS = os.path.join(TEST_BUILD, "app", "harness.js")


def _js_src():
    with open(HARNESS_JS, encoding="utf-8") as f:
        return f.read()


def _extract_function(src: str, name: str) -> str | None:
    """Extract a JS top-level function by brace counting."""
    marker = f"function {name}("
    idx = src.find(marker)
    if idx == -1:
        return None
    brace_start = src.index("{", idx)
    depth = 0
    for i in range(brace_start, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[idx : i + 1]
    return None


def _run_node(js_code: str) -> tuple[str, str, int]:
    """Run js_code in node, return (stdout, stderr, returncode)."""
    r = subprocess.run(
        ["node", "-e", js_code],
        capture_output=True, text=True,
        cwd=os.path.join(TEST_BUILD, "app"),
    )
    return r.stdout, r.stderr, r.returncode


# ─────────────────────────────────────────────────────────────────────────────
class D115_NodeSyntaxCheck(unittest.TestCase):
    """node --check app/harness.js must pass."""

    def test_node_check(self):
        r = subprocess.run(
            ["node", "--check", HARNESS_JS],
            capture_output=True, text=True,
        )
        self.assertEqual(
            r.returncode, 0,
            f"node --check failed:\n{r.stderr}",
        )


# ─────────────────────────────────────────────────────────────────────────────
class D116_ForbiddenWordingAbsent(unittest.TestCase):
    """
    Patterns that must NOT appear in user-facing code paths.
    Each assertion targets a specific dev-language leak that was present
    before this slice.
    """

    def setUp(self):
        self.src = _js_src()

    def test_no_registry_in_chat(self):
        self.assertNotIn(
            "not in my registry yet",
            self.src,
            "Old 'not in my registry yet' string still present",
        )

    def test_no_action_not_found_in_registry_status(self):
        self.assertNotIn(
            "Action not found in registry",
            self.src,
            "Dev status string 'Action not found in registry' still present",
        )

    def test_no_capability_locked(self):
        self.assertNotIn(
            "capability is locked",
            self.src,
            "'capability is locked' still surfaced to user",
        )

    def test_no_action_locked_status(self):
        self.assertNotIn(
            '"Action locked."',
            self.src,
            "Dev status string 'Action locked.' still present",
        )

    def test_no_translateResponse(self):
        self.assertNotIn(
            "function translateResponse",
            self.src,
            "translateResponse still defined (should be replaced by composeReply)",
        )

    def test_no_translateResponse_call(self):
        self.assertNotIn(
            "translateResponse(",
            self.src,
            "translateResponse still called somewhere",
        )

    def test_no_unknown_status(self):
        self.assertNotIn(
            'return "Unknown";',
            self.src,
            "translateStatus still returns 'Unknown' — should be 'Unverified'",
        )

    def test_no_action_id_in_chat_message(self):
        # The old message embedded data.action_id directly in the chat string
        self.assertNotIn(
            "${data.action_id}",
            self.src,
            "data.action_id still surfaced raw in a chat message",
        )

    def test_no_future_reason_in_chat_message(self):
        # The old unsupported-action message embedded action.future_reason directly
        # in an addChatMessage() call. Only chat messages are checked here.
        for line in self.src.split("\n"):
            if "addChatMessage" in line and "future_reason" in line:
                self.fail(
                    f"action.future_reason still surfaced in a chat message: {line.strip()!r}"
                )

    def test_no_capability_locked_anywhere(self):
        # "Capability locked" must not appear anywhere — not in chat, not in tooltips.
        self.assertNotIn(
            "Capability locked",
            self.src,
            "'Capability locked' still present in source (check btn.title)",
        )

    def test_no_locked_span_text(self):
        # reasonSpan.textContent = "Locked" was a visible label on roadmap buttons.
        # It must be replaced with something natural like "Roadmap".
        self.assertNotIn(
            'textContent = "Locked"',
            self.src,
            'Visible "Locked" span text still present on roadmap buttons',
        )

    def test_future_reason_not_in_tooltips(self):
        # btn.title must not interpolate action.future_reason — exposes internal wording.
        for line in self.src.split("\n"):
            if "btn.title" in line and "future_reason" in line:
                self.fail(
                    f"action.future_reason still exposed in btn.title tooltip: {line.strip()!r}"
                )

    def test_session_totals_no_tokens(self):
        # "Tokens:" must not appear in the normal session totals innerHTML.
        # It may still appear in the already-collapsed debug/observability blocks.
        src = self.src
        # Find updateSessionTotals function body
        fn_start = src.find("function updateSessionTotals()")
        fn_end   = src.find("\nfunction ", fn_start + 1)
        fn_body  = src[fn_start:fn_end]
        self.assertNotIn(
            "Tokens:",
            fn_body,
            "'Tokens:' still rendered inside updateSessionTotals() — visible to user",
        )

    def test_session_totals_no_est_cost(self):
        fn_start = self.src.find("function updateSessionTotals()")
        fn_end   = self.src.find("\nfunction ", fn_start + 1)
        fn_body  = self.src[fn_start:fn_end]
        self.assertNotIn(
            "Est. Cost:",
            fn_body,
            "'Est. Cost:' still rendered inside updateSessionTotals() — visible to user",
        )

    def test_session_totals_no_not_reported(self):
        fn_start = self.src.find("function updateSessionTotals()")
        fn_end   = self.src.find("\nfunction ", fn_start + 1)
        fn_body  = self.src[fn_start:fn_end]
        self.assertNotIn(
            "not reported",
            fn_body,
            "'not reported' still rendered inside updateSessionTotals() — visible to user",
        )

    def test_session_totals_keeps_studio_stats(self):
        # Actions / Verified / Failed / Time must still be present.
        fn_start = self.src.find("function updateSessionTotals()")
        fn_end   = self.src.find("\nfunction ", fn_start + 1)
        fn_body  = self.src[fn_start:fn_end]
        for label in ("Actions:", "Verified:", "Failed:", "Time:"):
            self.assertIn(
                label, fn_body,
                f"Studio stat '{label}' missing from session totals after cleanup",
            )


# ─────────────────────────────────────────────────────────────────────────────
class D117_ComposeReplyDefined(unittest.TestCase):
    """composeReply must exist; old translateResponse must be gone."""

    def setUp(self):
        self.src = _js_src()

    def test_composeReply_defined(self):
        fn = _extract_function(self.src, "composeReply")
        self.assertIsNotNone(fn, "composeReply not found in harness.js")
        self.assertIn("action", fn, "composeReply signature missing 'action' param")
        self.assertIn("response", fn, "composeReply signature missing 'response' param")

    def test_composeReply_uses_after_state(self):
        fn = _extract_function(self.src, "composeReply")
        self.assertIn(
            "after_state",
            fn,
            "composeReply should derive target from response.after_state",
        )

    def test_composeReply_uses_before_state(self):
        fn = _extract_function(self.src, "composeReply")
        self.assertIn(
            "before_state",
            fn,
            "composeReply should fall back to response.before_state for target",
        )

    def test_translateResponse_removed(self):
        fn = _extract_function(self.src, "translateResponse")
        self.assertIsNone(fn, "translateResponse still defined — should be removed")

    def test_translateStatus_returns_unverified(self):
        fn = _extract_function(self.src, "translateStatus")
        self.assertIsNotNone(fn, "translateStatus not found")
        self.assertIn("Unverified", fn, "translateStatus should return 'Unverified' not 'Unknown'")
        self.assertNotIn('"Unknown"', fn, "translateStatus still has 'Unknown'")


# ─────────────────────────────────────────────────────────────────────────────
class D118_ComposeReplyPureFunction(unittest.TestCase):
    """
    Run composeReply via node subprocess to test all key paths.
    composeReply is a pure function — no DOM references, safe to extract and eval.
    """

    @classmethod
    def setUpClass(cls):
        src = _js_src()
        fn_src = _extract_function(src, "composeReply")
        assert fn_src, "composeReply not found"

        cases = [
            # [action, response, description]
            [{"label": "Set Volume"}, {"ok": True,  "verification_status": "VERIFIED",       "after_state":  {"track_name": "Kick"}},  "verified_with_target"],
            [{"label": "Set Volume"}, {"ok": True,  "verification_status": "VERIFIED",       "after_state":  None},                    "verified_no_target"],
            [{"label": "Set Pan"},    {"ok": True,  "verification_status": "ALREADY_CORRECT","before_state": {"track_name": "Bass"}},  "already_correct_with_target"],
            [{"label": "Set Pan"},    {"ok": True,  "verification_status": "ALREADY_CORRECT","before_state": None},                   "already_correct_no_target"],
            [{"label": "Mute"},       {"ok": True,  "verification_status": "UNVERIFIED"},                                             "unverified_no_target"],
            [{"label": "Mute"},       {"ok": True,  "verification_status": "UNVERIFIED",     "after_state":  {"track_name": "Snare"}},"unverified_with_target"],
            # Error cases
            [{"label": "Undo"},       {"ok": False, "error_code": "UNDO_DRIFT_DETECTED"},    "undo_drift"],
            [{"label": "Bypass"},     {"ok": False, "error_code": "BRIDGE_PLUGIN_ABSENT"},   "plugin_absent_no_target"],
            [{"label": "Bypass"},     {"ok": False, "error_code": "BRIDGE_PLUGIN_ABSENT",    "after_state":  {"track_name": "Lead"}},  "plugin_absent_with_target"],
            [{"label": "Set Volume"}, {"ok": False, "error_code": "BRIDGE_PARAM_OUT_OF_RANGE"},"out_of_range"],
            [{"label": "Set Volume"}, {"ok": False, "error_code": "BRIDGE_TRACK_ABSENT"},    "track_absent"],
            [{"label": "Delete"},     {"ok": False, "error_code": "SECURITY_CONFIRMATION_REQUIRED"},"confirmation_required"],
            [{"label": "Route"},      {"ok": False, "error_code": "SECURITY_CLARIFY_REQUIRED"},    "clarify_required"],
            [{"label": "Play"},       {"ok": False, "error_code": "NEVER_DO_BLOCKED"},        "never_do"],
            [{"label": "Play"},       {"ok": False, "error_code": "ABLETON_DISCONNECTED"},    "disconnected"],
            [{"label": "Unknown"},    {"ok": False, "error_code": "SOME_UNKNOWN_CODE"},       "unknown_error"],
            [{"label": "Unknown"},    {"ok": False, "error_code": ""},                        "empty_error_code"],
        ]

        test_js = fn_src + "\n"
        test_js += "const cases = " + json.dumps(cases) + ";\n"
        test_js += """
const results = {};
for (const [action, response, label] of cases) {
    try {
        results[label] = composeReply(action, response);
    } catch (e) {
        results[label] = "__ERROR__: " + e.message;
    }
}
console.log(JSON.stringify(results));
"""
        stdout, stderr, rc = _run_node(test_js)
        if rc != 0:
            raise RuntimeError(f"node failed: {stderr}")
        cls.results = json.loads(stdout)

    # ── Success paths ──────────────────────────────────────────────────────

    def test_verified_with_target_contains_target(self):
        r = self.results["verified_with_target"]
        self.assertIn("Kick", r, f"Expected target 'Kick' in reply, got: {r!r}")

    def test_verified_with_target_contains_confirmed(self):
        r = self.results["verified_with_target"]
        self.assertIn("confirmed", r.lower(), f"Expected 'confirmed' in reply, got: {r!r}")

    def test_verified_no_target_still_succeeds(self):
        r = self.results["verified_no_target"]
        self.assertNotIn("__ERROR__", r)
        self.assertIn("confirmed", r.lower())

    def test_already_correct_with_target(self):
        r = self.results["already_correct_with_target"]
        self.assertIn("Bass", r)
        self.assertNotIn("__ERROR__", r)

    def test_already_correct_no_target(self):
        r = self.results["already_correct_no_target"]
        self.assertIn("already", r.lower())

    def test_unverified_no_target_honest(self):
        r = self.results["unverified_no_target"]
        # Must NOT claim success (no "confirmed"), must acknowledge uncertainty
        self.assertNotIn("confirmed", r.lower())
        self.assertNotIn("Done", r)
        self.assertNotIn("__ERROR__", r)

    def test_unverified_with_target_contains_target(self):
        r = self.results["unverified_with_target"]
        self.assertIn("Snare", r)
        self.assertNotIn("confirmed", r.lower())

    # ── Error paths ────────────────────────────────────────────────────────

    def test_undo_drift(self):
        r = self.results["undo_drift"]
        self.assertIn("undo", r.lower())
        self.assertNotIn("__ERROR__", r)

    def test_plugin_absent_no_target(self):
        r = self.results["plugin_absent_no_target"]
        self.assertIn("plugin", r.lower())
        self.assertNotIn("__ERROR__", r)

    def test_plugin_absent_with_target(self):
        r = self.results["plugin_absent_with_target"]
        self.assertIn("Lead", r)

    def test_out_of_range(self):
        r = self.results["out_of_range"]
        self.assertIn("range", r.lower())

    def test_track_absent(self):
        r = self.results["track_absent"]
        self.assertIn("track", r.lower())
        # Must not expose the raw error_code string to user
        self.assertNotIn("BRIDGE_TRACK_ABSENT", r)

    def test_confirmation_required(self):
        r = self.results["confirmation_required"]
        self.assertIn("confirmation", r.lower())
        self.assertNotIn("SECURITY_CONFIRMATION_REQUIRED", r)

    def test_confirmation_required_no_invented_undo_claim(self):
        # The reply must NOT claim "can't be undone" — that fact comes from
        # response.undo_eligible, which is absent in this test case.
        # Inventing undo information from the error code alone is dishonest.
        r = self.results["confirmation_required"]
        self.assertNotIn(
            "undone", r.lower(),
            f"Reply invents 'undone' claim without backend undo_eligible field: {r!r}",
        )

    def test_clarify_required(self):
        r = self.results["clarify_required"]
        self.assertIn("detail", r.lower())
        self.assertNotIn("SECURITY_CLARIFY_REQUIRED", r)

    def test_never_do_blocked(self):
        r = self.results["never_do"]
        self.assertIn("safety", r.lower())
        self.assertNotIn("NEVER_DO_BLOCKED", r)

    def test_disconnected(self):
        r = self.results["disconnected"]
        self.assertIn("connected", r.lower())
        self.assertNotIn("ABLETON_DISCONNECTED", r)

    def test_unknown_error_safe(self):
        r = self.results["unknown_error"]
        self.assertNotIn("__ERROR__", r)
        self.assertNotIn("SOME_UNKNOWN_CODE", r)

    def test_empty_error_code_safe(self):
        r = self.results["empty_error_code"]
        self.assertNotIn("__ERROR__", r)

    # ── No raw codes in any reply ─────────────────────────────────────────

    def test_no_raw_error_codes_in_any_reply(self):
        """No reply should surface a SCREAMING_SNAKE_CASE error code."""
        bad = re.compile(r'\b[A-Z]{2,}(?:_[A-Z]+){1,}\b')
        for label, r in self.results.items():
            self.assertIsNone(
                bad.search(r),
                f"Reply for '{label}' contains a raw error code: {r!r}",
            )

    def test_no_endpoint_names_in_any_reply(self):
        for label, r in self.results.items():
            self.assertNotIn(
                "/action/", r,
                f"Reply for '{label}' contains an endpoint path: {r!r}",
            )


# ─────────────────────────────────────────────────────────────────────────────
class D119_ProposalCardMetadataHidden(unittest.TestCase):
    """
    Endpoint, model, tokens must NOT be rendered outside a <details> element.
    They should only appear inside the 'Debug info' details block.
    """

    def setUp(self):
        self.src = _js_src()

    def test_metaDiv_gone(self):
        self.assertNotIn("metaDiv", self.src,
                         "metaDiv still present — endpoint/model/tokens are still visible")

    def test_epSpan_gone(self):
        self.assertNotIn("epSpan", self.src,
                         "epSpan still present — Endpoint is still rendered outside details")

    def test_confidence_shown_directly(self):
        # Confidence div should exist (not inside details)
        self.assertIn(
            "Confidence: ${confPct}%",
            self.src,
            "Confidence% display is missing from proposal card",
        )

    def test_endpoint_only_inside_debug_details(self):
        # proposal.endpoint must appear inside the pre block (after "Debug info" summary),
        # not in a span/code that's appended directly to container.
        # Verify the old epSpan pattern is gone.
        self.assertNotIn(
            'epSpan.textContent = "Endpoint: "',
            self.src,
            "epSpan Endpoint span still being built outside details",
        )

    def test_debug_info_summary_present(self):
        self.assertIn(
            '"Debug info"',
            self.src,
            "Summary text 'Debug info' not found — details block may be missing",
        )

    def test_model_tokens_inside_pre(self):
        # tokensStr and modelStr should appear only inside the pre block
        self.assertIn("tokensStr", self.src)
        self.assertIn("modelStr", self.src)
        # They must be in the pre.textContent template literal, not in a restSpan
        self.assertNotIn("restSpan", self.src,
                         "restSpan still present — model/tokens still visible outside details")


# ─────────────────────────────────────────────────────────────────────────────
class D120_NaturalPhrasing(unittest.TestCase):
    """
    Unsupported-action and not-in-registry chat messages are natural and
    contain none of the forbidden dev phrases.
    """

    def setUp(self):
        self.src = _js_src()

    def test_not_in_registry_natural(self):
        self.assertIn(
            "Not sure how to handle that one",
            self.src,
            "Natural 'not in registry' message missing",
        )

    def test_not_in_registry_no_registry_word(self):
        # The word "registry" should not appear in any addChatMessage call
        # (comments and internal variable names are OK — we check message strings)
        for line in self.src.split("\n"):
            if "addChatMessage" in line and "registry" in line.lower():
                self.fail(f"'registry' still in a chat message: {line.strip()!r}")

    def test_unsupported_no_locked(self):
        for line in self.src.split("\n"):
            if "addChatMessage" in line and "locked" in line.lower():
                self.fail(f"'locked' still in a chat message: {line.strip()!r}")

    def test_unsupported_no_future_reason(self):
        for line in self.src.split("\n"):
            if "addChatMessage" in line and "future_reason" in line:
                self.fail(f"future_reason still surfaced in a chat message: {line.strip()!r}")

    def test_unsupported_roadmap_message(self):
        self.assertIn(
            "roadmap",
            self.src,
            "Unsupported action message should mention 'roadmap'",
        )

    def test_status_not_available_yet(self):
        self.assertIn(
            '"Not available yet."',
            self.src,
            "Status for unsupported action should be 'Not available yet.'",
        )

    def test_status_couldnt_map(self):
        self.assertIn(
            '"Couldn\'t map that."',
            self.src,
            "Status for unknown action should be \"Couldn't map that.\"",
        )


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in [
        D115_NodeSyntaxCheck,
        D116_ForbiddenWordingAbsent,
        D117_ComposeReplyDefined,
        D118_ComposeReplyPureFunction,
        D119_ProposalCardMetadataHidden,
        D120_NaturalPhrasing,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
