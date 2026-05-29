# Conductor — Build Phases Temporary Memory
> DELETE THIS FILE once all phases are built, tested, and logged into relevant MD files.
> Purpose: survive context compaction. Resume from here after any session reset.
> Last updated: May 2026

---

## HOW TO USE THIS FILE

At the start of any new session, read this file first.
Find the first item marked ❌ and continue from there.
Mark ✅ when built + tested + logged into project.md / LIMITATIONS.md.

---

## CURRENT STATUS

Phase A — ✅ COMPLETE
Phase B — ✅ COMPLETE
Phase C — ✅ COMPLETE
Phase D — IN PROGRESS (Slices 1–5 complete, Expanded Actions 1–3A complete, Live Harness Slices 9–19 complete)
Phase E — NOT STARTED

### Locked Slices (current build)
- D Slices 1–5: PASS/LOCKED
- Expanded Actions Slice 1 (track management): PASS/LOCKED
- Expanded Actions Slice 2 (routing/sends/transport): PASS/LOCKED
- Expanded Actions Slice 3A (plugin_bypass): PASS/LOCKED
- Live Harness v1.5 (`app/harness.html`): present — product-preview shell
- D Slice 9 — Strict Confirm Parser: PASS/LOCKED
- D Slice 10 — GET /session/state: PASS/LOCKED
- D Slice 11 — Natural Replies + Premium UI: PASS/LOCKED
- D Slice 12 — Knowledge Gateway v1 (`POST /harness/orchestrate`): PASS/LOCKED
- D Slice 13 — `/session/state` v1.5: PASS/LOCKED
- D Slice 14 — Knowledge Explorer v1 (Build 6 + hardening): PASS/LOCKED
- D Slice 15 — Creative Critic v1 (Build 7): PASS/LOCKED
- D Slice 16 — Card-aware Creative Critic v1 (Build 8): PASS/LOCKED
- D Slice 17 — Plugin Knowledge Routing v1 (Builds 9 + 10): PASS/LOCKED
- D Slice 18 — Plugin Knowledge Trust Signals (Build 11): PASS/LOCKED
- D Slice 19 — Knowledge Status Context to Critic (Build 12): PASS/LOCKED

### Pending (not built)
- Product-layer re-alignment: docs → harness UX → session-state context → metadata hiding
- `track_delete` and `transport_record` disabled in harness pending confirmation UI
- `route_track` routing actions require careful confirmation policy
- ChromaDB memory may be missing locally — do not describe as fully available unless installed
- Future slices: plugin_param, plugin_load, export/bounce, clip/scene, memory promotion, marketplace, tutorial creator, Studio OS expansion remain roadmap

---

## PHASE A — FOUNDATION
> Goal: right files in the right places. No intelligence yet. That comes in Phase B.
> All files are readable by Conductor — not yet retrieved intelligently.

| # | What | File/Path | Status |
|---|---|---|---|
| A1 | Plugin scanner | `tools/plugin_scanner.py` | ✅ |
| A2 | Known plugins database | `data/known_plugins.json` (54 entries + aliases) | ✅ |
| A3 | Vault folder structure | `conductor-vault/` | ✅ |
| A4 | Producer DNA template | `conductor-vault/producer/producer_dna.md` | ✅ |
| A5 | Never Do Rules defaults | `conductor-vault/producer/never_do_rules.md` | ✅ |
| A6 | Studio Inventory template | `conductor-vault/studio/studio_inventory.md` (written by scanner) | ✅ |
| A7 | Operator card — Pro-Q 4 | `conductor-vault/plugins/Pro-Q 4 Operator Card.md` | ✅ |
| A8 | Operator card — Ozone 12 | `conductor-vault/plugins/Ozone 12 Operator Card.md` | ✅ |
| A9 | Operator card — Serum 2 | `conductor-vault/plugins/Serum 2 Operator Card.md` | ✅ |
| A10 | Operator card — EQ Eight | `conductor-vault/plugins/Ableton Stock Devices.md` (all stock combined) | ✅ |
| A11 | Operator card — Compressor | (combined into Ableton Stock Devices.md above) | ✅ |
| A12 | Failure cases folder | `conductor-vault/failure-cases/` — 6 LOM failures logged | ✅ |
| A13 | Onboarding flow doc | `documents/ONBOARDING_FLOW.md` | ✅ |
| A14 | RAG architecture doc | `docs/CONDUCTOR_RAG_ARCHITECTURE.md` | ✅ |
| A15 | Update project.md | Component #12 added, build status updated, Audit 3 logged | ✅ |
| A16 | Update LIMITATIONS.md | Phase A–E roadmap added | ✅ |

### Phase A — Vault folder structure (updated)

```
conductor-vault/
│
├── indexes/                        ← index files only, under 200 lines each
│   ├── memory.md                   ← master index, points to all other files
│   ├── plugins.md                  ← index of all operator cards
│   ├── projects.md                 ← index of all project files
│   └── tools.md                   ← index of all tool/DAW references
│
├── producer/
│   ├── producer_dna.md             ← taste, genres, workflow, permissions
│   ├── never_do_rules.md           ← hard safety rules
│   ├── confirmed_preferences.md    ← Level 3–4 memory
│   ├── rejected_patterns.md        ← what failed / what to avoid
│   └── workflow_style.md           ← how this producer works
│
├── studio/
│   ├── studio_inventory.md         ← written by plugin scanner
│   ├── plugin_inventory.md         ← full plugin list + risk levels
│   └── daw_setup.md                ← Ableton routing + MCP setup
│
├── plugins/                        ← operator cards, one file per plugin
│   ├── Pro-Q 4 Operator Card.md
│   ├── Ozone 12 Operator Card.md
│   ├── Serum 2 Operator Card.md
│   └── Ableton Stock Devices.md
│
├── projects/
│   └── [PROJECT-UUID]/
│       ├── current_state.md        ← live project state
│       ├── session_summary.md      ← rolling 5-save history
│       ├── daily_logs/             ← one file per date
│       ├── decisions/              ← confirmed / rejected / experiments
│       ├── audio_analysis/         ← stored LUFS / spectrum snapshots
│       └── audit_log.md            ← verbatim action timeline (on demand only)
│
├── references/
│   ├── genres/                     ← Punjabi Pop, Hindi Cinematic, etc.
│   ├── reference_tracks/           ← Reference Track DNA files
│   ├── manuals/                    ← plugin manual notes
│   └── techniques/                 ← mixing, EQ, orchestration etc.
│
└── memory_db/                      ← populated by ChromaDB/Qdrant
    ├── vector_index/
    ├── graph_index/                ← Phase E
    └── verbatim_index/             ← Phase D audit recall
```

### Phase A — Key decisions locked

- Vault is a folder of Markdown files. Obsidian NOT required for users.
- Plugin scanner runs at install time. Scans VST3/AU/VST paths on macOS.
- Only asks 4 questions: primary EQ / compressor / reverb / saturator.
- These 4 anchor plugins get full operator cards. Rest go into Studio Inventory as "owned."
- Source-of-truth files (already exist in NotebookLM Sources/) get indexed into ChromaDB for public users → replaces NotebookLM for basic use.
- NotebookLM stays as optional power-user feature (connect via Tutorials panel).
- Progressive model: works on day one, unlocks more as user configures.
- **system_prompt.md is the bootloader, not the whole brain. Target: under 200–300 lines. Reference external files — do not inline them.**
- **Context rot (video definition): system_prompt.md gets too big → Claude reads all of it at session start → attention dilutes → rules at the bottom get ignored. Fix: keep it small, point to external files.**
- **ChromaDB degradation is a separate problem** — retrieval quality drops after 150+ sessions due to no time decay, duplicates, contradictions. See LIMITATIONS.md. Not the same as context rot.

### Vault file rules (from video — 200 line rule)

- Every master/index file stays under 200 lines.
- No file dumps everything. Each file = one topic.
- Master files are indexes only — they point to topic files, not contain them.
- Topic detail lives in its own file, loaded only when that topic is relevant.
- Example: `conductor-vault/index.md` lists what exists.
  `conductor-vault/plugins/Pro-Q 4 Operator Card.md` loaded only when Pro-Q 4 is in use.
- system_prompt.md should reference external files, not contain them inline.
- ableton.md should become index.md + separate topic files per failure case.

### Plugin scanner — what it scans (macOS)

