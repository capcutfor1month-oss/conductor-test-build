import urllib.request
import urllib.parse
import json
import time

BRIDGE_URL = "http://localhost:4611/memory"

def post_memory(text, collection, mode=None, metadata=None):
    data = {
        "text": text,
        "collection": collection
    }
    if mode is not None:
        data["mode"] = mode
    if metadata is not None:
        data["metadata"] = metadata
    
    req = urllib.request.Request(
        BRIDGE_URL,
        data=json.dumps(data).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=3) as r:
            res = json.loads(r.read())
            return True, res
    except Exception as e:
        return False, {"error": str(e)}

print("--- TESTING FRESH LIVE WRITE-TIME SUPERSESSION (C3) ---")

ts = int(time.time())
# Inject a unique tag so they are treated as fresh entries
unique_tag = f"tag_{ts}"
old_txt = f"compress snare fast attack slow release parallel compression punch technique {unique_tag}"
new_txt = f"compress snare fast attack slow release parallel compression punch corrected improved {unique_tag}"

# 1. Seed old memory
ok_old, res_old = post_memory(
    old_txt, 
    "producer", 
    mode="INTERN_WRITE_SAFE", 
    metadata={"source_type": "confirmed_preference", "confidence": 0.8, "created_at": str(time.time() - 86400 * 10)}
)
old_id = res_old.get("id")
print(f"\nSeeded old memory:")
print(f"  ok: {ok_old} | id: {old_id}")

# Let ChromaDB index
time.sleep(0.3)

# 2. Add new contradicting memory
ok_new, res_new = post_memory(
    new_txt, 
    "producer", 
    mode="INTERN_WRITE_SAFE", 
    metadata={"source_type": "confirmed_preference", "confidence": 0.9}
)
new_id = res_new.get("id")
superseded = res_new.get("superseded", [])
print(f"\nAdded contradicting new memory:")
print(f"  ok: {ok_new} | id: {new_id}")
print(f"  Superseded returned in response: {superseded}")

# 3. Check if old_id was superseded
is_ok = ok_new and old_id in superseded
print(f"\nC3 write-time verification:")
print(f"  Result: {'PASS' if is_ok else 'FAIL'}")
