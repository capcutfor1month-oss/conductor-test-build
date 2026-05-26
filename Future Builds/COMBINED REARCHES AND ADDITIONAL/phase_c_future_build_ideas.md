# Phase C Future Build Ideas

> Archive only. Phase C C1–C6 is already PASS.  
> Do not treat any item here as already built.  
> This file preserves future Phase C research ideas so they are not lost.

## Current Phase C Status

- C1 Evidence labels: PASS
- C2 Context pack logging: PASS
- C3 Token budget: PASS
- C4 Corrective scope: PASS
- C5 Undo-log skeleton: PASS
- C6 BM25 hardening: PASS
- Phase C overall: PASS
- Blockers: none
- Ready for Phase D: yes

---

## 1. Advanced Corrective RAG

### Stronger entity/scope contradiction detection
- **Description:** Improve contradiction logic using explicit `project_id`, `plugin_id`, `track_id`, `parameter_key`, and `session_id` matching before marking memories as conflicting or superseded.
- **Why not now:** Current C4 scope-aware corrective RAG is passing and safe enough for the current backend kernel.
- **Prerequisite:** More real project/session records and a stable memory entity schema.
- **Priority:** Later

### Global preference conflict resolution UI
- **Description:** When producer preferences conflict, show both memories and let the user decide which one becomes active.
- **Why not now:** Needs UI/UX design and user confirmation flow.
- **Prerequisite:** Evidence viewer or memory-review panel.
- **Priority:** Later

### Stale/wrong-project audio suppression
- **Description:** Detect when audio-analysis memories belong to another project or stale session and suppress or label them clearly.
- **Why not now:** Current audio-analysis layer is not the main execution blocker.
- **Prerequisite:** Reliable project/session IDs attached to audio-analysis records.
- **Priority:** Later

### Confidence scoring improvements
- **Description:** Improve final evidence score using verification status, source type, recency, collection, and exact-match signals.
- **Why not now:** Current evidence labels and token budget already pass.
- **Prerequisite:** Retrieval evaluation dataset.
- **Priority:** Later

---

## 2. Advanced Hybrid Retrieval

### Better BM25/entity tokenizer
- **Description:** Improve tokenization for plugin aliases, compact names, hyphenated names, parameter names, track names, and failure codes.
- **Why not now:** C6 already handles current key cases like Pro-Q, ProQ4, Ozone12, F006, BRIDGE_TIMEOUT_003, LowShelf_Gain, and Kick_Bus_01.
- **Prerequisite:** More real failed retrieval examples.
- **Priority:** Later

### Field-weighted BM25
- **Description:** Give higher search weight to fields like `plugin_id`, `parameter_name`, `failure_code`, and `track_name` than body text.
- **Why not now:** Requires richer structured metadata in indexed records.
- **Prerequisite:** Phase A future metadata migration.
- **Priority:** Later

### RRF scoring experiments
- **Description:** Test Reciprocal Rank Fusion or other fusion formulas against current semantic + BM25 rescue.
- **Why not now:** Current retrieval is passing; avoid changing ranking without a benchmark.
- **Prerequisite:** Golden retrieval dataset.
- **Priority:** Research only

### Retrieval evaluation dataset
- **Description:** Build a dataset of queries with expected top results for plugins, parameters, track names, and failure codes.
- **Why not now:** Needs real usage data and failure examples.
- **Prerequisite:** Context-pack logs and manual labeling workflow.
- **Priority:** Later

---

## 3. Advanced Evidence and Audit System

### Richer context-pack log viewer
- **Description:** Build a local UI to inspect `context_pack_log.jsonl` records, showing injected/skipped evidence, scores, reasons, and token use.
- **Why not now:** JSONL logging already works; viewer is not required for backend readiness.
- **Prerequisite:** Stable log schema.
- **Priority:** Later

### Retrieval miss-rate metrics
- **Description:** Track how often retrieval returns no strong match or relies on fallback/generic evidence.
- **Why not now:** Needs enough real session data to be meaningful.
- **Prerequisite:** Production-style logs from real usage.
- **Priority:** Later

### Score histograms per collection
- **Description:** Visualize score distributions for each collection to tune thresholds.
- **Why not now:** Thresholds should not be tuned blindly without real query volume.
- **Prerequisite:** Larger query dataset.
- **Priority:** Later

### Golden dataset from real user failures
- **Description:** Convert real mistakes, bad retrievals, bad safety classifications, and user corrections into eval fixtures.
- **Why not now:** Needs actual user testing after Phase D execution starts.
- **Prerequisite:** Failure capture workflow.
- **Priority:** Later

---

## 4. Advanced Protection Model

### Larger adversarial prompt suite
- **Description:** Add many edge-case prompts for destructive edits, vague pronouns, unsupported GUI actions, batch edits, and mastering/export risk.
- **Why not now:** Current C protection tests pass; broader adversarial coverage is future hardening.
- **Prerequisite:** Collected real-world prompts and red-team cases.
- **Priority:** Later