```
/Library/Audio/Plug-ins/VST3/
~/Library/Audio/Plug-ins/VST3/
/Library/Audio/Plug-ins/Components/
~/Library/Audio/Plug-ins/Components/
/Library/Audio/Plug-ins/VST/
~/Library/Audio/Plug-ins/VST/
```

### Plugin scanner — output format

Writes `conductor-vault/Studio Inventory.md` automatically.
Columns: Plugin name | Type | Manufacturer | Operator Card loaded (yes/no)
Anchor plugins marked separately.

---

## PHASE B — CONTEXT PACK
> Goal: vault + memory + live Ableton state actually reaches the AI on every call.
> This is the single biggest gap. Nothing is injected right now.
>
> KEY LESSON FROM VIDEO: Do NOT rely on Claude deciding to search memory.
> Use a HOOK. Fire it automatically. Claude never has to remember to look.
> Delivery model: hook fires → injects index + top 3 matches → every prompt gets context.

| # | What | File/Path | Status |
|---|---|---|---|
| B1 | Context pack builder | `rag/context_pack_builder.py` | ✅ |
| B2 | Request mode classifier | `rag/request_mode_classifier.py` — 13/13 tests pass | ✅ |
| B3 | Risk classifier | Folded into B2 — risk_reason field in classify() return | ✅ |
| B4 | Wire context pack into UI | `conductorSendToAPI()` in `app/index.html` — real API call, streaming | ✅ |
| B5 | Bridge endpoint for context pack | `GET /context/pack` + `GET /context/system_prompt` in conductor_bridge.py | ✅ |
| B6 | Session-start hook | `conductorSessionStart()` — fires in DOMContentLoaded, fetches system prompt + baseline pack | ✅ |
| B7 | Prompt-submit hook | Inside `conductorSendToAPI()` — fetches fresh context pack per message | ✅ |
| B8 | Pre-risky-action hook | Inline confirmation UI in chat — blocks RISKY_WRITE until user approves | ✅ |
| B9 | Context Pack Debug view | Collapsible debug block after every AI response — mode, risk, sources, tokens, memories | ✅ |
| B10 | Session pack versioning | `session_pack_version` (ISO timestamp) + `state_hash` (12-char MD5) in `/context/session` response | ✅ |
| B11 | Stale session auto-refresh | If pack age > 30s before any RISKY action → auto-refresh Layer B first, then confirm | ✅ |
| B12 | Mode/risk at top of Layer C | `## MESSAGE PACK` header with Mode/Risk/Confirmation leads every message pack — Claude sees intent before context | ✅ |
| B13 | Dev mode | DEV toolbar button — auto-opens debug blocks, shows raw session pack excerpt, persisted to localStorage | ✅ |

### Request mode classifier — 5 modes

```
MENTOR          → advice, education, explanation. No tools needed.
INTERN_READ     → inspect Ableton/session/audio/memory. Tools OK.
INTERN_WRITE_SAFE   → small reversible change. Define result, execute, verify.
INTERN_WRITE_RISKY  → master/delete/export/batch/replace plugin. Confirm first.
CLARIFY         → request is ambiguous or unsafe without one answer.
```

### Context pack format — Three layers sent to Anthropic

**Layer A** — `system:` param — always sent every call. Never in user content.
```
You are Conductor, Adi's personal AI music production assistant…
```

**Layer B** — Session pack — injected once at session start, refreshed on state change.
Includes `session_pack_version` (ISO timestamp) and `state_hash` (12-char MD5) for staleness detection.
```md
## PRODUCER DNA
Producer: Adi | Level: Stage 3 diploma | Primary genre: Bollywood/Punjabi
Sound: cinematic · punchy · emotional | Anchor plugins: Pro-Q 4 · Ozone 12

## CURRENT PROJECT STATE
Project: [name] | Stage: [0-4] | BPM: [x] | Key: [x]

## TOOL STATUS
Ableton: connected | Audio Analyzer: available | Memory (ChromaDB): ready
```

**Layer C** — Message pack — fresh every message. Mode/risk leads — Claude sees intent before context.
```md
## MESSAGE PACK
Mode: INTERN_WRITE_RISKY
Risk: HIGH
Confirmation required: YES
Reason: Ozone 12 on master bus — HIGH risk plugin

Relevant retrieved context:

### Memory
1. [top ChromaDB result — 200 chars]
2. [second result]
3. [third result]

## OPERATOR CARD — Ozone 12
[Identity + Risky Writes + Never Do sections only]
```

**Staleness rules:**
- Layer B age > 30s before any `INTERN_WRITE_RISKY` → auto-refresh before confirm gate
- `state_hash` stored by UI; if bridge poll returns a different hash → force refresh
- Risky operations covered: master bus, Ozone, delete, export, routing, tempo/key, batch

---

## PHASE B — KEY ADDITIONS (logged here for completeness)
> Phase B completed before this file existed in detail. Adding the key decisions that were locked.

### Protection Model (added late Phase B)
`rag/protection_model.py` — replaces flat SAFE/RISKY with a 6-level protection model:
```
STATUS_ONLY          → advice/read — no write
AUTO_EXECUTE_ALLOWED → safe reversible write — execute directly
UNDO_LOG_REQUIRED    → medium reversible write (patch replace, randomise)
CONFIRM_REQUIRED     → dangerous/global/master/export — user must confirm
CLARIFY_REQUIRED     → unclear pronoun target — ask one question first
BLOCK_UNSUPPORTED    → GUI/mouse actions — can't execute, explain why
```

### Risk Taxonomy (added late Phase B)
`rag/risk_taxonomy.py` — generalization-first risky action classification:
- ACTION_CATEGORIES (delete, master_level, freeze_flatten, plugin_replace, …)
- Known plugins database at `data/known_plugins.json` (54 entries + camelCase aliases)
- Operator card file lookup by plugin alias (`get_card_file_for_message()`)
- `classify_risk()` returns `{is_risky, category, matched, reason}`

### Memory Write Contract (added late Phase B)
Every `POST /memory` caller must include: `mode`, `collection`, valid metadata, `source_type`.
Documented in `app/system_prompt.md` under `## MEMORY WRITE CONTRACT`.
Enforced in `conductor_bridge.py` — mode-absent writes get a `warnings[]` in response,
FREEFORM_GENERAL writes to project collection are hard-blocked (HTTP 400).

---

## PHASE C — RETRIEVAL QUALITY
> Goal: smarter search. Right memory reaches the AI, not just any memory.
> Status: ✅ COMPLETE. All 28 sections of phase_c_eval_set.py pass / 0 fail.
> Codex review: PASS (all C1–C6 sub-steps reviewed and signed off, no revert needed).

