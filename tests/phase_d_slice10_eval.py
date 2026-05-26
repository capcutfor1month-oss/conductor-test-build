"""
Phase D — Slice 10: GET /session/state Eval Suite
Sections D109–D114

Covers:
  D109  Connected — response shape (all required keys present and typed)
  D110  Disconnected — 503, ok=False, ableton_connected=False
  D111  Empty tracks / return_tracks — 200 with empty lists, not an error
  D112  selected_track read failure — null in response, NOT 500
  D113  state_completeness always present; clips/devices/routing = "not_available_v1"
  D114  Track type honesty:
          has_midi_input=True  → "midi"
          has_audio_input=True → "audio"
          neither/unknown      → "unknown"
          no is_midi_track fallback allowed
"""

import os
import sys
import importlib
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


def _make_track(index, name, track_type):
    """Build a single track dict as the LOM eval would return it.
    track_type must be one of "midi", "audio", "unknown".
    """
    return {
        "index":  index,
        "name":   name,
        "type":   track_type,
        "muted":  False,
        "soloed": False,
        "arm":    False,
    }


def _typical_state(track_count=3, return_count=2):
    """Build a realistic state dict the LOM eval would return.
    Uses all three type values ("midi", "audio", "unknown") so tests
    verify the endpoint passes them through unchanged.
    """
    type_cycle = ("midi", "audio", "unknown")
    tracks = [
        _make_track(i, f"Track {i + 1}", type_cycle[i % 3])
        for i in range(track_count)
    ]
    returns = [
        {"index": i, "name": f"Return {i + 1}"}
        for i in range(return_count)
    ]
    return {
        "tempo":          128.0,
        "time_signature": "4/4",
        "playing":        False,
        "record":         False,
        "tracks":         tracks,
        "return_tracks":  returns,
    }


# ══════════════════════════════════════════════════════════════════════════════
# D109 — Connected response shape
# ══════════════════════════════════════════════════════════════════════════════

