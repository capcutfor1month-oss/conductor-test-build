# Phase D Future Build Ideas

> **Conductor Brain — Phase D Future Build Backlog**  
> **Purpose:** Keep future Phase D ideas separate from the current Phase D MVP / Slice 1 build.  
> **Current rule:** Do not add these to the first Claude build unless Codex validates that they are safe and necessary.

---

## Current Phase D MVP / Slice 1 Boundary

Phase D MVP should stay focused on the execution trust foundation:

- ActionProof v1
- before/after readback verification
- structured bridge errors
- request_id / action_id correlation
- separate black box JSONL logs
- deterministic never-do preflight
- track-volume readback verification first
- offline tests proving no “done” without readback

The MVP should **not** try to solve all undo, memory, dashboard, or plugin-state problems at once.

---

## Future Build Decision Filter

Future ideas should only move into an active build if they pass this filter:

1. Multiple research sources agree.
2. It protects the current working Phase A/B/C system.
3. It is general, not plugin/example-specific.
4. It is source-backed / real engineering pattern, not AI fantasy.
5. It matches the product goal: trusted assistant engineer for Ableton.
6. It reduces future confusion and has clear ownership.
7. It can be implemented safely in stages.

Reject or delay anything that is overbuilt, risky to current tests, example-specific, slow, unclear, or based on unvalidated Ableton/PluginBridge assumptions.

---

# Future Build Items

## 1. POST /feedback Endpoint

**Status:** ✅ BUILT — Phase D Slice 3.

Built:

- `POST /feedback` in `tools/conductor_bridge.py` v1.7
- requires `proof_id` or `action_id`
- stores feedback in `memory/feedback_log.jsonl` (separate, append-only)
- supports: `KEEP`, `UNDO`, `TOO_MUCH`, `NOT_ENOUGH`, `WRONG_DIRECTION`
- no immediate memory promotion (deferred to Slice 5 / D3)
- no ChromaDB write in the hot path
- eval: `tests/phase_d_slice3_eval.py` — 22/22 Slice 3 core pass

---

## 2. Simple Compensating Undo

**Status:** ✅ BUILT — Phase D Slice 4.

Built:

- `rag/undo_engine.py` — `execute_undo()`, `UNDOABLE_ACTION_TYPES`, `UndoValidationError`
- `POST /action/undo` in `tools/conductor_bridge.py` v1.8
- Undo flow exactly as designed:
  ```text
  read ActionProof → get before_state
  → read current live state → check drift
  → write before_state back → verify restore by readback
  → create new ActionProof (UNDO_{original_type}, undo_eligible=False)
  → log to black box log
  ```
- Supported: track volume, pan, mute, solo
- Not supported (intentionally deferred): batch undo, routing undo, master bus undo, track deletion restore, preset restore, plugin-chain restore, render/export undo
- eval: `tests/phase_d_slice4_eval.py` — 27/27 ALL PASS

---

## 3. Drift Detection Before Undo

**Status:** ✅ BUILT — Phase D Slice 4 (paired with compensating undo).

Built inside `rag/undo_engine.py`:
- Before any undo write, reads current live state via `_read_volume` / `_read_pan` / `_read_bool_property`
- Compares to original `after_state` from the ActionProof
- Scalar tolerance: 0.005 normalized (matches readback default); Boolean: exact match
- If drifted and `confirm=False` → HTTP 409, `STATE_DRIFT_COLLISION`, stub proof created, BBL logged
- If `confirm=True` → proceeds and notes drift in proof summary
- Example response when blocked:
  ```text
  Undo blocked: current volume=0.45 drifted from original after_state (0.5).
  Pass confirm=true to override.
  ```

---

## 4. UI Proof Receipts

**Status:** Future Phase D slice or parallel frontend sprint.

Add visible proof in the UI after actions.

Safe verified action:

```text
✓ Threshold -12 dB → -18 dB [Kick Bus / Glue Comp]
[Undo] [Details]
```

Failed/unverified action:

```text
⚠ I sent the command, but could not verify the result.
Please check Ableton. I will not mark this as done.
```

Rules:

- safe actions get compact receipts
- risky actions get fuller proof cards
- failed/unverified actions must be visible
- never show “done” unless verified or already correct

---

## 5. Expand Readback Support Beyond Track Volume

**Status:** Future after Slice 1 proves track volume.

Add readback verification for:

- track pan
- mute / solo
- send level
- track rename, if track identity is reliable
- exposed plugin parameter, only after bridge readback is validated

Avoid starting with plugin parameters because they introduce hidden-state and timing complexity.

---

## 6. Plugin Parameter Verification

