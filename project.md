# Conductor — Project Audit Document
> Open book. No hidden things.
> Any fresh AI, collaborator, or auditor reads this and can immediately find flaws,
> understand how every piece connects, and suggest improvements.
>
> Updated every audit session. Date-stamped at the bottom.

---

## WHAT IS CONDUCTOR

A personal AI music production assistant that lives inside the producer's workflow.

**It is NOT:**
- A music generator (not Suno, not a prompt-to-audio tool)
- A generic chatbot with music knowledge
- A plugin that replaces creative decisions

**It IS:**
- A real-time control layer over Ableton Live
- A knowledge brain that queries the right source for the right question
- A memory system that builds a profile of this specific producer over time
- A bridge between the producer's intent and the DAW's execution

**The core USP:**
> It grows with the user. Session 1 it is generic. Session 20 it knows their patterns, their taste, their past decisions. No other tool does this for music production.

**Where the USP can fail:**
- If ChromaDB memory degrades after 150+ sessions (see LIMITATIONS.md)
- If the user never corrects bad AI decisions — wrong patterns get reinforced
- If context injection is not built — memory exists but never reaches the AI

---

## FULL ARCHITECTURE MAP

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER                                      │
│              types in Conductor chat UI                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ message
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONDUCTOR UI                                  │
│           app/index.html  (Phase 2 HTML — notch/chat)           │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │ Chat window │  │ Session tab  │  │ Settings / Tutorials   │  │
│  │ Auto toggle │  │ Stage toggle │  │ API keys, NLM connect  │  │
│  └─────────────┘  └──────────────┘  └────────────────────────┘  │
│                                                                  │
│  On send: message + stage + project context → Anthropic API     │
│  System prompt: app/system_prompt.md (injected every call)      │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP POST to Anthropic
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                 ANTHROPIC API (Claude)                          │
│                                                                  │
│  Receives: system_prompt.md + user message + context layers     │
│  Decides: which tool to call, what to answer directly           │
│  Returns: answer + optional tool calls                          │
└───────────────────────────┬─────────────────────────────────────┘
                            │ tool calls
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│              CONDUCTOR BRIDGE  (localhost:4601)                 │
│                   tools/conductor_bridge.py                     │
│                                                                  │
│  Single entry point for all tools. HTTP server.                 │
│                                                                  │
│  GET  /ping              → health check                         │
│  GET  /status            → all services status                  │
│  GET  /route             → semantic router (no LLM cost)        │
│  POST /ableton           → execute Python in Ableton LOM        │
│  GET  /notebooklm        → query NotebookLM CLI                 │
│  GET  /analyze           → run audio-analyzer on a file         │
│  GET  /memory            → semantic search ChromaDB             │
│  POST /memory            → save to ChromaDB                     │
│  GET  /context/ableton   → load ableton.md reference           │
│  POST /context/ableton   → write confirmed fix pattern          │
│  POST /errors            → log failure silently                 │
│  GET  /config            → read bridge config                   │
│  POST /config            → update bridge config                 │
└────┬──────────┬───────────────┬──────────────┬──────────────────┘
     │          │               │              │
     ▼          ▼               ▼              ▼
┌─────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────────────┐
│ Ableton │ │NLM CLI   │ │ Audio    │ │ ChromaDB                 │
│ TCP     │ │notebooklm│ │ Analyzer │ │ local, no API key        │
│ 16619   │ │ ask "..."│ │ Rust MCP │ │ memory/chromadb/         │
│         │ │          │ │          │ │ semantic search          │
│ Python  │ │ User's   │ │ Key, BPM │ │ cross-session memory     │
│ in LOM  │ │ personal │ │ LUFS     │ │ builds user profile      │
│         │ │ notebook │ │ stereo   │ │ over time                │
└─────────┘ └──────────┘ └──────────┘ └──────────────────────────┘
     │
     ▼
┌─────────────────────────────────────────────────────────────────┐
│                    ABLETON LIVE                                 │
│  Control Surface 1: Ableton_Live_MCP (primary)                  │
│  Control Surface 2: AbletonOSC (fallback)                       │
│  AgentAudioTap.amxd — captures audio to WAV                     │
│  PluginBridge.vst3 — full VST3/AU parameter control             │
└─────────────────────────────────────────────────────────────────┘
```

---

## HOW EACH PIECE TALKS TO EACH OTHER

| From | To | Protocol | What breaks if this fails |
|---|---|---|---|
| UI → Anthropic API | HTTPS | User gets no response |
| UI → Bridge | HTTP localhost:4601 | No tools work. AI answers from training only. |
| Bridge → Ableton | TCP 16619 | No DAW control. Session data unavailable. |
| Bridge → NotebookLM | CLI subprocess | No knowledge base queries. AI guesses. |
| Bridge → Audio Analyzer | MCP / CLI | No file analysis. Blind mixing. |
| Bridge → ChromaDB | Python import | No memory. Starts fresh every session. |
| Ableton → AgentAudioTap | File polling /tmp/ | No audio capture. No spectral analysis. |
| Ableton → PluginBridge | In-process / Helper | No third-party plugin control. |
| system_prompt.md → API | Injected on every call | AI has no behavior rules. Becomes generic. |

---

## COMPONENT BREAKDOWN

### 1. Conductor UI (`app/index.html`)
**What it does:** The chat interface. Notch UI. Stage toggle. Settings. Tutorials panel.
**Status:** Phase 2 HTML working. Tour sequence not built. Tutorials panel not built. API key fields not built.
**Connects to:** Anthropic API (direct), Bridge (for tool results)
**Weak points:**
- Context injection not wired — memory and session state not prepended to messages yet
- No error state UI — if bridge is down, user sees nothing
- No session history persistence built

---

### 2. system_prompt.md (`app/system_prompt.md`)
**What it does:** Injected into every Anthropic API call. Defines Claude's behavior, routing rules, stage system, memory behavior, execution discipline.
**Status:** Built. Reviewed. 5 revisions applied. Source file map added.
**Connects to:** Anthropic API (injected on every call)
**Weak points:**
- Only as good as the context it receives — if context injection is not built, this file operates blind
- Stage 0 exception added but stage inference from Ableton not yet wired
- RESEARCH FIRST protocol defined but DELEGATE routing depends on tools being connected

---

### 3. Conductor Bridge (`tools/conductor_bridge.py`)
**What it does:** HTTP server on port 4601. Single gateway to all tools. Handles Ableton, NotebookLM, Audio Analyzer, ChromaDB.
**Status:** Built. v1.1. ChromaDB wired. All endpoints working.
**Connects to:** Ableton (TCP 16619), NotebookLM CLI, Audio Analyzer CLI, ChromaDB
**Weak points:**
- No authentication — any process on localhost can call it
- No request queue — simultaneous calls can conflict
- NotebookLM path hardcoded to candidates list — breaks if installed elsewhere
- Bridge must be manually started — not auto-launched by the app yet

---

### 4. ChromaDB Memory (`memory/chromadb/`)
**What it does:** Local vector database. Stores production decisions with semantic embeddings. Searched at session start. Written after decisions that work.
**Status:** Built. Wired into bridge. Tested — semantic search working.
**Connects to:** Bridge (GET/POST /memory), UI (via bridge)
**Weak points:** See LIMITATIONS.md — no time decay, no contradiction resolution, degrades after 150+ sessions.
**Critical gap:** Memory exists but is not automatically injected into API calls. AI has to be told to search it. Context injection not built.

---

### 5. NotebookLM (`/notebooklm CLI`)
**What it does:** User's personal knowledge base. Deep technique queries — instruments, EQ, genre, orchestration. Queried via CLI subprocess.
**Status:** Working for dev (Adi's notebook). For public users — they connect their own notebook via Tutorials panel.
**Connects to:** Bridge (GET /notebooklm)
**Weak points:**
- CLI subprocess is slow (5–15 seconds per query)
- Response comes as raw text — no structure enforcement
- User must complete NotebookLM login + connect notebook manually
- If user skips Tutorials panel, this never gets connected

---

### 6. Audio Analyzer (`tools/audio-analyzer`)
**What it does:** Rust binary. Key, BPM, LUFS, stereo width, section boundaries. Runs in ~1.4s on a 48s file.
**Status:** Built. Wired into bridge. Working.
**Connects to:** Bridge (GET /analyze)
**Weak points:**
- File path must be absolute — no relative path support
- File must already exist on disk — no live capture without AgentAudioTap first
- Bridge exposes it but UI has no file picker to send a path

---

### 7. Ableton MCP (`TCP 16619`)
**What it does:** Python execution inside Ableton's Live Object Model. Track control, device loading, routing, BPM, MIDI.
**Status:** Working (bschoepke, patched). 10s timeout per call.
**Connects to:** Bridge (POST /ableton), Ableton Live
**Weak points:**
- Ableton must be open and MCP loaded — no graceful fallback
- 10s timeout kills multi-step operations
- GROUP TRACKS cannot be created via LOM
- VST3 plugins: 1 parameter only without PluginBridge

---

### 8. PluginBridge (`PluginBridge.vst3`)
**What it does:** VST3 plugin that hosts any other VST3/AU. Exposes all parameters via MCP on port 16620. Real-time per-track analysis.
**Status:** v0.6.0. Sprint 7 in progress.
**Connects to:** Ableton (in-process), Bridge (via separate MCP)
**Weak points:**
- Must be loaded manually per session onto each track
- Unsafe plugins (iZotope) get audio-only mode — GUI not available
- Port 16620 is first instance — multi-instance gets auto-port (not documented in UI)

---

### 9. ableton.md (`app/ableton.md`)
**What it does:** Primary Ableton reference. Loaded when a task fails or user is unsatisfied. Contains LOM hard limits, confirmed code patterns, bus routing, execute rules, AgentAudioTap, PluginBridge, Basic Pitch, known failure patterns.
**Status:** ✅ Built. Not yet wired to auto-load on failure.
**Connects to:** system_prompt.md (referenced as fallback), errors.md (source of new patterns)
**Weak points:**
- Auto-load on failure not wired — AI must be told to reference it
- Needs bridge endpoint to serve it on demand

---

### 10. errors.md (`errors.md`)
**What it does:** Project-wide error log. AI writes silently on every failure, hallucination, or user correction. Reviewed weekly. Patterns → fixes → reference file updates → pushed to users.
**Status:** ✅ Built. AI silent writing not yet wired.
**Connects to:** ableton.md (patterns flow here after fix), DATA COLLECTION.md (error patterns collected anonymously)
**Weak points:**
- Silent writing not wired — AI cannot currently write to files during a session
- Collection pipeline (server aggregation) not built
- Weekly review process is manual until server exists

---

### 11. Semantic Router (`tools/conductor_router.py`)
**What it does:** Embedding-based query routing. Reads the user's message and returns which knowledge source to hit — without any LLM call. Powers the Auto mode indicator in the UI.
**Repo:** https://github.com/aurelio-labs/semantic-router
**Status:** ✅ Built. 5 routes defined. 7/8 test cases correct. Exposed via `GET /route` on bridge.
**Connects to:** Bridge (`GET /route`), conductor_bridge.py (imported on startup)
**Routes:** notebooklm (technique/EQ/genre) · ableton (live session) · memory (past decisions) · analyzer (audio files) · direct (simple questions)
**Weak points:**
- Memory edge case: "remind me what I did for X" routes to notebooklm instead of memory — needs more utterances
- UI is not yet consuming `/route` — Auto mode indicator not wired
- Encoder needs sentence-transformers in the ableton-live-mcp venv (already installed for dev)

---

### 12. Conductor Vault (`conductor-vault/`)
**What it does:** Plain markdown folder. The AI's long-term knowledge store. Producer DNA, plugin operator cards, never-do rules, failure cases, reference files. No Obsidian required — just markdown files. Loaded and injected by the context pack builder (Phase B ✅).
**Status:** ✅ Phase A + B complete. Files seeded and live — injected into every API call.
**Contents:**
- `producer/producer_dna.md` — taste, genres, workflow, permissions (Layer B — always loaded)
- `producer/never_do_rules.md` — hard safety rules (read before every RISKY_WRITE)
- `plugins/Pro-Q 4 Operator Card.md` — full PluginBridge param guide (Layer C — on mention)
- `plugins/Ozone 12 Operator Card.md` — high-risk mastering plugin rules (Layer C — on mention)
- `plugins/Serum 2 Operator Card.md` — wavetable synth param guide (Layer C — on mention)
- `plugins/Ableton Stock Devices.md` — EQ Eight, Compressor, Glue, Limiter (Layer C — on mention)
- `studio/studio_inventory.md` — auto-generated by plugin scanner
- `failure-cases/` — Ableton LOM failures, routing failures, plugin quirks (Phase C: auto-retrieved before RISKY writes)
- `indexes/` — master index files (< 200 lines each)
**Connects to:** Context Pack Builder ✅, plugin scanner (A1 ✅)
**Weak points:**
- Failure case retrieval not yet wired — files exist, not queried before RISKY writes (Phase C)
- Vault is seeded with templates and defaults — personalisation requires onboarding
- Producer DNA is a blank template until user fills it in (onboarding flow)

---

### 13. Cinematic Intro + Tour (`Phase 1 HTML`)
**What it does:** First launch experience. Cinematic plays. Notch appears. Tour highlights each feature. Ends with pre-recorded AI chat demo.
**Status:** Cinematic 80% done. Tour sequence not built. Pre-recorded chat not built.
**Connects to:** Nothing — pure HTML/CSS/JS
**Weak points:**
- Tour and pre-recorded demo are planned but not built
- No bridge between cinematic end and app ready state

---

## THE BRAIN — HOW IT LAYERS

```
Every user message passes through 4 context layers before Claude answers:

Layer 1 — system_prompt.md       STATIC   Same for all users. Behavior rules.
Layer 2 — CURRENT PROJECT STATE  DYNAMIC  This song. Stage, BPM, key, notes.
Layer 3 — ChromaDB memory        DYNAMIC  This user. Past decisions, patterns.
Layer 4 — Live Ableton state     DYNAMIC  Right now. Tracks, routing, devices.

Currently built: Layer 1 ✅ | Layer 2 ✅ (injected as Layer B session pack) | Layer 3 ✅ (top 3 injected as Layer C per message) | Layer 4 ✅ (Ableton state in Layer B tool status block)
Currently wired into API calls: All 4 layers — via three-layer context pack architecture (Phase B ✅)
```

**Phase B resolved this gap.** All four layers now reach the AI on every call. Next gap: retrieval quality (Phase C — single ChromaDB collection, no temporal scoring, failure cases not yet auto-retrieved).

### Target context injection format (compact, not huge)

Every user message should prepend this block before sending to the API:

```
## CURRENT PROJECT STATE
Project: [name]
Stage: [0–4]
BPM: [value]
Key: [value]
Tracks: [comma-separated names]
Current Issue: [if any]

## RELEVANT MEMORY
- [top 3 ChromaDB results for this message]

## LIVE ABLETON STATE
Ableton: connected / disconnected
Bridge: healthy / down
Audio Analyzer: available / missing
NotebookLM: connected / not connected
```

Without this block, system_prompt.md operates blind.

---

## SELF-IMPROVING LOOP — ON THE SPOT

The full loop as built. Triggers immediately when a fix is confirmed — no end-of-session dependency.

```
Ableton task fails
        ↓
AI calls GET /context/ableton
        ↓
Reads Known Failure Patterns table
        ↓
Matching pattern found → apply confirmed fix → retry
No pattern found → retry with smaller request
        ↓
User says "yes" / "that worked" / "perfect"
        ↓
AI calls POST /context/ableton    → writes new pattern to ableton.md
AI calls POST /errors             → logs failure + fix with timestamp
        ↓
