# How to Submit a Knowledge Update
> Use this format to contribute to any part of the Conductor knowledge base.
> Drop your update block into the `## Pending Updates` section of the target file.
> Worker Claude Code will validate and apply it. Adi reviews anything medium/high risk.
>
> Covers: plugin operator cards · mixing techniques · genre targets ·
>         plugin manual notes · reference track DNA · failure cases

---

## What the team can update

| Knowledge area | Where | Risk | Needs Adi approval? |
|---|---|---|---|
| Plugin operator cards | `plugins/*.md` | medium–high | Yes for safety rules / risky writes |
| Mixing & EQ techniques | `references/techniques/` | low | No — auto-applied |
| Genre targets & references | `references/genres/` | low | No — auto-applied |
| Plugin manual notes | `references/manuals/` | low | No — auto-applied |
| Reference track DNA | `references/reference_tracks/` | low | No — auto-applied |
| Confirmed failure cases | `failure-cases/` | medium | Yes |
| **Producer DNA** | **`producer/`** | **LOCKED** | **Adi only — do not submit** |
| **Never-Do Rules** | **`producer/`** | **LOCKED** | **Adi only — do not submit** |

---

## The Update Block Format

Copy this block, fill it in, and paste it into `## Pending Updates` in the target file.

```md
### UPDATE — [short title, e.g. "Pro-Q 4 Band 3 freq ID correction"]
- Submitted by: [your name / GitHub handle]
- Date: YYYY-MM-DD
- Target file: conductor-vault/[folder]/[filename].md
- Knowledge type: [ ] operator-card  [ ] technique  [ ] genre  [ ] manual-note  [ ] reference-track  [ ] failure-case
- Risk: [ ] low  [ ] medium  [ ] high
- Confidence: [ ] confirmed-in-session  [ ] from-source (cite below)

**What to add / change:**
[Write the exact text, table row, or code block. Worker applies this verbatim.
Be specific. Wrong section → rejected. Vague language → rejected.]

**Why:**
[One sentence. What this corrects, adds, or updates.]

**Source (if from-source):**
[URL / manual name + page / reference track title]

**Verification:**
[How the worker should confirm this is correct before applying.
For operator cards: what MCP call or test to run.
For techniques: what to listen for / measure.
For manuals: which page number or section.]
```

---

## Examples

### Example 1 — Technique (low risk, auto-applied)

```md
### UPDATE — Vocal de-essing threshold range for Hindi vocals
- Submitted by: ravi-k
- Date: 2026-06-10
- Target file: conductor-vault/references/techniques/vocal_processing.md
- Knowledge type: ✅ technique
- Risk: ✅ low
- Confidence: ✅ confirmed-in-session

**What to add / change:**
Add to ## De-essing section:

Hindi female vocals: sibilance typically 6–8kHz. Threshold -18 to -22dBFS.
Ratio 3:1. Attack 1ms. Release 80ms. Wideband mode on Pro-DS.
Reference: Arijit Singh - Tum Hi Ho (2013) — de-ess starts at -20dBFS.

**Why:**
Hindi vocal sibilance sits higher than Western pop — 6–8kHz vs 5–7kHz.
Existing guidance was too generic.

**Source (if from-source):**
Confirmed in 3 sessions on Hindi ballad projects.

**Verification:**
Apply to a Hindi vocal with audible sibilance. LUFS of sibilant consonants
should match adjacent vowels within 3dB after processing.
```

---

### Example 2 — Genre (low risk, auto-applied)

```md
### UPDATE — Punjabi Pop arrangement section lengths
- Submitted by: adi-team
- Date: 2026-06-12
- Target file: conductor-vault/references/genres/Punjabi Pop.md
- Knowledge type: ✅ genre
- Risk: ✅ low
- Confidence: ✅ from-source

**What to add / change:**
Add to ## Arrangement section:

Typical section lengths (at 95–105 BPM):
- Intro: 8 bars
- Mukhda (chorus): 8 bars, repeats 3–4x
- Antara (verse): 16 bars
- Interlude / Taan: 4–8 bars (often instrumental, dhol feature)
- Outro: 4–8 bars, fade or hard cut

**Why:**
Diljit Dosanjh catalogue analysis — 12 songs, average section lengths.

**Source (if from-source):**
Analysis of: G.O.A.T (2020), GOAT (album), Born to Shine (2021).

**Verification:**
Check 3 Diljit songs — section lengths should fall within ±2 bars of above.
```

---

### Example 3 — Operator Card (medium risk, needs Adi approval)

```md
### UPDATE — Pro-Q 4 Band 3 param ID corrected in v4.1.2
- Submitted by: dev-sam
- Date: 2026-06-15
- Target file: conductor-vault/plugins/Pro-Q 4 Operator Card.md
- Knowledge type: ✅ operator-card
- Risk: ✅ medium
- Confidence: ✅ confirmed-in-session

**What to add / change:**
In ## PluginBridge — Key Parameter IDs table, update row:
| Band 3 Frequency | ~20 | Hz — normalized 0.0–1.0 |
(was ~18 in v4.1.0, changed in v4.1.2)

**Why:**
FabFilter shifted param IDs in Pro-Q 4 v4.1.2. Old ID ~18 now maps to Band 3 Q, not Freq.
Confirmed via search_param() in session — new ID is ~20.

**Source (if from-source):**
search_param("Vocal Bus", "Pro-Q 4", "band 3 freq") → returned ID 20.
Plugin version: Pro-Q 4 v4.1.2

**Verification:**
Run search_param("Vocal Bus", "Pro-Q 4", "band 3 freq").
Confirm returned ID matches ~20. Then set_params with that ID and verify frequency changes.
```

---

## Rules the Worker Enforces

- **No vague language.** "Cut the muddiness" → rejected. "Cut 200Hz / -2dB / Q 1.4" → accepted.
- **No numbers without units.** "-2 on the EQ" → rejected. "-2dB at 200Hz" → accepted.
- **No removal of safety rules.** You can only add or clarify — never remove a never-do or risky-write.
- **No edits to locked files.** Producer DNA and Never-Do Rules are Adi-only.
- **Conflicts go to Adi.** If your update contradicts existing content, worker flags it — Adi decides.

---

## After Submission

1. Worker picks up the update (manual run or Phase F server auto-trigger)
2. Low risk → applied directly, changelog updated, you're done
3. Medium/high risk → goes to `PENDING_APPROVAL.md`, Adi reviews
4. Rejected → logged in `WORKER_RUN_LOG.md` with reason
5. Approved and applied → Conductor instances sync on next session start

---

_Questions about a submission? Check WORKER_RUN_LOG.md after the next worker run._