### Learned/local risk classifier
- **Description:** Train or use a small local classifier to assist deterministic protection rules.
- **Why not now:** Rule-based protection is safer, faster, and passing. No LLM or model should be added to the hot path yet.
- **Prerequisite:** Large labeled safety dataset.
- **Priority:** Much later

### Stronger pronoun/target resolver
- **Description:** Resolve targets from recent history, active session focus, selected tracks, and user wording while still failing closed when ambiguous.
- **Why not now:** Current protection behavior passes core examples.
- **Prerequisite:** Reliable active selection and session focus from Phase D.
- **Priority:** Later

### Structured operation parser
- **Description:** Convert user intent into structured fields like `operation_type`, `target_scope`, `target_id`, `reversibility`, and `requires_undo`.
- **Why not now:** Needs Phase D execution contracts.
- **Prerequisite:** Stable action schema.
- **Priority:** Later

---

## 5. Advanced Undo and Transaction Layer

### Full rollback engine
- **Description:** Use undo records to actively restore prior DAW state after failure or user undo request.
- **Why not now:** C5 is only a skeleton. Real rollback needs Phase D execution/PluginBridge integration.
- **Prerequisite:** Reliable read/write adapters for Ableton and PluginBridge.
- **Priority:** Later

### Multi-step transaction grouping
- **Description:** Group multiple related operations into one transaction, such as adding a compressor, setting parameters, and routing to a bus.
- **Why not now:** Needs stable action execution and rollback primitives.
- **Prerequisite:** Phase D action executor.
- **Priority:** Later

### Rollback verification
- **Description:** After rollback, re-read DAW state and verify the previous values are restored.
- **Why not now:** Needs real live state readback.
- **Prerequisite:** Phase D verify-after-write system.
- **Priority:** Later

### Undo history browser
- **Description:** UI panel showing undo records, executed actions, failed actions, and rollback status.
- **Why not now:** Backend transaction layer must mature first.
- **Prerequisite:** Stable undo log format and action IDs.
- **Priority:** Later

### No-regression checks after execution
- **Description:** Verify that an operation did not worsen a metric, break routing, or change unrelated tracks.
- **Why not now:** Needs audio/project state evaluation after real execution.
- **Prerequisite:** Phase D and audio-analysis integration.
- **Priority:** Much later

---

## 6. Advanced Audio-Analysis Memory

### Stale audio-analysis detection
- **Description:** Mark audio-analysis records stale when they are older than the current session state or belong to a previous mix state.
- **Why not now:** Current Phase C safety is focused on retrieval/protection, not deep audio memory.
- **Prerequisite:** Audio-analysis records with project/session hashes.
- **Priority:** Later

### Wrong-project audio suppression
- **Description:** Prevent audio-analysis memories from one project influencing another project.
- **Why not now:** Needs robust project identity and audio-analysis metadata.
- **Prerequisite:** Project/session ID consistency.
- **Priority:** Later

### Mix metric history
- **Description:** Track LUFS, true peak, crest factor, spectral balance, and dynamic range over time.
- **Why not now:** Requires stable audio analyzer pipeline.
- **Prerequisite:** Phase D or later audio-analysis execution hooks.
- **Priority:** Later

### Reference-track analysis memory
- **Description:** Store reference-track fingerprints and compare current mix decisions against them.
- **Why not now:** Requires stable audio features and user-approved reference workflows.
- **Prerequisite:** Audio feature extractor and project-level reference mapping.
- **Priority:** Later

### Multimodal/audio retrieval
- **Description:** Retrieve based on audio features, waveforms, screenshots, meters, or plugin UI images.
- **Why not now:** Too complex for current local-first backend kernel.
- **Prerequisite:** Multimodal embedding/eval strategy.
- **Priority:** Research only

---

## 7. Future Research-Only Ideas

### Graph RAG
- **Description:** Add graph relationships between projects, plugins, tracks, preferences, and failure cases.
- **Why not now:** Graph databases add complexity and are unnecessary at current scale.
- **Prerequisite:** Clear proof that metadata filters + hybrid retrieval are insufficient.
- **Priority:** Research only

### Offline cross-encoder reranker
- **Description:** Use a local reranker to reorder retrieved chunks after BM25/vector retrieval.
- **Why not now:** Adds latency and complexity. Current retrieval passes.
- **Prerequisite:** Golden retrieval dataset showing ranking problems.
- **Priority:** Research only

### LLM-as-judge for offline evals only
- **Description:** Use an LLM to review retrieval/context quality offline, never during hot execution.
- **Why not now:** Hot path must stay deterministic and local.
- **Prerequisite:** Offline eval harness and fixed datasets.
- **Priority:** Research only

### Optional cloud/LangSmith tracing
- **Description:** Send traces to a cloud observability tool for richer dashboards.
- **Why not now:** Conductor is local-first; JSONL logging already works.
- **Prerequisite:** User opt-in and privacy model.
- **Priority:** Much later

### Team/shared retrieval dashboard
- **Description:** Dashboard for multiple testers to inspect retrieval quality, safety blocks, and failure trends.
- **Why not now:** Solo/local development comes first.
- **Prerequisite:** Stable logging, dataset format, and review workflow.
- **Priority:** Much later
