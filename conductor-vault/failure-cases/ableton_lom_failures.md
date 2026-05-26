# Failure Cases — Ableton LOM
> Confirmed failures from production use. Retrieved before RISKY_WRITE actions.

---

## F001 — `song.create_group_track()` does not exist

**What broke:** Calling `song.create_group_track()` to group tracks programmatically.
**Error:** AttributeError — method doesn't exist in Live API.
**Why:** Ableton never exposed group track creation in the LOM.
**Fix:** Group tracks via UI only — Cmd+G. Or use an Audio bus track + manual routing.
**Confirmed:** Yes.
**Never do:** Do not attempt `create_group_track()` or any variation.

---

## F002 — MIDI bus captures silence

**What broke:** Routing tracks to a MIDI track as a bus, expecting audio passthrough.
**Error:** No audio. MIDI tracks have `has_audio_input: False`.
**Why:** MIDI tracks process MIDI only. Audio doesn't pass through them.
**Fix:** Always use Audio tracks as bus tracks. Never MIDI.
**Confirmed:** Yes.
**Never do:** Never create a MIDI track as a bus for audio routing.

---

## F003 — `create_audio_track()` serialization error

**What broke:** Creating an audio track via LOM — got a serialization error in return.
**Error:** Serialization error on return value.
**Why:** Cosmetic error — the track IS created. Ableton returns before serialization completes.
**Fix:** After the call, run `len(song.tracks)` to confirm the track was created.
**Confirmed:** Yes.
**Never do:** Don't treat the serialization error as a hard failure — verify with `len(song.tracks)`.

---

## F004 — `delete_selected_notes()` doesn't exist

**What broke:** Trying to delete notes from a clip.
**Error:** AttributeError.
**Fix:** Use `clip.remove_notes(start_time, pitch, duration, 128)` instead.
**Full wipe:** `clip.remove_notes(0, 0, clip.length, 128)` removes all notes.
**Confirmed:** Yes.

---

## F005 — VST3 plugins: only 1 LOM param

**What broke:** Trying to control Pro-Q 4 / Serum bands via `device.parameters`.
**Error:** Only one generic parameter available — not the actual plugin params.
**Why:** Ableton's LOM exposes only a single "macro" param for VST3/AU third-party plugins.
**Fix:** Use PluginBridge MCP (`set_params`, `get_params`) for all third-party plugins.
**Confirmed:** Yes.
**Never do:** Never try to control Pro-Q 4, Serum, Ozone params via Ableton LOM.

---

## F006 — Bus monitoring: Monitor:In before No Input = feedback loop

**What broke:** Setting a bus track to Monitor:In, then setting No Input.
**Error:** Focusrite feedback loop — loud noise.
**Why:** When Monitor:In is active with audio input still connected, signal loops.
**Fix:** ALWAYS in this order: (1) Set to No Input first, (2) THEN set Monitor:In.
**Confirmed:** Yes.
**Rule locked in:** never_do_rules.md → "Never set Monitor:In before No Input."

---

_Add new failures here as they are discovered. One section per confirmed failure._
