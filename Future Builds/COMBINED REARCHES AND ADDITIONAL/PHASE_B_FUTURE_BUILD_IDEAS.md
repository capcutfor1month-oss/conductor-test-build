# Phase B Future Build Ideas

This file stores useful Phase B ideas that came from the Perplexity, Gemini, Arena, Kimi, Antigravity, and Codex research/audits, but should **not** be included in the immediate Claude fix prompt unless explicitly approved.

## Purpose

Phase B is the runtime context brain: it decides what Claude sees per message.

Current priority is small reliability hardening, not a redesign. These ideas are parked so they do not get lost.

---

## Current Phase B Immediate Fixes — Not Future

These are **not** future ideas. These are likely immediate reliability fixes:

1. Require `mode` on every `POST /memory` write.
2. Block `project_session_index` writes in FREEFORM.
3. Fix `CURRENT PROJECT STATE.md` parser to support the real markdown format.
4. Make risky refresh fail closed if `/context/session` fails.
5. Correct FREEFORM retrieval so it can allow producer/generic/plugin advice while excluding project/session context.
6. Add tests for the above before or alongside implementation.

Everything below is future/next-tier.

---

## Future Idea 1 — Local `context_pack_log.jsonl`

Persist every context-pack build to a local JSONL log:

```json
{
  "timestamp": "...",
  "message_id": "...",
  "mode": "SESSION",
  "protection_level": "CONFIRM_REQUIRED",
  "session_pack_version": "...",
  "state_hash": "...",
  "layer_a_tokens": 900,
  "layer_b_tokens": 700,
  "layer_c_tokens": 1200,
  "evidence": [],
  "items_dropped": []
}
```

Why useful:
- Lets developers inspect exactly what Claude saw.
- Forms the base of the future full debugger.
- Helps audit bad responses after real user sessions.

Do later after core reliability fixes.

---

## Future Idea 2 — Full Token Pruning Engine

Implement a real replace-not-expand policy for Layer C.

Keep:
- Layer A
- mode/Ableton status
- Level 4 never-do rules
- active failure-case fixes
- high-confidence operator safety snippets

Drop first:
- weak memories
- old low-score snippets
- generic advice
- raw Level 1 events
- non-safety operator sections

Why useful:
- Prevents context bloat as vault and memories grow.
- Keeps safety and relevance stable.

Do after immediate FREEFORM/memory/parser/risky-refresh fixes.

---

## Future Idea 3 — Advanced Operator Card H2 Section Routing

Current/near-term: static snippets like Identity, Risky Writes, Never Do.

Future:
Select sections based on intent:

| Intent | Sections |
|---|---|
| “what does it do?” | Overview / Identity |
| “set/change parameter” | Key Parameters / Risky Writes / Never Do |
| “why does it sound wrong?” | Common Mistakes / Failure Cases |
| “chain order” | Interaction Notes |
| “safe automation” | Safe Writes / Verification Steps |

Always include safety sections for risky/plugin-write modes.

---

## Future Idea 4 — Per-Item Token Counting

Add `token_count` to every injected item and every skipped item.

Why useful:
- Token budget becomes explainable.
- Debugger can show which item caused bloat.
- Pruning policy becomes testable.

---

## Future Idea 5 — Local Observability Trace Tree

A local LangSmith-style trace, but offline-first:

```text
request
  ├── mode classifier
  ├── session pack builder
  ├── routed retriever
  ├── corrective check
  ├── operator card loader
  ├── token pruning
  └── final prompt assembly
```

Each node logs duration, inputs, outputs, and status.

No cloud dependency.

---

## Future Idea 6 — Context Pack Debug Dashboard

Build a developer dashboard showing:

- current mode
- Ableton status
- session pack freshness
- state hash
- Layer A/B/C token sizes
- injected evidence
- skipped evidence
- why skipped
- retrieval misses
- stale state warnings
- current operator card snippets
- memory write attempts

This is part of the full Conductor debugger.

---

## Future Idea 7 — Conversation History Summarizer

Current cap can keep last N turns.

Future:
- keep last 6 turns verbatim
- summarize older chunks into compact session notes
- preserve open issues / user decisions / unresolved bugs
- attach summary hash/version

Useful for sessions that run for weeks/months.

---

## Future Idea 8 — Local Checkpoint Database

Inspired by LangGraph checkpointers.

Store:
- session pack snapshots
- state hashes
- mode switches
- last successful Ableton state
- last context pack log reference

Useful for:
- crash recovery
- time-travel debugging
- “what did Conductor know when it answered?”

