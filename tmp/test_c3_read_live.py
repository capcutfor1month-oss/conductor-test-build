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

print("--- QUERYING LIVE BRIDGE FOR CONFLICT QUERY ---")
phrase = "what Q should I use for vocal presence cut"
ok, res = get_context_pack(phrase)

if not ok:
    print(f"Error querying live bridge: {res.get('error')}")
    exit(1)

print("\nSuccess! Got context pack.")
debug_data = res.get("debug", {})
evidence = debug_data.get("evidence", [])

print(f"\nTotal retrieved evidence items: {len(evidence)}")
for i, item in enumerate(evidence):
    print(f"\n[Item #{i+1}] ID: {item.get('id')}")
    print(f"  Text: {item.get('text')[:60]}...")
    print(f"  Collection: {item.get('collection')}")
    print(f"  Similarity: {item.get('similarity')}")
    print(f"  Final Score: {item.get('final_score')}")
    print(f"  Injected: {item.get('injected')}")
    print(f"  Superseded: {item.get('superseded')}")
    print(f"  Superseded By: {item.get('superseded_by')}")
    print(f"  Skip Reason: {item.get('skip_reason')}")
