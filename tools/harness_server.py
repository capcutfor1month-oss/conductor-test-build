#!/usr/bin/env python3
"""Live Harness v1.5 Server — AI intent parser + Knowledge Gateway for Ableton Live."""

import http.server
import json
import os
import sys
import re
import urllib.request
import urllib.error
import urllib.parse

PORT = 4620

# ── Conductor Bridge URL ───────────────────────────────────────────────────────
BRIDGE_URL = "http://localhost:4611"

# ── Knowledge Explorer modes ────────────────────────────────────────────────────
# These modes trigger structured candidate-direction generation.
# READ / CLARIFY / unknown → direct answer path (call_knowledge_answer).
_EXPLORER_MODES = {"MENTOR", "FREEFORM_GENERAL"}

# ── Internal schema marker detection ────────────────────────────────────────────
# Case-insensitive, word-boundary regex — catches markers whether quoted, unquoted,
# YAML-style, mixed-case, or embedded in markdown-fenced blocks.
# Used in call_knowledge_explorer to guard against leaking schema to the user.
_STRUCTURAL_RE = re.compile(
    r"(?i)\b("
    r"candidates|direction|rationale|session_facts_used"
    r"|assumptions|source_hints|actionable|confidence|question_type"
    r")\b"
)

# ── Build 11/12 trust-label leak guard ───────────────────────────────────────────
# Detects internal context-pack and critic-prompt labels that must never appear
# in user-facing composed text.  Used in _compose_final_answer() to fall back to
# the explorer answer if the selected candidate direction/rationale was somehow
# contaminated with these strings.
_TRUST_LABEL_RE = re.compile(
    r"(?i)("
    r"KNOWLEDGE\s+STATUS"
    r"|Plugin\s+Knowledge\s+Context"
    r"|Operator\s+card:\s+not\s+available"
    r"|knowledge_evidence"
    r"|confidence\s*<="
    r"|confidence\s*≤"  # ≤ (unicode less-than-or-equal)
    r")"
)

# ── Action-mapping system prompt (parse_intent only) ──────────────────────────
SYSTEM_PROMPT = """You are Conductor, an AI music production assistant for Ableton Live.
The user will give you a natural language instruction about their Ableton session.
You must map their intent to EXACTLY ONE of the following action IDs.
If the intent doesn't match any action, return action_id: "unmapped".
If you need more information, return needs_confirmation: true with a clarification string.

Available actions:
- vol: Set track volume (params: track, volume 0.0-1.0)
- pan: Set track pan (params: track, pan 0.0-1.0 where 0.5=center)
- mute: Mute/unmute track (params: track, mute bool)
- solo: Solo/unsolo track (params: track, solo bool)
- create_track: Create track (params: name, type "midi"|"audio")
- dup_track: Duplicate track (params: track)
- ren_track: Rename track (params: track, new_name)
- arm_track: Arm track (params: track, arm bool)
- monitor_track: Set monitor mode (params: track, mode 0|1|2 where 0=In,1=Auto,2=Off)
- color_track: Set track color (params: track, color int 0-69)
- ret_track: Create return track (params: none)
- multi_track: Create multiple tracks (params: count int, type "midi"|"audio")
- route_track: Route track output (params: track, routing string, confirm true)
- send_track: Set send level (params: track, send int, value 0.0-1.0)
- play: Play transport (params: none)
- stop: Stop transport (params: none)
- loop: Toggle loop (params: loop bool)
- metronome: Toggle metronome (params: metronome bool)
- bypass: Bypass plugin (params: track, device_name, bypass bool)

Disabled actions (tell user these are not available yet):
- del_track, record, export, plugin_tweak, plugin_load, clip_action

Respond ONLY with valid JSON in this exact format, no markdown:
{
  "ok": true,
  "action_id": "mute",
  "params": {"track": "Kick", "mute": true},
  "confidence": 0.95,
  "needs_confirmation": false,
  "clarification": null,
  "reason": "Muting the Kick track as requested."
}

If you cannot map the intent:
{
  "ok": false,
  "action_id": "unmapped",
  "params": {},
  "confidence": 0.0,
  "needs_confirmation": false,
  "clarification": null,
  "reason": "I don't have a way to do that yet."
}"""


# ── Bridge helpers ─────────────────────────────────────────────────────────────

def _call_bridge_get(path, timeout=5.0):
    """
    GET request to conductor bridge (localhost:4611).
    Returns (data_dict, None) on success, (None, error_str) on any failure.
    Never raises — callers treat failure as unavailable context.
    """
    try:
        url = BRIDGE_URL + path
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read()), None
    except Exception as exc:
        return None, str(exc)


def _format_session_state(state):
    """
    Format a /session/state response dict into a compact context block.
    Returns "" if state is None, not ok, or carries no useful data.
    """
    if not state or not state.get("ok"):
        return ""
    lines = ["## LIVE ABLETON SESSION"]
    tempo = state.get("tempo")
    if tempo is not None:
        ts = state.get("time_signature", "")
        lines.append(
            f"Tempo: {tempo} BPM" + (f"  Time sig: {ts}" if ts else "")
        )
    playing = state.get("playing")
    if playing is not None:
        lines.append("Playing: " + ("yes" if playing else "no"))
    selected = state.get("selected_track")
    if selected:
        lines.append(f"Selected track: {selected}")
    tracks = state.get("tracks", [])
    if tracks:
        names = [t["name"] for t in tracks if t.get("name")]
        muted  = [t["name"] for t in tracks if t.get("muted")]
        soloed = [t["name"] for t in tracks if t.get("soloed")]
        armed  = [t["name"] for t in tracks if t.get("arm")]
        suffix = " …" if len(names) > 12 else ""
        lines.append(f"Tracks ({len(names)}): {', '.join(names[:12])}{suffix}")
        if muted:  lines.append(f"Muted:  {', '.join(muted)}")
        if soloed: lines.append(f"Soloed: {', '.join(soloed)}")
        if armed:  lines.append(f"Armed:  {', '.join(armed)}")
    returns = state.get("return_tracks", [])
    if returns:
        lines.append(f"Returns: {', '.join(r['name'] for r in returns if r.get('name'))}")
    return "\n".join(lines) if len(lines) > 1 else ""