Do not build until core runtime is stable.

---

## Future Idea 9 — Retrieval Miss Rate Metrics

Track when Layer C found no strong context.

Metrics:
- retrieval_miss_rate
- avg_score_by_collection
- most missed plugin names
- most missed failure cases
- stale-memory rate

Useful for improving the vault and operator cards.

---

## Future Idea 10 — Advanced Reranking

Possible later options:
- heuristic rerank: score + recency + safety + verification
- BM25 exact boost
- optional cross-encoder reranker
- optional LLM reranker

Do not use heavy reranking on the hot path yet.

---

## Future Idea 11 — Evidence Labels in Prompt + UI

Current debug may show evidence.

Future:
Add compact labels in Claude-visible snippets:

```text
[plugin_operator_index · manual · score 0.86 · age 14d]
```

And richer metadata in debug.

Balance carefully: do not clutter the user-facing experience.

---

## Future Idea 12 — FREEFORM Smart Advice Routing

Future FREEFORM should distinguish:

| FREEFORM query type | Retrieval allowed |
|---|---|
| casual non-music | none |
| general music advice | producer_memory_index + generic plugin knowledge |
| plugin conceptual question | generic/operator knowledge, no project state |
| project-specific request | refuse project assumption; ask to open Ableton |
| DAW action request | block action, explain Ableton disconnected |

This preserves UX without polluting project memory.

---

## Future Idea 13 — Risky Action State Diff

Before risky actions, compare old/new session state:

```text
before_hash != current_hash
```

Then report:
- track/plugin disappeared
- target changed
- Ableton disconnected
- PluginBridge unavailable
- project changed

Useful before real auto-execution.

---

## Future Idea 14 — Parameter Map Retrieval Gate

Parameter maps should load only when:
- user asks a specific parameter/control question
- execution plan needs exact parameter IDs/ranges
- PluginBridge verified map exists
- risky parameter boundary is being checked

Do not inject parameter maps for normal advice.

---

## Future Idea 15 — Context Pack Replay Tool

Given a `context_pack_log.jsonl` entry, recreate:

- Layer A
- Layer B
- Layer C
- final Claude payload

Useful for:
- debugging
- audits
- regression tests
- user bug reports

---

## Future Idea 16 — Mode Switch Timeline

Track:

```text
SESSION → FREEFORM
FREEFORM → SESSION
Ableton reconnect
PluginBridge unavailable
Project changed
State stale
```

Useful for diagnosing “why did Conductor answer in wrong mode?”

---

## Future Idea 17 — Context Quality Score

Score each context pack:

- freshness
- evidence strength
- token pressure
- retrieval confidence
- mode correctness
- safety coverage
- stale state risk

Then debug panel can show:

```text
Context quality: Good / Weak / Stale / Unsafe
```

---

## Future Idea 18 — Full Phase B Test Matrix

Long-term tests:

- FREEFORM allows producer advice but blocks project memory.
- SESSION enables full retrieval.
- stale state warning appears when state age crosses threshold.
- risky action refresh is synchronous and fail-closed.
- operator card not injected for unrelated prompts.
- parameter maps only load for explicit param queries.
- Layer C never exceeds budget.
- debug log reconstructs exact prompt.
- all injected items have evidence labels.
- all skipped items have skip reasons.

---

## Future Idea 19 — Async Logging Queue

When JSONL logging is added, make it non-blocking:

- enqueue log record
- write in background
- if logging fails, do not block chat response
- surface logging error only in dev/debug mode

---

## Future Idea 20 — Context Pack ID on Memory Writes

Every project/session memory write should include:

```json
{
  "context_pack_id": "...",
  "mode": "SESSION",
  "session_pack_version": "...",
  "source_message_id": "..."
}
```

This makes future memory audits possible.

---

## Future Idea 21 — User-Facing Minimal Debug Mode

Separate dev debug from user experience.

Dev mode:
- full context debug
- skipped items
- scores
- JSONL entry link

User mode:
- minimal status
- no scary technical clutter
- only warnings when action needs it

This protects UX.

---

## Future Idea 22 — Full Context Compiler Spec

Eventually document Phase B as a formal compiler:

```text
input: user message + session state + vault/memory indexes
passes:
  1. classify mode/intent/risk
  2. refresh session if needed
  3. retrieve candidates
  4. deconflict/suppress stale facts
  5. select operator sections
  6. enforce token budget
  7. assemble prompt
  8. emit debug trace
output: final Claude payload + context_pack_log record
```

This can become the internal engineering spec.