@section("D109")
def run_d109():
    print("=== Section D109: GET /session/state connected — response shape ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    state  = _typical_state(track_count=3, return_count=2)
    sel_ok = _ableton_ok("Kick")

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(state), sel_ok]
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data captured")
        for e in errors:
            print(f"  {FAIL} [D109] {e}")
        print("  D109: FAIL")
        return False

    # Required top-level keys
    required_keys = [
        "ok", "ableton_connected", "source",
        "tempo", "time_signature", "playing", "record",
        "selected_track", "tracks", "return_tracks",
        "state_completeness",
    ]
    for k in required_keys:
        if k not in d:
            errors.append(f"missing key: {k!r}")

    if d.get("ok") is not True:
        errors.append(f"ok={d.get('ok')!r}, expected True")
    if d.get("ableton_connected") is not True:
        errors.append(f"ableton_connected={d.get('ableton_connected')!r}, expected True")
    if d.get("source") != "ableton_mcp":
        errors.append(f"source={d.get('source')!r}, expected 'ableton_mcp'")
    if d.get("tempo") != 128.0:
        errors.append(f"tempo={d.get('tempo')!r}, expected 128.0")
    if d.get("time_signature") != "4/4":
        errors.append(f"time_signature={d.get('time_signature')!r}, expected '4/4'")
    if d.get("playing") is not False:
        errors.append(f"playing={d.get('playing')!r}, expected False")
    if d.get("record") is not False:
        errors.append(f"record={d.get('record')!r}, expected False")
    if d.get("selected_track") != "Kick":
        errors.append(f"selected_track={d.get('selected_track')!r}, expected 'Kick'")

    # Tracks shape — type must be one of the three honest values
    _VALID_TYPES = {"midi", "audio", "unknown"}
    tracks = d.get("tracks", [])
    if len(tracks) != 3:
        errors.append(f"tracks len={len(tracks)}, expected 3")
    for t in tracks:
        for tk in ("index", "name", "type", "muted", "soloed", "arm"):
            if tk not in t:
                errors.append(f"track[{t.get('index')}] missing key {tk!r}")
        if t.get("type") not in _VALID_TYPES:
            errors.append(
                f"track[{t.get('index')}] type={t.get('type')!r}, "
                f"must be one of {sorted(_VALID_TYPES)}"
            )

    # Return tracks shape
    returns = d.get("return_tracks", [])
    if len(returns) != 2:
        errors.append(f"return_tracks len={len(returns)}, expected 2")
    for r in returns:
        for rk in ("index", "name"):
            if rk not in r:
                errors.append(f"return_tracks[{r.get('index')}] missing key {rk!r}")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D109] {e}")
        print("  D109: FAIL")
        return False

    print(f"  {PASS} [D109] /session/state connected — shape correct, all three types accepted")
    print("  D109: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D110 — Disconnected → 503
# ══════════════════════════════════════════════════════════════════════════════

@section("D110")
def run_d110():
    print("=== Section D110: GET /session/state disconnected → 503 ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=False):
        with _mock.patch.object(bridge_mod, "ableton_execute") as exec_mock:
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

            if exec_mock.call_count != 0:
                errors.append(
                    f"ableton_execute called {exec_mock.call_count} time(s) "
                    "when disconnected — must not be called"
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
            errors.append("error field missing or empty")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D110] {e}")
        print("  D110: FAIL")
        return False

    print(f"  {PASS} [D110] disconnected → 503, ok=False, ableton_connected=False, execute not called")
    print("  D110: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D111 — Empty tracks / return_tracks → 200, not an error
# ══════════════════════════════════════════════════════════════════════════════

@section("D111")
def run_d111():
    print("=== Section D111: GET /session/state empty tracks → 200 ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    empty_state = {
        "tempo":          120.0,
        "time_signature": "4/4",
        "playing":        False,
        "record":         False,
        "tracks":         [],
        "return_tracks":  [],
    }

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(empty_state), _ableton_ok("Master")]
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200 for empty session")
    if d is None:
        errors.append("no response data")
    else:
        if d.get("ok") is not True:
            errors.append(f"ok={d.get('ok')!r}, expected True")
        if d.get("tracks") != []:
            errors.append(f"tracks={d.get('tracks')!r}, expected []")
        if d.get("return_tracks") != []:
            errors.append(f"return_tracks={d.get('return_tracks')!r}, expected []")
        if "state_completeness" not in d:
            errors.append("state_completeness missing on empty-tracks response")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D111] {e}")
        print("  D111: FAIL")
        return False

    print(f"  {PASS} [D111] empty tracks/returns → 200, ok=True")
    print("  D111: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D112 — selected_track read failure → null in response, NOT 500
# ══════════════════════════════════════════════════════════════════════════════

@section("D112")
def run_d112():
    print("=== Section D112: selected_track failure → null, not 500 ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    state = _typical_state(track_count=2, return_count=1)

    # Sub-case A: second call returns ok=False
    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(state), _ableton_err("view not accessible")]
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data
    if h._cap_code == 500:
        errors.append("sub-case A: selected_track read failure → 500 (must be 200 with null)")
    elif h._cap_code == 200:
        if d and d.get("selected_track") is not None:
            errors.append(
                f"sub-case A: selected_track={d.get('selected_track')!r} "
                "on read failure, expected None/null"
            )
    else:
        errors.append(f"sub-case A: unexpected HTTP {h._cap_code}")

    # Sub-case B: second call returns ok=True but result is None
    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(state), _ableton_ok(None)]
        ):
            h2 = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h2.do_GET()

    d2 = h2._cap_data
    if h2._cap_code != 200:
        errors.append(f"sub-case B: HTTP {h2._cap_code}, expected 200")
    if d2 and d2.get("selected_track") is not None:
        errors.append(
            f"sub-case B: selected_track={d2.get('selected_track')!r} "
            "when LOM returned None, expected null"
        )
    if d2 and d2.get("ok") is not True:
        errors.append(f"sub-case B: ok={d2.get('ok')!r}, expected True")

    if errors:
        for e in errors:
            print(f"  {FAIL} [D112] {e}")
        print("  D112: FAIL")
        return False

    print(f"  {PASS} [D112] selected_track failure → null, not 500 (both sub-cases)")
    print("  D112: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D113 — state_completeness always present; correct values
# ══════════════════════════════════════════════════════════════════════════════

@section("D113")
def run_d113():
    print("=== Section D113: state_completeness always present, correct values ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    _EXPECTED_FULL    = {"tracks", "return_tracks", "tempo"}
    _EXPECTED_BEST    = {"selected_track"}
    _EXPECTED_UNAVAIL = {"clips", "devices", "routing"}
    _UNAVAIL_VALUE    = "not_available_v1"

    state = _typical_state()

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(state), _ableton_ok("Lead Vox")]
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data

    if h._cap_code != 200:
        errors.append(f"HTTP {h._cap_code}, expected 200")

    if d is None:
        errors.append("no response data")
        for e in errors:
            print(f"  {FAIL} [D113] {e}")
        print("  D113: FAIL")
        return False

    sc = d.get("state_completeness")
    if not isinstance(sc, dict):
        errors.append(f"state_completeness={sc!r}, expected dict")
    else:
        for key in _EXPECTED_FULL:
            if sc.get(key) != "full":
                errors.append(f"state_completeness[{key!r}]={sc.get(key)!r}, expected 'full'")
        for key in _EXPECTED_BEST:
            if sc.get(key) != "best_effort":
                errors.append(
                    f"state_completeness[{key!r}]={sc.get(key)!r}, expected 'best_effort'"
                )
        for key in _EXPECTED_UNAVAIL:
            if sc.get(key) != _UNAVAIL_VALUE:
                errors.append(
                    f"state_completeness[{key!r}]={sc.get(key)!r}, "
                    f"expected {_UNAVAIL_VALUE!r} — do not represent unavailable data as empty"
                )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D113] {e}")
        print("  D113: FAIL")
        return False

    print(f"  {PASS} [D113] state_completeness: full/best_effort/not_available_v1 all correct")
    print("  D113: PASS")
    return True


