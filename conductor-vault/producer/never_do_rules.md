# Never-Do Rules
> Level 4 memory — strongest. Always retrieved before any RISKY_WRITE action.
> Pre-risky-action hook reads this file before: master bus edits, delete, batch operations, export.
> Add project-specific rules in the relevant project folder — they take priority here.

---

## Hard Rules (defaults — apply to all projects)

### Master Bus
- NEVER apply destructive processing to master bus without explicit "go ahead" confirmation
- NEVER exceed -0.3 dBTP True Peak on any export
- NEVER change master bus chain mid-session without logging what changed

### Deletes
- NEVER delete tracks, clips, or devices without explicit user confirmation
- NEVER use `clip.remove_notes()` without stating exactly what will be removed first

### Tempo / Key
- NEVER change project BPM or key without asking — this affects all existing audio clips
- NEVER warp audio clips without asking — destructive and non-obvious

### Exports / Bounces
- NEVER overwrite an existing export file — always version (add _v2, _v3)
- NEVER export at lower than 24-bit for stems, 16-bit for consumer deliverables

### Batch Operations
- NEVER run a for-loop that modifies more than 3 tracks without showing the plan first
- NEVER rename tracks in batch without previewing the rename list

### Routing
- NEVER change output routing on tracks mid-session without confirming first
- NEVER set a track to Monitor: In before setting it to No Input — causes feedback loop

### Memory
- NEVER save a guess to long-term memory — only save confirmed, user-approved decisions
- NEVER promote Level 1 memory to Level 3 or 4 automatically — needs repetition across sessions

---

## Plugin-Specific Rules

### Ozone 12 / iZotope mastering tools
- NEVER apply AI Mastering Assistant suggestions without showing targets first
- NEVER let Ozone auto-match loudness to a reference without confirming the target LUFS

### Pro-Q 4 / EQ
- NEVER apply a cut deeper than -6dB without explaining why
- NEVER boost above +3dB on a track that already has saturation downstream

---

## Project-Specific Overrides

> Each project can add rules here during onboarding or session work.
> Format: `[Project Name] — [Rule] — [added: YYYY-MM-DD]`

(none yet)

---

_These rules are read before every RISKY_WRITE action. Edit carefully._
_Last updated: — (auto-updated by Conductor)_
