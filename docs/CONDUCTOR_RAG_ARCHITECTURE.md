# Conductor — RAG Architecture
> How the AI retrieves the right knowledge at the right time.
> This is the core of what makes Conductor different from a generic chatbot.
> Updated as each phase is built.

---

## The Problem

A generic AI knows everything but remembers nothing.
Conductor needs to be the opposite — lean general knowledge, deep specific memory.

The challenge: you can't inject everything into every prompt. Context windows are finite.
You have to inject the right thing at the right time. That's what this architecture solves.

---

## The Golden Rule

> **Smallest correct context pack for this exact request — not everything, not nothing.**

Example — "make the master louder":
```
RETRIEVE:   current stage, master bus safety rules, Ozone 12 operator card,
            current LUFS/True Peak, loudness preferences, reference target,
            past rejected mastering moves

SKIP:       vocal chain notes, old sessions, full plugin manuals,
            all genre docs, unrelated technique files
```

---

## Architecture Overview

```
User message
    ↓
[Hook: prompt-submit fires automatically]
    ↓
Request Mode Classifier → MENTOR / READ / SAFE_WRITE / RISKY_WRITE / CLARIFY
    (pure keyword/regex, < 1ms, no LLM cost)
    ↓
[If RISKY_WRITE + session pack age > 30s → auto-refresh Layer B first]
    ↓
[If RISKY_WRITE → Pre-risky-action gate: inline confirm UI before proceeding]
    ↓
Layer C builder → per-message pack (fresh every message):
    ├── ## MESSAGE PACK header — Mode / Risk / Confirmation required  ← FIRST
    ├── Top 3 ChromaDB results for this message
    ├── Plugin operator card (if plugin detected in message)
    └── [Failure cases — Phase C]
    ↓
Compose final user content:
    [Layer B session pack]  +  [Layer C message pack]  +  ---  +  User: [message]
    ↓
Anthropic API call:
    system: [Layer A — system_prompt.md — ALWAYS present]
    messages: [...history, { role: user, content: above }]
    ↓
Claude answers with full context
    ↓
Context Pack Debug block appended to response
    (mode · risk · freshness · sources used · tokens · top memories)
```

---

## The 7 Memory Layers

| Layer | Name | Loaded when | Size target |
|---|---|---|---|
| A | Boot Context | Always | < 300 lines (system_prompt.md) |
| B | Producer DNA | Always | < 100 lines |
| C | Current Project Context | Ableton connected | < 50 lines |
| D | Semantic Retrieved Memory | Every prompt (hook) | 3 results max |
| E | Plugin Operator Context | Plugin relevant | 1 card = ~80 lines |
| F | Verbatim Audit Recall | ON DEMAND ONLY | Never auto-injected |
| G | Knowledge Base RAG | Deep query only | 1–3 passages |

**Layer F rule:** Verbatim logs are NOT injected normally. Only when user says "what did we do?", "undo that", "what broke?". Otherwise they create noise.

**Layer D rule:** Hook fires automatically. Claude never has to decide to search memory. Hook fires, top 3 results are injected, done.

---

## The 5 ChromaDB Collections

Each collection is searched independently. Results are tagged by source.
Routing is driven by request mode — never by hardcoded collection names.

| Collection | Memory type | What it stores | Threshold |
|---|---|---|---|
| `producer_memory_index` | Semantic | Producer taste, habits, confirmed preferences | 0.35 |
| `project_session_index` | Episodic | Current-song decisions and session history | 0.40 |
| `plugin_operator_index` | Procedural/archival | Plugin capability, param maps, operator cards, quirks | 0.30 |
| `failure_cases_index` | Procedural/safety | PluginBridge/LOM failures, known bugs, confirmed fixes | 0.30 |
| `audio_analysis_index` | Measurement/evidence | LUFS, stereo width, spectrum snapshots | 0.50 |

### Mode → Collection Routing

| Mode | Collections searched | Design rationale |
|---|---|---|
| `MENTOR` | producer · plugin_operator · failure | Plugin capability + advisory failure queries alongside taste |
| `INTERN_READ` | project · producer · plugin_operator · audio | Full inspection: session history + habits + plugin params + audio evidence |
| `INTERN_WRITE_SAFE` | producer · plugin_operator · failure | Preferences + plugin safety + failure evidence before executing |
| `INTERN_WRITE_RISKY` | failure · plugin_operator · producer · audio | Safety-first order — failure rules retrieved before preferences |
| `CLARIFY` | producer | Minimal — just enough context to resolve ambiguity |
| `FREEFORM_GENERAL` | (none) | Non-music query — skip all retrieval |

**Why MENTOR includes `failure_cases_index`:** advisory "what went wrong" and "what to avoid" questions benefit from failure context. MENTOR is retrieval-only — no execution risk.

