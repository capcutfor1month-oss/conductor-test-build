# Session Management
> Core reliability layer for Conductor.
> Defines how session history is stored, identified, and separated from casual use.
> Updated every audit session.

---

## The Problem

When a user reopens Conductor, there are two possible states:
- Ableton is open → they are working on a project
- Ableton is closed → they are using Conductor casually

These two states must never share the same chat history. Casual use must never pollute project session history.

---

## Two Types of History

| Type | When active | Saved? | Loaded on resume? |
|---|---|---|---|
| Session history | Ableton is open with a saved project | Yes, tied to Project ID | Yes, on next open with same project |
| Temporary bucket | Ableton is open, project is Untitled | Yes, temporarily | Migrated when user saves. Discarded if closed without saving. |
| Freeform history | Ableton is closed | No, disposable | Never loaded as project history |

---

## Project Identity

Session history must be tied to a stable Project ID — not only the visible project name.
Producers rename projects, duplicate them, use "final_final_v3", save copies, and work from templates.
Relying on project name alone will cause histories to split or merge incorrectly.

**Project ID priority:**
1. Ableton `.als` absolute file path
2. Ableton project folder path
3. Internal generated Project UUID stored by Conductor
4. Project name — display label only, never the primary key

**If the project is renamed:**
- Keep the same Project UUID
- Update the display name
- Do not create a new history unless the file path/folder changes AND user confirms it is a new project

**If the project is duplicated or saved-as:**
- Treat as a new project — generate a new Project UUID
- Do not carry over session history from the original
- Prompt user: "Is this a new project or a renamed version of [original name]?"

---

## On Launch — Decision Tree

```
Conductor opens
     ↓
Ping Ableton Bridge (TCP 16619)
     ↓
Read active Live Set identity (file path + project name)
     ↓
IF valid saved Project ID found (matches file path or UUID)
     → load matching project session history
     → resume from where they left off

IF Ableton is open but project is Untitled
     → create temporary unsaved session bucket
     → do not merge with any existing project
     → migrate bucket when user saves (attach to new Project ID)
     → discard bucket if user closes without saving

IF Ableton is open but bridge is stale / crashed
     → show warning: "Ableton connection lost"
     → start freeform chat until bridge reconnects
     → do not write to project history

IF Ableton is closed
     → start freeform chat
     → nothing saved to project history
```

---

## Stage 0 History Migration

When Ableton is open but the project is Untitled:
- Store chat history in a temporary unsaved session bucket
- Do not merge it with any existing project history
- When the user saves the project (Cmd+S), attach the temporary bucket to the new Project ID
- If the user closes without saving, discard the temporary bucket
- Exception: if the user explicitly says "save this note" during Stage 0, save it to ChromaDB global memory only — not to any project history

---

## Stage System

Stages live in the Session tab as a manual toggle. User sets their stage. Claude uses it for routing.

| Stage | Name | Signal |
|---|---|---|
| 0 | Free Flow | Project is Untitled. No Cmd+S yet. |
| 1 | Composing | User saved the project (Cmd+S trigger). Up to ~10-12 tracks. |
| 2 | Production | Arrangement building. Tracks filling out. |
| 3 | Mixing | All parts recorded. Balancing and shaping. |
| 4 | Mastering | Final mix locked. Preparing for release. |

---

## Stage Transition Triggers

| From | To | Trigger |
|---|---|---|
| Stage 0 | Stage 1 | User saves the project — detected via Ableton session name change from Untitled |
| Stage 1→2→3→4 | Next | Manual toggle in Session tab |

Stage never moves backwards automatically. User can manually set any stage at any time.

---

## Freeform Memory

Freeform chats are not loaded as project session history.
Freeform content is disposable by default.

Exception: save to ChromaDB **global memory** (not project history) when:
- User explicitly says "remember this"
- The content is a stable personal preference, not project-specific

> Example: "I usually hate bright hi-hats" → save to global ChromaDB memory.
> Example: "The kick in this project needs more punch" → project history only, not global.

---

## What Claude Does With Stage

- Stage is prepended to every message as context
- Claude never asks "what stage are you at?" if stage is already set
- Stage 0 (untitled, unsaved) → exploratory mode, no structured advice unless asked
- Stage informs routing priority in Auto mode

---

## Resume Flow

On every Conductor launch with Ableton open:

```
1. Load session file by Project UUID
2. Read live Ableton state (BPM, tracks, devices, routing)
3. Compare session file vs live state:

   → Match
     Resume seamlessly. No questions.

   → Mismatch
     Show diff to user:
     "Session says 142 BPM, Ableton shows 138 BPM. Which is correct?"
     Wait for user to confirm before proceeding.

   → Session file missing
     Start fresh. Ask Stage 0 questions.

   → Ableton closed
     Load session context only.
     No live data available — say so clearly.
```

Never silently assume the session file is correct. Always verify against live Ableton state.

---

## Current Project State

There is no single `CURRENT PROJECT STATE.md` file for public users.
Each project has its own live context stored in its session file:
`sessions/[Project-UUID]-[project-name]-session.md`

**Rules:**
- Read the session file before any major production, mix, or master decision
- Update the session file **only when Ableton project is saved (Cmd+S)**
- Never modify it during normal advice, exploration, troubleshooting, or tool execution
- The session file is the source of truth — do not contradict it without user confirmation

---

## Needs Reopen

If a later-stage issue requires revisiting an earlier decision — **never silently rewrite it.**
Flag it in the session file under `## NEEDS REOPEN` and let the producer decide.

**Format:**
```
## NEEDS REOPEN

### [timestamp] — Found at Stage [X]
Issue: [what's wrong]
Affects: [which tracks or decisions]
Blocking: [yes / no — can current stage work continue?]
Original decision: [what was decided in the earlier stage]
Suggested fix: [AI's best suggestion at time of flagging]
Status: Open
```

**When resolved:**
```
Status: Resolved — [timestamp]
What changed: [exactly what was updated]
```

**Why this matters:**
Without this flag, the AI could quietly rewrite Stage 2 decisions while the user thinks they're in Stage 3. The session file becomes unreliable. The producer loses trust in the system.

---

## Open Questions

- How does Conductor read the active Live Set file path from Ableton? (LOM: `song.get_current_beats_song_time()` or file path via `Application.get_document()`?)
- What UI prompt is shown when a save-as is detected — how does the user confirm new vs renamed project?
- Max session history length before pruning kicks in?
- Where is the Project UUID stored — in the `.als` file, in a Conductor sidecar file, or in ChromaDB?

---

*Last updated: May 2026*
