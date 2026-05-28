"""
Phase D — Slice 13: GET /session/state v1.5 Eval Suite
Sections D128–D134

Covers:
  D128  v1.5 response shape — new fields present (selected_device, track/return
         devices, clip_count, active_send_count, is_group_track, in_group)
  D129  state_completeness v1.5 — new keys present and correctly valued;
         v1 legacy keys unchanged (D113 regression guardrail)
  D130  Optional field failure tolerance — calls 3–6 fail → still 200,
         base fields intact, completeness = "unavailable" for failed fields
  D131  No writes — static source analysis of /session/state handler
  D132  Disconnected path unchanged — still 503, execute never called
  D133  v1 field regression — 2-call mock; all v1 fields intact
  D134  Group structure — is_group_track / in_group per track dict
"""

import os
import sys
import importlib
import inspect
import unittest.mock as _mock

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"

SECTIONS = {}


def section(label):
    def decorator(fn):
        SECTIONS[label] = fn
        return fn
    return decorator


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_mock_h(ConductorHandler, path_str):
    """GET handler — no request body."""
    class _MockH(ConductorHandler):
        def __init__(self, path):
            self.path      = path
            self.headers   = {}
            self._cap_data = None
            self._cap_code = None
        def _send_json(self, data, code=200):
            self._cap_data = data
            self._cap_code = code
            return None
        def log_message(self, *a):
            pass
    return _MockH(path_str)


def _ableton_ok(result):
    """Simulate a successful ableton_execute() response."""
    return {
        "ok":       True,
        "source":   "ableton",
        "data":     {"status": "ok", "result": result},
        "verified": False,
        "error":    None,
    }


def _ableton_err(msg="mock error"):
    """Simulate a failed ableton_execute() response."""
    return {
        "ok":       False,
        "source":   "ableton",
        "data":     {"status": "error", "error": msg},
        "verified": False,
        "error":    msg,
    }


def _make_track_v15(index, name, track_type, is_group=False, in_group=False):
    """Build a v1.5 track dict as the LOM eval would return it."""
    return {
        "index":          index,
        "name":           name,
        "type":           track_type,
        "muted":          False,
        "soloed":         False,
        "arm":            False,
        "is_group_track": is_group,
        "in_group":       in_group,
    }


def _typical_state_v15(track_count=3, return_count=2):
    """Build a v1.5 state dict (includes is_group_track/in_group flags)."""
    type_cycle = ("midi", "audio", "unknown")
    tracks = [
        _make_track_v15(
            i, f"Track {i + 1}", type_cycle[i % 3],
            is_group=(i == 0), in_group=(i == 1),
        )
        for i in range(track_count)
    ]
    returns = [{"index": i, "name": f"Return {i + 1}"} for i in range(return_count)]
    return {
        "tempo":          128.0,
        "time_signature": "4/4",
        "playing":        False,
        "record":         False,
        "tracks":         tracks,
        "return_tracks":  returns,
    }


def _full_side_effects_ok(state, track_names, return_names):
    """
    Build the 6 mock side effects for a fully-successful v1.5 call chain.
      Call 1: main state
      Call 2: selected_track
      Call 3: selected_device
      Call 4: device names
      Call 5: clip counts
      Call 6: send activity
    """
    track_devs = {n: ["EQ Eight", "Compressor"] if i == 0 else ["Reverb"] if i == 1 else []
                  for i, n in enumerate(track_names)}
    return_devs = {n: ["Reverb"] if i == 0 else [] for i, n in enumerate(return_names)}
    dev_result = {"tracks": track_devs, "returns": return_devs}
    clip_counts = {n: i * 2 for i, n in enumerate(track_names)}   # 0, 2, 4, ...
    send_counts = {n: 2 if i == 0 else (1 if i == 1 else 0)
                   for i, n in enumerate(track_names)}
    return [
        _ableton_ok(state),              # Call 1: main state
        _ableton_ok("Track 1"),          # Call 2: selected track
        _ableton_ok("EQ Eight"),         # Call 3: selected device
        _ableton_ok(dev_result),         # Call 4: device names
        _ableton_ok(clip_counts),        # Call 5: clip counts
        _ableton_ok(send_counts),        # Call 6: send activity
    ]


