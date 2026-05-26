import urllib.request
import urllib.parse
import json

BRIDGE_URL = "http://localhost:4611/memory"

def post_memory(text, collection, mode=None):
    data = {
        "text": text,
        "collection": collection
    }
    if mode is not None:
        data["mode"] = mode
    
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
    except urllib.error.HTTPError as e:
        try:
            res = json.loads(e.read())
            return False, res
        except:
            return False, {"error": e.reason}
    except Exception as e:
        return False, {"error": str(e)}

# Test live guard cases
print("--- TESTING LIVE FREEFORM WRITE GUARD ---")

# 1. Blocked: FREEFORM_GENERAL mode + project-session index
ok1, res1 = post_memory("Should fail", "project", mode="FREEFORM_GENERAL")
print(f"\nCase 1: FREEFORM_GENERAL + project")
print(f"  Result: {'Blocked (PASS)' if not ok1 and res1.get('error') == 'freeform_write_blocked' else 'FAILED'}")
print(f"  Response: {res1}")

# 2. Blocked: FREEFORM_GENERAL mode + project_session_index (full name)
ok2, res2 = post_memory("Should fail", "project_session_index", mode="FREEFORM_GENERAL")
print(f"\nCase 2: FREEFORM_GENERAL + project_session_index")
print(f"  Result: {'Blocked (PASS)' if not ok2 and res2.get('error') == 'freeform_write_blocked' else 'FAILED'}")
print(f"  Response: {res2}")

# 3. Allowed: FREEFORM_GENERAL mode + producer collection (cross-session preference)
ok3, res3 = post_memory("Vocal EQ preference", "producer", mode="FREEFORM_GENERAL")
print(f"\nCase 3: FREEFORM_GENERAL + producer")
print(f"  Result: {'Allowed (PASS)' if ok3 else 'FAILED'}")
print(f"  Response: {res3}")

# 4. Allowed: SESSION_MODE (e.g. INTERN_READ) + project collection
ok4, res4 = post_memory("Arrangement layout notes", "project", mode="INTERN_READ")
print(f"\nCase 4: SESSION_MODE (INTERN_READ) + project")
print(f"  Result: {'Allowed (PASS)' if ok4 else 'FAILED'}")
print(f"  Response: {res4}")
