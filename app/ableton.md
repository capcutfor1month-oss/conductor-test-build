# Conductor — Ableton Reference
> Primary reference for all Ableton-related tasks.
> Load this file when:
> - An Ableton task fails on first attempt
> - User is unsatisfied with an Ableton result
> - A task involves routing, buses, devices, or plugin control
>
> Updated automatically when errors.md identifies a new confirmed fix.
> Never guess when this file has a confirmed pattern.

---

## LOM HARD LIMITS

These are not bugs — they are permanent API constraints. Do not attempt workarounds.

| Limit | Detail | Correct Approach |
|---|---|---|
| No GROUP TRACKS via LOM | `song.create_group_track()` does not exist | Use Audio bus + routing. UI only: Cmd+G |
| BUS = AUDIO track only | MIDI bus has `has_audio_input: False` → captures silence | Always create Audio track for buses |
| VST3 = 1 param via LOM | Pro-Q 4, Serum 2 knobs unreachable via execute() | Use PluginBridge for full control |
| No `delete_selected_notes()` | Method does not exist | Use `clip.remove_notes(0, 0, clip.length, 128)` |
| `create_audio_track()` serialization error | Throws error but track IS created | Always verify with `len(song.tracks)` |
| No arbitrary file load via LOM | Cannot load samples or presets by file path | Use browser search + `load_to()` |

---

## EXECUTE() — RULES

**Timeout:** 10 seconds. One operation at a time. Never chain heavy loops.

**Keep results compact:**
```python
# ✅ Good — compact, fast
[(t.name, t.output_routing_type.display_name) for t in song.tracks]

# ❌ Bad — bloated, hits token limit
[(p.name, p.value, p.min, p.max, p.original_value) for p in song.tracks[0].devices[0].parameters]
```

**Multi-step operations:** use semicolons or `result =` to return data
```python
# ✅ Read then write in one call
t = [t for t in song.tracks if t.name == "Kick"][0]; t.name = "Kick Drum"; result = t.name
```

**BrowserItem loads:** always end with `result = "done"` or execution hangs
```python
browser_item.load_to(song.tracks[0]); result = "done"
```

---

## BUS ROUTING — CONFIRMED PATTERNS

### Route tracks to a bus
```python
# Route specific tracks to a named bus
for t in song.tracks:
    if t.name in ["Violin I", "Viola", "Cello"]:
        for rt in t.available_output_routing_types:
            if rt.display_name == "STRINGS BUS":
                t.output_routing_type = rt; break
```

### Bus monitoring — ORDER IS CRITICAL
⚠️ Always set NO INPUT first, then Monitor:In. Reverse order causes Focusrite feedback loop.
```python
for t in song.tracks:
    if t.name in ["DRUM BUS", "STRINGS BUS", "GUITAR BUS", "LEAD VOX BUS", "BV BUS"]:
        # Step 1 — No Input FIRST
        for rt in t.available_input_routing_types:
            if rt.display_name == "No Input":
                t.input_routing_type = rt; break
        # Step 2 — Monitor:In SECOND
        t.current_monitoring_state = 0  # 0=In, 1=Auto, 2=Off
```

### Verify routing was applied
```python
[(t.name, t.output_routing_type.display_name) for t in song.tracks]
```

---

## AGENT AUDIO TAP

Captures live audio from any point in Ableton's signal chain to a WAV file.

**Device location:** `User Library/Presets/Audio Effects/Max Audio Effect/AgentAudioTap.amxd`

**Correct capture sequence — do not skip steps:**
```
1. agent_audio_tap("open", "/tmp/tap.wav")   → arms the device
2. song.start_playing()                       → start playback
3. [wait N bars]
4. agent_audio_tap("stop")                    → flushes WAV file
5. song.stop_playing()                        → stop playback
6. audio_analyzer("/tmp/tap.wav")             → analyze result
```

