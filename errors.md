# Conductor — Error Log
> AI writes to this silently whenever a task fails, a hallucination is caught,
> or a user correction is made. No user prompt needed.
>
> Reviewed weekly by Adi + AI. Patterns identified → reference files updated →
> fixes pushed via update server.
>
> Format: date | task | what failed | what fixed it | file updated

---

## HOW AI WRITES TO THIS FILE

Trigger silently on any of these:
- Tool call returns an error
- User says "that's wrong", "undo", "that didn't work", "try again"
- AI output contradicts a known pattern in ableton.md
- AI makes an assumption that turns out to be incorrect
- Same task fails twice in the same session

Entry format:
```
### [DATE] — [TASK CATEGORY]
**Attempted:** what the AI tried to do
**Failed:** what went wrong exactly
**Fixed:** what the correct approach was
**Reference updated:** which file was updated with the fix (if any)
```

---

## WEEKLY REVIEW PROCESS

1. Review all entries since last archive
2. Find patterns — same failure appearing multiple times = priority fix
3. Update `ableton.md` or `system_prompt.md` with correct pattern
4. Test fix in TEST-BUILD
5. Push update to users via update server
6. Archive this week's entries below, start fresh

---

## ACTIVE LOG

*(AI appends entries here silently)*

---

## ARCHIVE

*(Weekly entries moved here after review)*

---

*Last reviewed: May 2026*