# ══════════════════════════════════════════════════════════════════════════════
# D114 — Track type honesty
#   has_midi_input=True  → "midi"
#   has_audio_input=True → "audio"
#   neither              → "unknown"
#   No is_midi_track fallback in the LOM code string
# ══════════════════════════════════════════════════════════════════════════════

@section("D114")
def run_d114():
    print("=== Section D114: track type honesty — midi/audio/unknown, no is_midi_track fallback ===")

    bridge_mod = importlib.import_module("tools.conductor_bridge")
    errors = []

    # ── Part A: verify the LOM code string uses the correct properties ─────────
    # Read the module source to confirm is_midi_track is absent from the
    # session/state code path and has_midi_input / has_audio_input are present.
    import inspect
    source = inspect.getsource(bridge_mod)

    # Extract just the /session/state handler block heuristically — search for
    # the _main_code string definition within a safe window.
    ss_idx = source.find("/session/state")
    if ss_idx == -1:
        errors.append("[A] /session/state not found in bridge source")
    else:
        # Look at the 3000 chars after the endpoint comment for the code string
        window = source[ss_idx: ss_idx + 3000]
        if "is_midi_track" in window:
            errors.append(
                "[A] LOM code string still contains 'is_midi_track' — "
                "this defaults unknown tracks to MIDI, violating session-state honesty"
            )
        if "has_midi_input" not in window:
            errors.append(
                "[A] LOM code string missing 'has_midi_input' — "
                "must use this to classify MIDI tracks"
            )
        if "has_audio_input" not in window:
            errors.append(
                "[A] LOM code string missing 'has_audio_input' — "
                "must use this to classify audio tracks"
            )
        if "'unknown'" not in window:
            errors.append(
                "[A] LOM code string missing 'unknown' fallback — "
                "tracks with neither input type must not be silently classified"
            )

    # ── Part B: endpoint passes through all three types unchanged ──────────────
    # The LOM eval runs inside Ableton; in tests we return pre-classified dicts.
    # This proves the endpoint does not re-map types on the way out.
    typed_state = {
        "tempo":          120.0,
        "time_signature": "4/4",
        "playing":        False,
        "record":         False,
        "tracks": [
            _make_track(0, "Synth",   "midi"),
            _make_track(1, "Guitar",  "audio"),
            _make_track(2, "Group",   "unknown"),
        ],
        "return_tracks": [],
    }

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(typed_state), _ableton_ok("Synth")]
        ):
            h = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h.do_GET()

    d = h._cap_data
    if h._cap_code != 200:
        errors.append(f"[B] HTTP {h._cap_code}, expected 200")
    elif d:
        tracks = d.get("tracks", [])
        if len(tracks) != 3:
            errors.append(f"[B] expected 3 tracks, got {len(tracks)}")
        else:
            expected_types = [
                (0, "Synth",  "midi"),
                (1, "Guitar", "audio"),
                (2, "Group",  "unknown"),
            ]
            for idx, name, expected_type in expected_types:
                t = tracks[idx]
                actual = t.get("type")
                if actual != expected_type:
                    errors.append(
                        f"[B] track[{idx}] '{name}': type={actual!r}, "
                        f"expected {expected_type!r} — "
                        "endpoint must not remap types returned by LOM"
                    )

    # ── Part C: "unknown" must not silently become "midi" ─────────────────────
    # Specifically test that a state with only "unknown" tracks survives intact.
    unknown_state = {
        "tempo":          100.0,
        "time_signature": "3/4",
        "playing":        True,
        "record":         False,
        "tracks": [
            _make_track(0, "Group Bus", "unknown"),
            _make_track(1, "Master Aux", "unknown"),
        ],
        "return_tracks": [],
    }

    with _mock.patch.object(bridge_mod, "ableton_connected", return_value=True):
        with _mock.patch.object(
            bridge_mod, "ableton_execute",
            side_effect=[_ableton_ok(unknown_state), _ableton_ok(None)]
        ):
            h2 = _make_mock_h(bridge_mod.ConductorHandler, "/session/state")
            h2.do_GET()

    d2 = h2._cap_data
    if h2._cap_code != 200:
        errors.append(f"[C] HTTP {h2._cap_code}, expected 200")
    elif d2:
        for t in d2.get("tracks", []):
            if t.get("type") != "unknown":
                errors.append(
                    f"[C] track '{t.get('name')}' type={t.get('type')!r}, "
                    "expected 'unknown' — must not default to 'midi'"
                )

    if errors:
        for e in errors:
            print(f"  {FAIL} [D114] {e}")
        print("  D114: FAIL")
        return False

    print(f"  {PASS} [D114] track types: midi/audio/unknown correct; no is_midi_track fallback")
    print("  D114: PASS")
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
    print(f"Phase D Slice 10 — GET /session/state: {passed}/{total} sections PASS")
    if passed == total:
        print("OVERALL: PASS")
    else:
        print("OVERALL: FAIL")
        sys.exit(1)


if __name__ == "__main__":
    main()
