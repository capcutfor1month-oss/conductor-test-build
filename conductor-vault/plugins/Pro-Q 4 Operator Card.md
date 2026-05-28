---
card_id: "fabfilter_pro_q_4"
display_name: "Pro-Q 4"
type: "eq"
risk_level: "low"
verification_status: "verified"
collection: "plugin_operator_index"
tags: ["eq", "equalizer", "fabfilter", "pro-q", "pro-q4"]
operator_card_triggers: ["eq", "pro-q", "pro-q 4", "equalizer", "fabfilter"]
---
# Operator Card — FabFilter Pro-Q 4
> Loaded when Pro-Q 4 is active in the session.
> Source: PluginBridge (737 params accessible via set_params)

---

## Identity

Manufacturer: FabFilter
Type: EQ (dynamic, linear phase, mid/side)
Risk level: medium
PluginBridge: ✅ Full control via set_params
Ableton LOM: ❌ Only 1 param — do NOT use LOM for Pro-Q 4

---

## What it does

Surgical and creative EQ. Dynamic bands react to transient content.
Linear phase mode eliminates phase shift (use on busses/master only — adds latency).
M/S mode processes mid and side independently.
Spectrum analyser shows real-time FFT, collision detection, and note labelling.

---

## Safe Reads (no confirmation needed)

- Read spectrum display via get_analysis()
- Read current band settings via get_params()
- search_param() to find any parameter by name

```python
# Find Band 1 frequency
search_param("Vocal Bus", "Pro-Q 4", "band 1 freq")

# Get current value
get_params("Vocal Bus", "Pro-Q 4", [12])

# Read live EQ curve from track
get_analysis("Vocal Bus")
```

---

## Risky Writes (confirm before executing)

- Any cut deeper than -6 dB
- Any boost above +3 dB on a track with downstream saturation
- Linear phase mode enable (adds latency — check buffer)
- High-pass filter on bass/kick bus (cuts fundamentals)
- Low-pass on high-frequency content with Q above 2.5

---

## PluginBridge — Key Parameter IDs

> IDs may shift across plugin versions. Always use search_param() first in a new session.

| Parameter | Typical ID | Notes |
|---|---|---|
| Band 1 Frequency | ~12 | Hz — normalized 0.0–1.0 |
| Band 1 Gain | ~13 | dB |
| Band 1 Q | ~14 | |
| Band 1 Type | ~15 | Bell, Shelf, HP, LP, etc. |
| Band 1 Dynamic | ~16 | Toggle |
| Global Gain | ~1 | Output level |
| Phase Mode | ~2 | Zero = minimum phase |

---

## Common Use Cases

### Vocal presence cut (harsh upper mids)
```
search_param → find "band N freq" closest to 3–4kHz
set to: freq ~ 3400Hz, gain ~ -1.0 to -1.5dB, Q ~ 2.2
Verify with get_analysis() after
```

### Air boost (presence above 10kHz)
```
Add shelf band at 10kHz, +1.5 to +2.5dB
Use high shelf, not bell
```

### Low-end cleanup (HPF on non-bass tracks)
```
HPF at 80–120Hz, slope 24dB/oct
Confirm: not a bass track, not a bus with bass routed in
```

---

## Never Do

- Never set gain via Ableton LOM on Pro-Q 4 — it hits a single generic param, not band gain
- Never use linear phase on individual tracks during mixing — latency causes phase issues
- Never set Q above 4.0 unless surgical notch removal (resonance kill)
- Never cut more than -6dB without logging the reason

---

## Verification Steps

After any Pro-Q 4 change:
1. `get_analysis("track name")` — check dBRMS didn't drop unexpectedly
2. Listen in context (A/B bypass)
3. If cut > 3dB: note it in session decisions

---

---

## Team Updates

> This section is the handoff point between the team and Conductor.
> Team members write update blocks below. Worker Claude Code picks them up,
> validates against safety rules, applies them to this card, and pushes to Conductor.
> Conductor is linked to: **Adi (mishrasharma118@gmail.com)**

---

### How to Submit an Update

Write an update block in the `## Pending Updates` section below. Use this format exactly:

```md
### UPDATE — [short title]
- Submitted by: [your name / GitHub handle]
- Date: YYYY-MM-DD
- Plugin version tested on: Pro-Q 4 vX.X
- Type: [ ] new-param  [ ] param-id-correction  [ ] new-use-case  [ ] new-quirk  [ ] risky-write-addition  [ ] never-do-addition
- Confidence: [ ] confirmed-in-session  [ ] suspected  [ ] from-manual

**What to add / change:**
[Write the exact text, code block, or table row to add. Be specific — worker will insert verbatim.]

**Why:**
[One sentence. What broke, what you discovered, what changed in a plugin update.]

**Verification:**
[How worker Claude Code should verify this is correct before applying.]
```

---

### Worker Claude Code — Config

```yaml
worker_target: claude-code (headless sub-agent)
linked_instance: Conductor → Adi (mishrasharma118@gmail.com)
validation_rules:
  - Never add a risky-write without a corresponding confirmation step
  - Never remove an existing never-do rule without explicit Adi approval
  - param-id-correction must include the old ID and new ID both
  - All code blocks must be tested (confidence: confirmed-in-session)
on_apply:
  - Bump card version (1.0 → 1.1 → etc.)
  - Move update block from Pending → Applied Changelog
  - Write one line to conductor-vault/indexes/plugins.md noting the change
  - If risky-write-addition: also add to never_do_rules.md
  - POST /memory to Conductor bridge → saves update to plugin_operator_index
push_to_conductor: true
sync_method: file write → conductor-vault/ → Conductor reads on next session start
```

**To trigger worker manually:**
```bash
# From TEST-BUILD root
claude --headless "Read conductor-vault/plugins/Pro-Q 4 Operator Card.md. 
Process all pending updates in the Pending Updates section. 
Validate each against the Worker Claude Code config rules. 
Apply valid ones. Move invalid ones to Rejected with reason."
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
