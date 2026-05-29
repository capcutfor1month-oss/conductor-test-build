#!/usr/bin/env python3
"""
phase_d_slice23_eval.py — Build 16: Ambient Feedback UI / Feedback Wiring v1
Tests D213–D220.

All checks are static source analysis (grep/regex on JS and HTML).
No browser runtime required.  Consistent with prior harness JS test patterns.
"""

import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
_HARNESS_JS   = os.path.join(_ROOT, "app", "harness.js")
_HARNESS_HTML = os.path.join(_ROOT, "app", "harness.html")
_SERVER_PY    = os.path.join(_ROOT, "tools", "harness_server.py")
_BRIDGE_PY    = os.path.join(_ROOT, "tools", "conductor_bridge.py")

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


def extract_js_function(src, fn_name):
    """Return the full source text of a named JS function (brace-balanced)."""
    m = re.search(r'function\s+' + re.escape(fn_name) + r'\s*\(', src)
    if not m:
        return None
    start = m.start()
    try:
        brace_start = src.index('{', start)
    except ValueError:
        return None
    depth = 0
    i = brace_start
    while i < len(src):
        if src[i] == '{':
            depth += 1
        elif src[i] == '}':
            depth -= 1
            if depth == 0:
                return src[start:i + 1]
        i += 1
    return None


js_src   = read_src(_HARNESS_JS)
html_src = read_src(_HARNESS_HTML)

print("=" * 64)
print("D213–D220  Build 16: Ambient Feedback UI / Feedback Wiring v1")
print("=" * 64)

# ── D213  addChatMessage returns wrap ─────────────────────────────
print("\n[D213] addChatMessage returns wrap")

fn_body = extract_js_function(js_src, "addChatMessage")
check("D213a", "addChatMessage function found in source", fn_body is not None)

if fn_body:
    has_return_wrap = bool(re.search(r'\breturn\s+wrap\b', fn_body))
    check("D213b", "addChatMessage body contains 'return wrap'", has_return_wrap)

    early_exit_ok = bool(re.search(r'if\s*\(!messages\)\s*return\s*;', fn_body))
    check("D213c", "early exit (no messages) still returns undefined cleanly", early_exit_ok)
else:
    check("D213b", "addChatMessage body contains 'return wrap'", False, "function not found")
    check("D213c", "early exit (no messages) returns undefined cleanly", False, "function not found")

# ── D214  answer branch attaches chips when response_id exists ────
print("\n[D214] answer branch attaches feedback chips when response_id exists")

# Capture entire answer block: from 'type === "answer"' to its closing 'return;'
answer_block_m = re.search(
    r'data\.type\s*===\s*["\']answer["\'].*?return\s*;',
    js_src,
    re.DOTALL
)
answer_block = answer_block_m.group(0) if answer_block_m else ""
check("D214a", "type === 'answer' branch found", bool(answer_block))

wrap_assign = bool(re.search(r'\bconst\s+wrap\s*=\s*addChatMessage\s*\(', answer_block))
check("D214b", "answer branch: const wrap = addChatMessage(...)", wrap_assign)

chips_call = bool(re.search(
    r'addFeedbackChips\s*\(\s*wrap\s*,\s*data\.response_id\s*\)',
    answer_block
))
check("D214c", "answer branch: addFeedbackChips(wrap, data.response_id)", chips_call)

gate = bool(re.search(r'if\s*\(\s*wrap\s*&&\s*data\.response_id\s*\)', answer_block))
check("D214d", "eligibility gate: if (wrap && data.response_id) present", gate)

# ── D215  Helpful sends HELPFUL ───────────────────────────────────
print("\n[D215] Helpful sends HELPFUL to /harness/feedback")

fn_send = extract_js_function(js_src, "_sendKnowledgeFeedback")
check("D215a", "_sendKnowledgeFeedback function defined", fn_send is not None)

if fn_send:
    has_post  = bool(re.search(r'["\']POST["\']', fn_send))
    has_ep    = bool(re.search(r'["\']\/harness\/feedback["\']', fn_send))
    has_rid   = "response_id" in fn_send
    has_ftype = "feedback_type" in fn_send
    check("D215b", "_sendKnowledgeFeedback uses POST /harness/feedback", has_post and has_ep,
          f"POST={has_post} endpoint={has_ep}")
    check("D215c", "response_id and feedback_type sent in body", has_rid and has_ftype)
    has_catch = bool(re.search(r'\.catch\s*\(\s*\(\s*\)\s*=>\s*\{?\s*\}', fn_send))
    check("D215d", "fire-and-forget: .catch(() => {}) present", has_catch)
