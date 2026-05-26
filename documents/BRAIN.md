# Conductor — Brain Map
> Last updated: May 2026 — Phases A, B, C complete.

---

## Knowledge Flow (as built)

```
User Message
     ↓
Request Mode Classifier   (pure regex, < 1ms, no LLM cost)
     ↓ MENTOR / INTERN_READ / INTERN_WRITE_SAFE / INTERN_WRITE_RISKY / CLARIFY / FREEFORM
     ↓
Protection Model          (6-level: STATUS_ONLY → BLOCK_UNSUPPORTED)
     ↓ auto_execute_allowed · confirmation_required · risk_category
     ↓
Routed Retriever          (mode → collection map, per message)
     ├── MENTOR          → producer_memory + plugin_operator + failure (advisory)
     ├── INTERN_READ     → project_session + producer + plugin_operator + audio
     ├── WRITE_SAFE      → producer + plugin_operator + failure
     ├── WRITE_RISKY     → failure → plugin_operator → producer → audio (safety order)
     ├── CLARIFY         → producer only
     └── FREEFORM        → (no retrieval)
     ↓
Semantic search (ChromaDB cosine)
     +
BM25 rescue               (exact plugin names / bus names / failure codes — C5)
     ↓
Similarity threshold filter (per collection: 0.30–0.50)
     ↓
Corrective RAG check      (in-flight Jaccard 0.40 — suppress older contradictions — C3)
     ↓
Temporal scoring          (semantic×0.60 + recency×0.30 + freq×0.10 — C2)
     ↓
Global sort across all collections
     ↓
Context Pack Builder      (Layer A + Layer B + Layer C → Anthropic API)
     ↓
Claude answers with full context
     ↓
debug.evidence block      (14-field per item: id · similarity · confidence · age_days
                           final_score · label · injected · superseded · rejected …)
```

---

## What Each Layer Does

| Layer | Role | Status |
|---|---|---|
| A — Boot Context | `system_prompt.md` — identity, safety, routing rules, memory write contract | ✅ |
| B — Producer DNA | Taste, genres, workflow, permissions. Under 100 lines. Refreshed on state change. | ✅ |
| C — Current Project | Project name, stage, BPM, key — from `CURRENT PROJECT STATE.md` | ✅ |
| D — Semantic Memory | Top retrieved evidence per message — routed by mode, scored by C2–C5 | ✅ |
| E — Plugin Operator | Operator card for detected plugin — safe reads, risky writes, quirks | ✅ |
| F — Verbatim Audit | Exact action timeline — NOT injected normally. ON DEMAND ONLY. | ❌ Phase D |
| G — Knowledge Base | Vault files, failure cases — hybrid semantic + BM25 retrieval | ✅ |

---

## The 5 ChromaDB Collections (Phase C)

| Collection | Memory Type | What it stores |
|---|---|---|
| `producer_memory_index` | Semantic | Producer taste, habits, confirmed preferences |
| `project_session_index` | Episodic | Current-song decisions and history |
| `plugin_operator_index` | Procedural/archival | Plugin capability, param maps, quirks, operator cards |
| `failure_cases_index` | Procedural/safety | PluginBridge/LOM failures, known bugs, confirmed fixes |
| `audio_analysis_index` | Measurement/evidence | LUFS, spectrum, stereo width snapshots |

Single source of truth: `rag/memory_schema.py`

---

## Mode → Collection Routing (Phase C)

| Mode | Collections searched | Rationale |
|---|---|---|
| MENTOR | producer · plugin_operator · failure | Taste + plugin capability + advisory failure context |
| INTERN_READ | project · producer · plugin_operator · audio | Full inspection — history + habits + params + evidence |
| INTERN_WRITE_SAFE | producer · plugin_operator · failure | Preferences + plugin safety before executing |
| INTERN_WRITE_RISKY | failure → plugin_operator → producer → audio | Safety-first enforced order |
| CLARIFY | producer | Minimal — just enough to resolve ambiguity |
| FREEFORM_GENERAL | (none) | Non-music query — skip all retrieval |

---

## Protection Model (Phase B — 6 levels)

```
STATUS_ONLY           → advice / read — no write action
AUTO_EXECUTE_ALLOWED  → safe reversible write — execute directly
UNDO_LOG_REQUIRED     → medium reversible (patch replace, randomise patch)
CONFIRM_REQUIRED      → dangerous: delete / master / export / batch / global tempo
CLARIFY_REQUIRED      → pronoun without referent ("lower it" — lower what?)
BLOCK_UNSUPPORTED     → GUI/mouse instruction — can't execute, explain why
```

---

## Corrective RAG (Phase C — C3)

Two layers protecting against stale or contradictory memories:

**Write-time (Layer 1):** When `POST /memory` adds a new item, `find_superseded_by_new()`
scans the same collection for similar old memories (Jaccard ≥ 0.70) and marks them
`superseded_by=new_id` in ChromaDB metadata. Bridge response returns `superseded: [ids]`.

**Read-time (Layer 2):** During retrieval, `apply_corrective_check()` groups items by
collection and compares pairs (Jaccard ≥ 0.40). Newer item wins (lower `age_days`);
on tie, higher `final_score` wins. Loser is suppressed in-flight with `reason="C3 contradiction"`.
Cross-collection: no suppression — failure memory never blocks producer memory.

---

## Temporal Scoring (Phase C — C2)

```python
final_score = semantic × 0.60 + recency × 0.30 + frequency × 0.10
recency     = 2^(-age_days / 7)   # half-life 7 days
frequency   = stub 0.5            # until access tracking is wired (Phase D)
```

Level 4 memories bypass scoring entirely → always score 9999 → always float to top.
Missing `created_at` → recency = 0.5 (neutral, no penalty, no crash).

---

## Stage Problem + Solution

Stage label alone → weak, goes stale.
Session state (Ableton tracks, plugins, routing) → strong live signal.
User message intent → direction.
ChromaDB profile (built over time) → who this producer actually is.

**Stage is inferred from all four combined — never asked directly.**

---

## Research Protocol (inside Claude)

```
IDENTIFY  → what exactly is being asked
DELEGATE  → which source has the best answer (mode classifier already picked)
EXTRACT   → pull exact values from retrieved evidence (Hz, dB, BPM, ms)
EXECUTE   → act with those values
VERIFY    → confirm result matched the target
```

---

## What Still Needs Building

| What | Phase |
|---|---|
| Memory promotion — "dreaming" (session-end scoring → Level 1 → 2 → 3 → 4) | D |
| Before/after proof system + `POST /feedback` endpoint | D |
| Session-end hook (summarise → extract → promote → update project log) | D |
| Feedback UI (Keep / Undo / Too much / Not enough / Wrong direction) | D |
| Graph RAG — concept relationship mapping (LightRAG) | E |
| Reference Track DNA comparison | E |
| Evaluated RAG test suite (Ragas) | E |
| Langfuse / Phoenix tracing | E |