| # | What | File/Path | Status |
|---|---|---|---|
| C1 | Multi-index ChromaDB collections — 5 targeted indexes | `rag/memory_schema.py` — schema, thresholds, validation | ✅ |
| C1 | Routed retriever replacing legacy `_query_memory()` | `rag/routed_retriever.py` — mode → collection routing | ✅ |
| C1 | Vault seeder — failure cases → ChromaDB at startup | `tools/seeder.py` — idempotent upsert, stable IDs | ✅ |
| C1 S1 | Evidence label completeness — 11 new EvidenceItem fields | `rag/routed_retriever.py` — source_type, verification_status, bm25_score, reason_injected, token_count, project_id, session_id, plugin_id, freshness, rescue_mode, conflict_flag | ✅ |
| C1 S1 | reason_injected normalization after C3 corrective check | `rag/routed_retriever.py` — C3-suppressed items always get reason_injected="not_injected" | ✅ |
| C1 S1 | All 11 fields exposed in debug.evidence per /context/pack | `rag/context_pack_builder.py` — evidence dict expanded to 25 fields total | ✅ |
| C2 | Temporal memory scoring | `rag/memory_scoring.py` — semantic×0.60 + recency×0.30 + freq×0.10 | ✅ |
| C2 | Context pack audit logging — JSONL per /context/pack call | `rag/context_pack_logger.py` — best-effort, non-fatal, thread-safe | ✅ |
| C2 | Bridge wired to logger | `tools/conductor_bridge.py` — log_pack() + log_pack_error() hooks | ✅ |
| C3 | Corrective RAG — write-time supersession | `rag/corrective_check.py` `find_superseded_by_new()` | ✅ |
| C3 | Corrective RAG — read-time in-flight suppression | `rag/corrective_check.py` `apply_corrective_check()` | ✅ |
| C3 | Token budget/drop policy — Layer C evidence pruning | `rag/token_budget.py` — drops lowest-priority injected items; Level 4 + failure_cases protected | ✅ |
| C3 | Budget hook wired into retrieve() after scoring | `rag/routed_retriever.py` — runs after final_score set, before all_injected built | ✅ |
| C4 | Evidence labels on every retrieved item | `rag/routed_retriever.py` — EvidenceItem C4 fields | ✅ |
| C4 | Evidence labels exposed in /context/pack debug | `rag/context_pack_builder.py` — 14-field evidence dict (original C4) | ✅ |
| C4 | Entity/scope-aware corrective RAG — over-supersession prevention | `rag/corrective_check.py` — different project_id: skip; different plugin_id: conflict_flag only | ✅ |
| C5 | Hybrid search — semantic + BM25 exact-term rescue | `rag/routed_retriever.py` — `_bm25_rescue()` | ✅ |
| C5 | Undo log skeleton — append-only JSONL pre-execution log | `rag/undo_log.py` — create_undo_record, mark_executed, mark_failed, UndoLogRequiredError | ✅ |
| C6 | Memory type routing — LangMem/Letta taxonomy applied | `rag/memory_schema.py` — `MODE_COLLECTION_MAP` redesign | ✅ |
| C6 | BM25 exact recall hardening — enhanced tokenizer | `rag/routed_retriever.py` — `_bm25_tokenize()` splits on _, -, . + alpha/numeric | ✅ |
| C6 | rescue_mode="bm25_exact" for top-75% batch score | `rag/routed_retriever.py` — `BM25_EXACT_FRACTION = 0.75` | ✅ |
| C6 | Content-hash dedup within BM25 rescue batch | `rag/routed_retriever.py` — `seen_content_hashes` set prevents same text twice | ✅ |
| A1 | Plugin/card/parameter-map JSON schemas | `data/schemas/plugin_metadata.schema.json`, `operator_card.schema.json`, `parameter_map.schema.json` | ✅ |
| A1 | Vault integrity test suite | `tests/test_vault_integrity.py` — 15 pass, 0 fail, 4 warnings (no frontmatter in cards) | ✅ |
| — | Test suite — 28 sections, 0 failures | `tests/phase_c_eval_set.py` | ✅ |

### C1 — 5 Collections (multi-index split)

| Collection | Memory type | What it stores | Similarity threshold |
|---|---|---|---|
| `producer_memory_index` | Semantic | Producer taste, habits, confirmed preferences | 0.35 |
| `project_session_index` | Episodic | Current-song decisions and history | 0.40 |
| `plugin_operator_index` | Procedural/archival | Plugin capability, param maps, quirks, operator cards | 0.30 |
| `failure_cases_index` | Procedural/safety | PluginBridge/LOM failures, known bugs, confirmed fixes | 0.30 |
| `audio_analysis_index` | Measurement/evidence | LUFS, spectrum, stereo width snapshots | 0.50 |

**Source-of-truth:** `rag/memory_schema.py` — never hardcode collection names elsewhere.

### C1 — Mode → Collection routing (updated in Phase C, late)

Applied LangMem/Letta/MIRIX taxonomy. Plugin data no longer dumped into producer_memory_index.

| Mode | Collections searched |
|---|---|
| `MENTOR` | producer · plugin_operator · failure (advisory) |
| `INTERN_READ` | project · producer · plugin_operator · audio |
| `INTERN_WRITE_SAFE` | producer · plugin_operator · failure |
| `INTERN_WRITE_RISKY` | failure · plugin_operator · producer · audio (safety-first order) |
| `CLARIFY` | producer |
| `FREEFORM_GENERAL` | (none) |

**Key routing decisions:**
- `MENTOR` now includes `failure_cases_index`: advisory "what went wrong" queries need failure context. No execution risk — MENTOR is retrieval-only.
- `INTERN_READ` now includes `plugin_operator_index` (show plugin params) and `audio_analysis_index` (show LUFS).
- `project_session_index` excluded from `INTERN_WRITE_RISKY`: session history is noise before a dangerous write.
- RISKY order enforced by `RISKY_WRITE_RETRIEVAL_ORDER` — safety rules first, not alphabetical.

### C2 — Temporal memory scoring

```python
final_score = semantic × 0.60 + recency × 0.30 + frequency × 0.10
```
- Recency: exponential decay, half-life = 7 days
- Level 4 memories always score 9999 — bypass threshold + float to top
- Missing `created_at` → recency = 0.5 (neutral, no crash)
- Global sort across all collections after C3 check

### C3 — Corrective RAG (two-layer contradiction protection)

**Layer 1 — Write-time:**
- After `col.add()` in `conductor_bridge.py`, `find_superseded_by_new()` runs
- Jaccard similarity (threshold 0.70) against recent memories in same collection
- Old matching memories get `superseded_by=new_id` written back to ChromaDB metadata
- Bridge response includes `superseded: [old_id, …]` for transparency

**Layer 2 — Read-time (in-flight):**
- `apply_corrective_check()` called in `retrieve()` after all collections queried
- Groups items by collection, compares pairs with Jaccard (threshold 0.40)
- Newer item (lower `age_days`) wins; on tie, higher `final_score` wins
- Loser gets `injected=False`, `reason="in-flight superseded by X (C3 contradiction: Jaccard=Y)"`
- Cross-collection: no suppression — failure memory never suppresses producer memory

### C1 Step 1 — Evidence Label Completeness (11 new fields)

Every `EvidenceItem` now exposes 11 additional completeness fields beyond the C4 originals:
```
source_type · verification_status · bm25_score · reason_injected · token_count
project_id · session_id · plugin_id · freshness · rescue_mode · conflict_flag
```
`reason_injected` normalization: `_apply_threshold()` sets it; `apply_corrective_check()` can later flip `injected=True→False` — a normalization pass after C3 corrects `"retrieval_match"` to `"not_injected"` on any suppressed item.

### C2 — Context Pack Audit Logging

`rag/context_pack_logger.py` — writes one JSONL record per `/context/pack` call to `memory/context_pack_log.jsonl`.
Record: timestamp, query, mode, protection_level, risk_category, pack_chars, token_estimate, memory_hits, injected_count, plugin_card, freeform, evidence (all 25 fields + text_preview), skipped list.
Best-effort: logging failure never breaks `/context/pack`. Thread-safe via `threading.Lock()`.

### C3 — Token Budget / Drop Policy

`rag/token_budget.py` — `apply_token_budget()` called in `retrieve()` after `final_score` is set.
Budget: `DEFAULT_BUDGET_TOKENS = 2000`. Drops lowest-priority injected items first.
Priority tiers (never dropped = P0/P1):
```
P0 memory_level == 4           Never-Do — absolutely protected
P1 failure_cases_index         safety evidence — protected
P2 memory_level == 3           dropped last after P0/P1 exhausted
P3 memory_level == 2
P4 memory_level == 1 or unknown   dropped first
```
Within tier: lowest `final_score` dropped first. Hard stop at P0/P1 — accepts budget overrun rather than drop safety evidence.
Dropped items: `injected=False`, `reason="token_budget_exceeded"`, `reason_injected="not_injected"`. Remain in `debug.evidence`.

### C4 — Evidence Labels + Scope-aware Corrective RAG

Original C4 — every `EvidenceItem` exposes:
```
id · confidence · age_days · final_score · superseded_by · rejected
```
Every `debug.evidence` dict in `/context/pack` response exposes 25 fields total (14 original C4 + 11 C1 Step 1).

Short source labels: `[producer]`, `[project]`, `[plugin]`, `[failure]`
BM25 rescue items: `[producer·bm25]`, `[producer·bm25_exact]`
Audio freshness items: `[audio·fresh]`, `[audio·stale] ⚠`, `[audio·old] ⚠`