else:
    for sub_id in ("D215b", "D215c", "D215d"):
        check(sub_id, f"sub-check {sub_id}", False, "_sendKnowledgeFeedback not found")

fn_chips = extract_js_function(js_src, "addFeedbackChips")
check("D215e", "addFeedbackChips function defined", fn_chips is not None)

if fn_chips:
    helpful_send = bool(re.search(
        r'_sendKnowledgeFeedback\s*\(\s*responseId\s*,\s*["\']HELPFUL["\']',
        fn_chips
    ))
    check("D215f", "Helpful chip calls _sendKnowledgeFeedback(responseId, 'HELPFUL')", helpful_send)
else:
    check("D215f", "Helpful chip calls _sendKnowledgeFeedback(responseId, 'HELPFUL')", False,
          "addFeedbackChips not found")

# ── D216  Not this opens sub-row only, does NOT send ─────────────
print("\n[D216] Not this opens sub-row; does not send NOT_HELPFUL")

if fn_chips:
    has_not_this_label = "Not this" in fn_chips
    check("D216a", "'Not this' chip label present", has_not_this_label)

    # NOT_HELPFUL must never appear as a sent type anywhere in harness.js
    has_not_helpful_literal = ('"NOT_HELPFUL"' in js_src or "'NOT_HELPFUL'" in js_src)
    check("D216b", "NOT_HELPFUL never appears as a sent type in harness.js",
          not has_not_helpful_literal)

    # "Not this" click only toggles sub.style.display, no _sendKnowledgeFeedback call
    # Extract the notThis listener block: between "Not this" label and the next }) block
    not_this_listener_m = re.search(
        r'Not this.*?notThis\.addEventListener\s*\(["\']click["\'],.*?\}\s*\)',
        fn_chips,
        re.DOTALL
    )
    if not_this_listener_m:
        nt_block = not_this_listener_m.group(0)
        no_send_in_nt = "_sendKnowledgeFeedback" not in nt_block
        check("D216c", "Not this click handler does NOT call _sendKnowledgeFeedback", no_send_in_nt)
    else:
        # Alternative: check that sub.style.display toggle is in source
        has_toggle = bool(re.search(r'sub\.style\.display', fn_chips))
        check("D216c", "sub.style.display toggle present in addFeedbackChips", has_toggle)
else:
    for sub_id in ("D216a", "D216b", "D216c"):
        check(sub_id, f"sub-check {sub_id}", False, "addFeedbackChips not found")

# ── D217  Sub-types send correct feedback_type values ─────────────
print("\n[D217] Too vague / Wrong / Outdated send correct types")

if fn_chips:
    for ftype, label in [("TOO_VAGUE", "Too vague"), ("WRONG", "Wrong"), ("OUTDATED", "Outdated")]:
        # Implementation uses a forEach that destructures { label, type } from an array of
        # objects and calls _sendKnowledgeFeedback(responseId, type).
        # Check: the type literal must appear in the chips source (in the subTypes array),
        # and the chip label must be present.
        has_literal = bool(re.search(r'["\']' + ftype + r'["\']', fn_chips))
        check(f"D217-{ftype}", f"'{ftype}' literal in addFeedbackChips sub-type array", has_literal)
        has_label = label in fn_chips
        check(f"D217-label-{ftype}", f"chip label '{label}' present", has_label)

    # The forEach calls _sendKnowledgeFeedback(responseId, type) — generic variable form
    has_generic_send = bool(re.search(
        r'_sendKnowledgeFeedback\s*\(\s*responseId\s*,\s*type\s*\)',
        fn_chips
    ))
    check("D217-send-call",
          "_sendKnowledgeFeedback(responseId, type) called inside sub-type forEach",
          has_generic_send)
else:
    for ftype in ("TOO_VAGUE", "WRONG", "OUTDATED"):
        check(f"D217-{ftype}", f"'{ftype}' literal", False, "addFeedbackChips not found")
        check(f"D217-label-{ftype}", f"label check", False, "addFeedbackChips not found")
    check("D217-send-call", "_sendKnowledgeFeedback(responseId, type) call", False,
          "addFeedbackChips not found")

