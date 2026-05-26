# Conductor — Known Limitations
> Documents current limitations across the stack and planned fixes.
> Update this as new limitations are found or fixes are shipped.

---

## CHROMADB MEMORY

### Limitations

**1. No time decay**
Old memories from session 1 are weighted the same as session 199. User's taste changes over time but ChromaDB has no concept of recency. A bad old decision can override a good new one.

**2. No contradiction resolution**
Conflicting memories can coexist with no way to resolve them:
> Session 10: "cut 200Hz on dhol worked"
> Session 80: "boosting 200Hz on dhol worked for this genre"
ChromaDB returns whichever is most similar to the query — it has no logic to determine which is currently correct.

**3. Duplicate buildup**
The same decision saved multiple times across sessions creates noise. Retrieval returns duplicates instead of useful distinct memories.

**4. Retrieval quality degrades at scale**
Top 3 results out of 2000+ memories may not be the most relevant. Wrong memory injected into context → wrong advice given confidently.

**5. No per-project isolation**
A mixing decision for a Punjabi pop track can be returned when working on a film score. No separation between project-specific and global preferences.

---

### Fixes (not yet built)

| Problem | Fix | Priority |
|---|---|---|
| No time decay | Add timestamp to every memory. Weight recent memories higher during retrieval. | High |
| Contradictions | "Supersede" mechanism — new decision on same topic overwrites old one | High |
| Duplicates | Dedup check before saving — if similar memory exists, update instead of add | Medium |
| Retrieval quality | Separate collections: project-specific vs global preferences vs technique knowledge | Medium |
| Per-project isolation | Tag memories with project name. Filter by project on retrieval, fall back to global. | Medium |

---

### When does this become a problem?

| Sessions | Status |
|---|---|
| 1–50 | Works well. Memory is small, retrieval is accurate. |
| 50–150 | Minor noise. Duplicates start building up. |
| 150+ | Retrieval quality degrades. Fixes needed before this point. |

---

---

## SESSION SAVE LOGIC

### Current state
Not built. No automatic session saving exists yet.

### Limitations

**1. Manual save trigger is unnatural**
Original design required user to say "save session" explicitly. Producers don't think that way — they press Cmd+S and expect everything to be captured.

**2. Multiple saves in one session**
If user saves 10 times in 5 hours, no logic exists for what to keep. Options:
- Overwrite — simple but loses history
- Timestamped snapshots — full history but heavy
- Rolling window (last 5 saves) — recommended, stays lean

**3. Crash recovery gap**
If bridge or Ableton crashes between saves, all context after the last Cmd+S is lost. No incremental write exists.

**4. No dirty flag**
No way to know if session state has changed since last save. Nothing tells the AI "unsaved changes exist."

---

### Planned fixes

| Problem | Fix | Priority |
|---|---|---|
| Manual save trigger | Detect Cmd+S via Ableton LOM → auto-snapshot session state | High |
| Multiple saves | Rolling window — keep last 5 saves, drop oldest on each new save | High |
| Crash recovery | Incremental context write every 10 minutes in background | Medium |
| Dirty flag | Track changes since last save, warn user on close if unsaved | Medium |
| Session file naming | `sessions/[Project-UUID]-[project-name]-session.md` — UUID prevents rename breaking history | High |

---

---

## KNOWLEDGE BASE CONNECTION

### Current state
SOURCE_OF_TRUTH files exist locally. NotebookLM CLI works for Adi's personal notebook. New users have no knowledge base connected by default.

### Limitations

**1. No auto-upload for new users**
SOURCE_OF_TRUTH files must be manually uploaded to the user's own NotebookLM notebook. No guided flow exists yet — Tutorials panel is not built.

**2. Source file map not wired to bridge**
`system_prompt.md` tells the AI which source file covers which task. But the bridge just sends a plain text query to NotebookLM — it cannot target a specific source file. NotebookLM searches whatever is in the user's notebook.

**3. Empty notebook = useless knowledge layer**
If user skips NotebookLM setup, all technique queries return nothing. AI falls back to training data — generic, not personal.

### Planned fixes

| Problem | Fix | Priority |
|---|---|---|
| No auto-upload | Bundle SOURCE_OF_TRUTH files with Conductor. Auto-upload to user's notebook on first connect via Tutorials panel | High |
| Source targeting | Pass source file name as context in NLM query so it searches the right document first | Medium |
| Empty notebook fallback | If NLM returns empty, fall back to SOURCE_OF_TRUTH files directly via bridge | Medium |

