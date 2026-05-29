# Conductor — Future Vision Roadmap

## Conductor Future Direction

Conductor starts as an AI music production assistant for Ableton.

But the long-term direction is larger:

```text
Conductor becomes the intelligent operating layer for music production.
```

Not an operating system like macOS or Windows.

A Studio Operating System:

- shared project intelligence
- persistent studio memory
- specialized expert modules
- trusted execution
- workflow continuity
- creator ecosystem
- installable production intelligence

---

# Current Foundation (Phase A/B/C/D)

The current architecture builds the foundation:

## Phase A
Protection, classification, execution safety.

## Phase B
Context assembly and workflow understanding.

## Phase C
Memory, retrieval, routed context, producer understanding.

## Phase D
Trust layer:
- verification
- proofs
- undo
- black box logs
- never-do rules
- feedback
- session memory promotion

### Memory Promotion — Feedback Learning Caveats (Build 18)

Build 18 (Memory Promotion v1) introduces the candidate generator. These rules
are locked into the architecture and must not be relaxed in future builds:

- **Build 15/16 feedback chips are explicit UI feedback only.** They appear on
  knowledge answer bubbles only. Absence of a chip interaction has zero learning
  weight — the feedback UI may not have been visible or available.

- **Voice mode reactions need a separate path.** Vocal approval/disapproval
  ("yeah that's good", "no that's off") cannot be treated as promotion-eligible
  feedback until a natural-reaction parser is built. Do not infer intent from
  conversational tone alone.

- **Music feedback is contextual.** One accepted suggestion does not become a
  universal user preference. A vocal treatment that works in one song may not
  apply to the next: song, genre, project goal, arrangement density, and
  recording quality all affect what is "correct." Scope defaults to
  session/project. Global user-taste elevation requires repeated explicit
  evidence across multiple sessions.

- **Absence of feedback is not a negative signal.** Missing feedback has zero
  learning weight in both directions. Do not penalise or suppress candidates
  because the user did not respond to a specific suggestion.

These phases are the infrastructure layer for all future expansion.

---

# Future Direction — Studio OS Layer

Future phases expand Conductor from “assistant” into a modular studio intelligence ecosystem.

---

# Shared Project Context System

## Core Idea

Every song/project becomes a living shared context space.

Example:

```text
Song A
- arrangement
- mix notes
- plugin chains
- references
- producer goals
- export history
- feedback history
- session memory
```

Every module reads from the same project truth.

Different modules interpret the same project differently depending on their role.

---

## Example

### Mixing Brain
Understands:
- separation
- masking
- balance
- dynamics
- depth
- stereo image
- transient conflicts

### Production Brain
Understands:
- arrangement
- energy flow
- transitions
- drops
- structure
- groove

### Tutorial Creator Brain
Understands:
- Shorts/Reels/TikTok hooks
- pacing
- captions
- viral structure
- educational flow
- visual storytelling

### Mastering Brain
Understands:
- loudness
- translation
- tonal balance
- true peak
- final polish

Same project.
Different intelligence lenses.
