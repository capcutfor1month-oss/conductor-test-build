# Live Harness v1.5 Guide

The Live Harness provides a secure, isolated frontend for testing Conductor's verified `/action/*` backend endpoints. It preserves the Phase 2 GPT Notch premium UI and adds AI Sandbox Mode for realistic natural-language testing.

> **Product Status:** Live Harness v1.5 is a **product-preview shell**, not the final shipped UI. It is useful for development and controlled testing but needs UX re-alignment before friend-test deployment. Safe actions should eventually feel effortless — backend safety stays under the hood, not surfaced as bank-approval UI. Debug/token/endpoint details are developer-only and must not appear in production surfaces.

## How to Run

```bash
cd "/Volumes/T7 Shield/Users/Aditya/Downloads/AI MUSIC PRODUCTION/TEST-BUILD"
./tools/run_harness.sh
```

Then open: `http://localhost:4620/harness.html`

The harness proxy server (`tools/harness_server.py`) serves the UI **and** provides the `/harness/parse_intent` endpoint for AI Sandbox Mode. It requires no pip dependencies (stdlib only).

## Modes

### Live Mode (Default)
- Actions tab buttons fire real POST requests to `http://localhost:4611/action/*`
- Responses reflect real backend verification (ActionProof, readback)
- **This affects Ableton.** Every confirmed action modifies live session state
- Works without an API key

### AI Sandbox Mode
- Switch to "AI Sandbox" in the top-right dropdown
- Type natural language in either the floating chat or the panel chat (e.g., "mute the kick")
- The harness proxy sends your text to a low-cost AI model
- The model returns a **structured proposal** — it never directly touches Ableton
- You see the proposed action, confidence, and model/token info
- Click **"Send to Live Mode"** in the same chat surface to execute the proposed action through the real verified backend
- The floating chat shows a compact proposal card with its own **Send to Live Mode** button; the panel chat shows the full proposal with parameters
- If the model can't map your request, it shows a studio-language clarification
- Sandbox chat history and proposals are browser-only — never written to producer memory

> **UX Note:** AI Sandbox currently works but its product UX needs re-alignment. The interaction model should eventually feel like talking to a co-producer, not submitting API requests.

### Demo / Mock Mode
- UI-only simulation, no backend calls
- Random mock responses after 800ms delay
- Token/cost/model values shown as "not reported" — never faked
- Always labeled `(DEMO)` in timeline entries

## .env Setup (AI Sandbox Only)

Copy `.env.example` to `.env` in the project root:

```bash
cp .env.example .env
```

Fill in your values:

```
HARNESS_AI_PROVIDER=openai_compatible
HARNESS_AI_BASE_URL=https://openprovider.mimika.in/v1
HARNESS_AI_MODEL=openprovider/auto-free
HARNESS_AI_API_KEY=your_key_here
```

Supported providers: `gemini`, `openai`, `openai_compatible`.

### OpenProvider Notes

For OpenProvider, use:

```
HARNESS_AI_PROVIDER=openai_compatible
HARNESS_AI_BASE_URL=https://openprovider.mimika.in/v1
HARNESS_AI_MODEL=atxp/gpt-5.5
HARNESS_AI_API_KEY=your_openprovider_api_key_here
```

`atxp/gpt-5.5` is an exact OpenProvider route. It requires two separate things:

- `HARNESS_AI_API_KEY`: an OpenProvider API key used by this harness.
- `ATXP_CONNECTION`: an ATXP provider connection string used to connect/sync the ATXP provider in OpenProvider. This is not an OpenProvider API key and cannot be used as the chat-completions bearer token.

You may keep `ATXP_CONNECTION=...` in `.env` for config parity, but the harness will not send it to the browser or to OpenProvider. If `ATXP_CONNECTION` is present but `HARNESS_AI_API_KEY` is missing, AI Sandbox fails safely with a clear setup message.

If `atxp/gpt-5.5` returns `invalid model ID`, it usually means the exact route is not available to the OpenProvider API key/account being used by the harness, even if the route appears in `/v1/models`. Re-sync or verify the ATXP provider connection in OpenProvider, then retry. `openprovider/auto-free` remains a useful fallback for confirming the harness path itself.

The harness logs provider failures with sanitized diagnostics only: status code, provider, model, endpoint, request field names, message roles, and a short provider message. It never logs Authorization headers or API keys.

**Security rules:**
- `.env` is git-ignored and never committed
- The API key is read server-side only and never transmitted to the browser
- The key never appears in UI, debug logs, or exported session reports
- If `.env` is missing or the key is empty, AI Sandbox returns a clear error; Live Mode still works

## Sandbox Isolation

Each harness session gets a unique `sandbox_session_id` (generated on page load).

**What sandbox isolates:**
- Chat history (browser-only, cleared on reset)
- AI proposals (browser-only, cleared on reset)
- Timeline entries are tagged with `sandbox=true` and `sandbox_session_id`
- No producer memory writes
- No memory promotion
- No Phase C mutation

