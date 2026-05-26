# Conductor — Handoff / Current State
> Resume from here after any session reset, context compaction, or agent handoff.
> Last updated: May 2026 — Pausing after Expanded Actions Slice 3A.

---

## LOCKED / COMPLETE (do not re-audit or re-build)

| Slice | Sections | Test file | Result |
|---|---|---|---|
| D Slice 1 — ActionProof + Volume Readback | D01–D10 | `phase_d_slice1_eval.py` | ✅ LOCKED |
| D Slice 2 — Pan / Mute / Solo Readback | D11–D20 | `phase_d_slice2_eval.py` | ✅ LOCKED |
| D Slice 3 — `POST /feedback` | D21–D30 | `phase_d_slice3_eval.py` | ✅ LOCKED |
| D Slice 4 — Compensating Undo + Drift Detection | D31–D38 | `phase_d_slice4_eval.py` | ✅ LOCKED |
| D Slice 5 — Never-Do Preflight Gate | D41–D51 | `phase_d_slice5_eval.py` | ✅ LOCKED |
| Expanded Slice 1 — Track Management (Create/Delete/Duplicate/Color/Rename/Group) | D52–D73 | `phase_d_slice6_eval.py` | ✅ LOCKED |
| Expanded Slice 2 — Routing/Sends/Arm/Monitor/Transport | D74–D93 | `phase_d_slice7_eval.py` | ✅ LOCKED |
| Expanded Slice 3A — `POST /action/plugin_bypass` | D94–D102 | `phase_d_slice8_eval.py` | ✅ LOCKED — 9/9 PASS |

**Phase C — RAG / retrieval:** ✅ LOCKED (28 sections, 410 checks — run as regression in every subsequent slice)
**test_vault_integrity.py:** ✅ PASS — 15 pass / 0 fail / 4 warnings (cosmetic — no frontmatter in operator cards)

---

## LAST CONFIRMED TEST RUN (this session)

```
phase_d_slice8_eval.py  — 9/9  PASS  (D94–D102, includes Slice 7 + Phase C regression)
phase_d_slice7_eval.py  — 20/20 PASS (D74–D93)
phase_c_eval_set.py     — all sections PASS (410 checks)
test_vault_integrity.py — 15/15 PASS
```

---

## PAUSED HERE — DO NOT BUILD NEXT WITHOUT USER INSTRUCTION

### ROADMAP — Expanded Actions (not built, not started)

| Slice | What | Notes |
|---|---|---|
| **Expanded Slice 3B** | `POST /action/plugin_param` | Parameter changes via PluginBridge. Requires PluginBridge MCP to be stable. |
| **Expanded Slice 3C** | PluginBridge placement on track | Load PluginBridge VST3 on a track, select plugin from within Conductor. |
| **Expanded Slice 3D** | `POST /action/plugin_load` | Load a plugin onto a track via LOM (stock only) or PluginBridge. |
| **Expanded Slice 4** | Export / Bounce | Pending explicit user decision — CONFIRM_REQUIRED action. |
| **Expanded Slice 5** | Clip / scene / session-view actions | Pending user approval of scope. |

### ROADMAP — Phase D Product Layer (not built)

| Item | What | Priority |
|---|---|---|
| **D6** | Feedback UI buttons | Keep / Undo / Too much / Not enough / Wrong direction in `app/index.html` wired to `POST /feedback`. Endpoint already built. |
| **D7** | Session-end hook | Triggers `memory_promotion.py` on session close; summarises session, extracts decisions. |
| **D3** | Memory promotion / "dreaming" | `rag/memory_promotion.py` — promotes Level 1 → 2 → 3 → 4 silently at session end. |
| **UI** | CoProducer Translation layer | **Required before friend-test.** Wraps all ActionProofs, drift errors, and bridge errors in human-readable assistant dialogue. No raw JSON / no error enums reach the user. |
| **UI** | Drift diff dialog | Premium modal: "You changed X to Y. Restore to Z or keep?" |
| **UI** | Studio timeline / debugger | Visual view of `action_log.jsonl`. |

---

## UI / PRODUCTION RULES (locked product direction)

- `app/index.html` is **prototype-only**. Not production UI.
- Every production Execute path must call verified `/action/*` endpoints.
- UI must never show "Executed" unless backend returns a verified `ActionProof` response.
- **`CoProducerResponse` translation layer is required before any friend-test UI deployment.**
- Conductor must feel like a premium studio assistant — not a bank approval app. No raw JSON, no error code enums, no terminal-style output in the UI.
- HARD_BLOCK is for truly destructive actions only. All other risky actions → `REQUIRE_CONFIRMATION` (ask, don't block).

---

## SAFETY INVARIANTS — NON-NEGOTIABLE

- Gate 1 (undo: after_state must exist) — never bypassable, including `confirm=True`
- Gate 2 (undo: current state readable) — never bypassable
- Gate 3 (undo: drift check) — bypassable with `confirm=True` only
- `action_log.jsonl` + `action_proof_log.jsonl` — append-only, never modified
- `ok=True` only when `vstat` is `VERIFIED` or `ALREADY_CORRECT`
- Never-do check before every write, before any LOM call
- Availability precheck (track_route) and range validation (track_send) before any LOM call
- `bypass` field on `/action/plugin_bypass` — strict bool parsing only (no truthy-string bugs)

---

## KEY FILES

| File | Role |
|---|---|
| `rag/readback.py` | All readback loops (volume/pan/mute/solo/arm/monitor/send/route/transport/plugin_bypass) |
| `rag/undo_engine.py` | Three-gate undo, drift detection, PLUGIN_BYPASS undo, `_parse_plugin_target` |
| `rag/never_do_check.py` | Static never-do table — ALLOW / REQUIRE_CONFIRMATION / HARD_BLOCK / UNDO_LOG_REQUIRED |
| `rag/action_proof.py` | ActionProof dataclass, create_proof(), VerificationStatus |
| `rag/black_box_log.py` | Append-only log writers |
| `tools/conductor_bridge.py` | All HTTP endpoints — single gateway |
| `tests/phase_d_slice8_eval.py` | Slice 3A eval — D94–D102 |
| `tools/run_tests.sh` | Full suite runner (10 suites including slice 8) |