**Why `project_session_index` is excluded from RISKY:** session history is noise before a dangerous write. Safety rules and plugin cards must be read first, uncontaminated.

Single source of truth for all routing: `rag/memory_schema.py` → `MODE_COLLECTION_MAP`.

---

## The 4 Hooks

| Hook | Fires when | Does | Status |
|---|---|---|---|
| Session start | Conductor opens | Fetch Layer A (system prompt) + Layer B (DNA + project + tools). Store version + state_hash. | ✅ |
| Prompt submit | User sends message | Classify mode, build Layer C (memory + card + mode header), compose + stream to Anthropic. | ✅ |
| Pre-risky action | `INTERN_WRITE_RISKY` detected | Check session pack age. If > 30s → refresh Layer B. Then show inline confirm gate. | ✅ |
| Session end | Session closes | Summarise → extract decisions → memory promotion ("dreaming"). | ❌ Phase D |

**Critical:** hooks fire automatically. Never rely on Claude deciding to retrieve. Always use hooks.

### Session Pack Staleness Detection

Every `/context/session` response includes:
- `session_pack_version`: ISO-8601 UTC timestamp of when the pack was built
- `state_hash`: 12-char MD5 of `ableton|pluginbridge|memory|project[:300]`

The UI stores `_sessionPackFetchedAt` (JS timestamp) and `_sessionPackStateHash`.
- If pack age > 30s before a RISKY_WRITE → auto-refresh before confirm gate
- State hash changes silently when Ableton disconnects, project opens, or PluginBridge loads — catching drift that the 8s bridge poll might miss between cycles

Debug block freshness display:
- Green: < 30s (safe for any action)
- Amber: 30–120s (warn for risky)
- Red: > 120s (stale — refreshed automatically before RISKY)

---

## Memory Levels

```
Level 1 — Raw event         (session only — one-time observation)
Level 2 — Session decision  (project-specific — used more than once this session)
Level 3 — Confirmed preference (cross-project — user approved this explicitly)
Level 4 — Producer rule / Never-Do (always retrieved — strongest signal)
```

**Promotion ("dreaming"):**
Session-end hook scores all Level 1 memories by: recency × repetition.
High score: promoted to Level 2 or 3.
Low score: forgotten.
Level 4 requires explicit user approval: "always do this" / "never do this again."

---

## RAG Types Used (by Phase)

| Type | What | Status |
|---|---|---|
| Semantic RAG | ChromaDB cosine similarity search | ✅ Phase B |
| Hybrid RAG | Semantic + BM25 exact-term rescue (`_bm25_rescue`) | ✅ Phase C |
| Temporal RAG | Time-weighted scoring — semantic×0.60 + recency×0.30 + freq×0.10 | ✅ Phase C |
| Corrective RAG | Two-layer contradiction protection — write-time + read-time Jaccard | ✅ Phase C |
| Operator/Tool RAG | Plugin operator card retrieval by alias detection | ✅ Phase A (files) / Phase B (injection) |
| Plugin-Aware RAG | Detect plugin name in message → load card | ✅ Phase B |
| Audio/Multimodal RAG | LUFS/spectrum snapshots → retrieved in INTERN_READ mode | ✅ Phase C (storage + retrieval routing) |
| Graph RAG (LightRAG) | Relationship mapping between concepts | ❌ Phase E |
| Reference Track RAG | Reference Track DNA comparison | ❌ Phase E |

---

## The Context Pack Format

Three layers. Each has a different lifetime and injection point.

**Layer A — system param (always, every call)**
```
You are Conductor, Adi's personal AI music production assistant…
```

**Layer B — session pack (once + refresh on state change)**
```md
## PRODUCER DNA
Producer: Adi | Level: Stage 3 | Primary genre: Bollywood/Punjabi
Sound: cinematic · punchy · emotional | Anchor plugins: Pro-Q 4 · Ozone 12

## CURRENT PROJECT STATE
Project: Song Name | Stage: Mixing | BPM: 94 | Key: D minor

## TOOL STATUS
Ableton: connected | Audio Analyzer: available | Memory (ChromaDB): ready
PluginBridge: detected on Vocal Bus
```

**Layer C — message pack (fresh every message, mode header FIRST)**
```md
## MESSAGE PACK
Mode: INTERN_WRITE_RISKY
Risk: HIGH
Confirmation required: YES
Reason: Ozone 12 on master bus — HIGH risk plugin

Relevant retrieved context:

### Memory
1. Used -14 LUFS integrated on last project, Adi approved
2. True Peak ceiling always -1dBTP on Spotify masters
3. Never chain Ozone Dynamics after Maximizer — clips internally

## OPERATOR CARD — Ozone 12
[Identity + Risky Writes + Never Do sections only — ~80 lines]
```

