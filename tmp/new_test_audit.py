import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from rag.protection_model import classify_protection

test_cases = [
    "Pan the hi-hat to 30 percent right",
    "Pan it right",
    "Create EQ on every track",
    "Add compression to every track",
    "Put EQ on all string tracks",
    "Put compressor on all backing vocal tracks",
    "Create guitar bus, pad bus and route them to Music Bus",
    "Delete all muted tracks",
    "Export final master"
]

print("--- CLAUDE FIXED BACKEND AUDIT CHECK ---")
for phrase in test_cases:
    res = classify_protection(phrase)
    print(f"\nPrompt: '{phrase}'")
    print(f"  Level:    {res['protection_level']:22} | Category: {res['risk_category']}")
    print(f"  Auto:     {res['auto_execute_allowed']} | Confirm:  {res['confirmation_required']}")
    print(f"  Reason:   {res['rationale']}")
