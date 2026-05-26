import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from rag.protection_model import classify_protection

test_cases = [
    # Safe additive
    "Create a new Omnisphere track with a warm pad.",
    "Load Omnisphere on a new track.",
    "Create guitar bus, pad bus, bass bus, string bus and route them to Music Bus.",
    "Lower the kick by 1 dB.",
    "Rename all guitar tracks cleanly.",
    # Reversible medium
    "Replace the current lead patch with Omnisphere.",
    "Randomize this Serum patch.",
    # Unclear pronouns
    "Lower it by 1 dB.",
    "Route it to the bus.",
    "Make it warmer.",
    "Turn it down.",
    "Compress it.",
    # Pan missing
    "Pan the hi-hat to 30 percent right.",
    "Pan it.",
    # Batch overrides
    "Add compression to every track.",
    "Add reverb on every track.",
    "Add Pro-Q to every vocal track.",
    "Create EQ on every track.",
    "Add saturation to all tracks.",
    # High-risk
    "Delete all muted tracks.",
    "Flatten every MIDI track.",
    "Push master to -7 LUFS.",
    "Export final master.",
    # Unsupported GUI
    "Open the plugin GUI and drag the wavetable by hand."
]

print("--- AUDIT TEST CASES ---")
for tc in test_cases:
    res = classify_protection(tc)
    print(f"\nPrompt: '{tc}'")
    print(f"  Protection Level: {res['protection_level']}")
    print(f"  Risk Category:    {res['risk_category']}")
    print(f"  Auto Execute:     {res['auto_execute_allowed']}")
    print(f"  Confirm Req:      {res['confirmation_required']}")
    print(f"  Rationale:        {res['rationale']}")