# ── D218  clarify guard: assistant message, no chips ──────────────
print("\n[D218] clarify type → assistant message, no chips")

has_clarify_guard = bool(re.search(r'data\.type\s*===\s*["\']clarify["\']', js_src))
check("D218a", "explicit type === 'clarify' guard exists in source", has_clarify_guard)

# Guard must appear BEFORE the answer branch
m_clar = re.search(r'data\.type\s*===\s*["\']clarify["\']', js_src)
m_ans  = re.search(r'data\.type\s*===\s*["\']answer["\']', js_src)
if m_clar and m_ans:
    check("D218b", "clarify guard appears before answer branch in source",
          m_clar.start() < m_ans.start())
else:
    check("D218b", "clarify guard appears before answer branch in source", False,
          f"clarify found={m_clar is not None} answer found={m_ans is not None}")

# Clarify block must NOT call addFeedbackChips
clarify_block_m = re.search(
    r'data\.type\s*===\s*["\']clarify["\'].*?return\s*;',
    js_src,
    re.DOTALL
)
if clarify_block_m:
    clar_block = clarify_block_m.group(0)
    no_chips = "addFeedbackChips" not in clar_block
    check("D218c", "clarify branch does NOT call addFeedbackChips", no_chips)
    has_text = bool(re.search(r'data\.text', clar_block))
    check("D218d", "clarify branch displays data.text as assistant message", has_text)
else:
    check("D218c", "clarify branch does NOT call addFeedbackChips", False,
          "clarify block not found in source")
    check("D218d", "clarify branch displays data.text", False, "clarify block not found")

# ── D219  action/proposal path gets no chips ─────────────────────
print("\n[D219] action/proposal path gets no chips")

# addFeedbackChips should appear exactly once in the JS source (answer branch + definition)
# The call site should be 1 (answer branch); the definition is in addFeedbackChips body itself.
# Calls from answer branch: count occurrences in handleSandboxChat context only.
# Simple rule: addFeedbackChips(wrap, ... ) call appears exactly once outside its own definition.
call_sites = re.findall(r'addFeedbackChips\s*\(', js_src)
# One call in answer branch, one in the function definition line — total 2 references
# (the definition `function addFeedbackChips(` and the call `addFeedbackChips(wrap,`)
definition_refs = len(re.findall(r'function\s+addFeedbackChips\s*\(', js_src))
call_refs = len(call_sites)
# call_refs counts both the call site AND any internal recursive calls; definition is separate
# Expected: 1 call (answer branch) and 1 definition = 2 total for `addFeedbackChips(`
check("D219a", "addFeedbackChips called exactly once (answer branch only)",
      call_refs == 1 + definition_refs,
      f"call occurrences={call_refs} definition={definition_refs}")

# buildProposalDOM must still be present (action path intact)
check("D219b", "buildProposalDOM still present (action path not broken)",
      "buildProposalDOM" in js_src)

# ACTION_REGISTRY.find still in source (action routing intact)
check("D219c", "ACTION_REGISTRY.find still in source (action routing intact)",
      "ACTION_REGISTRY.find" in js_src)

# ── D220  Backend files untouched; no forbidden wording ───────────
print("\n[D220] No backend/rag/memory files touched; no forbidden wording")

server_src = read_src(_SERVER_PY)
bridge_src = read_src(_BRIDGE_PY)

check("D220a", "harness_server.py has no Build 16 JS references",
      "addFeedbackChips" not in server_src and "fb-chips" not in server_src)
check("D220b", "conductor_bridge.py has no Build 16 JS references",
      "addFeedbackChips" not in bridge_src and "fb-chips" not in bridge_src)

for word in ["training data", "feedback dashboard", "survey"]:
    present = word.lower() in js_src.lower()
    check(f"D220-wording-{word[:9].replace(' ','_')}", f"no '{word}' wording in harness.js",
          not present)

# CSS classes must be defined in harness.html
for cls in (".fb-chips", ".fb-chip", ".fb-sub"):
    check(f"D220-css-{cls.strip('.')}", f"CSS class '{cls}' defined in harness.html",
          cls in html_src)

# .fb-chip:hover and .fb-chip[data-sent] must also be present
check("D220-css-hover", ".fb-chip:hover defined in harness.html", ".fb-chip:hover" in html_src)

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
