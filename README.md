# Conductor
**A personal AI music production assistant and co-producer for Ableton Live.**

Conductor is an AI assistant that lives inside the producer’s workflow. It combines live Ableton session state, trusted production knowledge, structured plugin Operator Cards, feedback/session signals, and verified execution paths so producers can ask musical questions, receive grounded suggestions, and safely turn selected ideas into supported Ableton actions.

## Why It Exists
Music production requires an immense amount of micro-decision making. Conductor exists to bridge the gap between creative intent and technical execution. 

Unlike a generic chatbot, Conductor is designed to operate as a studio assistant. As the system evolves, its goal is to adapt to your unique production style rather than offering one-size-fits-all advice.

## Current Status
Conductor is currently in **active development (Phase D)**. Major backend foundations are locked and tested, including local retrieval (RAG), session-state context, ActionProof/readback for supported Ableton actions, Knowledge Explorer/Critic, feedback logging, promotion candidates, and session reflection. Builds 1–20 are PASS/LOCKED.

The primary interface today is the **AI Sandbox (Live Harness v1.5)**, which provides answers, clarifications, and action proposals, serving as a product-preview shell and a strict developer safety boundary to simulate the AI interaction loop securely before the final product UI is deployed.

## Product Philosophy: Safety is Silent, Assistance is Vocal
Conductor should feel like a creative studio co-producer, not a compliance dashboard. While the backend employs rigorous three-gate validation, drift detection, and ActionProof systems, the user experience should feel effortless and encouraging. Technical guardrails are silent unless they actively prevent a destructive mistake. 

## Architecture Overview
- **Conductor Bridge (`localhost:4611`):** A single HTTP gateway to all tools. The AI never touches Ableton directly; it routes structured intents through this bridge.
- **Session State / Eyes:** Constantly maintains the live context of the Ableton project (BPM, key, track routing, connected plugins).
- **Knowledge Brain (RAG):** Local ChromaDB instance with 5 distinct collections ensuring cross-session memory and accurate retrieval of Operator Cards.
- **Operator Cards:** Structured constraints, risky-move notes, and plugin-specific reasoning guidance for current knowledge use and future deeper integration.
- **ActionProof / Readback:** The safety engine that verifies supported Ableton write actions via an un-bypassable 6-step loop.

## What is Built Today
- **Ableton LOM Control:** Real-time, verified execution of supported track, mix, routing, and transport actions covered by the locked test suites.
- **ActionProof Safety System:** Every supported write action captures a `before_state`, performs the change, reads the `after_state` back to verify, and provides eligible/verified compensating undo capabilities. 
- **Deterministic "Never-Do" Rules:** Hard-blocks actions that violate pre-defined user safety boundaries (e.g., never overwrite the master bus).
- **AI Sandbox Mode:** Natural language parsing into answers, clarifications, and structured Ableton action proposals. It acts as a safety boundary, allowing proposals to be reviewed before execution.

## Partially Built: Feedback & Learning Pipeline
The infrastructure for logging and generating memory-promotion candidates/session reflections is built, but not yet actively injected into the AI's real-time retrieval context.
- **Built:** Ambient Feedback UI, feedback log writing, feedback signal reading, promotion candidate generation, session reflection/summarization, and controlled memory writing for safe session/project-scoped signals through the existing memory-write contract.
- **Next:** Taste-context injection, where repeated or explicit user feedback can influence future retrieval, critic selection, and answer behavior.

Conductor treats feedback as contextual. A single accepted or rejected suggestion does not become universal taste. Signals are first scoped to the session or project, and broader producer-level taste requires repeated evidence or explicit user intent.

## What Is Not Built Yet (Roadmap)
The following features are directional anchors and **do not exist yet**:
- **PluginBridge / Parameter Tweaking:** The ability for Conductor to twist individual dials inside VSTs (e.g., tweaking an EQ band).
- **Auto Execute:** Automatic execution of AI proposals without manual user approval.
- **Full Taste-Context Injection:** Active integration of user taste preferences into the AI's immediate decision-making context.
- **Voice Mode:** Real-time audio voice interaction.
- **Web / Current Info:** Live internet search capabilities.
- **Production Electron App:** A standalone macOS app wrapper with auto-launching background services (the current UI is a developer/product-preview harness, not the final packaged app).

## Setup & Running Tests
See the active harness/build docs for current commands.

## Repo Structure
- `app/` — Developer Preview UI (`harness.html`, `harness.js`).
- `tools/` — HTTP Bridge (`conductor_bridge.py`), Server scripts, and test runners.
- `rag/` — Core AI logic: Retriever, Undo Engine, ActionProof, Token Budgets, Memory Schema.
- `memory/` — Local ChromaDB storage and append-only JSONL logs (actions, feedback).
- `conductor-vault/` — Static knowledge base: Producer DNA rules, failure cases, and Plugin Operator Cards.
- `tests/` — Evaluation suites for RAG accuracy and execution safety.

## Safety & Trust Model
Conductor enforces deterministic safety. 
- **Append-only History:** `action_log.jsonl` is never modified. An undo is recorded as a new compensating action.
- **Three-Gate Undo:** Before reverting an action, Conductor checks: (1) we have the original state, (2) the current state is readable, and (3) no external drift has occurred unless explicitly overridden.
- **No LLM Safety Judgment:** "Never-do" rules (e.g., "Don't touch the master fader") are enforced by deterministic Python-side rule checks, never by asking the AI to behave safely.

## Contribution & Audit Workflow
Conductor employs an iterative AI-audit model.
1. **Builder Phase:** Features and evaluations are written.
2. **Reviewer Phase:** A secondary system audits safety-critical files (`rag/undo_engine.py`, `tools/conductor_bridge.py`, etc.) ensuring no "silent product decisions" or hard-blocks are added unnecessarily.
3. **Lock:** Slices are marked PASS/LOCKED in the active build/handoff docs. No past locked slices may be modified without a full regression audit.