**What Reset Sandbox clears:**
- Sandbox chat messages
- Sandbox proposals
- Sandbox timeline UI
- Session stats counters

**What Reset Sandbox does NOT delete:**
- ActionProof logs (`action_proof_log.jsonl`)
- Black box logs (`action_log.jsonl`)
- Backend audit logs
- Previously exported session reports

**Limitation:** The backend does not natively tag actions with `sandbox_session_id`. Sandbox tagging is frontend-only. Backend logs record all actions identically regardless of harness mode.

## The Debug Drawer

Every executed action creates a Timeline entry with a collapsible **Debug Data** drawer.

**Primary UI shows:**
- Studio-language responses ("Confirmed in Ableton.", "It was already set that way.")
- Simple timing ("Verified in 420ms")

**Debug Drawer shows (developer-only):**
- Raw `verification_status`, `error_code`, `proof_id`
- Full observability: endpoint, mode, request timestamps, duration
- Model name, token counts (In/Out/Total), estimated cost — or "not reported"
- Backend timing breakdown (retrieval, execution, verification)
- Sandbox session ID if applicable
- Raw response JSON

> **Developer-only:** All debug drawer contents are developer-only. Token counts, proof IDs, endpoint paths, and raw JSON must never appear in the primary product UI for end users.

## Supported Actions

| Group | Action | Endpoint | Status |
|-------|--------|----------|--------|
| Mix | Set Volume | `/action/track_volume` | ✅ |
| Mix | Pan | `/action/track_pan` | ✅ |
| Mix | Mute | `/action/track_mute` | ✅ |
| Mix | Solo | `/action/track_solo` | ✅ |
| Mix | Route | `/action/track_route` | ✅ |
| Mix | Send | `/action/track_send` | ✅ |
| Track | Create | `/action/track_create` | ✅ |
| Track | Duplicate | `/action/track_duplicate` | ✅ |
| Track | Rename | `/action/track_rename` | ✅ |
| Track | Arm | `/action/track_arm` | ✅ |
| Track | Monitor | `/action/track_monitor` | ✅ |
| Track | Color | `/action/track_color` | ✅ |
| Track | Return Create | `/action/return_track_create` | ✅ |
| Track | Multi Create | `/action/tracks_create_multiple` | ✅ |
| Transport | Play | `/action/transport_play` | ✅ |
| Transport | Stop | `/action/transport_stop` | ✅ |
| Transport | Loop | `/action/transport_loop` | ✅ |
| Transport | Metronome | `/action/transport_metronome` | ✅ |
| Plugin | Bypass | `/action/plugin_bypass` | ✅ |
| Roadmap | Delete Track | `/action/track_delete` | 🔒 Needs confirmation flow |
| Roadmap | Record | `/action/transport_record` | 🔒 Needs confirmation flow |
| Roadmap | Bounce | `/action/export` | 🔒 Not built |
| Roadmap | Plugin Param | `/action/plugin_param` | 🔒 Not built |
| Roadmap | Load Plugin | `/action/plugin_load` | 🔒 Not built |
| Roadmap | Clip Edit | `/action/clip_edit` | 🔒 Not built |

## Updating the ACTION_REGISTRY

As future slices are built and locked:
1. Add the action to `ACTION_REGISTRY` in `app/harness.js`
2. Match endpoint, payload, and method exactly to `conductor_bridge.py`
3. Set `supported: true` only after the backend slice passes tests
4. Update the system prompt in `harness_server.py` to include the new action

**No fake execution rule:** If an endpoint doesn't exist on the bridge, it must stay in Roadmap with `supported: false`.

## Observability Rules

- Frontend timing (`duration_ms`) is measured honestly via `performance.now()`
- Token/cost data is only shown if the API or backend explicitly reports it
- If unavailable: "not reported" — never guessed or faked
- Token/cost details appear only in the Debug Drawer, not primary product UI
- Session reports include full observability data for audit

## Disabled Actions & Confirmation Policy

The following actions are backend-locked but **disabled in the harness** pending proper confirmation UI:

| Action | Reason |
|--------|--------|
| `track_delete` | Destructive — requires confirmation dialog before execution |
| `transport_record` | Session-altering — requires confirmation dialog before execution |

**Routing actions** (`track_route`, `track_send`) are enabled but should be treated carefully — routing changes can require confirmation depending on the target (e.g., master bus routing). Confirmation policy for routing is TBD.

## Re-Alignment Notes

- In the future correction slice, safe actions should **not feel like bank approvals**. The goal is effortless studio interaction with silent backend safety.
- The CoProducer Translation Layer (not yet built) will wrap all ActionProofs, drift errors, and bridge errors in human-readable assistant dialogue before they reach the user.
- Until that layer exists, the harness remains a developer-preview tool.
