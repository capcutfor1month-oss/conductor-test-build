---
card_id: "ableton_stock_devices"
display_name: "Ableton Stock Devices"
type: "stock"
risk_level: "low"
verification_status: "verified"
collection: "plugin_operator_index"
tags: ["eq", "compressor", "limiter", "stock"]
operator_card_triggers: ["eq eight", "compressor", "glue compressor", "limiter"]
---
# Operator Card — Ableton Stock Devices
> EQ Eight, Compressor, Glue Compressor, Limiter, Auto Filter
> Stock devices are FULLY controllable via Ableton LOM — no PluginBridge needed.
> This is the ONLY category where Ableton LOM works for parameter control.

---

## EQ Eight

### Identity
Built-in Ableton EQ. 8 bands. LOM-accessible. Zero latency.
**Use this for full LOM control. Use Pro-Q 4 for advanced EQ work.**

### LOM Access
```python
# Get device
device = song.tracks[i].devices[j]  # where device.class_name == "Eq8"

# Read all params (compact)
[(p.name, round(p.value, 2)) for p in device.parameters]

# Set a band
# EQ Eight param naming: "1 FreqA" = Band 1 Frequency, "1 GainA" = Band 1 Gain, "1 QA" = Band 1 Q
for p in device.parameters:
    if p.name == "1 FreqA":
        p.value = 200.0  # Hz — NOT normalized, actual Hz value
```

### Parameter format
| Param name | Value range | Notes |
|---|---|---|
| `N FreqA` | 20–20000 Hz | Actual Hz, not normalized |
| `N GainA` | -15 to +15 dB | Actual dB |
| `N QA` | 0.1–10 | Q value |
| `N FilterTypeA` | 0–7 | 0=Bell, 1=Low Shelf, 2=High Shelf, 3=HP, 4=LP, 5=Notch, 6=Bandpass, 7=Tilt Shelf |
| `N Mode` | 0=Stereo, 1=Mid, 2=Side | M/S mode per band |

### Safe targets (EQ Eight)
- Any cut up to -6dB: safe without confirmation
- HPF on non-bass tracks: safe if above 60Hz
- Notch cuts: safe up to -12dB if narrow Q

### Risky (EQ Eight)
- Boost above +3dB: confirm first
- HPF on bass/kick bus: confirm — cuts fundamentals
- Cut > -6dB: log reason

---

## Compressor

### Identity
Ableton stock Compressor. Full LOM access. Soft knee, lookahead, sidechain.
**Use for standard compression. Use PluginBridge + external compressor for character/vintage.**

### LOM Access
```python
# device.class_name == "Compressor2"
[(p.name, round(p.value, 2)) for p in device.parameters]

# Common writes
for p in device.parameters:
    if p.name == "Threshold":
        p.value = -18.0   # dBFS
    if p.name == "Ratio":
        p.value = 4.0     # ratio (2:1 to 10:1 typical)
    if p.name == "Attack":
        p.value = 10.0    # ms
    if p.name == "Release":
        p.value = 50.0    # ms
```

### Parameter format
| Param name | Value range | Notes |
|---|---|---|
| `Threshold` | -36 to 0 dBFS | |
| `Ratio` | 1.0–inf | 4.0 = 4:1 |
| `Attack` | 0.01–200 ms | |
| `Release` | 0.01–1200 ms | |
| `Gain` | -12 to +12 dB | Make-up gain |
| `Knee` | 0.0–20.0 dB | Soft knee width |
| `Lookahead` | 0=Off, 1.5ms, 3ms | |

### Safe targets (Compressor)
- Threshold between -24 and -6 dBFS: safe
- Ratio 2:1 to 6:1: safe
- Attack 5–50ms, release 50–200ms: safe

### Risky (Compressor)
- Ratio above 10:1 (limiter territory): confirm first
- Attack below 1ms on transient-heavy material: may kill snap
- Lookahead on anything except master/bus: adds latency in parallel chains

---

## Glue Compressor

### Identity
SSL-style bus compressor. LOM-accessible. Designed for gluing drums/mix buses.

### Key parameters
| Param name | Notes |
|---|---|
| `Threshold` | dBFS |
| `Ratio` | 2, 4, 10 (stepped) |
| `Attack` | 0.1–30ms (stepped) |
| `Release` | 0.1–Auto |
| `Makeup` | dB |
| `Range` | Gain reduction cap — set to 6–12dB for bus work |

---

## Limiter

### Identity
Hard limiter. LOM-accessible. Use on Master Bus or individual tracks for peak control.

### Safe use
- Master Bus ceiling: -0.3 dBTP
- Never set ceiling above -0.1 dBTP for any export

---

## Never Do (stock devices)

- Never use EQ Eight's Hz values as normalized (they're NOT normalized — it's actual Hz)
- Never use Compressor ratio above 20:1 without calling it a limiter and treating it as RISKY
- Never change Glue Compressor attack below 0.1ms on mix bus — kills transients
- Never remove Limiter from Master Bus without putting something else there first

---

---

## Team Updates

> This section is the handoff point between the team and Conductor.
> Team members write update blocks below. Worker Claude Code picks them up,
> validates against safety rules, applies them to this card, and pushes to Conductor.
> Conductor is linked to: **Adi (mishrasharma118@gmail.com)**
> This card covers: EQ Eight · Compressor · Glue Compressor · Limiter

---

### How to Submit an Update

Use this format exactly:

```md
### UPDATE — [short title]
- Submitted by: [your name / GitHub handle]
- Date: YYYY-MM-DD
- Ableton Live version tested on: vX.X
- Device: [ ] EQ Eight  [ ] Compressor  [ ] Glue Compressor  [ ] Limiter  [ ] Auto Filter
- Type: [ ] new-param  [ ] param-range-correction  [ ] new-use-case  [ ] new-quirk  [ ] risky-write-addition  [ ] never-do-addition
- Confidence: [ ] confirmed-in-session  [ ] suspected  [ ] from-manual

**What to add / change:**
[Write the exact text, code block, or table row to add. Include the device name as a section header.]

**Why:**
[One sentence.]

**Verification:**
[How worker Claude Code should verify this.]
```

---

### Worker Claude Code — Config

```yaml
worker_target: claude-code (headless sub-agent)
linked_instance: Conductor → Adi (mishrasharma118@gmail.com)
validation_rules:
  - EQ Eight Hz params are NOT normalized — verify any range claims against Ableton spec
  - param-range-correction must include the old range, new range, and Ableton version
  - new-param must include actual param name (as it appears in device.parameters[n].name)
  - Compressor ratio above 20:1 updates must add a risky-write-addition automatically
on_apply:
  - Bump card version
  - Move update block from Pending → Applied Changelog
  - Write to conductor-vault/indexes/plugins.md
  - If update affects EQ Eight Hz params: also check ableton_lom_failures.md for related failures
  - POST /memory → plugin_operator_index
push_to_conductor: true
sync_method: file write → conductor-vault/ → Conductor reads on next session start
```

**To trigger worker manually:**
```bash
claude --headless "Read conductor-vault/plugins/Ableton Stock Devices.md.
Process all pending updates in the Pending Updates section.
Validate against Worker Claude Code config rules. Apply valid ones."
```

---

### Pending Updates

_(empty — submit updates here)_

---

### Applied Changelog

| Version | Change | Device | Submitted by | Applied |
|---|---|---|---|---|
| 1.0 | Initial card created — EQ Eight, Compressor, Glue, Limiter | All | Conductor team | 2026-05-22 |

---

_Card version: 1.0_