Next session — pattern already in ableton.md
Never fails same task again
```

**Bridge responses are now standardised:**
```json
{ "ok": true, "source": "ableton", "data": {}, "verified": false, "error": null }
```
`verified` is always `false` by default. AI must read back the value to confirm before claiming success.

---

## ERROR COLLECTION — INTERIM PROCESS

Until the update server is built, everything stays local. No automatic collection.

```
Error happens → logged to local errors.md (on user's machine)
                        ↓
              stays there — no server, no collection
                        ↓
INTERIM WEEKLY REVIEW (manual):
Adi opens his own errors.md
Reviews with Claude/AI
Identifies patterns
Updates ableton.md manually
Pushes update to users
```

**Limitations of interim process:**
- Adi can only see his own errors, not users' errors
- No pattern detection across multiple users
- Fix discovery is manual and slower
- Scales only to a handful of users

**When update server is built:**
- errors.md patterns collected anonymously (opt-in)
- Aggregate patterns visible across all users
- Weekly review becomes data-driven
- Fixes pushed automatically after testing

---

## BUILD STATUS

| Component | Status | Gap |
|---|---|---|
| Conductor Bridge | ✅ Built | Not auto-launched |
| ChromaDB memory | ✅ Built + wired | Not injected into API calls |
| system_prompt.md | ✅ Built + reviewed | Operates blind without context injection |
| Audio Analyzer | ✅ Built + wired | No file picker in UI |
| Ableton MCP | ✅ Working | Must be manually started |
| install.command | ✅ Done | Bash only, not bundled in .app |
| Cinematic intro | 🔶 80% done | Tour + pre-recorded demo not built |
| Notch + chat UI | ✅ Working | Context injection not wired |
| Tutorials panel | ❌ Not built | — |
| API key fields in Settings | ❌ Not built | — |
| Tour sequence | ❌ Not built | — |
| Pre-recorded AI chat demo | ❌ Not built | — |
| ableton.md | ✅ Built | Not wired to auto-load on failure |
| errors.md | ✅ Built | AI silent writing not wired |
| RELIABILITY.md | ✅ Built | Not yet referenced in system_prompt.md |
| Context injection | ❌ Not built | Biggest gap |
| Auto-load ableton.md on failure | ❌ Not built | Needs bridge endpoint |
| AI silent write to errors.md | ❌ Not built | Needs file write capability |
| Error collection pipeline | ❌ Not built | Needs update server |
| Weekly error review → fix → push | ❌ Not built | Needs update server |
| Bundled .app installer | ❌ Not built | Needs Tauri or Electron |
| Update server | ❌ Not built | Needs backend + hosting |
| Semantic Router | ✅ Built + wired | UI not yet consuming /route endpoint |
| conductor_router.py | ✅ Built | 7/8 test cases correct, memory edge case needs fix |
| Stage inference from Ableton | ❌ Not built | — |
| Session history per project | ❌ Not built | — |
| Plugin Scanner | ✅ Built | `tools/plugin_scanner.py` — 665 plugins, 100% classified, Info.plist metadata |
| Known plugins DB | ✅ Built | `data/known_plugins.json` — 54 entries, aliases, tier 1 matching |
| Conductor Vault | ✅ Phase A done | Files seeded and injected into every API call via context pack builder |
| Producer DNA template | ✅ Built | `conductor-vault/producer/producer_dna.md` — Layer B |
| Never-Do Rules | ✅ Built | `conductor-vault/producer/never_do_rules.md` — read before RISKY_WRITE |
| Plugin Operator Cards | ✅ Built | Pro-Q 4, Ozone 12, Serum 2, Ableton stock — Layer C injection |
| Failure Cases vault | ✅ Built | `conductor-vault/failure-cases/` — 6 LOM failures |
| Onboarding flow | ✅ Designed | `documents/ONBOARDING_FLOW.md` — not yet implemented |
| RAG architecture | ✅ Updated | `docs/CONDUCTOR_RAG_ARCHITECTURE.md` — Phase C complete |
| Context Pack Builder | ✅ Built | `rag/context_pack_builder.py` — three-layer architecture, versioned, 14-field evidence |
| Context injection hooks | ✅ Built | Session-start + prompt-submit + pre-risky-action (stale auto-refresh) |
| Session pack versioning | ✅ Built | `session_pack_version` (ISO timestamp) + `state_hash` (MD5) per session response |
| Request mode classifier | ✅ Built | `rag/request_mode_classifier.py` — 5 modes, generalization-first |
| Protection model | ✅ Built | `rag/protection_model.py` — 6 levels: STATUS_ONLY → BLOCK_UNSUPPORTED |
| Risk taxonomy | ✅ Built | `rag/risk_taxonomy.py` — action categories, plugin aliases, operator card lookup |
| Memory write contract | ✅ Built | `POST /memory` enforces mode + collection + metadata; FREEFORM hard-blocked |
| Context Pack Debug view | ✅ Built | Collapsible block per response — mode, freshness, sources, tokens, top memories |
| Dev mode | ✅ Built | DEV toolbar button — auto-open debug blocks, raw pack view |
| 5 ChromaDB collections (split) | ✅ Phase C | `rag/memory_schema.py` — schema, thresholds, validation, mode map |
| Routed retriever | ✅ Phase C | `rag/routed_retriever.py` — mode → collection routing, replaces legacy query |
| Memory type taxonomy | ✅ Phase C | semantic · episodic · procedural · measurement — each to correct collection |
| Temporal memory scoring (C2) | ✅ Phase C | `rag/memory_scoring.py` — recency decay half-life 7d, Level 4 bypass |
| Corrective RAG write-time (C3) | ✅ Phase C | Jaccard 0.70 — marks superseded memories in ChromaDB on write |
| Corrective RAG read-time (C3) | ✅ Phase C | Jaccard 0.40 in-flight — newer wins, suppressed with reason |
| Evidence labels (C4) | ✅ Phase C | 14-field `debug.evidence` per item in `/context/pack` response |
| Hybrid BM25 search (C5) | ✅ Phase C | `_bm25_rescue()` — exact plugin/bus/code names not blurred by embeddings |
| Vault seeder | ✅ Phase C | `tools/seeder.py` — failure-cases vault → ChromaDB, idempotent |
| C1 Step 1 evidence completeness | ✅ Phase C | `rag/routed_retriever.py` — 11 new EvidenceItem fields; reason_injected normalization after C3 |
| Context pack audit log (C2) | ✅ Phase C | `rag/context_pack_logger.py` — JSONL per /context/pack; `memory/context_pack_log.jsonl` |
| Token budget/drop policy (C3) | ✅ Phase C | `rag/token_budget.py` — 2000-token default; Level 4 + failure_cases protected |
| Scope-aware corrective RAG (C4) | ✅ Phase C | `rag/corrective_check.py` — project_id/plugin_id guards prevent over-supersession |
| Undo log skeleton (C5) | ✅ Phase C | `rag/undo_log.py` — pre-execution state capture, UndoLogRequiredError; skeleton only |
| BM25 exact recall hardening (C6) | ✅ Phase C | `rag/routed_retriever.py` — `_bm25_tokenize()`, bm25_exact mode, content-hash dedup |
| A1 JSON schemas | ✅ Phase A | `data/schemas/` — plugin_metadata, operator_card, parameter_map (draft/2020-12) |
| Vault integrity tests | ✅ Phase A | `tests/test_vault_integrity.py` — 15 pass / 0 fail |
| Phase C eval suite | ✅ Phase C | `tests/phase_c_eval_set.py` — 28 sections, 0 failures; Codex review PASS |
| ActionProof v1 — before/after proof | ✅ Phase D S1 | `rag/action_proof.py` — create_proof(), read_all_proofs(), VerificationStatus |
| Structured bridge error codes | ✅ Phase D S1 | `rag/bridge_errors.py` — BridgeErrorCode enum, error_response(), ok_response() |
| Black box JSONL logs | ✅ Phase D S1 | `rag/black_box_log.py` — `memory/action_log.jsonl` + `memory/action_proof_log.jsonl` |
| Track volume readback (6-step loop) | ✅ Phase D S1 | `rag/readback.py` — verify_track_volume(), ALREADY_CORRECT detection |
| POST /action/volume | ✅ Phase D S1 | `tools/conductor_bridge.py` v1.5 — request_id/action_id, structured errors |
| Phase D Slice 1 eval suite | ✅ Phase D S1 | `tests/phase_d_slice1_eval.py` — D01–D10, 0 failures |
| Pan / mute / solo readback | ✅ Phase D S2 | `rag/readback.py` — verify_track_pan/mute/solo(), _read_pan(), _read_bool_property() |
| POST /action/pan + /mute + /solo | ✅ Phase D S2 | `tools/conductor_bridge.py` v1.6 |
| Phase D Slice 2 eval suite | ✅ Phase D S2 | `tests/phase_d_slice2_eval.py` — D11–D20, 0 failures |
| POST /feedback endpoint | ✅ Phase D S3 | `tools/conductor_bridge.py` v1.7 — KEEP/UNDO/TOO_MUCH/NOT_ENOUGH/WRONG_DIRECTION, `memory/feedback_log.jsonl` |
| Phase D Slice 3 eval suite | ✅ Phase D S3 | `tests/phase_d_slice3_eval.py` — D21–D30, 22/22 core pass |
| Compensating undo engine | ✅ Phase D S4 | `rag/undo_engine.py` — execute_undo(), drift detection, UndoValidationError |
| POST /action/undo | ✅ Phase D S4 | `tools/conductor_bridge.py` v1.9 — 409 on drift, new ActionProof per undo |
| Phase D Slice 4 eval suite | ✅ Phase D S4 | `tests/phase_d_slice4_eval.py` — D31–D38, 27/27 ALL PASS |
| Memory promotion ("dreaming") | ❌ Phase D S5+ | `rag/memory_promotion.py` not yet built |
| Session-end hook | ❌ Phase D S5+ | Triggers memory promotion on session close |
| Graph RAG (LightRAG) | ❌ Phase E | Concept relationship mapping |
| Reference Track DNA | ❌ Phase E | — |
| Ragas evaluation suite | ❌ Phase E | — |
| Hosted update server | ❌ Phase F | Needed for public users + teams |
| Operator card team submissions | ❌ Phase F | Markdown format exists, no server yet |
| Vault sync across instances | ❌ Phase F | Local files only right now |

---

## KNOWN FLAWS & OPEN QUESTIONS

### Critical
- **Bridge not auto-launched.** User must manually start the bridge before any tools work. Context pack silently degrades to fallback if bridge is down — this is by design.
- **Memory promotion not built.** Level 1 raw events are never promoted to Level 2/3. Memory stays flat until Phase D builds the "dreaming" session-end hook.

### Architectural
- **ChromaDB at scale.** Phase C adds time decay (recency scoring) and corrective RAG (contradiction suppression) — but access count tracking (`frequency` in C2) is a stub at 0.5 until Phase D wires actual tracking. See LIMITATIONS.md.
- **plugin_settings_index was an orphan.** Discovered during Phase C: this collection name was never in any mode's routing path. Decision: use `plugin_operator_index` (procedural knowledge) and `producer_memory_index` (semantic preferences) instead, with correct type routing.
- **NotebookLM is slow.** 5–15s CLI call on every technique query. No caching.
- **Stage is manual.** User sets stage via toggle. If they forget or pick wrong, routing is off.

### UX
- **No error state UI.** If bridge is down or Ableton is closed, user sees no feedback.
- **Tutorials panel not built.** Users cannot connect NotebookLM or set up Ableton MCP from within the app.
- **API key entry not built.** User cannot add their Anthropic key from the UI yet.

### Open Questions
- How does Conductor read the active Live Set file path from Ableton LOM?
- What UI prompt shown when save-as detected — new project vs renamed?
- Max ChromaDB session count before pruning is needed?
- Tauri vs Electron for .app packaging?
- Who hosts the update server and how is CI tested?
- Where is Project UUID stored — .als file, Conductor sidecar, or ChromaDB?

---

## AUDIT LOG

### Audit 1 — May 2026

**Documents created this session:**
- `conductor_ai_briefing.md` — generic AI briefing, no personal data, pasteable into any AI
- `LIMITATIONS.md` — ChromaDB limitations + fixes roadmap
- `project.md` — this file, open audit document

**system_prompt.md changes:**
- 5 revisions applied from external AI reviews: behavior language, tool priority contradiction fixed, Stage 0 exception, failure handling section, response format clarified
- Source file map added — routes instruments/tasks to correct knowledge source
- Currently reviewed and stable

**SESSION MANAGEMENT.md — full rewrite from external AI review (rated 8.5/10 → 9.2/10 with fixes):**
- Project Identity added — stable Project UUID as primary key, not project name
- Rename/duplicate/save-as handling defined
- Launch decision tree expanded — covers untitled, stale bridge, different project, closed Ableton
- Stage 0 temporary history bucket added — migrates on save, discards on close
- Freeform optional memory added — disposable by default, explicit saves go to ChromaDB global only

**What was found this session:**
- Context injection is the single biggest gap — brain designed correctly, pipeline not wired
- Session history will break at scale without stable Project ID (was using project name only)
- ChromaDB works now but needs 4 fixes before 150+ sessions
- Bridge complete but not auto-launched
- UI missing Tutorials panel, API key fields, tour sequence

**What was added this review:**
- RELIABILITY.md created — safe vs risky actions, verification rules, trust rules, snapshot triggers
- Memory quality filter added to system_prompt.md — what is worth saving vs noise
- Bridge tool response standardised — all Ableton responses now return {ok, source, data, verified, error}
- Compact context injection format documented in project.md and added to system_prompt.md
- project.md build status updated with RELIABILITY.md
- system_prompt.md — 6 additions: context injection format, PluginBridge as full tool, PluginBridge failure handling, reliability rules summary, freeform vs session mode behavior, reference to ableton.md
- PluginBridge wired throughout — context block, tools table, failure handling all updated

**SESSION MANAGEMENT.md — completed this session:**
- Resume flow added — match/mismatch/missing/closed decision tree
- Current Project State redefined — no single shared file, each project uses its own session file
- Needs Reopen flag added — full format with issue, affects, blocking, original decision, suggested fix, status, resolution tracking

**What is still open:**
- Context injection (critical — blocks all 3 dynamic layers)
- Auto-launch bridge
- Tutorials panel
- API key fields in UI
- ChromaDB time decay + dedup + contradiction fixes
- Bundled .app installer
- Project UUID storage decision
- Live Set file path reading from Ableton LOM
- Auto-load ableton.md on Ableton task failure
- AI silent write to errors.md
- Error collection pipeline + update server
- Weekly error review process (manual until server exists)
- Session save logic (Cmd+S trigger, rolling window, crash recovery) — see LIMITATIONS.md

### Audit 2 — May 2026

**Semantic Router — built and wired:**
- `conductor_router.py` created — 5 routes, HuggingFaceEncoder, sentence-transformers backend
- Installed into ableton-live-mcp venv (Homebrew pipx, PEP 668 workaround)
- Named conductor_router.py to avoid Python import conflict with semantic_router package
- 7/8 test cases routing correctly
- Memory edge case noted: "remind me what I did for X" → needs more memory utterances
- Bridge updated to v1.3 — added `GET /route` endpoint
- `/status` endpoint now reports `semantic_router` availability
- Startup banner updated — shows router status on launch
- LIMITATIONS.md updated — Semantic Router section changed from NOT BUILT → BUILT ✅
- project.md updated — build status, architecture diagram, component breakdown

**What is still open after this session:**
- UI consuming GET /route for Auto mode indicator (not wired yet)
- Memory utterances: add "remind me what I did for X" style phrases to conductor_router.py
- Everything from Audit 1 still open

---

### Audit 3 — May 2026 (Phase A complete)

**Phase A — Foundation complete:**
- Plugin scanner (`tools/plugin_scanner.py`) — scans 6 macOS paths, reads Info.plist, 3-tier classification
- Known plugins DB (`data/known_plugins.json`) — 54 entries, aliases array, normalized fuzzy matching
- Vault folder structure (`conductor-vault/`) — all 8 top-level folders created
- Producer DNA template (`producer/producer_dna.md`)
- Never-Do Rules (`producer/never_do_rules.md`) — 6 hard rules pre-seeded
- Plugin operator cards: Pro-Q 4, Ozone 12, Serum 2, Ableton Stock Devices
- Failure cases vault — 6 Ableton LOM failures migrated from ableton.md
- Onboarding flow doc (`documents/ONBOARDING_FLOW.md`)
- RAG architecture doc (`docs/CONDUCTOR_RAG_ARCHITECTURE.md`)
- project.md updated with vault component (component #12) + build status

**Critical finding during Phase A:**
Plugin scanner initially had 96% failure rate (17/665 recognised). Root cause:
(1) scan was 1 level deep — missed vendor subfolders like `Soundtoys/`
(2) alias matching failed for install-name variants
(3) hand-curated 54-entry DB cannot cover 665 plugins
Fix: switched to Info.plist metadata-first approach — every VST3/AU bundle contains manufacturer + display name + AU type code. After fix: 665/665 = 100% classified, 0 unclassified.

**Accountability note:**
Assistant saw the 96% failure signal, called it success, moved to next phase. User caught it. Acknowledged. Now: always verify output numbers before marking a phase complete.

**What is still open after Phase B:**
- Retrieval quality (Phase C) — 5-collection ChromaDB split, temporal scoring, corrective RAG, failure case retrieval before RISKY writes
- Trust layer (Phase D) — before/after proof, feedback loop, memory promotion ("dreaming")
- Graph RAG + evaluation (Phase E)
- Hosted team knowledge server (Phase F)
- All Phase C, D, E, F items from BUILD_PHASES.md

---

### Audit 4 — May 2026 (Phase B late additions + Phase C complete)

**Phase B — Late additions (completed before Phase C):**

Protection model (`rag/protection_model.py`):
- Replaced flat SAFE/RISKY with 6-level model: STATUS_ONLY → AUTO_EXECUTE_ALLOWED → UNDO_LOG_REQUIRED → CONFIRM_REQUIRED → CLARIFY_REQUIRED → BLOCK_UNSUPPORTED
- Effect inserts on named/group targets → AUTO_EXECUTE (no heavy warning card)
- Unclear pronoun target ("lower it", "route it") → CLARIFY_REQUIRED
- GUI/mouse instructions → BLOCK_UNSUPPORTED with explanation
- Project-wide scope on additive creates → CONFIRM_REQUIRED (was silently falling to AUTO)
- Panning a named track → AUTO_EXECUTE_ALLOWED (was silently falling to STATUS_ONLY)

Risk taxonomy (`rag/risk_taxonomy.py`):
- ACTION_CATEGORIES drives all risky classification — no individual plugin names hardcoded
- Known plugins database at `data/known_plugins.json` — 54 entries + camelCase aliases (FabFilterProQ4, iZotopeOzone12, etc.)
- `get_card_file_for_message()` — operator card file lookup by alias
- `get_high_risk_plugin_terms()` — combined canonical + alias list for risk pattern matching
- Broadened freeze_flatten category: "freeze every MIDI track", "flatten the lead synth"
- Broadened plugin_replace: "remove plugin from kick channel", "load a new patch in Omnisphere"

Memory Write Contract:
- Documented in `app/system_prompt.md` under `## MEMORY WRITE CONTRACT`
- Every `POST /memory` caller must include: `mode`, `collection`, valid `metadata`, `source_type`
- Mode-absent writes → `warnings[]` in response (not blocked)
- `FREEFORM_GENERAL` + project collection → HTTP 400 `freeform_write_blocked`
- Cross-project collections always open in FREEFORM (producer, plugin, failure, audio)
- Enforced in `conductor_bridge.py`

FREEFORM_GENERAL patterns (`rag/memory_schema.py`):
- Conservative guardrail — only fires for clearly non-music queries
- Patterns: food/cooking, weather, explicit document formats (email/essay), language-specific translation, named officials, small talk
- Safety rule: bare "translate this", "make this better", "write something" → NOT FREEFORM
- 21 must-fire + 11 must-not-fire cases verified in test suite

**Phase C — Retrieval Quality (complete):**

C1 — 5-collection multi-index split:
- `rag/memory_schema.py` — single source of truth for all collection names, thresholds, source types, metadata schemas, mode routing
- `rag/routed_retriever.py` — replaces legacy `_query_memory()`; `EvidenceItem` dataclass with C4 fields; `retrieve()` with mode-based routing, BM25 rescue, C3 check, C4 scoring, global sort
- `tools/seeder.py` — failure-cases vault markdown → ChromaDB at startup; idempotent upsert with stable IDs (vault_f001…vault_f006)

C2 — Temporal memory scoring (`rag/memory_scoring.py`):
- `final_score = semantic×0.60 + recency×0.30 + frequency×0.10`
- Recency: exponential decay with 7-day half-life (`2^(-age_days/7)`)
- Level 4 always scores 9999 — bypasses threshold, floats to top
- Missing `created_at` → recency = 0.5 (neutral, no crash)
- Global sort across all collections after C3 check (not per-collection)

C3 — Corrective RAG (`rag/corrective_check.py`):
- Two-layer: write-time (Jaccard 0.70 → marks `superseded_by` in ChromaDB) + read-time (Jaccard 0.40 → in-flight suppression, no DB write)
- Token normalization: lowercase, alphanumeric ≥ 3 chars, stopwords removed
- Newer wins (lower `age_days`); on tie, higher `final_score` wins
- Cross-collection isolation: producer memory never suppresses failure memory
- Bridge response includes `superseded: [old_id, …]` for write-time transparency

C4 — Evidence Labels:
- `EvidenceItem` exposes: `id · confidence · age_days · final_score · superseded_by · rejected`
- `debug.evidence` in `/context/pack` exposes 14 fields per item
- Short labels: `[producer]`, `[project]`, `[plugin]`, `[failure]`, `[audio·fresh]`, `[producer·bm25]`

C5 — Hybrid BM25 search:
- `_bm25_rescue()` in `routed_retriever.py` — `rank_bm25.BM25Okapi` on full collection
- Items not found by semantic search rescued if BM25 score > 0
- Fixed similarity: `BM25_RESCUE_SIMILARITY = 0.45` (above all thresholds except audio 0.50 — by design)
- Graceful fallback if `rank_bm25` not installed

C6 — Memory type routing (LangMem/Letta/MIRIX taxonomy):
- MENTOR now searches `plugin_operator_index` + `failure_cases_index` — plugin capability and advisory failure queries. No execution risk.
- INTERN_READ now searches `plugin_operator_index` + `audio_analysis_index` — plugin param inspection and LUFS/stereo evidence.
- `project_session_index` excluded from INTERN_WRITE_RISKY — session history is noise before a dangerous write.
- RISKY order: failure → plugin_operator → producer → audio (enforced by `RISKY_WRITE_RETRIEVAL_ORDER`)
- Discovered and fixed: `plugin_settings_index` was an orphan collection never in any mode's routing path. Plugin data now routes by knowledge type into `plugin_operator_index` (procedural) and `producer_memory_index` (semantic preferences).

Eval suite (`tests/phase_c_eval_set.py`):
- 21 sections, 0 failures
- Covers: mode classification, metadata validation, seeder idempotency, collection routing, risky keywords, failure code dedup, risk taxonomy, collection guard, FREEFORM single-source, INTERN_WRITE_SAFE failure retrieval, temporal scoring, generalization, live bridge, FREEFORM guardrail, protection levels, FREEFORM write guard, C4 evidence labels, C3 corrective RAG, C5 hybrid BM25, memory type routing

**What is still open after Phase C:**
- Memory promotion — "dreaming" (Phase D)
- Before/after proof + `POST /feedback` (Phase D)
- Session-end hook (Phase D)
- Feedback UI buttons — Keep / Undo / Too much / Not enough (Phase D)
- Graph RAG (Phase E)
- Reference Track DNA (Phase E)
- Ragas evaluation (Phase E)
- Hosted team knowledge server (Phase F)

---

---

### Audit 5 — May 2026 (Phase C hardening + A1 schemas complete)

**Phase C hardening — all sub-steps built and Codex-reviewed:**

C1 Step 1 — Evidence label completeness:
- 11 new fields added to `EvidenceItem`: `source_type`, `verification_status`, `bm25_score`, `reason_injected`, `token_count`, `project_id`, `session_id`, `plugin_id`, `freshness`, `rescue_mode`, `conflict_flag`
- All 11 fields propagated through `_query_collection()`, `_bm25_rescue()`, `_apply_threshold()`, and `context_pack_builder.py` evidence dict (now 25 fields total)
- `reason_injected` normalization pass added after `apply_corrective_check()` — C3-suppressed items correctly get `"not_injected"` not `"retrieval_match"`
- Regression test [H] added to Section 23 covering the C3 suppression path

C2 — Context pack audit logging:
- `rag/context_pack_logger.py` — one JSONL record per `/context/pack` call to `memory/context_pack_log.jsonl`
- Best-effort: never blocks inference path. Thread-safe. Includes all 25 evidence fields + `text_preview`
- Wired into `conductor_bridge.py` as `log_pack()` / `log_pack_error()` hooks

C3 — Token budget/drop policy:
- `rag/token_budget.py` — `apply_token_budget()` called in `retrieve()` after `final_score` set
- `DEFAULT_BUDGET_TOKENS = 2000`. Drops P4→P2 in priority order; hard-stops before P0 (Level 4) and P1 (failure_cases)
- Dropped items stay in `debug.evidence` with `injected=False`, `reason="token_budget_exceeded"`

C4 — Scope-aware corrective RAG:
- `rag/corrective_check.py` enhanced with two scope guards before Jaccard comparison:
  - Different non-empty `project_id` → skip entirely (different projects can't supersede)
  - Different non-empty `plugin_id` → `conflict_flag=True` on both, no suppression
- Global producer memories (both `project_id=""`) → existing Jaccard logic unchanged (no regression)

C5 — Undo log skeleton:
- `rag/undo_log.py` — append-only JSONL to `memory/undo_log.jsonl`
- `create_undo_record()` writes `executed=False` pre-execution record; raises `UndoLogRequiredError` if `UNDO_LOG_REQUIRED` action is missing `prior_state`
- `mark_executed()` / `mark_failed()` append outcome records (append-only, never modify originals)
- Scope: infrastructure skeleton only. Full rollback (re-applying prior_state to Ableton LOM) is Phase D

C6 — BM25 exact recall hardening:
- `_bm25_tokenize()` added — splits on `_`, `-`, `.` + alpha/numeric runs. Handles Pro-Q, ProQ4, Ozone12, F006, BRIDGE_TIMEOUT_003, LowShelf_Gain, Kick_Bus_01
- `rescue_mode="bm25_exact"` set for scores ≥ 75% of batch maximum; otherwise `"bm25"`
- Content-hash dedup within rescue batch prevents same text appearing twice
- BM25 rescue still respects mode/routing/protection — no bypass

Phase A1 schemas:
- `data/schemas/plugin_metadata.schema.json` — validates all 61 entries in `known_plugins.json`; 8 required + 10 optional future fields
- `data/schemas/operator_card.schema.json` — validates optional YAML frontmatter in operator card MD files
- `data/schemas/parameter_map.schema.json` — future-ready; `plugin_id` + `parameters` array
- `tests/test_vault_integrity.py` — 15 pass / 0 fail / 4 warnings (no YAML frontmatter in current cards — expected)

Eval suite:
- `tests/phase_c_eval_set.py` expanded from 21 to 28 sections
- Sections 24–28 cover: C2 audit logging, C3 token budget, C4 scope-aware corrective RAG, C5 undo log, C6 BM25 hardening
- All 28 sections: 0 failures. Codex review: PASS. No revert needed.

**Known limitations carried into Phase D:**
- `rank_bm25` not installed in ChromaDB venv → Section 28 D/E and Section 20 BM25 live-corpus tests skip. Fix: `pip install rank-bm25` in the venv.
- C5 undo log is infrastructure only — no actual rollback engine. Phase D must wire `prior_state` capture to Ableton LOM before RISKY writes.
- `frequency` score in C2 temporal scoring is stubbed at `0.5` — actual access count tracking requires Phase D to wire `POST /feedback`.

**What is still open after Phase C hardening:**
- Memory promotion / "dreaming" (Phase D)
- Before/after proof + `POST /feedback` (Phase D)
- Session-end hook (Phase D)
- Full undo rollback via Ableton LOM (Phase D — wire `undo_log.py` to LOM)
- `rank_bm25` install in bridge venv (D1 quick-fix)
- Graph RAG (Phase E)
- Hosted team knowledge server (Phase F)

---

---

### Audit 6 — May 2026 (Phase C cleanup + Phase D Slices 1–4 complete)

**Phase C cleanup:**
- `len(None)` crash fixed in `rag/routed_retriever.py` — `len(doc) // 4` → `len(doc or "") // 4` at both occurrences (lines ~200 and ~439). Root cause: ChromaDB can return `None` as a document string.
- `tests/phase_c_eval_set.py` — C5 and MT21 seed blocks wrapped in `try/finally` so cleanup always runs even if queries crash. Prevents stale timestamp IDs polluting `failure_cases_index`.
- 9 stale seeds (`c5_f003_*`, `mt21_failure_*`, `mt21_plugin_*`) deleted manually from ChromaDB.
- Confirmed: `phase_c_eval_set.py` passes on 2 consecutive runs (idempotency proven).
- All 5 test suites (phase_c_eval_set, test_vault_integrity, slice1, slice2, slice3) still pass after cleanup.

**Phase D Slice 1 — ActionProof + Structured Errors + Volume Readback:**
- `rag/action_proof.py` — ActionProof dataclass, create_proof(), read_all_proofs(), VerificationStatus enum (VERIFIED / ALREADY_CORRECT / FAILED / UNVERIFIED)
- `rag/bridge_errors.py` — BridgeErrorCode enum, error_response(), ok_response()
- `rag/black_box_log.py` — log_event(), log_requested(); separate JSONL logs: `memory/action_log.jsonl` + `memory/action_proof_log.jsonl`
- `rag/readback.py` — verify_track_volume() with 6-step readback loop: read before → ALREADY_CORRECT check → write → stabilize → read after → compare
- `tools/conductor_bridge.py` v1.5 — POST /action/volume, request_id/action_id correlation, structured errors
- `tests/phase_d_slice1_eval.py` — D01–D10, 10/10 pass

**Phase D Slice 2 — Pan / Mute / Solo Readback:**
- `rag/readback.py` extended — verify_track_pan(), verify_track_mute(), verify_track_solo(), _read_pan(), _read_bool_property()
- Bridge v1.6 — POST /action/pan, /action/mute, /action/solo with same ActionProof pattern
- `tests/phase_d_slice2_eval.py` — D11–D20, 10/10 pass

**Phase D Slice 3 — POST /feedback:**
- `tools/conductor_bridge.py` v1.7 — POST /feedback endpoint
- Stores feedback in `memory/feedback_log.jsonl` (separate append-only log — never merged with proof log)
- Supports: KEEP / UNDO / TOO_MUCH / NOT_ENOUGH / WRONG_DIRECTION
- Error codes: FEEDBACK_INVALID_TYPE, FEEDBACK_NO_REFERENCE, FEEDBACK_PROOF_NOT_FOUND, FEEDBACK_ACTION_NOT_FOUND
- No hot-path memory promotion (deferred to Phase D Slice 5+)
- `tests/phase_d_slice3_eval.py` — D21–D30, 22/22 Slice 3 core pass

**Phase D Slice 4 — Compensating Undo + Drift Detection:**
- `rag/undo_engine.py` — execute_undo(), UNDOABLE_ACTION_TYPES (volume/pan/mute/solo), UndoValidationError (with .bridge_error_code), _parse_target()
- Undo eligibility: only VERIFIED or ALREADY_CORRECT proofs can be undone; before_state must exist
- Drift detection: reads current live state before write, compares to original after_state. Tolerance: 0.005 normalized for scalars, exact for booleans. Blocks unless confirm=True.
- New proof per undo: action_type=`UNDO_{original_type}`, undo_eligible=False (no undo-of-undo)
- Append-only log invariant: original proof NEVER modified
- `tools/conductor_bridge.py` v1.9 — POST /action/undo, HTTP 409 on drift, hint: "Pass confirm=true to undo despite drift"
- Error codes added: UNDO_PROOF_NOT_FOUND, UNDO_NOT_ELIGIBLE, UNDO_UNSUPPORTED_ACTION, UNDO_NO_BEFORE_STATE
- `tests/phase_d_slice4_eval.py` — D31–D38, 27/27 ALL PASS

**Accountability note:**
D31 initially failed because `_make_proof()` test helper created an in-memory dict but never wrote to `action_proof_log.jsonl`. `read_all_proofs()` couldn't find it. Fixed by using `create_proof()` in the seed step.

**What is still open after Phase D Slices 1–4:**
- Memory promotion / "dreaming" (Slice 5+ / D3)
- Session-end hook (D7)
- Never-do preflight gate (D5) — rules file exists; enforcement not wired
- Feedback UI buttons (D6)
- Batch undo, routing undo, master bus undo (Slice 5+)
- Plugin parameter verification (after PluginBridge confirms reliable readback)
- Session-end summary / "what did you change?" (Slice 5+)
- Graph RAG (Phase E)
- Hosted team knowledge server (Phase F)

---

---

### Audit 7 — May 2026 (Phase D Slice 5 + Expanded Actions Slices 1–2)

**Phase D Slice 5 — Never-Do Preflight Gate:**
- `rag/never_do_check.py` — deterministic static table: HARD_BLOCK / REQUIRE_CONFIRMATION / ALLOW / UNDO_LOG_REQUIRED per action type; context overrides (batch escalation, target patterns); rule text returned; missing rules file → graceful degradation
- Wired to all write endpoints in `tools/conductor_bridge.py` — fires before any LOM call
- `tests/phase_d_slice5_eval.py` — D41–D51, ALL PASS

**Expanded Actions Slice 1 — Track Management:**
- `rag/readback.py` — `verify_track_create`, `verify_track_delete`, `verify_track_arm`, `verify_track_monitor` + color/rename/duplicate readback helpers
- `tools/conductor_bridge.py` — `POST /action/create_track`, `/action/delete_track`, `/action/duplicate_track`, `/action/rename_track`, `/action/color_track`, `/action/group_tracks` — all with ActionProof + never-do gate
- DELETE_TRACK = REQUIRE_CONFIRMATION (not HARD_BLOCK — preserves user agency)
- `tests/phase_d_slice6_eval.py` — D52–D73, ALL PASS (includes D73 proof field honesty + undo eligibility assertions)

**Expanded Actions Slice 2 — Routing / Sends / Transport:**
- `rag/readback.py` — `verify_track_send`, `verify_track_route`, `verify_transport_play/stop/loop/metronome`
- `tools/conductor_bridge.py` — `POST /action/track_send`, `/action/track_route`, `/action/transport_play`, `/action/transport_stop`, `/action/transport_loop`, `/action/transport_metronome`
- `tests/phase_d_slice7_eval.py` — D74–D90 core + D91–D93 Slice 2 blocker fixes

**Slice 2 Blocker Fixes (applied after Codex audit):**
1. `track_send` invalid send index (`< 0`) — 400 `BRIDGE_PARAM_OUT_OF_RANGE` before any LOM call
2. `track_send` out-of-range level (`< 0.0` or `> 1.0`) — 400 before write; silent clamp removed from `verify_track_send` (proof intended_value now matches actual written value)
3. `track_route` destination validation — `available_output_routing_types` precheck in bridge before `verify_track_route`; empty list → graceful degradation (BSCE path); 1-call precheck does not affect existing mock counts in D75/D83
- D91/D92/D93 added to `phase_d_slice7_eval.py` — **20/20 PASS**

---

### Audit 8 — May 2026 (Expanded Actions Slice 3A — Plugin Bypass)

**Expanded Actions Slice 3A — `POST /action/plugin_bypass`:**
- `rag/readback.py` — `verify_plugin_bypass()`: combined find+read first call (returns `[name, idx, is_active]` or None), write, after_read; `_read_plugin_bypass()` for undo drift detection
  - BRIDGE_PLUGIN_ABSENT on None result → 1 call, no write
  - BeforeStateCaptureError on executor failure on find call
  - State keys: `before_state = {"device_name": matched_name, "is_active": before_active}`, `after_state = {"device_name": matched_name, "is_active": after_active}`
- `rag/undo_engine.py` — PLUGIN_BYPASS in UNDOABLE_ACTION_TYPES, state_key = "is_active"; `_parse_plugin_target()` uses `rfind(":device:")` to handle colons in names; 4-call undo sequence (drift read, find+read, write, after_read); bool drift detection
- `rag/never_do_check.py` — `"PLUGIN_BYPASS": NeverDoDecision.ALLOW`
- `tools/conductor_bridge.py` — `POST /action/plugin_bypass`: bypass field parsed; ndc gate; verify_plugin_bypass; BRIDGE_PLUGIN_ABSENT → 400 before proof creation; target_str = `track:{track}:device:{matched_name}`; undo_eligible = is_confirmed and bool(before_state)
- `tests/phase_d_slice8_eval.py` — D94–D102 (9 sections)
- `tools/run_tests.sh` — `tests/phase_d_slice8_eval.py` added to SUITES

**Slice 3A Blocker Fixes (applied in same session):**
1. `"PLUGIN_BYPASS"` missing from `never_do_check.py` → every endpoint call returned 403 HARD_BLOCK → added `ALLOW`
2. `bool(bypass_raw)` → `bool("false") == True` Python truthy bug → replaced with strict parsing: JSON bool passes through; `"true"`/`"false"` strings parse correctly; any other string/type → 400 before ndc check
3. D102 added to `phase_d_slice8_eval.py`: real `check("PLUGIN_BYPASS")==ALLOW`, `"false"`→`is_active_val=True`, success path proof/log/undo_eligible=True

**Final test results:**
- `phase_d_slice8_eval.py` — **9/9 PASS** (D94–D102)
- `phase_d_slice7_eval.py` — **20/20 PASS**
- `phase_c_eval_set.py` — **all sections PASS** (410 checks, no regressions)

**What is still open after Expanded Slice 3A:**
- Expanded Slice 3B — `POST /action/plugin_param` (PluginBridge parameter control)
- Feedback UI buttons (D6) — `app/index.html` wired to `POST /feedback`
- Session-end hook (D7) + memory promotion / "dreaming" (D3)
- CoProducer Translation layer — ActionProofs → assistant dialogue (no raw JSON/enums to user)
- Drift diff dialog — premium modal on drift-blocked undo
- Studio timeline / visual debugger — visual view of `action_log.jsonl`
- Phase E — Graph RAG, reference track DNA, Ragas evaluation
- Phase F — Hosted team knowledge server, public user model

---

### Audit 9 — May 2026 (Live Harness Slices 9–14 / Knowledge Explorer v1)

**Phase D Slice 9 — Strict Confirm Parser (D103–D108):**
- `_parse_confirm_strict()` in `tools/conductor_bridge.py` — accepts JSON `true` only; rejects all string forms (`"true"`, `"false"`, `"yes"`)
- Wired to `track_delete`, `tracks_create_multiple`, `track_route`, `transport_record`
- `tests/phase_d_slice9_eval.py` — **6/6 PASS**

**Phase D Slice 10 — GET /session/state (D109–D114):**
- `GET /session/state` endpoint in `tools/conductor_bridge.py` — live Ableton snapshot
- `state_completeness` dict with `full` / `best_effort` / `not_available_v1` per field
- `tests/phase_d_slice10_eval.py` — **6/6 PASS**

**Phase D Slice 11 — Natural Replies + Premium UI (D115–D120):**
- `composeReply()` in `app/harness.js` — ActionProof → natural assistant dialogue; no raw JSON/enums surfaced
- Premium UI shell: Live Harness v1.5 (`app/harness.html`) — debug info, session totals, forbidden wording absent
- `tests/phase_d_slice11_eval.py` — **56/56 PASS**

**Phase D Slice 12 — Knowledge Gateway v1 (D121–D127):**
- `POST /harness/orchestrate` in `tools/harness_server.py` — WRITE modes → action-ID, all others → knowledge answer
- `call_knowledge_answer()` — context-enriched free-text LLM call; `_call_bridge_get()` assembles 3 context layers
- `tests/phase_d_slice12_eval.py` — **7/7 PASS**

**Phase D Slice 13 — /session/state v1.5 (D128–D134):**
- Per-track v1.5 fields: `devices`, `clip_count`, `active_send_count`, `is_group_track`, `in_group`
- Calls 3–6 wrapped in `try/except Exception` — optional fields; failure silently absent, never 500
- `state_completeness` v1.5 keys alongside all legacy v1 keys unchanged
- `tests/phase_d_slice13_eval.py` — **7/7 PASS**

**Phase D Slice 14 — Knowledge Explorer v1 (D135–D142): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice14_eval.py`.

- `_EXPLORER_MODES = {"MENTOR", "FREEFORM_GENERAL"}` — modes that trigger structured candidate generation
- `call_knowledge_explorer()` — single LLM call requesting JSON `answer` (user-facing) + `candidates` (internal). Gemini: `response_mime_type: application/json`; OpenAI: `json_object`; openai_compatible: no response_format
- `_build_explorer_instructions(session_available)` — injects session-availability honesty note
- Explorer routing in `_handle_orchestrate`: MENTOR/FREEFORM_GENERAL → explorer; READ/CLARIFY → direct; WRITE → action
- `explorer` key in response is internal metadata — not surfaced in chat UI
- `tests/phase_d_slice14_eval.py` — **8/8 PASS**

**Build 6 hardening (final pass — same session):**
- Problem: `_INTERNAL_MARKERS` tuple (5 quoted markers) did not catch unquoted YAML-style (`candidates: ...`), mixed-case (`CANDIDATES:`), or markdown-fenced output — raw schema could leak to user
- Fix: replaced `_INTERNAL_MARKERS` + `any()` with `_STRUCTURAL_RE = re.compile(r"(?i)\b(candidates|direction|rationale|session_facts_used|assumptions|source_hints|actionable|confidence|question_type)\b")` — case-insensitive, word-boundary, all 9 markers
- Added `raw_stripped.startswith("```")` fence detection
- D137 Sub-D (YAML-style), Sub-E (fenced partial schema), Sub-F (mixed-case) added to prove all three paths return fallback, not raw schema

**Full audit evidence:**
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

---

---

### Audit 10 — May 2026 (Build 7 — Creative Critic v1 / D Slice 15)

**Phase D Slice 15 — Creative Critic v1 (D143–D153): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice15_eval.py`.

- `call_creative_critic()` in `tools/harness_server.py` — single LLM call evaluating Explorer candidates on 6 criteria: genericity, session_grounding, session_contradiction, goal_fit, practicality, unsupported_assumptions. Returns `({}, tokens)` on parse failure or invalid selection index. Never raises to caller.
- `_build_critic_prompt()` + `_CRITIC_JSON_SCHEMA` — 6-criterion evaluation prompt; JSON schema specifying `selected`, `kept`, `rejected`, `reasons`, `critic_summary`.
- `_compose_final_answer(explorer_answer, explorer_data, critic_data)` — deterministic composer (no LLM). Reads `critic_data["selected"]`, validates index against candidates length, builds `"{direction}. {rationale}."`. Safety-guarded by `_STRUCTURAL_RE`. Falls back to `explorer_answer` on empty critic, invalid/out-of-range index, missing direction, or structural marker in composed text.
- `_handle_orchestrate` Explorer branch updated — calls `call_creative_critic` after `call_knowledge_explorer`, then `_compose_final_answer`. Sends `"text": final_text` (Critic-filtered). `"explorer"` and `"critic"` fields remain internal. Critic failure non-fatal; always falls back to `explorer_answer`.
- `tests/phase_d_slice15_eval.py` — **11/11 PASS** (D143–D153)
  - D152: core filtering proof — 5 assertions proving rejected candidate cannot control the final answer
  - D153: real `call_creative_critic()` parser — 7 sub-cases (malformed, missing key, out-of-range, valid, `_compose_final_answer` edge cases)

**Backup Coding Protocol docs added (same session):**
- `CLAUDE.md` (TEST-BUILD) — added "BACKUP CODING / LIMIT EXHAUSTED PROTOCOL" section: required context checklist, backup assistant rules, Graphify usage rules, handoff format template, recovery rule
- `CODEX_REVIEWER.md` — added "Backup Coding Audit" section: trigger, 5-item checklist, output format
- `HANDOFF_CURRENT_STATE.md` (root) + `tmp/HANDOFF_CURRENT_STATE.md` — handoff template, filled Build 7 block, known limitation note, "Critic composer polish" roadmap item

**Known limitation (do not reopen Build 7):**
`_compose_final_answer()` outputs `"{direction}. {rationale}."` — safe and correct but intentionally plain. Future: smoother sentence flow, session-fact weaving, co-producer voice. Track as "Critic composer polish — post Build 7". New slice only.

**Full audit evidence:**
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

---

### Audit 11 — May 2026 (Build 8 — Card-aware Creative Critic v1 / D Slice 16)

**Phase D Slice 16 — Card-aware Creative Critic v1 (D154–D161): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice16_eval.py`.

- `_extract_operator_card_context(message_pack_text)` in `tools/harness_server.py` — scans `/context/pack` text for `## OPERATOR CARD` block, returns it (up to 3000 chars) for forwarding to Critic.
- `call_creative_critic()` updated — accepts `card_context=""` kwarg. When present, `_build_critic_prompt()` injects an `## Operator Card Context` section instructing the Critic to penalize or reject candidates violating Operator Card Never Do rules, Risky Writes, plugin identity, or supported controls.
- `operator_card_compliance` added as 7th evaluation criterion in the Critic prompt.
- `_handle_orchestrate` updated — calls `_extract_operator_card_context(message_pack_text)` and passes result to `call_creative_critic` as `card_context`.
- `tests/phase_d_slice16_eval.py` — **8/8 PASS** (D154–D161)

**Full audit evidence:**
| Suite | Result |
|---|---|
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `tests/phase_d_slice14_eval.py` | 8/8 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `node --check app/harness.js` | PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

---

### Audit 12 — May 2026 (Builds 9 + 10 — Operator Card v2 Schema + Plugin Knowledge Routing v1 / D Slice 17)

**Phase D Slice 17 — Plugin Knowledge Routing v1 (D162–D168 + D162b): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice17_eval.py` or `tests/test_seeder_safety.py`.

**Build 9 — Operator Card v2 Schema & Content Readiness:**
- `seed_operator_cards()` in `tools/conductor_bridge.py` — unsafe stale-ID deletion removed. Seeder is upsert-only; `delete()` is never called on `plugin_operator_index`. Stable IDs: `vault_plugin_{card_id}`.
- YAML frontmatter added to all 4 operator cards: `card_id`, `display_name`, `type`, `risk_level`, `verification_status`, `collection`, `tags`, `operator_card_triggers`.
- `tests/test_seeder_safety.py` — 3/3 PASS (B9-S1, B9-S2).

**Build 10 — Plugin Knowledge Routing v1:**
- `_get_stable_card_id(card_file)` — reads YAML frontmatter `card_id`, returns `vault_plugin_{card_id}`. Fails closed (returns `None`) if file missing, no frontmatter, or no `card_id`.
- Guard A: when file-based snippet for plugin X is injected, the ChromaDB full-body card for X is excluded from the Memory section (`dedup_file_path_is_authoritative`).
- Guard B: when no plugin is name-detected, BM25-rescued plugin cards are blocked (`no_plugin_detected_bm25_rescue_blocked`). Semantic hits still pass.
- Guard rebuild fix: `_new_injected` iterates `retrieval.injected` (weight-sorted), not `retrieval.retrieved` (raw ChromaDB order).

**Full audit evidence:**
| Suite | Result |
|---|---|
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/test_seeder_safety.py` | 3/3 PASS |
| `tests/test_vault_integrity.py` | 15/15 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile rag/context_pack_builder.py` | PASS |

---

### Audit 13 — May 2026 (Build 11 — Plugin Knowledge Trust Signals / D Slice 18)

**Phase D Slice 18 — Plugin Knowledge Trust Signals (D169–D176): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice18_eval.py`.

- `get_known_plugin_name_for_message(message)` in `rag/risk_taxonomy.py` — scans all 61 inventory entries (has_card=True or False), returns canonical plugin name or `""`. Used to detect "recognized plugin with no card" case.
- `_check_plugin_knowledge_status(message, card_file)` in `rag/context_pack_builder.py` — returns `("verified", name)` when card present, `("missing", name)` when plugin recognized but no card, `("none", "")` when no plugin recognized.
- `## KNOWLEDGE STATUS` block injected into message pack when status is `"missing"`. Absent when card is present or no plugin is recognized. Tells Explorer/Critic: "answer from general knowledge only; flag plugin-specific claims as unverified."
- `knowledge_gap` rule added to `_build_explorer_instructions()` — when `## KNOWLEDGE STATUS` present, populate `assumptions` and set `confidence ≤ 0.5` for plugin-specific candidates.
- `knowledge_evidence` criterion added to `_build_critic_prompt()` — penalize ungrounded plugin-specific claims when no Operator Card is available.
- `tests/phase_d_slice18_eval.py` — **8/8 PASS** (D169–D176)

**Full audit evidence:**
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

### Audit 14 — May 2026 (Build 12 — Knowledge Status Context to Critic / D Slice 19)

**Phase D Slice 19 — Knowledge Status Context to Critic (D177–D186): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice19_eval.py`.

- `_extract_knowledge_status_context(message_pack_text, max_chars=600)` in `tools/harness_server.py` — extracts `## KNOWLEDGE STATUS` block from `/context/pack` text; stops at the next `##` section; returns `""` when absent. Mirrors `_extract_operator_card_context()`.
- `_build_critic_prompt()` — `knowledge_status_context=""` param added; injects `## Plugin Knowledge Context` block (internal only) when present, directing Critic to apply `knowledge_evidence` and penalize unacknowledged plugin-specific claims.
- `call_creative_critic()` — `knowledge_status_context=""` param added; passed through to `_build_critic_prompt()`.
- `_handle_orchestrate()` — extracts `knowledge_status_context` from `message_pack_text` and passes to `call_creative_critic()` alongside `card_context`. Closes the gap where `knowledge_evidence` criterion had no direct context to evaluate.
- `_TRUST_LABEL_RE` — new module-level regex covering 6 internal trust labels: `KNOWLEDGE STATUS`, `Plugin Knowledge Context`, `Operator card: not available`, `knowledge_evidence`, `confidence <=`, `confidence ≤`.
- `_compose_final_answer()` — trust-label guard added using `_TRUST_LABEL_RE`: if selected-candidate `direction` or `rationale` contains any marker, falls back to `explorer_answer`. Blocks Build 11/12 internal labels from leaking into user-facing composed text.
- `tests/phase_d_slice15_eval.py` and `tests/phase_d_slice16_eval.py` — two `fake_critic` mock signatures each updated to accept `knowledge_status_context=""` (required by new kwarg, no behavior change).
- `tests/phase_d_slice19_eval.py` — **10/10 PASS** (D177–D186): extractor tests (D177–D179), critic prompt injection (D180–D182), orchestrate integration (D183–D184), adversarial trust-label fallback (D185), `_TRUST_LABEL_RE` unit coverage (D186).

**Codex audit result:** PASS — Build 12 locked.

**Full audit evidence:**
| Suite | Result |
|---|---|
| `tests/phase_d_slice19_eval.py` | 10/10 PASS |
| `tests/phase_d_slice18_eval.py` | 8/8 PASS |
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |

---

---

### Audit 15 — May 2026 (Build 13 — Critic Composer Polish / D Slice 20)

**Phase D Slice 20 — Critic Composer Polish (D187–D196): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice20_eval.py`.

- `_compose_final_answer()` — em-dash prose join for short directions (≤ 8 words); period join for longer. Trailing punctuation stripped before joining so connectors land cleanly.
- `_safe_session_facts(facts)` — new helper filtering `session_facts_used` entries for user-facing safety. Drops: JSON-looking facts (`{`, `[`), internal key:value metadata (`mode:`, `risk:`, `score:`, `selected:`, `kept:`, `rejected:`), ID references (`proof id`, `request id`, `action id`), `_STRUCTURAL_RE` / `_TRUST_LABEL_RE` matches, Operator Card refs, markdown headers, snake_case keys, entries > 60 chars.
- `_compose_final_answer()` — light session_facts_used weaving: novel safe facts (at most 2, not already in composed text) appended as parenthetical `(fact1, fact2).`
- `tests/phase_d_slice16_eval.py` — D154/D157 assertions updated for em-dash format ("Use gentle Ozone mastering moves" is 6 words, now uses em-dash connector).
- `tests/phase_d_slice20_eval.py` — **10/10 PASS** (D187–D196): em-dash prose (D187), direction-only (D188), facts weaving (D189–D190), debug-fact guard (D191), `_STRUCTURAL_RE` regression (D192), `_TRUST_LABEL_RE` regression (D193), invalid-critic fallbacks (D194), new metadata filter (D195), clean facts still weave (D196).

**Codex audit result:** PASS — Build 13 locked. Commit: `8bb4b0b`

**Full audit evidence:**
| Suite | Result |
|---|---|
| `tests/phase_d_slice20_eval.py` | 10/10 PASS |
| `tests/phase_d_slice19_eval.py` | 10/10 PASS |
| `tests/phase_d_slice18_eval.py` | 8/8 PASS |
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |
| `node --check app/harness.js` | PASS |

---

### Audit 16 — May 2026 (Build 14 — CLARIFY Mode Hardening / D Slice 21)

**Phase D Slice 21 — CLARIFY Mode Hardening (D197–D204): PASS/LOCKED**

> Do not reopen unless a regression appears in `tests/phase_d_slice21_eval.py`.

- `_CLARIFY_LABEL_RE` — module-level regex (`re.IGNORECASE`) guarding internal category/label names from leaking into composed clarify questions.
- `_CLARIFY_VERB_RE` — module-level regex extracting action verbs from ambiguous pronoun messages.
- `_clarify_safe(question)` — final safety guard; rejects non-questions and outputs containing `_CLARIFY_LABEL_RE` / `_STRUCTURAL_RE` / `_TRUST_LABEL_RE` matches.
- `_compose_clarify_question(original_text, risk_reason, risk_category)` — deterministic composer, no LLM call. Template map: `unclear*` → verb-grounded question; `too_short` → natural re-ask; `*scope*` → track/bus/plugin question; generic fallback from `risk_reason` when safe; BLOCK/unknown → `""`.
- `_handle_orchestrate()` — extracts `risk_reason` and `risk_category` from `pack_data`. CLARIFY fast-path inserted before context assembly: returns `type:"clarify"` deterministically with zero LLM tokens when composer succeeds; falls through to `call_knowledge_answer()` (type:`"answer"`) when composer returns `""`.
- `tests/phase_d_slice21_eval.py` — **8/8 PASS** (D197–D204): composer unit tests all branches (D197), label guard (D198), pronoun integration (D199), too_short integration (D200), fallback path (D201), MENTOR unaffected (D202), risk field extraction (D203), symbol importability (D204).

**Codex audit result:** PASS — Build 14 locked. Commit: `7376a41`

**Full audit evidence:**
| Suite | Result |
|---|---|
| `tests/phase_d_slice21_eval.py` | 8/8 PASS |
| `tests/phase_d_slice20_eval.py` | 10/10 PASS |
| `tests/phase_d_slice19_eval.py` | 10/10 PASS |
| `tests/phase_d_slice18_eval.py` | 8/8 PASS |
| `tests/phase_d_slice17_eval.py` | 8/8 PASS |
| `tests/phase_d_slice16_eval.py` | 8/8 PASS |
| `tests/phase_d_slice15_eval.py` | 11/11 PASS |
| `python3 -m py_compile tools/harness_server.py` | PASS |
| `node --check app/harness.js` | PASS |

---

*Last updated: May 2026 — Phase D through Slice 21 (Build 14 — CLARIFY Mode Hardening) complete. Slices 9–21 and Expanded Actions 1–3A all PASS/LOCKED. Builds 1–14 locked.*
