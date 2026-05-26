#!/usr/bin/env python3
"""Live Harness v1.5 Server — AI intent parser for Ableton Live."""

import http.server
import json
import os
import sys
import urllib.request
import urllib.error

PORT = 4620

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
        if self.path != "/harness/parse_intent":
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

        try:
            if self.provider == "openai_compatible":
                parsed, tokens = call_openai(
                    text,
                    self.model,
                    self.api_key,
                    self.base_url,
                    include_response_format=False,
                )
            elif self.provider == "openai":
                parsed, tokens = call_openai(
                    text,
                    self.model,
                    self.api_key,
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