---

## SEMANTIC ROUTER — BUILT ✅

### What it is
Fast embedding-based query routing. Reads user message → matches to correct knowledge source without any LLM call. No API cost. No latency.

**Repo:** https://github.com/aurelio-labs/semantic-router
**File:** `tools/conductor_router.py`

### Current state
Installed. Routes defined. Wired into bridge as `GET /route`. Imports into conductor_bridge.py on startup.

**Install path:** `/opt/homebrew/var/pipx/venvs/ableton-live-mcp/bin/python3`
**Encoder:** `HuggingFaceEncoder` (sentence-transformers, local, no API key)
**Test results:** 7/8 correct. One edge case ("remind me what I did for the kick" → went notebooklm instead of memory) — more memory utterances needed.

### How it works

```
User message
     ↓
Semantic Router (embedding match — no LLM cost)
     ↓
     ├── Deep knowledge    → NotebookLM
     ├── Live session      → Ableton
     ├── Past decisions    → ChromaDB memory
     ├── Audio file        → Audio Analyzer
     └── Simple question   → Claude directly
     ↓
Bridge fetches result  (or GET /route returns route to UI)
     ↓
Claude answers with data
```

### Bridge endpoint

```
GET /route?q=how do I layer strings
→ { "ok": true, "route": "notebooklm", "router": "semantic", "query": "..." }
```

`router: "fallback"` means sentence-transformers not available — defaults to notebooklm for all.

### What it unlocks
- Auto mode becomes truly automatic — no LLM decision needed for routing
- Consistent routing — same question always hits the same source
- GET /route lets UI show the user which source is being queried (Auto mode indicator)
- Zero API cost for routing decision

### Remaining gaps

| Problem | Fix | Priority |
|---|---|---|
| Memory edge case ("remind me what I did for X") | Add 5–10 more memory utterances to conductor_router.py | Medium |
| UI not consuming /route yet | Wire Auto mode indicator to GET /route | Medium |
| Cold start (session 1) | Already handled — fallback to notebooklm | Done |
| sentence-transformers missing | Installed into ableton-live-mcp venv | Done |

### Naming note
File is named `conductor_router.py` (not `semantic_router.py`) to avoid a Python import conflict with the `semantic_router` package itself.

---

---

## BUILD ROADMAP — PHASE A TO E

The following phases address the open limitations above. Detailed tracking in `tmp/BUILD_PHASES.md`.

### Phase A — Foundation ✅ COMPLETE
Goal: right files in the right places. No intelligence yet.

- Plugin scanner — scans macOS VST3/AU paths, reads Info.plist, 100% classification
- Known plugins DB — 54 entries, aliases, 3-tier matching
- Conductor Vault — markdown folder structure, no Obsidian required
- Producer DNA template — taste, genres, workflow, permissions
- Never-Do Rules — hard safety rules pre-seeded
- Plugin Operator Cards — Pro-Q 4, Ozone 12, Serum 2, Ableton stock
- Failure cases vault — 6 LOM failures logged
- Onboarding flow designed
- RAG architecture documented

**Remaining gap after Phase A:** All vault files exist. None reach the AI automatically. Context injection not built.

---

### Phase B — Context Pack ✅ COMPLETE (B1–B13)
Goal: vault + memory + live Ableton state actually reaches the AI on every call.

Built:
- Context pack builder (`rag/context_pack_builder.py`) — three-layer architecture
- Request mode classifier (`rag/request_mode_classifier.py`) — 5 modes, 13/13 tests pass
- Session-start hook — fetches Layer A (system prompt) + Layer B (DNA + project + tools)
- Prompt-submit hook — Layer C built fresh each message (mode header first, then memories + card)
- Pre-risky-action hook — stale auto-refresh (if age > 30s) + inline confirm gate
- Bridge endpoints: `GET /context/system_prompt`, `GET /context/session`, `GET /context/pack`
- Session pack versioning: `session_pack_version` (ISO timestamp) + `state_hash` (12-char MD5)
- Context Pack Debug view: mode, freshness (green/amber/red), sources, tokens, top memories
- Dev mode: DEV toolbar button — auto-open debug blocks + raw pack excerpt

