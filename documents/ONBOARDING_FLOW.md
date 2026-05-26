# Conductor — Onboarding Flow
> What happens when a new user installs Conductor for the first time.
> Goal: works on Day 1 with zero configuration. Advanced features unlock with setup.
> Design principle: progressive — never block on setup. Always offer a path forward.

---

## Principles

1. **Never block.** If a step is skipped, Conductor still works — just with less context.
2. **Scan first, ask minimally.** Plugin scanner auto-detects the library. Only ask 4 questions.
3. **No Obsidian required.** The vault is a plain markdown folder. Users never need to install anything extra.
4. **First session should feel magical.** Even with no configuration, AI works with full knowledge of their plugin library.

---

## Step 1 — Install

- User downloads Conductor
- Installer places:
  - `app/` — Electron app or web UI
  - `tools/` — bridge, scanner, router, RAG scripts
  - `conductor-vault/` — pre-seeded vault with templates
  - `data/` — known_plugins.json
  - Source knowledge files (SOURCE_OF_TRUTH / NotebookLM Sources)

---

## Step 2 — First Launch

### Screen: Welcome
- Brief what Conductor is (2 sentences)
- "Let's set up your studio in 60 seconds"
- CTA: "Start setup" / "Skip setup"

**If skip:** loads with blank producer_dna.md — AI has no personal profile. Works, but generic.

---

## Step 3 — Plugin Scan (automatic)

Runs in background as user reads welcome screen.

```
Scanning your plugin library...
```

`tools/plugin_scanner.py` runs with `--quiet` flag:
- Scans 6 macOS paths
- Reads Info.plist from every bundle
- Classifies 3 tiers: DB matched / auto-detected / unknown
- Writes `conductor-vault/studio/studio_inventory.md`

**User sees:** "Found 665 plugins. Recognised 665. 0 unknown."

No blocking — scan result shown as confirmation, not a gate.

---

## Step 4 — 4 Anchor Questions

After scan completes:

```
Great! We found your plugin library.

Now tell us your go-to tools:

1. Primary EQ (e.g., Pro-Q 4, EQ Eight, TDR Nova):
   ___________________

2. Primary Compressor (e.g., Pro-C 2, Ableton Compressor, LA-2A):
   ___________________

3. Primary Reverb (e.g., Valhalla Room, Seventh Heaven):
   ___________________

4. Primary Saturator (e.g., Decapitator, Satin, Saturn 2):
   ___________________
```

**What happens with answers:**
- Writes to `producer_dna.md` → Anchor Plugins section
- Marks those 4 plugins in studio_inventory.md
- Queues operator card generation for those 4 plugins
- If plugin is in known_plugins.json: full operator card created
- If plugin is auto-detected only: basic card created (type + risk only)

**If skipped:** anchor plugins left blank. AI can still work — asks at first use.

---

## Step 5 — Producer DNA (optional, 2 minutes)

```
Optional: tell us more about you.

Genres you make:
Reference artists:
One word to describe your sound:
```

Writes to `producer_dna.md`. Takes 2 minutes. If skipped, left blank.

---

## Step 6 — Ableton Connection (optional)

```
Connect Ableton Live for real-time control?

Install steps:
1. Copy Ableton_Live_MCP folder to User Library/Remote Scripts/
2. Open Ableton → Preferences → Link/MIDI
3. Set Control Surface 1 = Ableton_Live_MCP
4. Restart Ableton
```

**If skipped:** Conductor works as chat-only knowledge assistant. No DAW control.
**If connected:** full workflow unlocks (MIDI programming, routing, analysis, plugin control).

---

## Step 7 — Done

```
✅ Setup complete.

Your studio: 665 plugins found
Your anchors: Pro-Q 4 | Pro-C 2 | Valhalla Room | Decapitator
Ableton: Connected

Start producing.
```

---

## Day 1 Capabilities (no advanced setup)

| Feature | Works? |
|---|---|
| Chat with AI about production | ✅ |
| Plugin library knowledge | ✅ (from studio_inventory.md) |
| Anchor plugin operator cards | ✅ (from step 4) |
| Never-do rules | ✅ (defaults pre-seeded) |
| Source-of-truth knowledge | ✅ (bundled files) |
| Ableton control | Requires step 6 |
| ChromaDB memory | Works day 1, builds over time |
| NotebookLM deep queries | Requires user to connect their notebook |
| Cross-session memory | Builds from session 2 onward |

---

## Progressive Unlock Path

| When | What unlocks |
|---|---|
| Day 1 — install | Core chat, plugin library, operator cards, never-do rules |
| First Ableton session | Real-time control, analysis, MIDI programming |
| Session 5 | ChromaDB has enough memories to be useful |
| Session 10+ | Memory promotion starts. AI starts making personalised recommendations |
| Optional: NotebookLM connect | Deep technique queries (orchestration, genre, instrument techniques) |
| Optional: Add genre files | Genre-specific EQ targets, arrangement templates |
| Optional: Add reference tracks | Reference Track DNA comparison |

---

_This doc describes the target onboarding. Build status: planned — not yet implemented._
_See BUILD_PHASES.md for implementation order._
