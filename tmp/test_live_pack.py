import urllib.request
import urllib.parse
import json

BRIDGE_URL = "http://localhost:4611/context/pack"

def get_context_pack(phrase):
    url = f"{BRIDGE_URL}?{urllib.parse.urlencode({'q': phrase})}"
    try:
        with urllib.request.urlopen(url, timeout=3) as r:
            res = json.loads(r.read())
            return True, res
    except Exception as e:
        return False, {"error": str(e)}

test_cases = [
    ("Pan the hi-hat to 30 percent right", "AUTO_EXECUTE_ALLOWED", True, False),
    ("Pan it right", "CLARIFY_REQUIRED", False, False),
    ("Create EQ on every track", "CONFIRM_REQUIRED", False, True),
    ("Add compression to every track", "CONFIRM_REQUIRED", False, True),
    ("Put EQ on all string tracks", "AUTO_EXECUTE_ALLOWED", True, False),
    ("Put compressor on all backing vocal tracks", "AUTO_EXECUTE_ALLOWED", True, False),
    ("Create guitar bus, pad bus and route them to Music Bus", "AUTO_EXECUTE_ALLOWED", True, False),
    ("Delete all muted tracks", "CONFIRM_REQUIRED", False, True),
    ("Export final master", "CONFIRM_REQUIRED", False, True)
]

print("--- TESTING LIVE BRIDGE /context/pack ENDPOINT ---")
all_ok = True

for phrase, exp_level, exp_auto, exp_confirm in test_cases:
    ok, res = get_context_pack(phrase)
    if not ok:
        print(f"\n❌ Request failed for: '{phrase}' - {res.get('error')}")
        all_ok = False
        continue
        
    got_level = res.get("protection_level")
    got_auto = res.get("auto_execute_allowed")
    got_confirm = res.get("confirmation_required")
    
    matches = (got_level == exp_level and got_auto is exp_auto and got_confirm is exp_confirm)
    sym = "✅" if matches else "❌"
    if not matches:
        all_ok = False
        
    print(f"\n{sym} Prompt: '{phrase}'")
    print(f"  Expected: level={exp_level:22} | auto={exp_auto} | confirm={exp_confirm}")
    print(f"  Got:      level={got_level:22} | auto={got_auto} | confirm={got_confirm}")
    print(f"  Mode:     {res.get('mode'):22} | Risk Cat: {res.get('risk_category')}")
    print(f"  Reason:   {res.get('rationale')}")

print("\n-------------------------------------------")
print(f"OVERALL LIVE BRIDGE RESULT: {'PASS' if all_ok else 'FAIL'}")