⚠️ `open` alone does NOT record. `start` must be called after `open`.
⚠️ Check for leftover solos before capturing — a solo silences all other tracks.
⚠️ "no function /agent_audio_tap" in Max console = cosmetic OSC error. Ignore it. File polling still works.

**Shell script for N-bar capture (auto-calculates duration from BPM):**
```bash
tools/capture_strings.sh 8   # captures 8 bars, auto-stops
```

---

## AUDIO ANALYZER

File-based. ~1.4s on a 48s WAV. Use for key, BPM, LUFS, stereo, sections.

```python
# Via bridge
GET /analyze?path=/tmp/tap.wav

# Direct CLI
audio-analyzer-rs/cli /path/to/file.wav
```

**Outputs:** Key + confidence, BPM + beat timestamps, LUFS (Integrated/True Peak/LRA), stereo width, phase correlation, mono compatibility, section boundaries, spectral contrast per band.

**Use audio_analyzer instead of analyze_spectrum when you need:** key, BPM, LUFS, stereo, dynamics, or section analysis.

---

## BASIC PITCH — AUDIO TO MIDI

Transcribes any audio file to MIDI. Polyphonic. Any instrument.

```bash
basic-pitch /output/dir/ /path/to/audio.wav --save-midi --model-serialization onnx
# → /output/dir/audio_basic_pitch.mid
```

⚠️ File path must not contain spaces — copy to `/tmp/` first if needed.

**Workflow:**
```
Record idea → WAV → Basic Pitch → MIDI → import to Ableton
AI reads MIDI → understands harmony → suggests voicings
```

---

## PLUGINBRIDGE — FULL VST3/AU CONTROL

Unlocks all parameters for any third-party plugin. Load `PluginBridge.vst3` on a track first.

**Per-session setup:**
1. Load `PluginBridge.vst3` on the track you want to control
2. Select channel name from dropdown (e.g. "Vocal Bus")
3. Pick the plugin from the TreeView browser (e.g. Pro-Q 4)
4. MCP tools are live instantly — port 16620 (first instance) or auto-port

**Workflow:**
```
list_instances()                                     → ["Vocal Bus", "Drum Bus"]
list_plugins("Vocal Bus")                            → ["Pro-Q 4"]
get_analysis("Vocal Bus")                            → "-16.2 dBRMS | Peak:-1.1 | low:+7 | bright"
search_param("Vocal Bus", "Pro-Q 4", "band 1 freq") → [{id:12, name:"Band 1 Freq", value:0.5}]
set_params("Vocal Bus", "Pro-Q 4", {12: 0.3})       → "ok"
get_analysis("Vocal Bus")                            → "-16.2 dBRMS | balanced"
```

**Pro-Q 4 — critical:** Each band has a `Band X Used` parameter separate from `Enabled`.
Must set `Used = 1.0` to make a band appear. Use `search_param` to find all 737 parameter names first.

**Safe plugins** (full GUI in Ableton): Pro-Q 4, The God Particle, Little MicroShift, LIMITER
**Unsafe plugins** (audio-only, MCP still works): iZotope Ozone 12, Neutron 5

---

## KNOWN FAILURE PATTERNS

Patterns confirmed from errors.md. Check here before attempting these tasks.

| Task | Known Failure | Confirmed Fix |
|---|---|---|
| Create bus track | Creating MIDI bus → captures silence | Always create Audio track for buses |
| Bus monitoring | Setting Monitor:In before No Input → Focusrite feedback loop | No Input first, Monitor:In second |
| Audio capture | Calling `open` only → nothing recorded | Must call `start` after `open` |
| Audio capture | Solo left on → meters show -200dB | Clear all solos before capture |
| Multi-step execute | Transport + write in same call → timeout | Split into separate execute() calls |
| Pro-Q 4 band | Band not appearing after set_params | Set `Band X Used = 1.0` first |
| Track creation | Serialization error → assume track not created | Always verify with `len(song.tracks)` |

---

*Last updated: May 2026*
*Connected to: errors.md (source of new patterns), system_prompt.md (behavior rules)*
