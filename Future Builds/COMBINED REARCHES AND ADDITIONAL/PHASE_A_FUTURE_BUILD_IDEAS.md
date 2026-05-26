# Phase A Future Build Ideas

This file preserves strong ideas from Phase A research that should not be lost, but should not all be implemented immediately.

## Purpose

Separate:

- build now
- build soon
- save for later

This prevents good research ideas from being wasted while protecting the current working Phase C backend.

## Future Idea 1 — Directory-Based Operator Packages

Instead of one flat markdown card per plugin, each important plugin could become a package:

```text
conductor-vault/plugins/operator-packages/fabfilter_pro_q_4/
  operator-card.md
  parameter-map.json
  references.md
  failure-cases.md
  test-prompts.md
  examples/
```

Why useful:

- keeps PluginBridge maps, docs, failures, and examples together
- easier team review
- easier hosted operator-card marketplace later

Do later. Do not restructure current vault immediately.

## Future Idea 2 — Temporal Validity Windows

Add validity metadata to plugin facts and parameter maps:

```json
{
  "valid_from": "2026-05-24",
  "valid_until": null,
  "superseded_by": null
}
```

Why useful:

- plugin versions change
- PluginBridge scans can become stale
- old parameter maps should not be treated as current truth

Good for PluginBridge mature phase.

## Future Idea 3 — MCP-Style Action Annotations

Borrow MCP-like tool/action hints:

```json
{
  "read_only": true,
  "destructive": false,
  "idempotent": true,
  "requires_undo_log": false
}
```

Useful for Smart Execution and future real DAW action wiring.

## Future Idea 4 — Advanced Trust Tiers for Teams

Current recommended trust values:

- `bridge_verified`
- `manual`
- `inferred`
- `deprecated`

Future team/server values may include:

- `community_verified`
- `team_verified`
- `official_vendor`
- `certified_pluginbridge`

This belongs to hosted/team Phase F, not immediate Phase A cleanup.

## Future Idea 5 — Vault Health Dashboard

A UI/debug view showing:

- cards missing frontmatter
- broken card_file links
- stale parameter maps
- deprecated facts
- missing generic class fallbacks
- Chroma/vault hash mismatch
- last ingest time
- retrieval smoke test status

Useful for full Conductor debugger/black box.

## Future Idea 6 — Database Integrity Probe

Before Chroma ingest, run:

1. write probe document
2. read probe document
3. delete probe document
4. verify deletion

This catches silent DB failures.

Good to add before enabling automatic Chroma sync.

## Future Idea 7 — Ingest Manifest

Add manifest file:

```json
{
  "doc_id": "...",
  "path": "...",
  "source_hash": "...",
  "chunk_ids": ["..."],
  "last_indexed_at": "..."
}
```

Useful for incremental ingest and stale chunk deletion.

## Future Idea 8 — Generic Class Card Expansion

Create generic cards for:

- EQ
- compressor
- limiter
- reverb
- delay
- saturation
- de-esser
- synth
- sampler
- transient shaper
- pitch correction
- restoration/noise reduction
- analyzer
- utility

These prevent safety dead zones for plugins without dedicated cards.

## Future Idea 9 — Runtime Capability Comparison

Compare:

- official/manual plugin facts
- known_plugins.json registry
- PluginBridge live scan
- current project plugin instance state

Then show mismatch warnings:

```text
Manual says parameter exists, but PluginBridge scan did not expose it.
```

Useful for robust automation.

## Future Idea 10 — Operator Card Trigger System

Add trigger metadata:

```yaml
triggers:
  - "pro q"
  - "surgical eq"
  - "dynamic eq"
  - "band 2"
```

Use it to lazy-load cards like Agent Skills.

## Future Idea 11 — Card Summary + Detail Chunks

For each operator card, generate:

- one summary chunk
- H2 detail chunks
- critical safety chunk
- verification chunk

This supports both broad and exact queries.

## Future Idea 12 — PluginBridge Parameter Search Index

Create exact lookup for:

- parameter display names
- aliases
- logical paths
- param IDs
- safe ranges

Should complement BM25 + semantic search.

## Future Idea 13 — Full Operator Card Factory

A future pipeline where AI helps draft cards from manuals, but every fact is marked:

- source
- confidence
- verification status
- human reviewed or not
- PluginBridge verified or not

AI drafts. Human/PluginBridge verifies.

## Future Idea 14 — Team Operator Registry

For Phase F:

- hosted operator cards
- team-approved cards
- shared failure cases
- contributor review flow
- versioned releases
- rollback support

## Future Idea 15 — Obsidian Workflow

Use Obsidian as the human editing/review cockpit for:

- operator cards
- producer DNA
- never-do rules
- failure cases
- plugin documentation notes

But runtime still uses validated schemas + Chroma derived index.

## Future Idea 16 — Vault Source Citation Enforcement

Require source citations for:

- plugin limits
- risk rules
- parameter facts
- PluginBridge quirks
- official claims

Example:

```yaml
source_citations:
  - type: official_manual
    url: "https://www.fabfilter.com/help/pro-q"
    checked_at: "2026-05-24"
```

## Future Idea 17 — Semantic / Episodic / Procedural Labels

Add memory type labels:

- semantic
- episodic
- procedural
- evidence
- failure

This helps retrieval routing and debugging.

## Future Idea 18 — Deprecated Fact Archive

Do not delete old plugin facts. Mark them:

```yaml
verification_status: deprecated
superseded_by: "new_fact_id"
```

Default retrieval excludes deprecated facts.

## Future Idea 19 — Retrieval Smoke Tests Per Card

Each operator card can include test prompts:

```yaml
test_queries:
  - "how many bands does pro q support"
  - "set band 2 frequency"
```

Ingest tests verify the expected card chunk is retrieved.

## Future Idea 20 — Auto-Generated Card Quality Score

Score cards by:

- has frontmatter
- has source citation
- has verification status
- has failure cases
- has PluginBridge map
- has test prompts
- has generic fallback

Useful for onboarding and QA.