def _extract_operator_card_context(message_pack_text, max_chars=3000):
    """
    Extract the existing Operator Card block from /context/pack text.

    Build 8 does not add new card routing or RAG. It only forwards the card
    snippet that already reached Knowledge Explorer into Creative Critic.
    """
    if not message_pack_text:
        return ""

    lines = str(message_pack_text).splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("## OPERATOR CARD"):
            block = [line]
            for follow in lines[i + 1:]:
                # Stop at ANY next top-level markdown section (including adjacent cards).
                if follow.startswith("## "):
                    break
                block.append(follow)
            card = "\n".join(block).strip()
            return card[:max_chars]

    return ""


def _extract_knowledge_status_context(message_pack_text, max_chars=600):
    """
    Extract the ## KNOWLEDGE STATUS block from /context/pack text.

    Build 12: passes the knowledge gap signal directly into Creative Critic so
    the knowledge_evidence criterion is grounded in actual context, not only
    whatever Explorer chose to carry into candidate assumptions.
    Returns "" when no KNOWLEDGE STATUS block is present (verified card or
    no plugin recognized — both mean the Critic needs no gap signal).
    """
    if not message_pack_text:
        return ""

    lines = str(message_pack_text).splitlines()
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("## KNOWLEDGE STATUS"):
            block = [line]
            for follow in lines[i + 1:]:
                # Stop at the next top-level markdown section.
                if follow.startswith("## "):
                    break
                block.append(follow)
            status = "\n".join(block).strip()
            return status[:max_chars]

    return ""


def _load_system_prompt(project_root):
    """Load app/system_prompt.md (Conductor identity + context rules). Returns '' on failure."""
    path = os.path.join(project_root, "app", "system_prompt.md")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


# ── LLM helpers ───────────────────────────────────────────────────────────────

def sanitize_provider_error(raw):
    """Return a short provider error summary without credentials or headers."""
    if not raw:
        return "Provider returned an empty error body."
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:300]

    error = payload.get("error", payload)
    if isinstance(error, dict):
        message = error.get("message") or error.get("error") or error.get("type")
    else:
        message = str(error)
    return str(message or "Provider returned an error.").replace("\n", " ")[:300]


def log_provider_http_error(e, *, provider, model, base_url, request_body, safe_message):
    """Log provider diagnostics without Authorization headers or API keys."""
    endpoint = f"{base_url.rstrip('/')}/chat/completions" if base_url else "not configured"
    request_summary = {
        "model": model,
        "endpoint": endpoint,
        "request_keys": sorted(request_body.keys()),
        "message_roles": [m.get("role") for m in request_body.get("messages", [])],
        "has_response_format": "response_format" in request_body,
        "temperature": request_body.get("temperature"),
    }
    print(
        "[Harness] LLM provider error "
        + json.dumps(
            {
                "status": e.code,
                "provider": provider,
                "request": request_summary,
                "provider_message": safe_message,
            },
            ensure_ascii=True,
        ),
        file=sys.stderr,
    )


def load_env(path):
    """Parse a .env file manually. No python-dotenv."""
    env = {}
    if not os.path.isfile(path):
        return env
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, sep, value = line.partition("=")
            if not sep:
                continue
            key = key.strip()
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            env[key] = value
    return env