**Design principle:** mode/risk header leads Layer C so Claude sees the risk classification _before_ reading any retrieved context. Prevents memories from anchoring the model before it processes intent.

---

## Build Status

| Component | Status | Notes |
|---|---|---|
| **Phase A — Foundation** | | |
| Layer A — Boot Context (`system_prompt.md`) | ✅ | Always in `system:` param |
| Layer E — Plugin Operator Cards | ✅ | 4 cards: Pro-Q 4, Ozone 12, Serum 2, Ableton stock |
| Vault folder structure | ✅ | `conductor-vault/` — plugins, producer, failure-cases, studio |
| Plugin scanner + known_plugins.json | ✅ | 54 entries with camelCase aliases |
| **Phase B — Context Pack** | | |
| Layer B — Producer DNA | ✅ | `conductor-vault/producer/producer_dna.md` |
| Layer B — Project Context | ✅ | `CURRENT PROJECT STATE.md` parsed by session pack builder |
| Layer B — Tool Health | ✅ | Bridge status dict → formatted block |
| Layer B — Versioning | ✅ | `session_pack_version` (ISO) + `state_hash` (12-char MD5) |
| Request Mode Classifier (5 modes) | ✅ | MENTOR / INTERN_READ / WRITE_SAFE / WRITE_RISKY / CLARIFY |
| Protection Model (6 levels) | ✅ | STATUS_ONLY → AUTO_EXECUTE → UNDO_LOG → CONFIRM → CLARIFY → BLOCK |
| Risk Taxonomy | ✅ | `rag/risk_taxonomy.py` — ACTION_CATEGORIES, plugin aliases, card lookup |
| Memory Write Contract | ✅ | `POST /memory` enforces mode + collection + metadata; FREEFORM blocked |
| Plugin card injection | ✅ | Mode header leads Layer C — Claude sees risk before context |
| Pre-risky-action hook + stale refresh | ✅ | Confirm gate + auto-refresh if pack age > 30s |
| Context Pack Debug view | ✅ | Collapsible per response — mode, freshness, sources, tokens |
| Dev mode | ✅ | DEV toolbar — auto-open debug blocks + raw session pack |
| **Phase C — Retrieval Quality** | | |
| 5 ChromaDB collections (split + routed) | ✅ | `rag/memory_schema.py` — schema, thresholds, validation, mode map |
| Routed retriever (replaces legacy `_query_memory`) | ✅ | `rag/routed_retriever.py` — mode → collection routing |
| Memory type taxonomy (LangMem/Letta aligned) | ✅ | semantic · episodic · procedural · measurement — each to correct collection |
| Temporal scoring (C2) | ✅ | `rag/memory_scoring.py` — recency decay, half-life 7d, Level 4 bypass |
| Corrective RAG write-time (C3) | ✅ | `find_superseded_by_new()` — Jaccard 0.70, marks old memory in ChromaDB |
| Corrective RAG read-time (C3) | ✅ | `apply_corrective_check()` — Jaccard 0.40 in-flight, newer wins |
| Evidence labels (C4) | ✅ | 14-field `debug.evidence` per item in `/context/pack` response |
| Hybrid BM25 search (C5) | ✅ | `_bm25_rescue()` — exact plugin/bus/code names not blurred by embeddings |
| Vault seeder | ✅ | `tools/seeder.py` — failure-cases vault → ChromaDB, idempotent |
| 21-section eval suite | ✅ | `tests/phase_c_eval_set.py` — 0 failures |
| **Phase D — Trust Layer** | | |
| Before/after proof system | ❌ | Phase D |
| Memory promotion ("dreaming") | ❌ | Phase D — `rag/memory_promotion.py` |
| Session-end hook | ❌ | Phase D |
| Feedback UI (Keep / Undo / Too much) | ❌ | Phase D |
| **Phase E — Advanced** | | |
| Graph RAG (LightRAG) | ❌ | Phase E |
| Reference Track DNA | ❌ | Phase E |
| Ragas evaluation suite | ❌ | Phase E |

---

## What's NOT Built Yet (as of Phase C)

Phases A, B, C are complete. All 21 retrieval eval sections pass.

**Remaining gaps:**
- Memory promotion / dreaming at session end (Phase D)
- Before/after proof and feedback loop (Phase D — `POST /feedback`)
- Session-end hook (Phase D — triggers memory_promotion.py)
- Graph RAG for concept relationship mapping (Phase E)
- Reference Track DNA retrieval (Phase E)

---

_Last updated: May 2026 — Phase C complete (C1–C6, 21-section eval suite)_
_Phase A–B complete. Phase D next. See BUILD_PHASES.md for detail._