# ══════════════════════════════════════════════════════════════════════════════
# D128 — v1.5 response shape: new fields present
# ══════════════════════════════════════════════════════════════════════════════

@section("D128")
def run_d128():
    print("=== Section D128: v1.5 response shape — new fields present ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    state = _typical_state_v15(track_count=3, return_count=2)
    track_names  = [t["name"] for t in state["tracks"]]
    return_names = [r["name"] for r in state["return_tracks"]]

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=_full_side_effects_ok(state, track_names, return_names),
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data captured")
        for e in errors:
            print(f"  {FAIL} [D128] {e}")
        print("  D128: FAIL")
        return False

    # selected_device must be present at top level
    if "selected_device" not in d:
        errors.append("top-level 'selected_device' key missing")
    elif d["selected_device"] != "EQ Eight":
        errors.append(
            f"selected_device={d['selected_device']!r}, expected 'EQ Eight'"
        )

    # Tracks: v1.5 fields
    tracks = d.get("tracks", [])
    if len(tracks) != 3:
        errors.append(f"tracks len={len(tracks)}, expected 3")
    else:
        for t in tracks:
            tname = t.get("name", "?")
            # is_group_track / in_group must be present (from Call 1)
            if "is_group_track" not in t:
                errors.append(f"track '{tname}' missing 'is_group_track'")
            if "in_group" not in t:
                errors.append(f"track '{tname}' missing 'in_group'")
            # devices injected by Call 4
            if "devices" not in t:
                errors.append(f"track '{tname}' missing 'devices' (Call 4)")
            elif not isinstance(t["devices"], list):
                errors.append(f"track '{tname}'.devices must be a list")
            # clip_count injected by Call 5
            if "clip_count" not in t:
                errors.append(f"track '{tname}' missing 'clip_count' (Call 5)")
            elif not isinstance(t["clip_count"], int):
                errors.append(f"track '{tname}'.clip_count must be int")
            # active_send_count injected by Call 6
            if "active_send_count" not in t:
                errors.append(f"track '{tname}' missing 'active_send_count' (Call 6)")
            elif not isinstance(t["active_send_count"], int):
                errors.append(f"track '{tname}'.active_send_count must be int")

    # Return tracks: devices injected by Call 4
    returns = d.get("return_tracks", [])
    if len(returns) != 2:
        errors.append(f"return_tracks len={len(returns)}, expected 2")
    else:
        for r in returns:
            rname = r.get("name", "?")
            if "devices" not in r:
                errors.append(f"return track '{rname}' missing 'devices' (Call 4)")
            elif not isinstance(r["devices"], list):
                errors.append(f"return track '{rname}'.devices must be a list")

    # Check specific device list for Track 1 (should be ["EQ Eight", "Compressor"])
    if tracks and "devices" in tracks[0]:
        t1_devs = tracks[0]["devices"]
        if t1_devs != ["EQ Eight", "Compressor"]:
            errors.append(
                f"Track 1 devices={t1_devs!r}, expected ['EQ Eight', 'Compressor']"
            )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D128] {e}")
        print("  D128: FAIL")
        return False

    print(f"  {PASS} [D128] v1.5 shape correct: selected_device, devices, clip_count, "
          "active_send_count, is_group_track, in_group all present")
    print("  D128: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D129 — state_completeness v1.5: new keys correct, legacy keys unchanged
# ══════════════════════════════════════════════════════════════════════════════

@section("D129")
def run_d129():
    print("=== Section D129: state_completeness v1.5 — new keys + legacy keys ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    state = _typical_state_v15(track_count=2, return_count=1)
    track_names  = [t["name"] for t in state["tracks"]]
    return_names = [r["name"] for r in state["return_tracks"]]

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=_full_side_effects_ok(state, track_names, return_names),
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D129] {e}")
        print("  D129: FAIL")
        return False

    sc = d.get("state_completeness")
    if not isinstance(sc, dict):
        errors.append(f"state_completeness={sc!r}, expected dict")
        for e in errors:
            print(f"  {FAIL} [D129] {e}")
        print("  D129: FAIL")
        return False

    # ── v1 "full" keys ─────────────────────────────────────────────────────
    for key in ("tempo", "time_signature", "playing", "record", "tracks", "return_tracks"):
        if sc.get(key) != "full":
            errors.append(
                f"[v1 full] state_completeness[{key!r}]={sc.get(key)!r}, expected 'full'"
            )

    # ── v1 "best_effort" key ────────────────────────────────────────────────
    if sc.get("selected_track") != "best_effort":
        errors.append(
            f"[v1 best_effort] state_completeness['selected_track']="
            f"{sc.get('selected_track')!r}, expected 'best_effort'"
        )

    # ── v1 legacy not-available keys (D113 regression guardrail) ───────────
    for key in ("clips", "devices", "routing"):
        if sc.get(key) != "not_available_v1":
            errors.append(
                f"[D113 regression] state_completeness[{key!r}]={sc.get(key)!r}, "
                "expected 'not_available_v1' — do NOT remove legacy keys"
            )

    # ── v1.5 new keys — all calls succeeded so all must be "best_effort" ───
    v15_best_effort = (
        "selected_device", "group_structure",
        "track_device_names", "return_device_names",
        "clip_counts", "send_activity",
    )
    for key in v15_best_effort:
        if key not in sc:
            errors.append(f"[v1.5] state_completeness missing key {key!r}")
        elif sc[key] != "best_effort":
            errors.append(
                f"[v1.5] state_completeness[{key!r}]={sc[key]!r}, "
                "expected 'best_effort' when call succeeded"
            )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D129] {e}")
        print("  D129: FAIL")
        return False

    print(f"  {PASS} [D129] state_completeness correct: "
          "v1 full/best_effort/not_available_v1 unchanged; "
          "v1.5 keys all 'best_effort'")
    print("  D129: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D130 — Optional field failure tolerance
#   Calls 3–6 fail (ok=False) → still 200, base fields intact,
#   completeness = "unavailable" for failed optional fields
# ══════════════════════════════════════════════════════════════════════════════

@section("D130")
def run_d130():
    print("=== Section D130: optional field failure tolerance ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    state = _typical_state_v15(track_count=2, return_count=1)

    failed_side_effects = [
        _ableton_ok(state),                   # Call 1: main state  — OK
        _ableton_ok("Track 1"),               # Call 2: selected track — OK
        _ableton_err("device view error"),    # Call 3: selected device — FAIL
        _ableton_err("devices load error"),   # Call 4: device names  — FAIL
        _ableton_err("clip slot error"),      # Call 5: clip counts   — FAIL
        _ableton_err("mixer error"),          # Call 6: send activity — FAIL
    ]

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=failed_side_effects,
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    # Must not 500
    if h._cap_code == 500:
        errors.append("optional field failures → 500 (must be 200, never 500)")
    elif h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200 despite optional failures")

    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D130] {e}")
        print("  D130: FAIL")
        return False

    # Base fields must still be present and correct
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("ableton_connected") is not True:
        errors.append(f"ableton_connected={d.get('ableton_connected')!r}, expected True")
    if d.get("tempo") != 128.0:
        errors.append(f"tempo={d.get('tempo')!r}, expected 128.0")
    if d.get("selected_track") != "Track 1":
        errors.append(f"selected_track={d.get('selected_track')!r}, expected 'Track 1'")
    if not isinstance(d.get("tracks"), list):
        errors.append("tracks not a list after optional failures")
    if not isinstance(d.get("return_tracks"), list):
        errors.append("return_tracks not a list after optional failures")

    # selected_device must be None when Call 3 failed
    if d.get("selected_device") is not None:
        errors.append(
            f"selected_device={d.get('selected_device')!r}, "
            "expected None when Call 3 failed"
        )

    # Tracks must NOT have devices/clip_count/active_send_count when calls failed
    for t in d.get("tracks", []):
        tname = t.get("name", "?")
        # is_group_track / in_group come from Call 1 — still OK
        if "is_group_track" not in t:
            errors.append(f"track '{tname}' missing is_group_track (came from Call 1)")
        # Optional fields must be absent (not None, absent)
        for optional_key in ("devices", "clip_count", "active_send_count"):
            if optional_key in t:
                errors.append(
                    f"track '{tname}' has {optional_key!r} when Call failed — "
                    "should be absent, not present with a bad value"
                )

    # state_completeness: optional v1.5 fields must be "unavailable"
    sc = d.get("state_completeness", {})
    for key in ("track_device_names", "return_device_names", "clip_counts", "send_activity"):
        if sc.get(key) != "unavailable":
            errors.append(
                f"state_completeness[{key!r}]={sc.get(key)!r}, "
                "expected 'unavailable' when call failed"
            )

    # Legacy v1 keys must still be correct
    if sc.get("clips") != "not_available_v1":
        errors.append(
            f"[D113 regression] state_completeness['clips']={sc.get('clips')!r}, "
            "expected 'not_available_v1'"
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D130] {e}")
        print("  D130: FAIL")
        return False

    print(f"  {PASS} [D130] optional failures tolerated: 200, base fields intact, "
          "optional keys absent, completeness='unavailable'")
    print("  D130: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D131 — No writes in /session/state handler
# ══════════════════════════════════════════════════════════════════════════════

@section("D131")
def run_d131():
    print("=== Section D131: static analysis — no writes in /session/state handler ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    source = inspect.getsource(bridge_mod)

    # Isolate the /session/state handler block heuristically.
    # Find the endpoint comment and take the window up to the next elif/else.
    ss_start = source.find("elif path == \"/session/state\"")
    if ss_start == -1:
        ss_start = source.find("path == \"/session/state\"")
    if ss_start == -1:
        errors.append("Could not locate /session/state handler in source")
        for e in errors:
            print(f"  {FAIL} [D131] {e}")
        print("  D131: FAIL")
        return False

    # Take the next 6000 chars — enough to cover all 6 calls
    window = source[ss_start: ss_start + 6000]

    # Find the end of the handler (next top-level elif / else at same indent)
    _end_markers = ["\n        elif path ==", "\n        else:"]
    _end_idx = len(window)
    for marker in _end_markers:
        idx = window.find(marker)
        if idx != -1 and idx < _end_idx:
            _end_idx = idx
    handler_block = window[:_end_idx]

    # Forbidden write patterns inside the LOM code strings
    # These are Python assignment operators that would appear in LOM code strings
    # if any write were accidentally included.
    FORBIDDEN = [
        "song.tempo =",
        "song.record_mode =",
        "song.is_playing =",
        "t.mute =",
        "t.solo =",
        "t.arm =",
        "t.name =",
        ".create_",
        ".delete_",
        ".duplicate_",
        ".fire(",
        ".stop(",
    ]

    for pattern in FORBIDDEN:
        if pattern in handler_block:
            errors.append(
                f"Forbidden write pattern {pattern!r} found in /session/state handler"
            )

    # The LOM code strings must only use read operations: .tempo, .tracks, etc.
    # Verify at least one read-only pattern is present
    if "song.tempo" not in handler_block:
        errors.append("Expected 'song.tempo' read not found in handler block")
    if "song.tracks" not in handler_block:
        errors.append("Expected 'song.tracks' read not found in handler block")

    # Verify song-property writes (song.X = ...) are absent.
    # Note: "variable = song.X" is a READ — only "song.X =" is a write.
    import re as _re
    # Match "song.<identifier> =" patterns (writes TO a song property).
    # Exclude "song.<identifier>." chaining which is a nested read.
    song_writes = _re.findall(r"\bsong\.\w+ =(?!=)", handler_block)
    if song_writes:
        errors.append(
            f"Potential LOM write(s) to song object: {song_writes!r}"
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D131] {e}")
        print("  D131: FAIL")
        return False

    print(f"  {PASS} [D131] static analysis: no write patterns found in /session/state handler")
    print("  D131: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D132 — Disconnected path unchanged → 503
# ══════════════════════════════════════════════════════════════════════════════

@section("D132")
def run_d132():
    print("=== Section D132: disconnected path unchanged → 503 ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False):
        with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

            if exec_mock.call_count != 0:
                errors.append(
                    f"ableton_execute called {exec_mock.call_count} time(s) "
                    "when disconnected — must not be called at all"
                )

    d = h._cap_data

    if h._cap_code != 503:
        errors.append(f"HTTP {h._cap_code}, expected 503")

    if d is None:
        errors.append("no response data")
    else:
        if d.get("ok") is not False:
            errors.append(f"ok={d.get('ok')!r}, expected False")
        if d.get("ableton_connected") is not False:
            errors.append(
                f"ableton_connected={d.get('ableton_connected')!r}, expected False"
            )
        if not d.get("error"):
            errors.append("error field missing or empty on disconnected response")
        # v1.5 must not add extra fields on disconnected path
        forbidden_keys = ("selected_device", "state_completeness", "tracks")
        for k in forbidden_keys:
            if k in d:
                errors.append(
                    f"disconnected response should not have {k!r} "
                    "(added in v1.5 but must not appear on 503 path)"
                )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D132] {e}")
        print("  D132: FAIL")
        return False

    print(f"  {PASS} [D132] disconnected → 503, ok=False, execute not called, "
          "no v1.5 fields on error path")
    print("  D132: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D133 — v1 field regression (2-call mock)
#   Provide only Calls 1+2 (as D109/D113 did). Calls 3–6 raise StopIteration
#   which the v1.5 try/except Exception blocks catch silently.
#   All v1 keys must still be correct; state_completeness legacy keys intact.
# ══════════════════════════════════════════════════════════════════════════════

@section("D133")
def run_d133():
    print("=== Section D133: v1 field regression — 2-call mock ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    # v1-style state (no is_group_track/in_group — simulates old LOM result)
    # The endpoint must tolerate missing optional keys in the returned dict.
    v1_state = {
        "tempo":          140.0,
        "time_signature": "3/4",
        "playing":        True,
        "record":         False,
        "tracks": [
            {"index": 0, "name": "Kick",   "type": "audio", "muted": False,
             "soloed": False, "arm": True},
            {"index": 1, "name": "Synth",  "type": "midi",  "muted": True,
             "soloed": False, "arm": False},
        ],
        "return_tracks": [
            {"index": 0, "name": "Reverb Bus"},
        ],
    }

    # Only 2 side effects — calls 3–6 will raise StopIteration (caught by v1.5 try/except)
    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(v1_state), _ableton_ok("Kick")],
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code == 500:
        errors.append(
            "2-call mock → 500 (v1.5 try/except must catch StopIteration "
            "from exhausted mock, never 500)"
        )
    elif h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D133] {e}")
        print("  D133: FAIL")
        return False

    # All v1 required keys must be present
    v1_required = [
        "ok", "ableton_connected", "source",
        "tempo", "time_signature", "playing", "record",
        "selected_track", "tracks", "return_tracks",
        "state_completeness",
    ]
    for k in v1_required:
        if k not in d:
            errors.append(f"v1 regression: key {k!r} missing")

    # v1 values correct
    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("tempo") != 140.0:
        errors.append(f"tempo={d.get('tempo')!r}, expected 140.0")
    if d.get("time_signature") != "3/4":
        errors.append(f"time_signature={d.get('time_signature')!r}, expected '3/4'")
    if d.get("playing") is not True:
        errors.append(f"playing={d.get('playing')!r}, expected True")
    if d.get("selected_track") != "Kick":
        errors.append(f"selected_track={d.get('selected_track')!r}, expected 'Kick'")

    tracks = d.get("tracks", [])
    if len(tracks) != 2:
        errors.append(f"tracks len={len(tracks)}, expected 2")
    if d.get("return_tracks") and len(d["return_tracks"]) != 1:
        errors.append(f"return_tracks len={len(d.get('return_tracks'))}, expected 1")

    # Track arm flag must pass through
    if tracks:
        kick = tracks[0]
        if kick.get("arm") is not True:
            errors.append(f"track[0].arm={kick.get('arm')!r}, expected True")
        synth = tracks[1]
        if synth.get("muted") is not True:
            errors.append(f"track[1].muted={synth.get('muted')!r}, expected True")

    # state_completeness legacy v1 keys intact
    sc = d.get("state_completeness", {})
    for key in ("clips", "devices", "routing"):
        if sc.get(key) != "not_available_v1":
            errors.append(
                f"[D113 regression] state_completeness[{key!r}]={sc.get(key)!r}, "
                "expected 'not_available_v1'"
            )
    for key in ("tempo", "tracks", "return_tracks"):
        if sc.get(key) != "full":
            errors.append(
                f"state_completeness[{key!r}]={sc.get(key)!r}, expected 'full'"
            )
    if sc.get("selected_track") != "best_effort":
        errors.append(
            f"state_completeness['selected_track']={sc.get('selected_track')!r}, "
            "expected 'best_effort'"
        )

    # v1.5 optional fields unavailable when calls 3–6 failed/exhausted
    for key in ("track_device_names", "return_device_names", "clip_counts", "send_activity"):
        if sc.get(key) != "unavailable":
            errors.append(
                f"state_completeness[{key!r}]={sc.get(key)!r}, "
                "expected 'unavailable' (calls 3–6 not mocked)"
            )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D133] {e}")
        print("  D133: FAIL")
        return False

    print(f"  {PASS} [D133] v1 regression: all v1 fields intact under 2-call mock; "
          "StopIteration caught silently")
    print("  D133: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D134 — Group structure: is_group_track / in_group per track dict
# ══════════════════════════════════════════════════════════════════════════════

@section("D134")
def run_d134():
    print("=== Section D134: group structure — is_group_track / in_group per track ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    # Build state with explicit group topology:
    #   Track 0 "Drum Group"  — is_group_track=True,  in_group=False
    #   Track 1 "Kick"        — is_group_track=False, in_group=True
    #   Track 2 "Snare"       — is_group_track=False, in_group=True
    #   Track 3 "Lead Vox"    — is_group_track=False, in_group=False
    group_state = {
        "tempo":          120.0,
        "time_signature": "4/4",
        "playing":        False,
        "record":         False,
        "tracks": [
            {"index": 0, "name": "Drum Group", "type": "audio",
             "muted": False, "soloed": False, "arm": False,
             "is_group_track": True,  "in_group": False},
            {"index": 1, "name": "Kick",       "type": "audio",
             "muted": False, "soloed": False, "arm": False,
             "is_group_track": False, "in_group": True},
            {"index": 2, "name": "Snare",      "type": "audio",
             "muted": False, "soloed": False, "arm": False,
             "is_group_track": False, "in_group": True},
            {"index": 3, "name": "Lead Vox",   "type": "midi",
             "muted": False, "soloed": False, "arm": True,
             "is_group_track": False, "in_group": False},
        ],
        "return_tracks": [],
    }

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(group_state), _ableton_ok("Lead Vox")],
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D134] {e}")
        print("  D134: FAIL")
        return False

    tracks = d.get("tracks", [])
    if len(tracks) != 4:
        errors.append(f"tracks len={len(tracks)}, expected 4")
    else:
        expected = [
            ("Drum Group", True,  False),
            ("Kick",       False, True),
            ("Snare",      False, True),
            ("Lead Vox",   False, False),
        ]
        for t, (exp_name, exp_is_group, exp_in_group) in zip(tracks, expected):
            tname = t.get("name")
            if tname != exp_name:
                errors.append(f"track name {tname!r}, expected {exp_name!r}")
                continue
            # is_group_track
            if "is_group_track" not in t:
                errors.append(f"track '{tname}' missing 'is_group_track'")
            elif t["is_group_track"] is not exp_is_group:
                errors.append(
                    f"track '{tname}' is_group_track={t['is_group_track']!r}, "
                    f"expected {exp_is_group!r}"
                )
            # in_group
            if "in_group" not in t:
                errors.append(f"track '{tname}' missing 'in_group'")
            elif t["in_group"] is not exp_in_group:
                errors.append(
                    f"track '{tname}' in_group={t['in_group']!r}, "
                    f"expected {exp_in_group!r}"
                )

    # state_completeness group_structure must be "best_effort" (always, since it
    # comes from Call 1 which always succeeds or fails the whole response)
    sc = d.get("state_completeness", {})
    if sc.get("group_structure") != "best_effort":
        errors.append(
            f"state_completeness['group_structure']={sc.get('group_structure')!r}, "
            "expected 'best_effort'"
        )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D134] {e}")
        print("  D134: FAIL")
        return False

    print(f"  {PASS} [D134] group structure: is_group_track / in_group pass through "
          "correctly for group, child, and flat tracks")
    print("  D134: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Runner
# ══════════════════════════════════════════════════════════════════════════════

def main():
    results = {}
    for label, fn in sorted(SECTIONS.items()):
        try:
            results[label] = fn()
        except Exception as exc:
            print(f"  {FAIL} [{label}] EXCEPTION: {exc}")
            import traceback; traceback.print_exc()
            results[label] = False
        print()

    passed = sum(1 for v in results.values() if v)
    total  = len(results)
    print("=" * 60)
    print(f"Phase D Slice 13 — /session/state v1.5: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
