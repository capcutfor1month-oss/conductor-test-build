#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
#  Conductor — Test Runner
#  Run all Phase C and Phase D eval suites.
#
#  IMPORTANT: Must use the chromadb pipx venv Python — NOT system python3.
#  Reason: the venv has chromadb + rank-bm25; system Python (Homebrew 3.14)
#  is externally managed and cannot install packages system-wide.
#
#  Usage:
#    bash tools/run_tests.sh              # all suites
#    bash tools/run_tests.sh phase_c      # single suite by keyword
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
ROOT="$( dirname "$SCRIPT_DIR" )"

# ── Python selection (mirrors start_bridge.sh) ────────────────────────────────
CHROMA_PY_T7="/Volumes/T7 Shield/Users/Aditya/.local/pipx/venvs/chromadb/bin/python3"
CHROMA_PY_HOME="$HOME/.local/pipx/venvs/chromadb/bin/python3"

if [ -x "$CHROMA_PY_T7" ]; then
    PYTHON="$CHROMA_PY_T7"
elif [ -x "$CHROMA_PY_HOME" ]; then
    PYTHON="$CHROMA_PY_HOME"
else
    echo "  ⚠  chromadb venv not found — falling back to system python3."
    echo "     BM25 tests will soft-skip. Run: pipx install chromadb && pipx inject chromadb rank-bm25"
    PYTHON="python3"
fi

echo ""
echo "  Conductor Test Runner"
echo "  Python  : $PYTHON"
echo "  Root    : $ROOT"
echo ""

# ── Suite list ────────────────────────────────────────────────────────────────
SUITES=(
    "tests/phase_c_eval_set.py"
    "tests/test_vault_integrity.py"
    "tests/phase_d_slice1_eval.py"
    "tests/phase_d_slice2_eval.py"
    "tests/phase_d_slice3_eval.py"
    "tests/phase_d_slice4_eval.py"
    "tests/phase_d_slice5_eval.py"
    "tests/phase_d_slice6_eval.py"
    "tests/phase_d_slice7_eval.py"
    "tests/phase_d_slice8_eval.py"
)

FILTER="${1:-}"
PASS=0
FAIL=0
ERRORS=()

for suite in "${SUITES[@]}"; do
    # Optional keyword filter
    if [ -n "$FILTER" ] && [[ "$suite" != *"$FILTER"* ]]; then
        continue
    fi

    echo "─────────────────────────────────────────────"
    echo "  Running: $suite"
    echo "─────────────────────────────────────────────"

    cd "$ROOT" && "$PYTHON" "$suite"
    EXIT=$?

    if [ $EXIT -eq 0 ]; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        ERRORS+=("$suite")
    fi
    echo ""
done

# ── Summary ───────────────────────────────────────────────────────────────────
echo "══════════════════════════════════════════════"
echo "  Test run complete"
echo "  Passed : $PASS"
echo "  Failed : $FAIL"
if [ ${#ERRORS[@]} -gt 0 ]; then
    echo "  Failing suites:"
    for e in "${ERRORS[@]}"; do echo "    ✗  $e"; done
fi
echo "══════════════════════════════════════════════"

[ $FAIL -eq 0 ]   # exit 0 on all pass, 1 on any fail