**C4 scope-aware enhancement** (`rag/corrective_check.py`):
- Different non-empty `project_id` on both items → skip (different projects can't conflict)
- Different non-empty `plugin_id` on both items → set `conflict_flag=True` on both, no suppression
- Same project_id (or both empty) + same plugin_id (or both empty) → existing Jaccard logic unchanged

### C5 — Hybrid BM25 Search + Undo Log Skeleton

**Hybrid BM25 search** (original C5):
Strategy: semantic-first with BM25 rescue.
1. ChromaDB cosine similarity search (primary)
2. BM25 (`rank_bm25.BM25Okapi`) on full collection — rescues exact plugin names, bus names, failure codes
3. BM25 hits not already in semantic results → added with `similarity=0.45`
4. Items found by both: keep semantic similarity
`BM25_RESCUE_SIMILARITY = 0.45` — above all collection thresholds (0.30–0.40), below audio 0.50 by design.
Graceful fallback: if `rank_bm25` not installed → BM25 step silently skipped.

**Undo log skeleton** (`rag/undo_log.py`):
Append-only JSONL to `memory/undo_log.jsonl`. Three operations:
- `create_undo_record(action_type, prior_state, **kwargs)` → `record_id` — written before action, `executed=False`
- `mark_executed(record_id)` → appends `{executed:True}` outcome record
- `mark_failed(record_id, error)` → appends `{failed:True, error:...}` outcome record
- `UndoLogRequiredError` — raised if `protection_level="UNDO_LOG_REQUIRED"` and `prior_state` is missing/empty
Scope: skeleton only — infrastructure for pre-execution state capture. Full rollback (re-applying prior_state to Ableton LOM) is Phase D.

### Memory levels (unchanged from design)

```
Level 1 — Raw event         (weak — session only, eligible to expire)
Level 2 — Session decision  (medium — project-specific, kept across sessions)
Level 3 — Confirmed preference (strong — cross-project, user explicitly approved)
Level 4 — Producer rule / Never-Do (strongest — always retrieved, bypasses threshold)
```

### C6 — BM25 Exact Recall Hardening

`_bm25_tokenize(text)` added to `routed_retriever.py` — replaces naive `.lower().split()` in `_bm25_rescue()`:
- Splits on `_`, `-`, `.` separators and keeps both parts and compound
- Splits alpha runs from digit runs (e.g. `Ozone12` → `ozone`, `12`, `ozone12`)
- Handles: `Pro-Q`, `ProQ4`, `Ozone12`, `F006`, `BRIDGE_TIMEOUT_003`, `LowShelf_Gain`, `Kick_Bus_01`

`rescue_mode="bm25_exact"` set when BM25 score ≥ top score × `BM25_EXACT_FRACTION` (0.75). Otherwise `"bm25"`.
Label reflects: `[producer·bm25_exact]` vs `[producer·bm25]`.

Content-hash dedup: `hashlib.md5(doc)` tracked within each `_bm25_rescue()` call — same text with different ChromaDB IDs not added twice.

BM25 rescue still respects mode/routing/protection — it runs per-collection inside the existing routing loop, same `_apply_threshold()` and C3 checks apply.

### Phase C — Key files

| File | Role |
|---|---|
| `rag/memory_schema.py` | Single source of truth: collections, thresholds, levels, mode map, validation |
| `rag/routed_retriever.py` | Main retrieval engine: routing, BM25 (C5+C6), C3 corrective, C4 scoring, budget hook, global sort |
| `rag/corrective_check.py` | Corrective RAG: Jaccard contradiction, write-time + read-time, C4 scope guards |
| `rag/memory_scoring.py` | Temporal scoring: recency decay, frequency |
| `rag/token_budget.py` | Token budget/drop policy: priority tiers, hard-stop for Level 4 + failure_cases |
| `rag/context_pack_logger.py` | C2 audit logger: JSONL per /context/pack, best-effort, thread-safe |
| `rag/undo_log.py` | C5 undo log skeleton: pre-execution state capture, outcome markers, UndoLogRequiredError |
| `rag/context_pack_builder.py` | Builds full context pack: calls retrieve(), formats 25-field evidence dict |
| `rag/protection_model.py` | B2-era protection levels (updated Phase B, unchanged in C) |
| `rag/request_mode_classifier.py` | Mode classification (Phase B, routing updated in Phase C) |
| `rag/risk_taxonomy.py` | Plugin risk, operator card lookup, risky action categories |
| `tools/conductor_bridge.py` | HTTP bridge: POST /memory write contract + C3 supersession + C2 logging hooks |
| `tools/seeder.py` | Vault → ChromaDB seeder (idempotent, stable IDs) |
| `data/schemas/` | A1 JSON schemas: plugin_metadata, operator_card, parameter_map |
| `tests/phase_c_eval_set.py` | 28-section eval suite: mode, routing, scoring, C1–C6, budget, undo, BM25 hardening |
| `tests/test_vault_integrity.py` | A1 vault integrity: schema validation, known_plugins.json, operator cards |

---

## PHASE D — TRUST LAYER
> Goal: producer can see what changed, approve it, and Conductor learns from the answer.
>
> KEY LESSON FROM VIDEO: Memory promotion ("dreaming") runs at SESSION END silently.
> Not when user says "remember this." Automatically. Scores decisions by recency + repetition.
> Promotes Level 1 → 2 → 3 → 4. Forgets stale one-offs. Never saves guesses.

### Phase D — Slice 1 (ActionProof + Structured Errors + Volume Readback) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D1-S1 | ActionProof v1 — before/after proof dataclass | `rag/action_proof.py` — create_proof(), read_all_proofs(), VerificationStatus enum | ✅ |
| D1-S1 | Structured bridge error codes | `rag/bridge_errors.py` — BridgeErrorCode enum, error_response(), ok_response() | ✅ |
| D1-S1 | Black box JSONL logs | `rag/black_box_log.py` — log_event(), log_requested(); `memory/action_log.jsonl`, `memory/action_proof_log.jsonl` | ✅ |
| D1-S1 | Track volume readback + verification | `rag/readback.py` — verify_track_volume(); 6-step readback loop; ALREADY_CORRECT detection | ✅ |
| D1-S1 | POST /action/volume bridge endpoint | `tools/conductor_bridge.py` v1.5 — request_id/action_id correlation, structured errors | ✅ |
| D1-S1 | Phase D Slice 1 eval suite | `tests/phase_d_slice1_eval.py` — D01–D10 offline tests, 0 failures | ✅ |

### Phase D — Slice 2 (Expanded Readback: Pan / Mute / Solo) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D1-S2 | Pan readback + verification | `rag/readback.py` — verify_track_pan(), _read_pan() | ✅ |
| D1-S2 | Mute readback + verification | `rag/readback.py` — verify_track_mute(), _read_bool_property() | ✅ |
| D1-S2 | Solo readback + verification | `rag/readback.py` — verify_track_solo() | ✅ |
| D1-S2 | Bridge endpoints: pan / mute / solo | `tools/conductor_bridge.py` v1.6 — POST /action/pan, /action/mute, /action/solo | ✅ |
| D1-S2 | Phase D Slice 2 eval suite | `tests/phase_d_slice2_eval.py` — D11–D20 offline tests, 0 failures | ✅ |

### Phase D — Slice 3 (POST /feedback) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D2 | POST /feedback endpoint | `tools/conductor_bridge.py` v1.7 — stores judged outcomes in `memory/feedback_log.jsonl` | ✅ |
| D2 | Feedback types: KEEP / UNDO / TOO_MUCH / NOT_ENOUGH / WRONG_DIRECTION | `rag/bridge_errors.py` — FEEDBACK_INVALID_TYPE, FEEDBACK_NO_REFERENCE, FEEDBACK_PROOF_NOT_FOUND, FEEDBACK_ACTION_NOT_FOUND | ✅ |
| D2 | Feedback log JSONL (append-only, separate from proof log) | `memory/feedback_log.jsonl` | ✅ |
| D2 | Phase D Slice 3 eval suite | `tests/phase_d_slice3_eval.py` — D21–D30, 22/22 Slice 3 core pass | ✅ |

### Phase D — Slice 4 (Compensating Undo + Drift Detection) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S4 | Compensating undo engine | `rag/undo_engine.py` — execute_undo(), UNDOABLE_ACTION_TYPES, UndoValidationError, _parse_target() | ✅ |
| D-S4 | Drift detection before undo | `rag/undo_engine.py` — reads current live state vs original after_state; blocks unless confirm=True | ✅ |
| D-S4 | POST /action/undo bridge endpoint | `tools/conductor_bridge.py` v1.8 — 409 on drift, new ActionProof per undo | ✅ |
| D-S4 | Undo error codes | `rag/bridge_errors.py` — UNDO_PROOF_NOT_FOUND, UNDO_NOT_ELIGIBLE, UNDO_UNSUPPORTED_ACTION, UNDO_NO_BEFORE_STATE | ✅ |
| D-S4 | Phase D Slice 4 eval suite | `tests/phase_d_slice4_eval.py` — D31–D38, 27/27 ALL PASS | ✅ |

### Phase D — Slice 5 (Never-Do Preflight Gate) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S5 | Never-do rules enforcement (preflight gate) | `rag/never_do_check.py` — deterministic static table + context overrides; wired to write endpoints in bridge | ✅ |
| D-S5 | Phase D Slice 5 eval suite | `tests/phase_d_slice5_eval.py` — ALL PASS | ✅ |

### Phase D — Expanded Actions Slice 1 ✅

| # | What | File/Path | Status |
|---|---|---|---|
| EA-S1 | Track management (Create, Delete, Duplicate, Rename) | `tools/conductor_bridge.py` + `rag/readback.py` | ✅ |
| EA-S1 | Track visuals (Color, Group) | `tools/conductor_bridge.py` + `rag/readback.py` | ✅ |
| EA-S1 | Expanded Actions Slice 1 eval suite | `tests/phase_d_slice6_eval.py` — ALL PASS | ✅ |

### Phase D — Expanded Actions Slice 2 ✅

| # | What | File/Path | Status |
|---|---|---|---|
| EA-S2 | Track routing & sends | `tools/conductor_bridge.py` + `rag/readback.py` | ✅ |
| EA-S2 | Track arm & monitor | `tools/conductor_bridge.py` + `rag/readback.py` | ✅ |
| EA-S2 | Transport controls (Play, Stop, Record, Loop, Metronome) | `tools/conductor_bridge.py` + `rag/readback.py` | ✅ |
| EA-S2 | Slice 2 blocker fixes (send index/value validation, route availability precheck) | `tools/conductor_bridge.py` — 3 fixes; `rag/readback.py` — clamp removed | ✅ |
| EA-S2 | Expanded Actions Slice 2 eval suite | `tests/phase_d_slice7_eval.py` — D74–D93, 20/20 PASS | ✅ |

### Phase D — Expanded Actions Slice 3A ✅

| # | What | File/Path | Status |
|---|---|---|---|
| EA-S3A | `POST /action/plugin_bypass` endpoint | `tools/conductor_bridge.py` — device bypass with ActionProof, never-do gate, BRIDGE_PLUGIN_ABSENT before proof | ✅ |
| EA-S3A | `verify_plugin_bypass` (3-call readback loop) | `rag/readback.py` — find+read, write, after_read; `_read_plugin_bypass` for undo drift | ✅ |
| EA-S3A | PLUGIN_BYPASS undo support | `rag/undo_engine.py` — `_parse_plugin_target`, 4-call undo, bool drift detection | ✅ |
| EA-S3A | `"PLUGIN_BYPASS": NeverDoDecision.ALLOW` | `rag/never_do_check.py` — fixes HARD_BLOCK blocker | ✅ |
| EA-S3A | Strict bool parsing for `bypass` field | `tools/conductor_bridge.py` — `"false"`→False, `"true"`→True, invalid→400 | ✅ |
| EA-S3A | Expanded Actions Slice 3A eval suite | `tests/phase_d_slice8_eval.py` — D94–D102, 9/9 PASS | ✅ |

### Phase D — Slice 9 (Strict Confirm Parser) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S9 | `_parse_confirm_strict()` — accepts only JSON `true`, rejects all strings/other | `tools/conductor_bridge.py` | ✅ |
| D-S9 | Wired to `track_delete`, `tracks_create_multiple`, `track_route`, `transport_record` | `tools/conductor_bridge.py` | ✅ |
| D-S9 | Phase D Slice 9 eval suite | `tests/phase_d_slice9_eval.py` — D103–D108, 6/6 PASS | ✅ |

### Phase D — Slice 10 (GET /session/state) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S10 | `GET /session/state` endpoint — live Ableton state snapshot | `tools/conductor_bridge.py` | ✅ |
| D-S10 | `state_completeness` dict — `full` / `best_effort` / `not_available_v1` per field | `tools/conductor_bridge.py` | ✅ |
| D-S10 | Phase D Slice 10 eval suite | `tests/phase_d_slice10_eval.py` — D109–D114, 6/6 PASS | ✅ |

### Phase D — Slice 11 (Natural Replies + Premium UI) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S11 | `composeReply()` — ActionProof → natural assistant dialogue; no raw JSON/enums to user | `app/harness.js` | ✅ |
| D-S11 | Premium UI shell — `app/harness.html` Live Harness v1.5 with debug info, session totals | `app/harness.html` | ✅ |
| D-S11 | Phase D Slice 11 eval suite | `tests/phase_d_slice11_eval.py` — D115–D120, 56/56 PASS | ✅ |

### Phase D — Slice 12 (Knowledge Gateway v1) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S12 | `POST /harness/orchestrate` endpoint — routes WRITE → action-ID, all other modes → knowledge answer | `tools/harness_server.py` | ✅ |
| D-S12 | `call_knowledge_answer()` — context-enriched LLM call (Gemini + OpenAI/compatible); returns `type:"answer"` | `tools/harness_server.py` | ✅ |
| D-S12 | `_call_bridge_get()` — bridge proxy; 3 context layers: context/pack, context/session, session/state | `tools/harness_server.py` | ✅ |
| D-S12 | Phase D Slice 12 eval suite | `tests/phase_d_slice12_eval.py` — D121–D127, 7/7 PASS | ✅ |

### Phase D — Slice 13 (/session/state v1.5) ✅

| # | What | File/Path | Status |
|---|---|---|---|
| D-S13 | `/session/state` v1.5 — per-track: `devices`, `clip_count`, `active_send_count`, `is_group_track`, `in_group` | `tools/conductor_bridge.py` | ✅ |
| D-S13 | Calls 3–6 wrapped in `try/except Exception` — optional fields; failure silently omitted | `tools/conductor_bridge.py` | ✅ |
| D-S13 | `state_completeness` v1.5 keys alongside legacy keys | `tools/conductor_bridge.py` | ✅ |
| D-S13 | Phase D Slice 13 eval suite | `tests/phase_d_slice13_eval.py` — D128–D134, 7/7 PASS | ✅ |

### Phase D — Slice 14 (Knowledge Explorer v1) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice14_eval.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S14 | `_EXPLORER_MODES = {"MENTOR", "FREEFORM_GENERAL"}` — modes that trigger explorer path | `tools/harness_server.py` | ✅ |
| D-S14 | `_STRUCTURAL_RE` — `re.compile(r"(?i)\b(candidates\|direction\|rationale\|session_facts_used\|assumptions\|source_hints\|actionable\|confidence\|question_type)\b")` | `tools/harness_server.py` | ✅ |
| D-S14 | `call_knowledge_explorer()` — single LLM call: JSON with `answer` (user-facing) + `candidates` (internal). Parses structured response; hardens fallback path with regex structural detection | `tools/harness_server.py` | ✅ |
| D-S14 | `_build_explorer_instructions(session_available)` — injects session-availability note into LLM context | `tools/harness_server.py` | ✅ |
| D-S14 | Explorer routing in `_handle_orchestrate`: MENTOR/FREEFORM_GENERAL → explorer; READ/CLARIFY → direct; WRITE → action | `tools/harness_server.py` | ✅ |
| D-S14 | Phase D Slice 14 eval suite | `tests/phase_d_slice14_eval.py` — D135–D142, 8/8 PASS | ✅ |

**What Build 6 hardening fixed (final pass):**
- `_INTERNAL_MARKERS` tuple (5 quoted-only markers) replaced with `_STRUCTURAL_RE` — catches all 9 schema keys in any form: quoted, unquoted, YAML-style, mixed-case, word-boundary
- Added `startswith("```")` markdown-fence detection to `_looks_structural`
- Previously: `candidates: cut EQ\ndirection: ...` (unquoted YAML) and `CANDIDATES:` (mixed-case) bypassed the guard and could leak raw schema text to the user — now caught
- `_check_no_internal_exposure` in test helper updated to mirror production regex; Sub-D/E/F added to D137

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice14_eval.py` | 8/8 PASS |
| `tests/phase_d_slice13_eval.py` | 7/7 PASS |
| `tests/phase_d_slice12_eval.py` | 7/7 PASS |
| `tests/phase_d_slice11_eval.py` | 56/56 PASS |
| `tests/phase_d_slice10_eval.py` | 6/6 PASS |
| `tests/phase_d_slice9_eval.py` | 6/6 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `node --check app/harness.js` | PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

### Phase D — Slice 15 (Creative Critic v1 — Build 7) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice15_eval.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S15 | `call_creative_critic()` — single LLM call evaluating Explorer candidates on 6 criteria (genericity, session_grounding, session_contradiction, goal_fit, practicality, unsupported_assumptions). Returns `({}, tokens)` on parse failure or invalid index. Never raises to caller. | `tools/harness_server.py` | ✅ |
| D-S15 | `_build_critic_prompt()` + `_CRITIC_JSON_SCHEMA` — compact prompt with 6 evaluation criteria; JSON schema specifying `selected`, `kept`, `rejected`, `reasons`, `critic_summary` | `tools/harness_server.py` | ✅ |
| D-S15 | `_compose_final_answer(explorer_answer, explorer_data, critic_data)` — deterministic composer (no LLM). Builds `"{direction}. {rationale}."` from Critic-selected candidate. Falls back to `explorer_answer` on empty critic, invalid index, missing direction, or `_STRUCTURAL_RE` fire. | `tools/harness_server.py` | ✅ |
| D-S15 | `_handle_orchestrate` Explorer branch updated — calls `call_creative_critic` after `call_knowledge_explorer`, then `_compose_final_answer`. Sends `"text": final_text` (Critic-filtered) instead of raw `answer_text`. Critic failure is non-fatal. | `tools/harness_server.py` | ✅ |
| D-S15 | Phase D Slice 15 eval suite | `tests/phase_d_slice15_eval.py` — D143–D153, 11/11 PASS | ✅ |

**Known limitation (do not reopen Build 7):**
`_compose_final_answer()` outputs `"{direction}. {rationale}."` — safe and correct but plain. Future polish: smoother sentence flow, session-fact weaving, co-producer voice. Track as: "Critic composer polish — post Build 7". New slice only.

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `tests/phase_d_slice14_eval.py` | 8/8 PASS |
| `tests/phase_d_slice13_eval.py` | 7/7 PASS |
| `tests/phase_d_slice12_eval.py` | 7/7 PASS |
| `tests/phase_d_slice11_eval.py` | 56/56 PASS |
| `tests/phase_d_slice10_eval.py` | 6/6 PASS |
| `tests/phase_d_slice9_eval.py` | 6/6 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `node --check app/harness.js` | PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

---

### Phase D — Slice 16 (Card-aware Creative Critic v1 — Build 8) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice16_eval.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S16 | `_extract_operator_card_context(message_pack_text)` — extracts `## OPERATOR CARD` block from `/context/pack` text and forwards it to Creative Critic as `card_context` | `tools/harness_server.py` | ✅ |
| D-S16 | `call_creative_critic()` updated — accepts `card_context=""` kwarg; `_build_critic_prompt()` injects Operator Card section when present; `operator_card_compliance` added as 7th evaluation criterion | `tools/harness_server.py` | ✅ |
| D-S16 | Phase D Slice 16 eval suite | `tests/phase_d_slice16_eval.py` — D154–D161, 8/8 PASS | ✅ |

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `tests/phase_d_slice14_eval.py` | 8/8 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `node --check app/harness.js` | PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

---

### Phase D — Slice 17 (Plugin Knowledge Routing v1 — Builds 9 + 10) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice17_eval.py` or `tests/test_seeder_safety.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S17 | Build 9: `seed_operator_cards()` unsafe stale-ID deletion removed. Seeder is upsert-only; never deletes unrelated IDs from `plugin_operator_index`. | `tools/conductor_bridge.py` | ✅ |
| D-S17 | Build 9: Operator Card YAML frontmatter (`card_id`, `display_name`, `type`, `risk_level`, `verification_status`, `collection`, `tags`, `operator_card_triggers`) added to all 4 cards. | `conductor-vault/plugins/*.md` | ✅ |
| D-S17 | Build 10: `_get_stable_card_id(card_file)` — reads frontmatter `card_id`, returns `vault_plugin_{card_id}`. Fails closed. | `rag/context_pack_builder.py` | ✅ |
| D-S17 | Build 10 Guard A: when `_detect_plugin()` fires for plugin X, the ChromaDB full-body card for X is excluded from the Memory section (file-based snippet is authoritative). | `rag/context_pack_builder.py` | ✅ |
| D-S17 | Build 10 Guard B: when no plugin is name-detected, BM25-rescued plugin cards (`rescue_mode="bm25"`) are blocked. Semantic hits still allowed. | `rag/context_pack_builder.py` | ✅ |
| D-S17 | Build 10 guard rebuild fix: `_new_injected` iterates `retrieval.injected` (weight-sorted), not `retrieval.retrieved` (raw order). | `rag/context_pack_builder.py` | ✅ |
| D-S17 | Phase D Slice 17 eval suite | `tests/phase_d_slice17_eval.py` — D162–D168 + D162b, 8/8 PASS | ✅ |
| D-S17 | Seeder safety suite | `tests/test_seeder_safety.py` — B9-S1 + B9-S2, 3/3 PASS | ✅ |

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/test_seeder_safety.py` | 3/3 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile rag/context_pack_builder.py` | PASS |

---

### Phase D — Slice 18 (Plugin Knowledge Trust Signals — Build 11) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice18_eval.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S18 | `get_known_plugin_name_for_message(message)` — scans all 61 inventory entries (has_card or not), returns canonical plugin name or `""`. | `rag/risk_taxonomy.py` | ✅ |
| D-S18 | `_check_plugin_knowledge_status(message, card_file)` — returns `("verified", name)` / `("missing", name)` / `("none", "")`. | `rag/context_pack_builder.py` | ✅ |
| D-S18 | `## KNOWLEDGE STATUS` block injection — present only when a known plugin is recognized but has no Operator Card. Absent when card is present or no plugin recognized. | `rag/context_pack_builder.py` | ✅ |
| D-S18 | Explorer `knowledge_gap` rule — when `## KNOWLEDGE STATUS` present, populate `assumptions` and set `confidence ≤ 0.5` for plugin-specific candidates. | `tools/harness_server.py` | ✅ |
| D-S18 | Critic `knowledge_evidence` criterion — penalize ungrounded plugin-specific claims when no Operator Card is available. | `tools/harness_server.py` | ✅ |
| D-S18 | Phase D Slice 18 eval suite | `tests/phase_d_slice18_eval.py` — D169–D176, 8/8 PASS | ✅ |

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice18_eval.py` | 8/8 PASS |
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `tests/phase_d_slice14_eval.py` | 8/8 PASS |
| `tests/test_seeder_safety.py` | 3/3 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `node --check app/harness.js` | PASS |
| `python3 -m py_compile rag/risk_taxonomy.py rag/context_pack_builder.py tools/harness_server.py` | PASS |

---

### Phase D — Slice 19 (Knowledge Status Context to Critic — Build 12) ✅ LOCKED

> **Do not reopen unless a regression appears in `tests/phase_d_slice19_eval.py`.**

| # | What | File/Path | Status |
|---|---|---|---|
| D-S19 | `_extract_knowledge_status_context(message_pack_text, max_chars=600)` — extracts `## KNOWLEDGE STATUS` block from `/context/pack` text; stops at next `##` section; returns `""` if absent. Mirrors `_extract_operator_card_context()`. | `tools/harness_server.py` | ✅ |
| D-S19 | `_build_critic_prompt()` — `knowledge_status_context=""` param added; injects `## Plugin Knowledge Context` block (internal only) when present, instructing Critic to apply `knowledge_evidence` criterion and penalize unacknowledged plugin-specific claims. | `tools/harness_server.py` | ✅ |
| D-S19 | `call_creative_critic()` — `knowledge_status_context=""` param added; passed through to `_build_critic_prompt()`. | `tools/harness_server.py` | ✅ |
| D-S19 | `_handle_orchestrate()` — extracts `knowledge_status_context` from `message_pack_text` and passes to `call_creative_critic()` alongside `card_context`. Closes the gap where `knowledge_evidence` had no direct context. | `tools/harness_server.py` | ✅ |
| D-S19 | `_TRUST_LABEL_RE` — new module-level regex guarding 6 internal trust labels: `KNOWLEDGE STATUS`, `Plugin Knowledge Context`, `Operator card: not available`, `knowledge_evidence`, `confidence <=`, `confidence ≤`. | `tools/harness_server.py` | ✅ |
| D-S19 | `_compose_final_answer()` — trust-label guard added: if selected-candidate `direction` or `rationale` contains any `_TRUST_LABEL_RE` match, falls back to `explorer_answer` (same pattern as existing `_STRUCTURAL_RE` guard). Blocks Build 11/12 internal labels from leaking into user-facing composed text. | `tools/harness_server.py` | ✅ |
| D-S19 | Phase D Slice 19 eval suite | `tests/phase_d_slice19_eval.py` — D177–D186, 10/10 PASS | ✅ |
| D-S19 | Slice 15/16 mock signatures updated | `tests/phase_d_slice15_eval.py`, `tests/phase_d_slice16_eval.py` — two `fake_critic` side-effects each updated to accept `knowledge_status_context=""` (required by new kwarg, no behavior change) | ✅ |

**Codex audit result:** PASS — Build 12 can be locked.

**Audit evidence (May 2026):**
| Suite | Result |
|---|---|
| `tests/phase_d_slice19_eval.py` | 10/10 PASS |
| `tests/phase_d_slice18_eval.py` | 8/8 PASS |
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

---

### Phase D — Expanded Actions Roadmap (not built — roadmap only)

| Slice | What | Status |
|---|---|---|
| Expanded Slice 3B | `POST /action/plugin_param` — PluginBridge parameter control | ❌ Roadmap |
| Expanded Slice 3C | PluginBridge placement on track (load PluginBridge VST3, select plugin) | ❌ Roadmap |
| Expanded Slice 3D | `POST /action/plugin_load` — load plugin via LOM or PluginBridge | ❌ Roadmap |
| Expanded Slice 4 | Export / Bounce — pending explicit user decision | ❌ Roadmap |
| Expanded Slice 5 | Clip / scene / session-view actions — pending user approval of scope | ❌ Roadmap |

### Phase D — Product Layer (not built — roadmap only)

| # | What | File/Path | Status |
|---|---|---|---|
| D6 | Feedback UI buttons | `app/index.html` — Keep / Undo / Too much / Not enough / Wrong direction wired to `POST /feedback` | ❌ Roadmap |
| D7 | Session-end hook | Triggers `memory_promotion.py` on session close; summarise session, extract decisions | ❌ Roadmap |
| D3 | Memory promotion — "dreaming" | `rag/memory_promotion.py` — runs at session end, silently scores + promotes decisions Level 1→4 | ❌ Roadmap |
| UI | CoProducer Translation layer | **Required before friend-test** — wraps ActionProofs + errors in assistant dialogue; no raw JSON/enums to user | ❌ Roadmap |
| UI | Drift diff dialog | Premium modal on drift-blocked undo | ❌ Roadmap |
| UI | Studio timeline / visual debugger | Visual view of `action_log.jsonl` | ❌ Roadmap |

**UI rule (locked):** `app/index.html` is prototype-only. `CoProducerResponse` translation layer required before friend-test deployment. No raw JSON or error enums in production UI.

### Phase D — Slice 4 Recommendation for Slice 5

1. Batch undo — `proof_ids: [...]`; execute in reverse-chronological order; per-proof results
2. Undo chain — `parent_proof_id` tracking so undo-of-undo is detectable/decidable
3. Action log fallback — look up `before_state` from `action_log.jsonl` when proof exists there but not in proof log
4. Session undo summary — `GET /action/undo/list` returning all undo-eligible proofs
5. Memory promotion from feedback — UNDO feedback type + confirmed undo proof → eligible for Phase C promotion

### Phase C — Cleanup (May 2026) ✅

| What | File | Fix |
|---|---|---|
| `len(None)` crash in retriever | `rag/routed_retriever.py` — both occurrences of `len(doc) // 4` → `len(doc or "") // 4` | ✅ |
| Stale ChromaDB seeds on crash | `tests/phase_c_eval_set.py` — C5 + MT21 seed blocks wrapped in `try/finally` | ✅ |
| Manual stale seed cleanup | 9 stale `c5_f003_*` and `mt21_*` timestamp IDs deleted from ChromaDB | ✅ |
| Phase C eval idempotent | `tests/phase_c_eval_set.py` — confirmed ✅ on 2 consecutive runs | ✅ |

### Feedback outcome format (stored in ChromaDB)

```md
Action: Pro-Q 4 Band 2 — 3.4kHz / -1.5dB / Q2.2
Project: [name] | Stage: [x] | Genre: [x]
User feedback: Too much
Learning: For this producer, vocal presence cuts should start at -1.0dB not -1.5dB
Memory level: Level 3
```

---

## PHASE E — ADVANCED INTELLIGENCE
> Goal: graph relationships, reference tracks, evaluation, observability.
> Do not start until Phase D is complete and stable.

| # | What | Status |
|---|---|---|
| E1 | Graph RAG (LightRAG) | ❌ |
| E2 | Reference Track DNA | ❌ |
| E3 | Audio feature memory | ❌ |
| E4 | Evaluated RAG test suite (Ragas) | ❌ |
| E5 | Langfuse / Phoenix tracing | ❌ |

---

## PHASE F — TEAMS & HOSTED KNOWLEDGE BASE
> Goal: the entire conductor-vault becomes a living, team-maintained knowledge base.
> Not just operator cards — plugin manuals, music theory, genre references, techniques.
> Team members contribute from anywhere. Adi approves. All Conductor instances sync.
> Do not start until Phase E is stable OR until Conductor has public users — whichever comes first.
>
> Shares infrastructure with the Error Collection pipeline (project.md).
> One hosted server handles: knowledge submissions + error collection + vault sync.

| # | What | File/Path | Status |
|---|---|---|---|
| F1 | Hosted server | `server/main.py` (FastAPI — Railway / Supabase / Render) | ❌ |
| F2 | Auth system | JWT or Supabase Auth — roles: viewer / contributor / approver | ❌ |
| F3 | POST /knowledge/submit | Unified endpoint — any knowledge type, any vault folder | ❌ |
| F4 | GET /knowledge/pending | Adi reviews all pending submissions in one place | ❌ |
| F5 | POST /knowledge/approve | Adi approves → worker applies → vault updated | ❌ |
| F6 | Worker Claude Code (server-side) | Headless sub-agent — validates + applies all knowledge types | ❌ |
| F7 | GET /vault/sync | Conductor pulls latest vault on session start | ❌ |
| F8 | Approval notifications | Email / Conductor UI — "3 pending submissions need review" | ❌ |
| F9 | Error collection merged in | Anonymous error patterns feed into same server | ❌ |
| F10 | Team review panel | Web UI — pending / approved / rejected per knowledge area | ❌ |
| F11 | Knowledge area permissions | Who can submit to which folder (contributor map) | ❌ |
| F12 | Version history per file | Git-style — every approved update is a versioned snapshot | ❌ |

---

### Phase F — Knowledge Areas Covered

| Folder | Content type | Team-editable? | Risk | Needs Adi approval? |
|---|---|---|---|---|
| `plugins/` | Operator cards | ✅ Yes | medium–HIGH | Yes for risky-write / never-do |
| `references/techniques/` | EQ approaches, mixing, orchestration | ✅ Yes | low | No — auto-apply after worker review |
| `references/genres/` | Genre targets, arrangement templates | ✅ Yes | low | No — auto-apply after worker review |
| `references/manuals/` | Plugin manual notes | ✅ Yes | low | No — auto-apply after worker review |
| `references/reference_tracks/` | Reference track DNA | ✅ Yes | low | No — auto-apply after worker review |
| `producer/producer_dna.md` | Taste, workflow, permissions | ❌ Adi only | — | N/A — locked |
| `producer/never_do_rules.md` | Hard safety rules | ❌ Adi only | HIGH | N/A — locked |
| `failure-cases/` | Confirmed LOM failures | ✅ Yes | medium | Yes — affects live session safety |

---

### Phase F — Unified Submission Format

One format covers all knowledge types. `target_file` routes it to the right vault folder.

```md
### KNOWLEDGE UPDATE — [short title]
- Submitted by: [name / GitHub handle]
- Date: YYYY-MM-DD
- Target file: conductor-vault/[folder]/[filename].md
- Knowledge type: [ ] operator-card  [ ] technique  [ ] genre  [ ] manual-note  [ ] reference-track  [ ] failure-case
- Risk: [ ] low  [ ] medium  [ ] high
- Confidence: [ ] confirmed  [ ] suspected  [ ] from-source (cite it)

**What to add / change:**
[Exact text, table row, or code block to insert. Worker applies verbatim.]

**Why:**
[One sentence — what this adds or corrects.]

**Source (if from-source):**
[URL, manual page, or reference name.]

**Verification:**
[How worker should check this before applying.]
```

---

### Phase F — Architecture

```
Team member (anywhere)
  → POST /knowledge/submit  (authenticated)
  → Server stores in pending queue by knowledge type + risk level
  ↓
  Low risk (technique / genre / manual) → auto-queued for worker
  Medium / High risk (operator card / failure case) → queued for Adi review
  ↓
Adi notification → reviews medium/high items
  → POST /knowledge/approve or /reject  (with optional note)
  ↓
Worker Claude Code (server-side headless)
  → reads WORKER_INSTRUCTIONS.md (global rules)
  → reads knowledge-type-specific rules
  → applies to correct vault file, bumps version, updates changelog
  ↓
GET /vault/sync → all linked Conductor instances pull updated files
  ↓
ChromaDB on each instance updated (POST /memory → correct collection)
```

---

### Phase F — Minimum to unlock (MVP)

```
F1 + F2 + F3 + F4 + F5  →  usable by a team of 3–5 people
F6 (server-side worker)  →  can stay as local bash trigger in MVP
F7 (vault sync)          →  required for public users
F10 (review panel)       →  nice-to-have, Adi can use API directly at first
```

---

### Phase F — Shares with Error Collection

```
Same server, same deployment:
  POST /knowledge/submit     ← team knowledge contributions
  POST /errors               ← anonymous error patterns from all users
  GET  /vault/sync           ← Conductor instances pull latest vault
  GET  /updates/check        ← check if new files available
```

Both need a hosted server. One deployment, two jobs.

---

### Phase F — What changes in operator cards when live

- Remove manual bash trigger from each card's Worker Config
- Replace with: `submit_endpoint: https://conductor.app/api/knowledge/submit`
- Pending Updates section replaced by server queue (file becomes read-only display)
- Applied Changelog auto-synced — not hand-edited

---

## THINGS TO ADD TO SESSION MANAGEMENT.md
> These came out of the Producer Trust System review and external research.
> Add these in the next SESSION MANAGEMENT.md update pass.

| # | What to add | Source |
|---|---|---|
| S1 | Memory levels 1–4 — how session decisions get stored and promoted | Trust system review + research doc section 17 |
| S2 | Project Taste Memory — separate from global taste. Project may intentionally be different from producer's usual style | Trust system review #12 |
| S3 | Memory consolidation at session end — raw logs → extract decisions → confirm → save durable memory | Research doc section 12 (Memory Consolidation RAG) |
| S4 | Approval/rejection loop tied to session — feedback (Keep/Undo/Too much/Not enough) stored against session context | Trust system review #7 + research doc section 18 |
| S5 | Request mode classifier in session context — MENTOR/INTERN_READ/SAFE_WRITE/RISKY_WRITE/CLARIFY prepended to session state | Research doc section 16 |

---

## THE 7 MEMORY LAYERS — CONDUCTOR SPECIFIC
> Source: AI review of YouTube video, music-production-specific adaptation.
> This is the definitive memory model for Conductor. Build toward this layer by layer.

| Layer | Name | Loaded when | What it contains | Phase |
|---|---|---|---|---|
| A | Boot Context | Always | system_prompt.md — identity, routing, safety, tool rules, how to retrieve more | Done |
| B | Producer DNA | Always | Taste, genres, workflow, permissions. Short. Under 100 lines. | Phase A |
| C | Current Project Context | Ableton open | Project ID, stage, BPM, key, tracks, buses, plugins, current goal, last analysis | Phase B |
| D | Semantic Retrieved Memory | Per prompt (hook) | Top 3 relevant past decisions, preferences, failures for this specific message | Phase B–C |
| E | Plugin Operator Context | When plugin relevant | Operator card for the plugin in use — safe reads, risky writes, quirks, verification | Phase A–B |
| F | Verbatim Audit Recall | ON DEMAND ONLY | Exact timeline of actions — NOT injected normally. Only for: "what happened?", undo, debug, recovery | Phase D |
| G | Knowledge Base / Obsidian RAG | Deep query only | Plugin manuals, genre notes, Ableton API, techniques, reference track DNA | Phase A (files), Phase C (retrieval) |

**Critical rule for Layer F:**
Do NOT inject verbatim audit logs into normal prompts. They create noise.
Only retrieve when user says: "what did we decide?", "why did that change?", "undo what you did", "what worked yesterday?"

**Critical rule for Layer D:**
Semantic search must fire on every prompt via hook — not when Claude decides to search.
"Vocal hurts" must retrieve "harsh upper-mid presence 3.4kHz" even though words don't match.

---

## THE 4 HOOKS — WHEN CONTEXT FIRES
> Every hook fires automatically. Claude never has to remember to retrieve.

| Hook | Fires when | Injects / Does |
|---|---|---|
| **Session start** | Conductor opens with Ableton connected | Memory index + Producer DNA summary + Current project state + Tool/studio health status |
| **Prompt submit** | User sends any message | Semantic search → top 3 relevant matches from producer/project/plugin/failure indexes → compact context pack |
| **Session end** | User closes Conductor or session ends | Summarise session → extract decisions → separate confirmed/rejected/experimental → update project log → trigger memory_promotion.py (dreaming) |
| **Pre-risky action** | Request classified as RISKY_WRITE | Retrieve safety rules + plugin operator card + require confirmation if: master bus, delete, batch edit, export, global tempo/key change |

These 4 hooks ARE Phase B (B6, B7) and Phase D (D7).
Nothing works correctly without them.

---

## CONTEXT PACK PRINCIPLE — SMALLEST CORRECT PACK
> "Smallest correct context pack for this exact request" — not everything, not nothing.

Example — "make the master louder":
```
RETRIEVE:         current stage, master bus safety rules, Ozone 12 operator card,
                  current LUFS/True Peak, producer loudness preferences,
                  reference track target, past rejected mastering moves

DO NOT RETRIEVE:  vocal chain notes, old unrelated sessions,
                  full plugin manuals, all past conversations, all genre docs
```

The context pack builder (Phase B — B1) enforces this.
Semantic router (already built) selects the right indexes.
Risk classifier (Phase B — B3) adds the safety layer.

---

## MEMORY ARCHITECTURE — VIDEO LEVEL MAP
> Source: YouTube video — "6 levels of Claude Code memory systems"
> Maps each level to Conductor's current state and target.

| Level | What | Conductor state | Action |
|---|---|---|---|
| 1 — Native | CLAUDE.md + memory.md | ✅ Done — system_prompt.md + ChromaDB | Keep, improve |
| 2 — Structured + hooks | Index files + session-start hook auto-injects memory | ✅ Done — conductorSessionStart() + Layer B session pack | Phase B ✅ |
| 3 — Semantic injection | user_prompt_submit hook → top 3 matches auto-injected every prompt | ✅ Done — conductorSendToAPI() Layer C with mode header | Phase B ✅ |
| 4 — Verbatim recall + dreaming | Background promotion: session decisions → long-term memory | 🔶 Memory levels designed, promotion not built | Phase D — D3, D7 |
| 5 — LLM Wiki / Knowledge base | Obsidian vault — team writes, Conductor reads | ✅ Vault built + injected. Hybrid search = Phase C | Phase A ✅ / Phase C |
| 6 — Cross-tool universal brain | Postgres/Supabase shared across all AI tools | ❌ Skip for MVP | Phase E or never |

### Three rules from the video to never forget

```
1. Never rely on Claude deciding to search. Use hooks. Inject automatically.
2. Every file is an index or a single topic. Never a dump. 200 line max.
3. Promotion is silent and automatic at session end — not user-triggered.
```

---

## FRAMEWORKS TO USE (do not build from scratch)

| Need | Framework | Priority |
|---|---|---|
| Orchestration | LangGraph | Phase B |
| Obsidian ingestion | LangChain ObsidianLoader or LlamaIndex ObsidianReader | Phase B |
| Vector DB (advanced) | Qdrant (upgrade from ChromaDB for plugin/manual indexes) | Phase C |
| Graph RAG | LightRAG | Phase E |
| Evaluation | Ragas | Phase E |
| Tracing | Langfuse | Phase E |

> ChromaDB stays for producer_memory_index (already working).
> Qdrant added for plugin_operator_index and other read-heavy indexes in Phase C.

---

## WHAT IS CONDUCTOR'S MOAT (never outsource these)

```
Producer DNA schema
Studio/plugin inventory schema
Plugin Operator Cards
DAW action risk classifier
Ableton Context Pack Builder
PluginBridge parameter mapping and verification
Before/after proof system
Memory promotion rules
Project/session separation
Reference Track DNA interpretation
Audio feature memory
Human approval workflow
Session black box logs
```

---

*Delete this file when all phases are ✅ and logged into project.md, LIMITATIONS.md, and SESSION MANAGEMENT.md.*
