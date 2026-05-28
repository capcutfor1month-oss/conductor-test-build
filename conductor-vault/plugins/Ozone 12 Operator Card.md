---
card_id: "izotope_ozone_12"
display_name: "Ozone 12"
type: "mastering"
risk_level: "high"
verification_status: "verified"
collection: "plugin_operator_index"
tags: ["mastering", "limiter", "eq", "ozone"]
operator_card_triggers: ["ozone", "mastering", "maximizer", "ozone 12"]
---
# Operator Card — iZotope Ozone 12
> Loaded when Ozone 12 is active in the session — typically on Master Bus.
> Risk: HIGH. This plugin sits at the end of the chain. Mistakes here affect the whole mix.

---

## Identity

Manufacturer: iZotope
Type: Mastering suite (EQ, limiter, imager, vintage tape, maximizer, AI assistant)
Risk level: HIGH
PluginBridge: ✅ MCP works (audio-only mode — no GUI in PluginBridge window)
Ableton LOM: ❌ Do not use

---

## What it does

Full mastering chain in one plugin. Modules: Equalizer, Dynamic EQ, Spectral Shaper,
Imager, Vintage Tape, Vintage EQ, Vintage Limiter, Maximizer, Low End Focus, Master Rebalance.
AI Assistant can automatically suggest a mastering chain — use with caution.

---

## Safe Reads

- Read current LUFS via audio_analyzer MCP (file-based) — most reliable
- Read True Peak via audio_analyzer MCP
- Read stereo width via audio_analyzer MCP or PluginBridge get_analysis()
- search_param() to inspect current settings before touching anything

---

## Risky Writes — ALWAYS confirm before executing

Every write on Ozone 12 is a RISKY_WRITE. No exceptions.

| Action | Why risky |
|---|---|
| AI Assistant apply | Auto-applies a full chain — may overwrite manual settings |
| Maximizer ceiling change | Affects True Peak on final export |
| Imager width change | Can cause mono incompatibility |
| EQ global output gain | Affects comparative loudness reference |
| Master Rebalance | Affects relative levels of vocals/drums/bass — irreversible perception shift |

---

## PluginBridge Workflow

```python
# 1. Check current LUFS before touching anything
# Use audio analyzer on a quick bounce, or get_analysis on master track

# 2. Find what you want to change
search_param("Master Bus", "Ozone 12", "maximizer threshold")

# 3. Read current value
get_params("Master Bus", "Ozone 12", [id_from_step_2])

# 4. Confirm with user: "Currently at X. Plan: set to Y. OK?"

# 5. Set only if confirmed
set_params("Master Bus", "Ozone 12", {id: new_value})

# 6. Verify
get_analysis("Master Bus")  → check dBRMS / peak didn't jump
```

---

## Loudness Targets

| Platform | LUFS Integrated | True Peak |
|---|---|---|
| Spotify | -14 LUFS | -1.0 dBTP |
| Apple Music | -16 LUFS | -1.0 dBTP |
| YouTube | -14 LUFS | -1.0 dBTP |
| Tidal | -14 LUFS | -1.0 dBTP |
| CD / Download | -9 to -14 LUFS | -0.3 dBTP |

---

## AI Assistant — Rules

- NEVER apply AI Assistant results automatically
- Always show the suggested chain to the user first
- User must explicitly say "apply it" before setting any params
- After apply: verify LUFS and True Peak against targets above

---

## Never Do

- Never let Maximizer ceiling go above -0.3 dBTP for any export
- Never use Master Rebalance on a live mixing session (use only at mastering stage)
- Never change Ozone settings mid-mix without saving a preset snapshot first
- Never apply AI Matching to a reference without checking the reference's LUFS first
- Never use Ozone on individual tracks — mastering only (unless intentional creative use)

---

## Verification Steps

After any Ozone 12 change:
1. Bounce 30 seconds to WAV
2. Run audio_analyzer MCP → check LUFS Integrated, True Peak, LRA
3. Compare against platform target above
4. Log LUFS before and after in session decisions

---

## Safe Preset Approach

Before any session touching Ozone:
1. Save current state as a named preset inside Ozone ("pre-session backup")
2. Make changes
3. If unhappy: reload preset
4. If happy: log the final settings in session decisions

---

---

## Team Updates

> This section is the handoff point between the team and Conductor.
> Team members write update blocks below. Worker Claude Code picks them up,
> validates against safety rules, applies them to this card, and pushes to Conductor.
> Conductor is linked to: **Adi (mishrasharma118@gmail.com)**
> ⚠️ HIGH-RISK CARD — extra validation required. All param writes need confirmation evidence.

---

### How to Submit an Update

Use this format exactly:

```md
### UPDATE — [short title]
- Submitted by: [your name / GitHub handle]
- Date: YYYY-MM-DD
- Plugin version tested on: Ozone 12 vX.X
- Type: [ ] new-param  [ ] param-id-correction  [ ] new-use-case  [ ] new-quirk  [ ] risky-write-addition  [ ] never-do-addition  [ ] loudness-target-update
- Confidence: [ ] confirmed-in-session  [ ] suspected  [ ] from-manual

**What to add / change:**
[Write the exact text, code block, or table row to add.]

**Why:**
[One sentence. What broke, what you discovered, what changed in a plugin update.]

**Verification:**
[How worker Claude Code should verify this. For high-risk cards: must be confirmed-in-session.]
```

---

### Worker Claude Code — Config

```yaml
worker_target: claude-code (headless sub-agent)
linked_instance: Conductor → Adi (mishrasharma118@gmail.com)
risk_level: HIGH
validation_rules:
  - HIGH-RISK card: only confirmed-in-session updates accepted
  - Never remove a risky-write entry without explicit Adi approval
  - Never remove a never-do rule without explicit Adi approval
  - loudness-target-update must cite the platform's published spec
  - Any new write targeting Maximizer ceiling must be reviewed by Adi personally
  - param-id-correction must include old ID, new ID, and plugin version where it changed
on_apply:
  - Bump card version
  - Move update block from Pending → Applied Changelog
  - Write to conductor-vault/indexes/plugins.md
  - If loudness-target-update: also update CONDUCTOR_RAG_ARCHITECTURE.md loudness table
  - POST /memory → plugin_operator_index
push_to_conductor: true
sync_method: file write → conductor-vault/ → Conductor reads on next session start
requires_adi_approval: [risky-write-addition, never-do-addition, loudness-target-update]
```

**To trigger worker manually:**
```bash
claude --headless "Read conductor-vault/plugins/Ozone 12 Operator Card.md.
Process all pending updates. This is a HIGH-RISK card — only apply confirmed-in-session updates.
Flag suspected or from-manual updates as Rejected with reason: unverified.
Validate each against the Worker Claude Code config rules."
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

_Card version: 1.0 — HIGH-RISK. Review when iZotope updates Ozone._