def call_gemini(text, model, api_key):
    """Call Gemini for action-ID JSON mapping (parse_intent / orchestrate WRITE path)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    body = {
        "contents": [
            {"role": "user", "parts": [{"text": SYSTEM_PROMPT + "\n\nUser: " + text}]}
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0.1,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())

    llm_text = data["candidates"][0]["content"]["parts"][0]["text"]
    parsed = json.loads(llm_text)

    usage = data.get("usageMetadata", {})
    tokens = {
        "input": usage.get("promptTokenCount", 0),
        "output": usage.get("candidatesTokenCount", 0),
        "total": usage.get("totalTokenCount", 0),
    }
    return parsed, tokens


def call_openai(
    text,
    model,
    api_key,
    base_url="https://api.openai.com/v1",
    include_response_format=True,
):
    """Call OpenAI-compatible API for action-ID JSON mapping (parse_intent / orchestrate WRITE path)."""
    url = f"{base_url.rstrip('/')}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        "temperature": 0.1,
    }
    if include_response_format:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        safe_message = sanitize_provider_error(raw)
        log_provider_http_error(
            e,
            provider="openai_compatible"
            if not include_response_format
            else "openai",
            model=model,
            base_url=base_url,
            request_body=body,
            safe_message=safe_message,
        )
        e.safe_message = safe_message
        raise

    llm_text = data["choices"][0]["message"]["content"]
    parsed = json.loads(llm_text)

    usage = data.get("usage", {})
    tokens = {
        "input": usage.get("prompt_tokens", 0),
        "output": usage.get("completion_tokens", 0),
        "total": usage.get("total_tokens", 0),
    }
    return parsed, tokens


def call_knowledge_answer(enriched_text, system_prompt_str, provider, model, api_key, base_url=None):
    """
    Call LLM for a natural-language knowledge / mentor answer.

    Unlike call_gemini / call_openai this does NOT force a JSON response.
    It uses the Conductor system_prompt.md as the system context and sends
    the enriched user message (session pack + memory + live state + user text).

    Returns (answer_text: str, tokens: dict).
    Raises urllib.error.HTTPError / URLError on network failure.
    """
    if provider == "gemini":
        # Gemini v1beta: single-turn, combine system + user content
        full = (system_prompt_str + "\n\n" + enriched_text) if system_prompt_str else enriched_text
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "contents": [
                {"role": "user", "parts": [{"text": full}]}
            ],
            "generationConfig": {"temperature": 0.6},
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
        answer = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        tokens = {
            "input":  usage.get("promptTokenCount", 0),
            "output": usage.get("candidatesTokenCount", 0),
            "total":  usage.get("totalTokenCount", 0),
        }
        return answer.strip(), tokens

    else:  # openai / openai_compatible
        resolved_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{resolved_base}/chat/completions"
        sys_content = system_prompt_str or "You are Conductor, an AI music production assistant."
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": sys_content},
                {"role": "user",   "content": enriched_text},
            ],
            "temperature": 0.6,
            # No response_format — free-text answer, not action-ID JSON
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            safe_message = sanitize_provider_error(raw)
            log_provider_http_error(
                e,
                provider=provider,
                model=model,
                base_url=resolved_base,
                request_body=body,
                safe_message=safe_message,
            )
            e.safe_message = safe_message
            raise
        answer = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = {
            "input":  usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
            "total":  usage.get("total_tokens", 0),
        }
        return answer.strip(), tokens


# ── Knowledge Explorer ────────────────────────────────────────────────────────

_EXPLORER_JSON_SCHEMA = """\
Respond ONLY with valid JSON — no markdown fences, no preamble:
{
  "answer": "Your direct, natural response to the producer. Do NOT number the candidates or expose the internal list. Sound like a knowledgeable collaborator.",
  "question_type": "creative|session|factual",
  "candidates": [
    {
      "direction": "Brief label for this approach (5-10 words)",
      "rationale": "Why this approach fits the available context",
      "session_facts_used": ["specific track name, tempo, device, or state you actually saw in the context"],
      "assumptions": ["what you assumed because session data was missing or unclear"],
      "source_hints": ["production concept, technique, or tool relevant here"],
      "actionable": true,
      "confidence": 0.85
    }
  ]
}"""


def _build_explorer_instructions(session_available):
    """
    Build the Knowledge Explorer instruction block injected into the LLM system context.
    session_available: True when /session/state returned ok=True.
    """
    session_note = (
        "Live session context IS available — use specific session facts "
        "(track names, tempo, selected track, devices) in candidates."
        if session_available
        else "No live session data available — note what you cannot see in "
             "assumptions. Do NOT invent session facts."
    )
    return (
        "## Knowledge Explorer Mode\n"
        "The producer asked a question. Your task:\n"
        "1. Explore 2–3 candidate musical directions or approaches internally.\n"
        "2. Synthesize the best approach into a single natural, concise answer.\n\n"
        f"Session availability: {session_note}\n\n"
        "Rules:\n"
        "- Generate 2–3 candidates for creative or session-aware questions; "
        "1 candidate is sufficient for direct factual questions.\n"
        "- session_facts_used: only list things visible in the context above. "
        "Empty array if nothing relevant.\n"
        "- assumptions: be explicit. The producer needs to know what you guessed.\n"
        "- actionable: true if the producer can take an immediate concrete step.\n"
        "- confidence: 0.0–1.0 based on how well available context supports this direction.\n"
        "- knowledge_gap: if the context includes '## KNOWLEDGE STATUS' with "
        "'Operator card: not available', populate assumptions with the knowledge "
        "gap for every candidate that makes plugin-specific claims, and set "
        "confidence ≤ 0.5 for those candidates.\n"
        "- The answer field synthesises the best direction naturally. "
        "Do not expose or number the candidate list.\n\n"
        + _EXPLORER_JSON_SCHEMA
    )


def call_knowledge_explorer(
    enriched_text,
    session_available,
    system_prompt_str,
    provider,
    model,
    api_key,
    base_url=None,
):
    """
    Knowledge Explorer: single LLM call that generates 2–3 internal candidate directions
    AND a natural user-facing answer in one structured JSON response.

    Returns (answer_text: str, explorer_data: dict, tokens: dict).
      answer_text  — the natural user-facing answer (what gets shown in chat)
      explorer_data — {"question_type": ..., "candidates": [...]} (internal only)
      tokens       — {"input": N, "output": N, "total": N}

    Falls back to (raw_text, {}, tokens) if JSON parsing fails, so the caller
    always gets a usable answer even on a malformed LLM response.
    Raises urllib.error.HTTPError / URLError on network failure.
    """
    explorer_block = _build_explorer_instructions(session_available)
    full_system = (
        (system_prompt_str + "\n\n" + explorer_block).strip()
        if system_prompt_str
        else explorer_block
    )

    if provider == "gemini":
        full_prompt = full_system + "\n\n" + enriched_text
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": full_prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.6,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = json.loads(resp.read())
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        tokens = {
            "input":  usage.get("promptTokenCount", 0),
            "output": usage.get("candidatesTokenCount", 0),
            "total":  usage.get("totalTokenCount", 0),
        }

    else:  # openai / openai_compatible
        resolved_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{resolved_base}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {"role": "system", "content": full_system},
                {"role": "user",   "content": enriched_text},
            ],
            "temperature": 0.6,
        }
        if provider == "openai":
            body["response_format"] = {"type": "json_object"}
        # openai_compatible: skip response_format (not universally supported)
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            safe_message = sanitize_provider_error(raw)
            log_provider_http_error(
                e,
                provider=provider,
                model=model,
                base_url=resolved_base,
                request_body=body,
                safe_message=safe_message,
            )
            e.safe_message = safe_message
            raise
        raw_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = {
            "input":  usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
            "total":  usage.get("total_tokens", 0),
        }

    # Parse structured JSON response
    try:
        parsed = json.loads(raw_text)
        raw_answer = (parsed.get("answer") or "").strip()
        # If "answer" is absent or empty, do NOT fall back to raw_text —
        # that would expose the full JSON / internal candidate structure.
        answer_text = (
            raw_answer
            if raw_answer
            else "Couldn't form a clear answer — try rephrasing your question."
        )
        explorer_data = {
            "question_type": parsed.get("question_type", "unknown"),
            "candidates":    parsed.get("candidates", []),
        }
    except (json.JSONDecodeError, TypeError):
        # JSON parse failed (malformed / truncated response).
        # Check whether raw_text contains internal schema markers —
        # if so, returning it verbatim would expose candidate structure to the user.
        # Detection uses case-insensitive word-boundary regex (_STRUCTURAL_RE) so it
        # catches quoted, unquoted, YAML-style, mixed-case, and markdown-fenced output.
        raw_stripped = (raw_text or "").strip()
        _looks_structural = (
            raw_stripped.startswith("{")
            or raw_stripped.startswith("```")
            or bool(_STRUCTURAL_RE.search(raw_stripped))
        )
        answer_text = (
            "Couldn't parse the response — try rephrasing your question."
            if _looks_structural
            else (raw_stripped or "Couldn't get an answer — try rephrasing.")
        )
        explorer_data = {}

    return answer_text, explorer_data, tokens


# ── Creative Critic ────────────────────────────────────────────────────────────

_CRITIC_JSON_SCHEMA = """\
Respond ONLY with valid JSON — no markdown fences, no preamble:
{
  "selected": 0,
  "kept": [0],
  "rejected": [1],
  "reasons": {
    "1": "generic — does not use session facts, applies to any session"
  },
  "critic_summary": "Direction 0 selected — grounded in Lead Vocals context"
}"""


def _build_critic_prompt(candidates, question_text, session_context, card_context="",
                         knowledge_status_context=""):
    """
    Build the compact critic evaluation prompt.
    candidates: list of candidate dicts from the Explorer.
    session_context: formatted session state block or "".
    card_context: optional Operator Card snippet already present in /context/pack.
    knowledge_status_context: optional ## KNOWLEDGE STATUS block from /context/pack
        (Build 12). When present, tells Critic the plugin is recognized but has no
        Operator Card — grounds the knowledge_evidence criterion in actual context.
        Internal only; never surfaced in user-facing output.
    """
    parts = [
        "## Creative Critic",
        "You are a quality filter for music production advice.",
        "Evaluate the candidate directions below and select the best one.",
        "",
        f"Producer question: {question_text}",
    ]
    if session_context:
        parts += ["", session_context]
    if card_context:
        parts += [
            "",
            "## Operator Card Context",
            "Use this as hard plugin/tool context. Penalize or reject candidates that violate Operator Card Never Do rules, Risky Writes guidance, plugin identity, or supported controls. Do not quote this block in the user-facing answer.",
            card_context.strip(),
        ]
    if knowledge_status_context:
        parts += [
            "",
            "## Plugin Knowledge Context",
            "The plugin below was recognized in the producer's message but no Operator Card exists for it.",
            "Apply the knowledge_evidence criterion:",
            "- Penalize candidates that make confident plugin-specific parameter or workflow claims without acknowledging the knowledge gap.",
            "- Reward candidates that note the gap and frame plugin-specific guidance as general principles.",
            "- Do not surface this block in the user-facing answer.",
            knowledge_status_context.strip(),
        ]
    parts += ["", "Candidates:"]
    for i, c in enumerate(candidates):
        parts.append(f"\n[{i}] direction: {c.get('direction', '')}")
        parts.append(f"    rationale: {c.get('rationale', '')}")
        facts = c.get("session_facts_used") or []
        parts.append(f"    session_facts_used: {facts!r}")
        assumptions = c.get("assumptions") or []
        parts.append(f"    assumptions: {assumptions!r}")
    parts += [
        "",
        "Evaluation criteria (apply to each candidate):",
        "  genericity            — specific to this session vs applies to any session",
        "  session_grounding     — uses actual visible session facts (track names, tempo)",
        "  session_contradiction — contradicts facts visible in the session",
        "  goal_fit              — actually answers the producer's question",
        "  practicality          — producer can act on this immediately",
        "  unsupported_assumptions — assumes things not present in context",
        "  operator_card_compliance — respects Operator Card Never Do, Risky Writes, plugin identity, and supported controls",
        "  knowledge_evidence    — penalize candidates making specific plugin-parameter "
        "or plugin-workflow claims when '## KNOWLEDGE STATUS' says no Operator Card is "
        "available; reward candidates that acknowledge the knowledge gap explicitly.",
        "",
        "Select the highest-scoring candidate as 'selected' (index into the list above).",
        "Set 'kept' to indices that score well; 'rejected' to generic/contradicted/impractical ones.",
        "Give a short reason string for each rejected index.",
        "Write a one-line 'critic_summary' naming the selected direction.",
        "",
        _CRITIC_JSON_SCHEMA,
    ]
    return "\n".join(parts)


def call_creative_critic(
    candidates,
    question_text,
    session_context,
    provider,
    model,
    api_key,
    base_url=None,
    card_context="",
    knowledge_status_context="",
):
    """
    Creative Critic v1: single LLM call that evaluates Explorer candidates and
    selects the best one using structured quality criteria.

    Criteria evaluated per candidate:
      genericity, session_grounding, session_contradiction,
      goal_fit, practicality, unsupported_assumptions,
      operator_card_compliance, knowledge_evidence

    Returns (critic_data: dict, tokens: dict).
      critic_data — {"selected": int, "kept": [...], "rejected": [...],
                     "reasons": {...}, "critic_summary": str}
                    Empty dict {} on JSON parse failure or invalid selection index
                    (caller falls back to explorer answer — never causes a 500).
      tokens      — {"input": N, "output": N, "total": N}

    Raises urllib.error.HTTPError / URLError on network failure.
    Caller must catch all exceptions and fall back to explorer answer gracefully.
    """
    if not candidates:
        return {}, {"input": 0, "output": 0, "total": 0}

    prompt = _build_critic_prompt(
        candidates, question_text, session_context, card_context,
        knowledge_status_context=knowledge_status_context,
    )

    if provider == "gemini":
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "response_mime_type": "application/json",
                "temperature": 0.2,
            },
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        usage = data.get("usageMetadata", {})
        tokens = {
            "input":  usage.get("promptTokenCount", 0),
            "output": usage.get("candidatesTokenCount", 0),
            "total":  usage.get("totalTokenCount", 0),
        }

    else:  # openai / openai_compatible
        resolved_base = (base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{resolved_base}/chat/completions"
        body = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a music production quality critic. "
                        "Respond only with valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
        }
        if provider == "openai":
            body["response_format"] = {"type": "json_object"}
        # openai_compatible: skip response_format (not universally supported)
        req = urllib.request.Request(
            url,
            data=json.dumps(body).encode(),
            headers={
                "Content-Type":  "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", "replace")
            safe_message = sanitize_provider_error(raw)
            log_provider_http_error(
                e,
                provider=provider,
                model=model,
                base_url=resolved_base,
                request_body=body,
                safe_message=safe_message,
            )
            e.safe_message = safe_message
            raise
        raw_text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        tokens = {
            "input":  usage.get("prompt_tokens", 0),
            "output": usage.get("completion_tokens", 0),
            "total":  usage.get("total_tokens", 0),
        }

    # Parse and validate critic JSON response
    try:
        parsed = json.loads(raw_text)
        selected = parsed.get("selected")
        # selected must be a valid index into the candidates list
        if not isinstance(selected, int) or selected < 0 or selected >= len(candidates):
            return {}, tokens
        critic_data = {
            "selected":       selected,
            "kept":           parsed.get("kept", [selected]),
            "rejected":       parsed.get("rejected", []),
            "reasons":        parsed.get("reasons", {}),
            "critic_summary": (parsed.get("critic_summary") or "").strip(),
        }
        return critic_data, tokens
    except (json.JSONDecodeError, TypeError):
        return {}, tokens


# ── Build 14: CLARIFY composer ────────────────────────────────────────────────

# Internal category/label names that must never leak into a composed clarify question.
_CLARIFY_LABEL_RE = re.compile(
    r"\b("
    r"clarify|clarify_required"
    r"|unclear_target|unclear_scope|too_short|unsupported_manual_gui"
    r"|risk_category|protection_level|block_unsupported"
    r")\b"
    r"|(mode:|risk:|protection:)",
    re.IGNORECASE,
)

# Action verbs used to extract intent from ambiguous pronoun messages.
_CLARIFY_VERB_RE = re.compile(
    r"\b(lower|raise|boost|cut|compress|route|pan|mute|solo|arm|"
    r"filter|eq|bypass|enable|disable|rename|color|duplicate|"
    r"create|load|send|add|remove|set|adjust|apply|change)\b",
    re.IGNORECASE,
)


def _clarify_safe(question):
    """
    Build 14: final safety guard for a composed clarify question.
    Returns the question if it is clean and ends with '?'; otherwise ''.
    """
    if not question or not question.strip().endswith("?"):
        return ""
    if (
        _CLARIFY_LABEL_RE.search(question)
        or _STRUCTURAL_RE.search(question)
        or _TRUST_LABEL_RE.search(question)
    ):
        return ""
    return question


def _compose_clarify_question(original_text, risk_reason, risk_category):
    """
    Build 14: deterministic clarify question composer. No LLM call.

    Returns a single natural studio-style question ending with '?' when the
    ambiguity category is recognised. Returns '' to signal that the caller
    should fall back to call_knowledge_answer().

    Template map:
      unclear_target / any 'unclear' category  →  "Which track or plugin should I {verb}?"
      too_short                                →  "What would you like to do — could you say a bit more?"
      *_unclear_scope                          →  "Which track, bus, or plugin are you working on?"
      generic fallback (safe risk_reason)      →  "Could you clarify — {cleaned reason}?"
      unsupported / block / unknown            →  '' (fall back to LLM)

    Never exposes internal labels (Mode:, Risk:, CLARIFY, protection levels, etc.).
    """
    cat = (risk_category or "").lower().strip()

    # ── Pronouns / unclear target ─────────────────────────────────────────────
    # e.g. "Lower it", "Compress it", "Pan it right" — no referent in message.
    if "unclear" in cat:
        m = _CLARIFY_VERB_RE.search(original_text or "")
        question = (
            f"Which track or plugin should I {m.group(1).lower()}?"
            if m else
            "Which track or plugin are you referring to?"
        )
        return _clarify_safe(question)

    # ── Too short ─────────────────────────────────────────────────────────────
    if cat == "too_short":
        return "What would you like to do — could you say a bit more?"

    # ── Unclear scope (routing_unclear_scope, effect_unclear_scope, …) ────────
    if "scope" in cat:
        return "Which track, bus, or plugin are you working on?"

    # ── Generic fallback: derive a question from risk_reason if safe ──────────
    reason = (risk_reason or "").strip()
    if reason:
        # Strip internal instruction phrasing injected by protection_model.
        reason = re.sub(
            r"(?i)ask\s+(exactly\s+)?one\s+clarifying\s+question[^.]*\.",
            "", reason,
        ).strip()
        reason = re.sub(
            r"(?i)\bbefore\s+(any\s+action|proceeding)\.?", "", reason,
        ).strip()
        reason = reason.rstrip(".,:; ")
        if reason and not _CLARIFY_LABEL_RE.search(reason) and len(reason) < 120:
            q = f"Could you clarify — {reason[0].lower()}{reason[1:]}?"
            return _clarify_safe(q)

    # No safe template matched — return '' so caller falls back to LLM path.
    return ""


# ── Critic answer composer helpers ────────────────────────────────────────────

def _safe_session_facts(facts):
    """
    Filter session_facts_used to strings safe for user-facing output.

    Strips the 'Selected track:' prefix produced by _format_session_state().
    Drops:
      - internal schema markers (_STRUCTURAL_RE matches)
      - trust labels (_TRUST_LABEL_RE matches)
      - Operator Card references (internal plugin doc labels)
      - markdown headers (start with '#')
      - snake_case internal key names (session_facts_used, knowledge_evidence, …)
      - JSON-looking facts (start with '{' or '[')
      - internal metadata key:value pairs (mode:, risk:, score:, selected:, kept:, rejected:)
      - ID references (proof id, request id, action id — space form;
        underscore forms already caught by snake_case check)
      - entries over 60 characters

    Build 13: used by _compose_final_answer() for light session-fact weaving.
    """
    safe = []
    for f in (facts or []):
        f = str(f).strip()
        # Strip "Selected track:" prefix injected by _format_session_state()
        if re.match(r'(?i)selected\s+track:\s*', f):
            f = re.sub(r'(?i)selected\s+track:\s*', '', f).strip()
        if not f or len(f) > 60:
            continue
        # Skip markdown headers
        if f.startswith('#'):
            continue
        # Skip JSON-looking facts
        if f.startswith('{') or f.startswith('['):
            continue
        # Skip internal schema markers and trust labels
        if _STRUCTURAL_RE.search(f) or _TRUST_LABEL_RE.search(f):
            continue
        # Skip Operator Card references (internal plugin documentation labels)
        if re.search(r'(?i)\bOperator\s+Card\b', f):
            continue
        # Skip snake_case internal key names (session_facts_used, source_hints, …)
        if re.search(r'\b\w+_\w+\b', f):
            continue
        # Skip internal metadata key:value pairs
        if re.match(r'(?i)(mode|risk|score[s]?|selected|kept|rejected)\s*:', f):
            continue
        # Skip ID references (space-separated form; underscore form caught above)
        if re.search(r'(?i)\b(proof|request|action)\s+id\b', f):
            continue
        safe.append(f)
    return safe


# ── Critic answer composer ─────────────────────────────────────────────────────

def _compose_final_answer(explorer_answer, explorer_data, critic_data):
    """
    Deterministic composer: derive the final user-facing answer from the
    Critic-selected candidate. No LLM call.

    Build 13: improved prose joining and light session_facts_used weaving.
    - Short direction labels (≤ 8 words) + rationale → em-dash connector for
      natural one-sentence flow instead of two separate statements.
    - Longer directions (already sentence-length) keep the period separator.
    - Safe, novel session_facts_used entries are appended as a parenthetical
      grounding note (at most 2, only when not already present in the text).
    - All safety guards (_STRUCTURAL_RE, _TRUST_LABEL_RE) unchanged.

    If Critic selected a valid candidate index → compose from that candidate's
    direction, rationale, and session_facts_used.
    If Critic is empty, malformed, or the selected index is out of range →
    fall back to explorer_answer unchanged.
    """
    if not critic_data:
        return explorer_answer

    selected_idx = critic_data.get("selected")
    candidates   = explorer_data.get("candidates", [])

    if (
        not isinstance(selected_idx, int)
        or selected_idx < 0
        or selected_idx >= len(candidates)
    ):
        return explorer_answer

    selected  = candidates[selected_idx]
    direction = (selected.get("direction") or "").strip()
    rationale = (selected.get("rationale") or "").strip()

    if not direction:
        return explorer_answer

    # Build 13: natural prose joining.
    # Strip trailing punctuation so connectors land cleanly regardless of
    # how the LLM ended each field.
    dir_clean = direction.rstrip(". ")
    rat_clean = rationale.rstrip(". ") if rationale else ""

    if rat_clean:
        # Short direction labels read better with an em-dash connector —
        # they merge into one flowing sentence instead of two blunt fragments.
        # Longer directions are already sentence-length; keep the period.
        if len(dir_clean.split()) <= 8:
            composed = f"{dir_clean} — {rat_clean}."
        else:
            composed = f"{dir_clean}. {rat_clean}."
    else:
        composed = f"{dir_clean}."

    # Build 13: light session_facts_used weaving.
    # Only inject facts that are safe and not already present in the text.
    # Formatted as a parenthetical grounding note at the end.
    facts       = selected.get("session_facts_used") or []
    safe_facts  = _safe_session_facts(facts)
    novel_facts = [f for f in safe_facts if f.lower() not in composed.lower()]
    if novel_facts:
        fact_str = ", ".join(novel_facts[:2])
        composed = f"{composed.rstrip('.')} ({fact_str})."

    # Safety guard: never expose internal schema markers in the composed answer.
    if _STRUCTURAL_RE.search(composed) or composed.strip().startswith("{"):
        return explorer_answer

    # Build 11/12 trust-label guard: never expose context-pack or critic-prompt
    # internal labels that an LLM might echo into candidate direction/rationale.
    if _TRUST_LABEL_RE.search(composed):
        return explorer_answer

    return composed


# ── HTTP handler ──────────────────────────────────────────────────────────────

class HarnessHandler(http.server.SimpleHTTPRequestHandler):
    provider = None
    model = None
    api_key = None
    base_url = None
    atxp_connection_present = False
    app_dir = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=self.app_dir, **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_POST(self):
        _VALID_PATHS = {"/harness/parse_intent", "/harness/orchestrate"}
        if self.path not in _VALID_PATHS:
            self.send_json(404, {"ok": False, "error": "Not found"})
            return

        if not self.api_key:
            if self.provider == "openai_compatible" and self.atxp_connection_present:
                self.send_json(
                    503,
                    {
                        "ok": False,
                        "error": "AI Sandbox needs HARNESS_AI_API_KEY. ATXP_CONNECTION is a provider connection string, not an OpenProvider API key.",
                    },
                )
                return
            self.send_json(
                503,
                {
                    "ok": False,
                    "error": "AI Sandbox requires .env configuration. See .env.example",
                },
            )
            return

        if self.provider == "openai_compatible" and not self.base_url:
            self.send_json(
                503,
                {
                    "ok": False,
                    "error": "AI Sandbox requires HARNESS_AI_BASE_URL for openai_compatible provider. See .env.example",
                },
            )
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length)
            body = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            self.send_json(400, {"ok": False, "error": "Invalid JSON body"})
            return

        text = body.get("text", "").strip()
        if not text:
            self.send_json(400, {"ok": False, "error": "Missing 'text' field"})
            return

        if self.path == "/harness/parse_intent":
            self._handle_parse_intent(text)
        else:
            self._handle_orchestrate(text)

    # ── POST /harness/parse_intent ─────────────────────────────────────────────
    # Action-ID mapping — unchanged from v1. No context pack, no session state.

    def _handle_parse_intent(self, text):
        try:
            if self.provider == "openai_compatible":
                parsed, tokens = call_openai(
                    text, self.model, self.api_key, self.base_url,
                    include_response_format=False,
                )
            elif self.provider == "openai":
                parsed, tokens = call_openai(
                    text, self.model, self.api_key,
                    "https://api.openai.com/v1",
                    include_response_format=True,
                )
            else:
                parsed, tokens = call_gemini(text, self.model, self.api_key)
        except urllib.error.HTTPError as e:
            safe_message = getattr(e, "safe_message", "Provider rejected the request.")
            self.send_json(
                502,
                {
                    "ok": False,
                    "error": f"LLM API error {e.code}: {safe_message}",
                },
            )
            return
        except urllib.error.URLError as e:
            self.send_json(
                502, {"ok": False, "error": f"Network error: {e.reason}"}
            )
            return
        except (json.JSONDecodeError, KeyError, IndexError) as e:
            self.send_json(
                502, {"ok": False, "error": f"Failed to parse LLM response: {e}"}
            )
            return
        except Exception as e:
            self.send_json(502, {"ok": False, "error": str(e)})
            return

        result = {
            "ok": parsed.get("ok", False),
            "action_id": parsed.get("action_id", "unmapped"),
            "params": parsed.get("params", {}),
            "confidence": parsed.get("confidence", 0.0),
            "needs_confirmation": parsed.get("needs_confirmation", False),
            "clarification": parsed.get("clarification", None),
            "reason": parsed.get("reason", ""),
            "model": self.model,
            "provider": self.provider,
            "tokens": tokens,
        }
        self.send_json(200, result)

    # ── POST /harness/orchestrate ──────────────────────────────────────────────
    # Knowledge Gateway v1:
    #   WRITE modes  → action-ID mapping (same as parse_intent) + type:"action"
    #   All other modes → context-enriched knowledge answer + type:"answer"

    def _handle_orchestrate(self, text):
        # ── Step 1: context pack (classify + ChromaDB + operator card) ───────────
        pack_data, _pack_err = _call_bridge_get(
            "/context/pack?q=" + urllib.parse.quote(text, safe=""),
            timeout=6.0,
        )
        mode              = (pack_data.get("mode") or "MENTOR") if pack_data else "MENTOR"
        message_pack_text = (pack_data.get("pack")  or "")      if pack_data else ""
        # Build 14: extract risk fields used by the CLARIFY composer.
        risk_reason   = (pack_data.get("risk_reason")   or "") if pack_data else ""
        risk_category = (pack_data.get("risk_category") or "") if pack_data else ""

        # ── Step 2: session pack (DNA + project state + tool health) ────────────
        session_data, _session_err = _call_bridge_get("/context/session", timeout=4.0)
        session_pack_text = (session_data.get("pack") or "") if session_data else ""

        # ── Step 3: live session state — best-effort, short timeout ─────────────
        state_data, _state_err = _call_bridge_get("/session/state", timeout=2.0)
        session_state_block = _format_session_state(state_data)

        # ── Step 4: route by mode ────────────────────────────────────────────────
        _WRITE_MODES = {"INTERN_WRITE_SAFE", "INTERN_WRITE_RISKY"}

        if mode in _WRITE_MODES:
            # Delegate to action-ID mapping — same LLM call as parse_intent
            try:
                if self.provider == "openai_compatible":
                    parsed, tokens = call_openai(
                        text, self.model, self.api_key, self.base_url,
                        include_response_format=False,
                    )
                elif self.provider == "openai":
                    parsed, tokens = call_openai(
                        text, self.model, self.api_key,
                        "https://api.openai.com/v1",
                        include_response_format=True,
                    )
                else:
                    parsed, tokens = call_gemini(text, self.model, self.api_key)
            except urllib.error.HTTPError as e:
                safe_message = getattr(e, "safe_message", "Provider rejected the request.")
                self.send_json(502, {"ok": False, "error": f"LLM API error {e.code}: {safe_message}"})
                return
            except urllib.error.URLError as e:
                self.send_json(502, {"ok": False, "error": f"Network error: {e.reason}"})
                return
            except Exception as e:
                self.send_json(502, {"ok": False, "error": str(e)})
                return

            self.send_json(200, {
                "ok":                 parsed.get("ok", False),
                "type":               "action",
                "action_id":          parsed.get("action_id", "unmapped"),
                "params":             parsed.get("params", {}),
                "confidence":         parsed.get("confidence", 0.0),
                "needs_confirmation": parsed.get("needs_confirmation", False),
                "clarification":      parsed.get("clarification", None),
                "reason":             parsed.get("reason", ""),
                "model":              self.model,
                "provider":           self.provider,
                "tokens":             tokens,
            })
            return

        # ── Build 14: CLARIFY fast-path — deterministic composer, no LLM call ──
        # Fires before context assembly so ambiguous messages get one clean
        # natural question without paying an LLM token cost.
        # If the composer cannot produce a safe question (BLOCK_UNSUPPORTED,
        # unknown categories) it returns '' and execution falls through to the
        # normal call_knowledge_answer() path below.
        if mode == "CLARIFY":
            clarify_text = _compose_clarify_question(text, risk_reason, risk_category)
            if clarify_text:
                self.send_json(200, {
                    "ok":       True,
                    "type":     "clarify",
                    "text":     clarify_text,
                    "mode":     mode,
                    "model":    self.model,
                    "provider": self.provider,
                    "tokens":   {"input": 0, "output": 0, "total": 0},
                })
                return
            # Composer returned '' — fall through to call_knowledge_answer() below.

        # ── Knowledge / mentor / read / clarify (fallback) / freeform path ──────
        # Assemble context layers (same for both explorer and direct paths)
        context_parts = []
        if session_pack_text:
            context_parts.append(session_pack_text)
        if message_pack_text:
            context_parts.append(message_pack_text)
        if session_state_block:
            context_parts.append(session_state_block)
        context_parts.append(f"---\nUser: {text}")
        enriched = "\n\n".join(context_parts)

        # Load Conductor system prompt (Conductor identity + context layer rules)
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        system_prompt_str = _load_system_prompt(project_root)

        # session_available drives the explorer's honesty about what it can see
        session_available = bool(state_data and state_data.get("ok"))

        # Build 8: pass the existing Operator Card snippet to Creative Critic.
        operator_card_context = _extract_operator_card_context(message_pack_text)
        # Build 12: pass the ## KNOWLEDGE STATUS block to Creative Critic so
        # knowledge_evidence is grounded in actual context, not only Explorer assumptions.
        knowledge_status_context = _extract_knowledge_status_context(message_pack_text)

        try:
            if mode in _EXPLORER_MODES:
                # Knowledge Explorer path:
                #   Generates 2–3 internal candidate directions, then synthesises
                #   a natural user-facing answer. The 'explorer' field in the
                #   response is internal metadata — not shown in the chat UI.
                answer_text, explorer_data, tokens = call_knowledge_explorer(
                    enriched, session_available, system_prompt_str,
                    self.provider, self.model, self.api_key, self.base_url,
                )
                # ── Creative Critic: evaluate candidates (internal, non-fatal) ──
                # Runs only when Explorer produced candidates.
                # Failure at any point is caught here — explorer answer always stands.
                critic_data = {}
                _candidates_for_critic = explorer_data.get("candidates", [])
                if _candidates_for_critic:
                    try:
                        critic_data, _critic_tok = call_creative_critic(
                            _candidates_for_critic,
                            text,
                            session_state_block,
                            self.provider, self.model, self.api_key, self.base_url,
                            card_context=operator_card_context,
                            knowledge_status_context=knowledge_status_context,
                        )
                    except Exception:
                        # Critic failure is non-fatal — explorer answer unchanged
                        critic_data = {}
                # Compose final answer: Critic-selected candidate takes precedence
                # over the Explorer's synthesised answer. Falls back to
                # explorer_answer if Critic is empty or returned an invalid index.
                final_text = _compose_final_answer(answer_text, explorer_data, critic_data)
                self.send_json(200, {
                    "ok":       True,
                    "type":     "answer",
                    "text":     final_text,
                    "explorer": explorer_data,
                    "critic":   critic_data,
                    "mode":     mode,
                    "model":    self.model,
                    "provider": self.provider,
                    "tokens":   tokens,
                })
            else:
                # Direct answer path — READ, CLARIFY, or unknown modes.
                # No candidate generation; answer returned as-is.
                answer_text, tokens = call_knowledge_answer(
                    enriched, system_prompt_str,
                    self.provider, self.model, self.api_key, self.base_url,
                )
                self.send_json(200, {
                    "ok":       True,
                    "type":     "answer",
                    "text":     answer_text,
                    "mode":     mode,
                    "model":    self.model,
                    "provider": self.provider,
                    "tokens":   tokens,
                })
        except urllib.error.HTTPError as e:
            safe_message = getattr(e, "safe_message", "Provider rejected the request.")
            self.send_json(502, {"ok": False, "error": f"LLM API error {e.code}: {safe_message}"})
            return
        except urllib.error.URLError as e:
            self.send_json(502, {"ok": False, "error": f"Network error: {e.reason}"})
            return
        except Exception as e:
            self.send_json(502, {"ok": False, "error": str(e)})
            return

    def send_json(self, code, obj):
        payload = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        sys.stderr.write(f"[harness] {fmt % args}\n")


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    env_path = os.path.join(project_root, ".env")
    app_dir = os.path.join(project_root, "app")

    env = load_env(env_path)
    provider = os.environ.get("HARNESS_AI_PROVIDER") or env.get("HARNESS_AI_PROVIDER", "gemini")
    model = os.environ.get("HARNESS_AI_MODEL") or env.get("HARNESS_AI_MODEL", "gemini-2.0-flash")
    api_key = os.environ.get("HARNESS_AI_API_KEY") or env.get("HARNESS_AI_API_KEY", "")
    base_url = os.environ.get("HARNESS_AI_BASE_URL") or env.get("HARNESS_AI_BASE_URL", "")
    atxp_connection = os.environ.get("ATXP_CONNECTION") or env.get("ATXP_CONNECTION", "")

    HarnessHandler.provider = provider
    HarnessHandler.model = model
    HarnessHandler.api_key = api_key if api_key else None
    HarnessHandler.base_url = base_url
    HarnessHandler.atxp_connection_present = bool(atxp_connection)
    HarnessHandler.app_dir = app_dir

    if not api_key:
        extra = " | ATXP_CONNECTION present" if atxp_connection else ""
        print(f"Live Harness v1.5 Server | Port {PORT} | AI Sandbox: disabled (no HARNESS_AI_API_KEY){extra}")
    else:
        print(f"Live Harness v1.5 Server | Port {PORT} | Provider: {provider} | Model: {model}")

    server = http.server.HTTPServer(("", PORT), HarnessHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