**Known limitation carried into Phase C:** Single ChromaDB collection. All memories compete in one pool — retrieval degrades at 150+ sessions. Phase C splits into 5 targeted collections.

---

### Phase C — Retrieval Quality ✅ COMPLETE (Codex PASS)
Goal: right memory reaches the AI, not just any memory.

Built:
- 5 separate ChromaDB collections (producer / project / plugin / failure / audio)
- Temporal scoring — recency decay half-life 7 days; Level 4 always floats to top
- Corrective RAG — Jaccard contradiction detection at write-time (0.70) and read-time (0.40); scope-aware: different project_id or plugin_id bypasses auto-suppress
- Hybrid BM25 search — enhanced tokenizer handles Pro-Q, F006, BRIDGE_TIMEOUT_003 etc.; `bm25_exact` mode for top matches; content-hash dedup
- Token budget — 2000-token evidence cap; Level 4 and failure_cases protected from drop
- Audit logging — JSONL per /context/pack call, 25-field evidence record
- Undo log skeleton — pre-execution state capture; `UndoLogRequiredError` guard
- 25-field evidence schema per retrieved item in `debug.evidence`
- 28-section eval suite, 0 failures

**Known limitations still open after Phase C:**
- `rank_bm25` not installed in bridge's ChromaDB venv — BM25 rescue silently skipped at runtime until `pip install rank-bm25` in that venv
- Undo log is infrastructure only — `prior_state` capture and Ableton LOM rollback not wired (Phase D)
- `frequency` weight in C2 temporal scoring stubbed at 0.5 — real access count tracking requires Phase D feedback loop
- Token budget accepts budget overrun rather than drop Level 4 / failure_cases — correct behavior, documented

**Addresses:** ChromaDB degradation at 150+ sessions (documented above). All five original fix items now built.

---

### Phase D — Trust Layer ❌ NOT STARTED
Goal: producer can see what changed, approve it, and Conductor learns from the answer.

Key items:
- Before/after proof system
- POST /feedback endpoint
- Memory promotion ("dreaming") — session-end background process
- Session black box logs
- Feedback UI buttons — Keep / Undo / Too much / Not enough / Wrong direction

---

### Phase F — Teams & Hosted Knowledge Base ❌ NOT STARTED
Goal: the entire conductor-vault becomes a living, team-maintained knowledge base.
Not just operator cards — plugin manuals, music theory, genre references, mixing techniques, reference track DNA.
Team submits anywhere. Adi approves medium/high risk. All Conductor instances sync automatically.

What the team can contribute:
- Plugin operator cards (param IDs, quirks, use cases, risky write rules)
- Mixing & EQ techniques (with exact Hz / dB / ratio values — no vague language)
- Genre targets (BPM ranges, LUFS targets, arrangement templates — Punjabi Pop, Hindi Cinematic, etc.)
- Plugin manual notes (key points from manuals, version-specific behaviour)
- Reference track DNA (LUFS, BPM, key, spectral features)
- Confirmed failure cases (what broke, root cause, confirmed fix)

What is locked (Adi only, never team-editable):
- `producer/producer_dna.md` — personal taste and workflow
- `producer/never_do_rules.md` — hard safety rules

Key infrastructure:
- Hosted server (FastAPI — Railway/Supabase/Render)
- `POST /knowledge/submit` — unified endpoint for all knowledge types
- Auth — team roles: viewer / contributor / approver
- Worker Claude Code server-side — validates + applies by knowledge type + risk level
- Vault sync — `GET /vault/sync` — every Conductor instance pulls latest on session start
- Shares infrastructure with Error Collection pipeline (one server, both jobs)

**Current state:** update protocol exists as markdown files + manual bash trigger. KNOWLEDGE_UPDATE_FORMAT.md + WORKER_INSTRUCTIONS.md document the full format. Works for solo dev + direct file access. Breaks at public scale — needs Phase F server.

---

### Phase E — Advanced Intelligence ❌ NOT STARTED
Goal: graph relationships, reference tracks, evaluation, observability.

Key items:
- Graph RAG (LightRAG) — relationship mapping between concepts
- Reference Track DNA — compare mix against reference
- Audio feature memory — store LUFS/spectrum snapshots cross-session
- Evaluated RAG test suite (Ragas)
- Langfuse / Phoenix tracing

---

*Last updated: May 2026*
