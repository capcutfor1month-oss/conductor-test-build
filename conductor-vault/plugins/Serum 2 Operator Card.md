# Operator Card — Xfer Records Serum 2
> Loaded when Serum 2 is active in the session.
> Typically on synth, lead, bass, or pad tracks.

---

## Identity

Manufacturer: Xfer Records
Type: Wavetable synthesiser
Risk level: medium
PluginBridge: ✅ Full param control via set_params
Ableton LOM: ❌ Only 1 param accessible — do NOT use LOM for Serum 2

---

## What it does

Wavetable synthesis with visual interface. Two oscillators (Osc A/B) + Sub + Noise.
Built-in FX chain: Distortion → Filter → EQ → Compressor → Delay → Reverb → Chorus → Phaser → Flanger.
Modulation matrix (LFOs, Envelopes, Macros).
Macros (1–8) are the main real-time control surface — great targets for MCP.

---

## Safe Reads

- search_param() to find any knob by name
- get_params() to read current synth state
- Read Macro values (Macro 1–8) — safe, no audio risk
- Read oscillator waveform type — safe

---

## Risky Writes

| Action | Why risky |
|---|---|
| Load new preset | Wipes current patch — all current settings lost |
| Change wavetable | Completely changes the sound character |
| Change filter cutoff drastically | Can cause sudden resonance spikes at high Q |
| Change envelope attack to 0ms | Click/pop on transient |
| Change envelope release to 0ms | Abrupt cutoff artifacts |

---

## PluginBridge — Key Targets

> Macros are the safest write targets — designed for real-time control.

```python
# Find all macros
search_param("Synth Track", "Serum 2", "macro")

# Read current macro values
get_params("Synth Track", "Serum 2", [macro_1_id, macro_2_id, ...])

# Write a macro (safe — this is what they're designed for)
set_params("Synth Track", "Serum 2", {macro_1_id: 0.75})
```

Common writable targets:
- `Osc A Level` — oscillator volume balance
- `Filter Cutoff` — filter frequency
- `Filter Reso` — filter resonance (careful — can spike at high values)
- `Master Volume` — overall patch level
- `LFO 1 Rate` — modulation speed
- `Env 1 Attack / Decay / Sustain / Release` — amplitude envelope

---

## Common Use Cases

### Automate a macro for evolving texture
```
search_param → "macro 1"
set_params: sweep from 0.3 to 0.8 over multiple calls
Verify: get_analysis() to check level didn't spike
```

### Adjust filter for current mix
```
search_param → "filter cutoff"
Start conservative: small moves (0.05–0.1 change per step)
Listen after each step
```

### Read current patch state before any edit
```
get_params() → note all current values
Only then make changes
```

---

## Never Do

- Never load a new preset via MCP without confirming — it wipes the current patch
- Never set filter resonance above 0.9 without a limiter downstream
- Never set envelope attack to exactly 0 without checking for clicks
- Never use LOM to control Serum 2 params (only reaches generic plugin param)

---

## Verification Steps

After any Serum 2 parameter change:
1. `get_analysis("track name")` — check peak/RMS didn't spike
2. Listen: is the sound still in key, still sitting in the mix?
3. If patch was modified significantly: note in session decisions

---

---

## Team Updates

> This section is the handoff point between the team and Conductor.
> Team members write update blocks below. Worker Claude Code picks them up,
> validates against safety rules, applies them to this card, and pushes to Conductor.
> Conductor is linked to: **Adi (mishrasharma118@gmail.com)**

---

### How to Submit an Update

Use this format exactly:

```md
### UPDATE — [short title]
- Submitted by: [your name / GitHub handle]
- Date: YYYY-MM-DD
- Plugin version tested on: Serum 2 vX.X
- Type: [ ] new-param  [ ] param-id-correction  [ ] new-use-case  [ ] new-quirk  [ ] risky-write-addition  [ ] never-do-addition  [ ] macro-mapping
- Confidence: [ ] confirmed-in-session  [ ] suspected  [ ] from-manual

**What to add / change:**
[Write the exact text, code block, or table row to add.]

**Why:**
[One sentence.]

**Verification:**
[How worker Claude Code should verify this before applying.]
```

---

### Worker Claude Code — Config

```yaml
worker_target: claude-code (headless sub-agent)
linked_instance: Conductor → Adi (mishrasharma118@gmail.com)
validation_rules:
  - Never add a preset-load operation without a "wipes current patch" warning
  - macro-mapping updates must include the macro number AND what it controls
  - param-id-correction must include old ID, new ID, plugin version
  - new-use-case must include a verification step
on_apply:
  - Bump card version
  - Move update block from Pending → Applied Changelog
  - Write to conductor-vault/indexes/plugins.md
  - POST /memory → plugin_operator_index
push_to_conductor: true
sync_method: file write → conductor-vault/ → Conductor reads on next session start
```

**To trigger worker manually:**
```bash
claude --headless "Read conductor-vault/plugins/Serum 2 Operator Card.md.
Process all pending updates in the Pending Updates section.
Validate against Worker Claude Code config rules. Apply valid ones."
```

---

### Pending Updates

_(empty — submit updates here)_

---

### Applied Changelog

| Version | Change | Submitted by | Applied |
|---|---|---|---|
| 1.0 | Initial card created | Conductor team | 2026-05-22 |

---

_Card version: 1.0_
