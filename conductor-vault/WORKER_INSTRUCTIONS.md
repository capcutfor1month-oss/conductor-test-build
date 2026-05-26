# Worker Claude Code — Knowledge Update Instructions
> Read this file before processing ANY update in the conductor-vault.
> Covers all knowledge types: operator cards, techniques, genres, manuals, reference tracks, failure cases.
> Conductor instance: Adi (mishrasharma118@gmail.com)
> Worker mode: headless Claude Code sub-agent

---

## What the Worker Does

1. Reads a target file (or scans a folder for pending updates)
2. Finds `## Pending Updates` sections
3. Validates each update block — global rules first, then knowledge-type rules below
4. Applies valid updates to the correct section of the target file
5. Moves the update block from Pending → Applied Changelog (with date + submitter)
6. Bumps the file version
7. Writes a one-line summary to the relevant index file
8. If `push_to_conductor: true` → POSTs to bridge `POST /memory` with the correct collection
9. Items requiring Adi approval → written to `PENDING_APPROVAL.md`, NOT applied

---

## Global Validation Rules

Apply to every knowledge type without exception.

```
1. Never remove existing content — only add or clarify. Removal requires Adi approval.
2. Never apply suspected or from-source confidence to HIGH-risk files (operator cards, failure cases).
3. Never apply an update that contradicts existing content — flag as conflict → PENDING_APPROVAL.md.
4. Never apply a duplicate — if the same information already exists, discard silently and log.
5. from-source confidence: source must be cited. If no source given, reject with reason.
6. confirmed confidence: must state where it was confirmed (session, test, manual).
7. All code blocks must include a verification step. No code without verification.
8. Producer DNA and Never-Do Rules are LOCKED — reject any submission targeting these files.
```

---

## Knowledge-Type Rules

### operator-card (plugins/)
```
- Only confirmed confidence accepted for HIGH-risk cards (Ozone 12)
- risky-write-addition → requires Adi approval before applying
- never-do-addition → requires Adi approval before applying
- param-id-correction → must include old ID, new ID, plugin version where it changed
- Any update that removes a verification step → reject
- After apply: POST /memory → plugin_operator_index
```

### technique (references/techniques/)
```
- confirmed or from-source accepted (cite the source)
- Low risk — auto-apply after worker validation, no Adi approval needed
- Must fit the existing section structure (EQ / Compression / Reverb / etc.)
- Numeric values required — no vague language ("boost a bit", "cut slightly")
  Good: "cut 200–250Hz / -2dB / Q 1.4"   Bad: "cut the muddiness"
- After apply: POST /memory → producer_memory_index (technique knowledge)
```

### genre (references/genres/)
```
- confirmed or from-source accepted (cite the reference track or source)
- Low risk — auto-apply after worker validation
- Must include: BPM range, key tendencies, mix targets (LUFS), arrangement note
- If submission is opinion without numbers → reject with reason: needs numeric targets
- After apply: POST /memory → producer_memory_index (genre knowledge)
```

### manual-note (references/manuals/)
```
- from-source accepted — must cite manual version + page/section
- Low risk — auto-apply after worker validation
- Format: plugin name → section → key point (one line per point)
- Do not reproduce long manual passages — summarise in under 5 lines
- After apply: POST /memory → plugin_operator_index
```

### reference-track (references/reference_tracks/)
```
- confirmed only — must have been analysed via audio_analyzer MCP
- Include: LUFS, True Peak, BPM, key, stereo width, notable spectral features
- Low risk — auto-apply after worker validation
- After apply: POST /memory → audio_analysis_index
```

### failure-case (failure-cases/)
```
- confirmed only — must have been reproduced and fixed
- Must include: what broke / error message / root cause / confirmed fix
- Medium risk — requires Adi approval before applying
- After apply: POST /memory → failure_cases_index
- Also check: does this failure already exist in ableton_lom_failures.md?
  If yes: update existing entry instead of creating new one
```

---

## Locked Files — Reject All Submissions

```
conductor-vault/producer/producer_dna.md     → Adi only
conductor-vault/producer/never_do_rules.md   → Adi only
conductor-vault/producer/confirmed_preferences.md → Adi only
conductor-vault/producer/rejected_patterns.md     → Adi only
```

If a submission targets any of these files → reject immediately.
Write to PENDING_APPROVAL.md with reason: "Locked file — Adi must edit directly."

---

## How to Run — Single File

```bash
claude --headless "
Read /path/to/conductor-vault/plugins/WORKER_INSTRUCTIONS.md first.
Then read [target file].
Process all pending updates in the Pending Updates section.
Apply global validation rules + knowledge-type rules for the file's type.
Apply valid updates. Flag ones requiring Adi approval. Discard duplicates.
Report: how many applied, flagged, discarded.
"
```

## How to Run — Full Vault Scan

```bash
claude --headless "
Read /path/to/conductor-vault/plugins/WORKER_INSTRUCTIONS.md first.
Scan every .md file in conductor-vault/ (all subfolders) for a Pending Updates section.
Process each using global + knowledge-type rules.
Skip locked files (producer/ folder).
Write WORKER_RUN_LOG.md when done.
"
```

---

## Output Files (auto-written by worker)

### WORKER_RUN_LOG.md

```md
# Worker Run Log
Run date: YYYY-MM-DD HH:MM

| File | Type | Applied | Flagged for Adi | Discarded | New version |
|---|---|---|---|---|---|
| Pro-Q 4 Operator Card.md | operator-card | 1 | 0 | 0 | 1.1 |
| Punjabi Pop.md | genre | 2 | 0 | 1 | 1.2 |
| Ozone 12 Operator Card.md | operator-card | 0 | 1 | 0 | 1.0 |
```

### PENDING_APPROVAL.md

```md
# Pending Adi Approval
> Worker flagged these. Not applied. Review and confirm or reject.

---
### [File] — [Update title]
Type: [knowledge type] | Submission type: [risky-write-addition / etc.]
Submitted by: [name] | Date: [date]
Reason flagged: [rule that triggered the flag]

[Full update block reproduced here]

To approve: confirm in chat and re-run worker with --apply-approved
To reject: delete this block
```

---

## Collection Map — Where Each Type Gets Posted

| Knowledge type | ChromaDB collection |
|---|---|
| operator-card | `plugin_operator_index` |
| technique | `producer_memory_index` |
| genre | `producer_memory_index` |
| manual-note | `plugin_operator_index` |
| reference-track | `audio_analysis_index` |
| failure-case | `failure_cases_index` |

---

## Index Files to Update After Each Apply

| Knowledge type | Index file to update |
|---|---|
| operator-card | `conductor-vault/indexes/plugins.md` |
| technique | `conductor-vault/indexes/tools.md` |
| genre | `conductor-vault/indexes/memory.md` |
| manual-note | `conductor-vault/indexes/plugins.md` |
| reference-track | `conductor-vault/indexes/memory.md` |
| failure-case | `conductor-vault/indexes/tools.md` |

---

_This file is the worker's ground truth. Do not modify during a worker run._
_When Phase F server is live: this file moves server-side. Local copy kept for offline fallback._