**Status:** Future / validation required.

Add support for exposed plugin parameters only if PluginBridge can reliably:

- set the parameter
- read the parameter back
- identify the parameter consistently
- return structured errors when the parameter is not available
- handle stabilization delay / tolerance correctly

Do not claim plugin parameter proof if the plugin state cannot be read back.

---

## 7. Parameter-Specific Tolerance Tuning

**Status:** Future hardening.

The MVP can start with a configurable tolerance map.

Later, tune tolerance by parameter type:

- gain
- pan
- frequency
- boolean bypass
- send level
- true peak / limiter ceiling
- plugin-specific normalized values

Do not hardcode a single global epsilon forever.

---

## 8. Bridge-Side Idempotency Cache

**Status:** Nice-to-have future.

Useful for avoiding duplicate state-changing writes during retries or UI double-clicks.

Future behavior:

- state-changing requests carry idempotency keys
- duplicate key returns cached result
- mismatched payload with same key is rejected
- prevents double-write bugs

Not required before request_id/action_id and structured errors.

---

## 9. Advanced “What Did You Change?” Queries

**Status:** Future after black box logs exist.

MVP can answer simple session summaries.

Future queries:

- what did you change on vocals?
- what failed today?
- what did I undo?
- what changed since yesterday?
- what actions touched the master?
- what plugin writes failed readback?

Must query ActionProof / black box logs, not guess from chat history.

---

## 10. Session-End Summary

**Status:** Future after action logs + feedback are stable.

At session end:

- summarize verified actions
- summarize failed/unverified actions
- summarize undos
- summarize feedback
- list possible project decisions
- do not automatically write long-term memory yet

This should not inject raw black box logs into normal context.

---

## 11. Memory Promotion / Dreaming Engine

**Status:** Future / not MVP.

Runs only at session end or pre-compaction.

Possible flow:

```text
Level 1 raw events
→ Level 2 project decisions
→ Level 3 producer preferences
→ Level 4 never-do rules
```

Rules:

- no hot-path memory promotion
- no promotion from failed/unverified actions
- no promotion from one feedback click
- no automatic Level 3/4 writes
- user confirmation required for global preferences
- explicit confirmation required for never-do rules

Why future:

- Needs real verified action + feedback data first.
- Building it too early risks memory pollution.

---

## 12. Feedback Scope Confirmation UI

**Status:** Future, needed before safe memory promotion.

Ask user whether feedback applies to:

- this action only
- this project
- all future projects
- never again

Do not infer global producer preference silently.

---

## 13. Level 3 Producer Preference Promotion

**Status:** Future only.

Can be considered only when:

- similar verified actions appear across multiple projects
- feedback is repeatedly positive
- no contradiction exists
- user explicitly confirms global scope

Never promote from one action.

---

## 14. Level 4 Never-Do Rule Proposal Flow

**Status:** Future only.

Never-do rules must not be auto-generated from feedback alone.

Future flow:

```text
Conductor detects repeated negative feedback
→ proposes a possible never-do rule
→ user explicitly confirms
→ writes to conductor-vault/producer/never_do_rules.md
```

Never-do rules require explicit producer intent.

---

## 15. Never-Do Rule Editor and Versioning

**Status:** Future.

Possible features:

- add rule
- remove rule
- disable rule
- project-scoped rule
- global rule
- severity:
  - hard block
  - confirmation required
  - undo-log required
- rule version history
- conflict detection

MVP only parses and enforces the existing file.

---

## 16. Batch Undo

**Status:** Future / complex.

Batch undo requires dependency analysis.

Risks:

- action 4 may depend on action 3
- undoing one item may corrupt later edits
- partial batch failure needs per-target proof

Do not build in MVP.

---

## 17. Routing Undo

**Status:** Future / complex.

Routing can involve:

- output routing
- input routing
- sends
- sidechains
- bus dependencies
- multi-track signal flow

Requires full routing snapshot and safe compensation plan.

Do not build first.

---

## 18. Master Bus Undo

**Status:** Future / high-risk.

Master bus changes should be confirmed, verified, and logged in early phases.

Undo for master bus should wait for stronger gates and reliable proof.

Do not promise master bus undo in MVP.

---

## 19. Plugin Insert / Remove Undo

**Status:** Future.

Plugin insert can maybe be verified if the bridge exposes the device list.

Undo should wait because:

- chain order may change
- plugin state may not serialize
- user may manually reorder plugins
- removing the plugin may not restore sound reliably

Do not promise plugin insert/remove undo in first build.

---

## 20. Preset / Plugin-State Restore

**Status:** Future research.

Requires:

- plugin state snapshots
- preset identifiers
- parameter maps
- plugin-specific restore logic
- reliable bridge support

Not Phase D MVP.

---

## 21. Native Ableton Undo Stack Integration

**Status:** Rejected for MVP; future only if Ableton exposes reliable support.

Do not depend on:

- `Song.begin_undo_step()`
- `Song.end_undo_step()`
- `Song.undo()`

Reason:

- native undo stack is not reliably observable
- Conductor cannot prove what Ableton’s undo stack contains
- ActionProof + compensating writes are more auditable

---

## 22. VST3 Gesture Wrapper Integration

**Status:** PluginBridge roadmap / future validation.

Possible future concepts:

- `beginChangeGesture`
- `performEdit`
- `endChangeGesture`

Do not make this Phase D MVP.

Phase D should treat PluginBridge as the execution boundary and verify by readback.

---

## 23. SQLite Projection for Action History

**Status:** Future only.

JSONL remains the source of truth.

SQLite can be added later as a projection if needed for:

- large action history
- fast filtering
- cross-session queries
- analytics dashboard

Do not start with SQLite.

---

## 24. Trust / Debug Dashboard

**Status:** Future, valuable.

Possible dashboard:

- action timeline
- verified vs failed actions
- undo history
- feedback history
- never-do hits
- bridge errors
- plugin reliability
- readback latency
- unsupported undo actions

Useful later for debugging and product improvement.

---

## 25. Cross-Session Trust Statistics

**Status:** Future.

Track:

- which plugins verify reliably
- which action types fail often
- which parameters are unstable
- which actions users undo
- which actions receive “too much” feedback
- plugin/action reliability score

This should be based on real logs, not guesses.

---

## 26. Action Grouping / Scenario Undo

**Status:** Future.

Group related actions under a scenario:

- “warm vocal chain attempt”
- “drum bus tightening pass”
- “master loudness pass”

Allows feedback and undo at group level.

Requires strong dependency tracking, so not MVP.

---

## 27. Cloud / Hosted Telemetry

**Status:** Later / probably not Phase D.

Phase D should remain local-first.

No user session data should be sent externally by default.

---

# Phase D Slices 1–4 — What Was Built

> All items below are ✅ COMPLETE as of May 2026.

| Slice | What | Status |
|---|---|---|
| Slice 1 | ActionProof v1, structured errors, black box logs, track volume readback | ✅ |
| Slice 2 | Pan / mute / solo readback + bridge endpoints | ✅ |
| Slice 3 | POST /feedback — 5 feedback types, JSONL log | ✅ |
| Slice 4 | POST /action/undo — compensating undo + drift detection | ✅ |

---

# Still Not Built in Phase D (remaining)

- UI proof receipts (item 4 above)
- memory promotion / “dreaming” (D3)
- automatic Level 3 / Level 4 promotion (D3)
- session-end hook (D7)
- **batch undo** — dependency analysis needed; not safe without it
- **routing undo** — full signal-flow snapshot required
- **master bus undo** — higher risk, needs stronger proof gates
- plugin insert/remove undo
- preset restore
- native Ableton undo stack integration
- VST3 gesture wrappers
- SQLite projection (JSONL is source of truth, fine for now)
- trust dashboard
- cloud tracing / analytics
- graph RAG (Phase E)

---

# Recommended Next Build Order (Slice 5+)

Starting from Slices 1–4 complete:

1. **Slice 5a** — Batch undo: `proof_ids: [...]`, reverse-chronological, per-proof results
2. **Slice 5b** — Undo chain: `parent_proof_id` so undo-of-undo is detectable
3. **Slice 5c** — Action log fallback: look up `before_state` from `action_log.jsonl` when only BBL record exists
4. **Slice 5d** — Session undo summary: `GET /action/undo/list` returning all undo-eligible proofs
5. **Slice 6** — Memory promotion from feedback: UNDO feedback type + confirmed undo proof → eligible for Phase C promotion; no auto-promotion without user scope confirmation
6. **Slice 7** — UI proof receipts: compact receipt after verified actions, ⚠ card for failed/unverified
7. **Slice 8** — Session-end hook: summarize verified/failed/undone, extract promotion candidates, trigger dreaming
8. **Slice 9** — Plugin parameter verification: only after PluginBridge confirms reliable readback
9. **Slice 10** — Memory promotion “dreaming”: Level 1 → 2 → 3 → 4, session-end only, user confirms global scope

---

# Final Rule

Phase D future work should only be added after the foundation proves this contract:

```text
Conductor never says “done” unless the action is verified by readback.
```

Everything else is secondary.
