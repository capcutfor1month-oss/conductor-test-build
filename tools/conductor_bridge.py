#!/usr/bin/env python3
"""
Conductor Bridge v1.9 (Phase D S5)
─────────────────────
Local HTTP server (localhost:4611) that bridges the Conductor web UI
to local tools: Ableton MCP (TCP 16619), NotebookLM CLI, audio-analyzer CLI,
ChromaDB memory (local, no API key).

Start:  python3 conductor_bridge.py
Stop:   Ctrl+C
"""

import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

# ── SEMANTIC ROUTER SETUP ─────────────────────────────────────────────────────
try:
    sys.path.insert(0, os.path.dirname(__file__))
    from conductor_router import route_message
    ROUTER_AVAILABLE = True
except ImportError:
    ROUTER_AVAILABLE = False
    def route_message(msg): return "notebooklm"

# ── CONTEXT PACK BUILDER SETUP ────────────────────────────────────────────────
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from rag.context_pack_builder import build_context_pack
    CONTEXT_PACK_AVAILABLE = True
except ImportError:
    CONTEXT_PACK_AVAILABLE = False
    def build_context_pack(msg, status=None):
        return {"ok": False, "pack": "", "mode": "MENTOR", "risk_reason": "", "error": "context_pack_builder not available"}

# ── CHROMADB SETUP ────────────────────────────────────────────────────────────
try:
    import chromadb
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

# Memory schema — collection names and metadata helpers
try:
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from rag.memory_schema import COLLECTIONS, ALL_COLLECTION_NAMES, make_metadata
    SCHEMA_AVAILABLE = True
except ImportError:
    COLLECTIONS = {
        "producer":  "producer_memory_index",
        "project":   "project_session_index",
        "plugin":    "plugin_operator_index",
        "failure":   "failure_cases_index",
        "audio":     "audio_analysis_index",
    }
    ALL_COLLECTION_NAMES = list(COLLECTIONS.values())
    SCHEMA_AVAILABLE = False
    def make_metadata(collection, overrides=None):
        import time
        meta = {"collection": collection, "memory_level": 1, "source_type": "",
                "created_at": "", "updated_at": ""}
        if overrides:
            meta.update(overrides)
        return meta

LEGACY_COLLECTION = "conductor_memory"

_chroma_client = None
_chroma_collections = {}   # short_key → collection object

def get_chroma_client():
    """Return initialised ChromaDB client — creates the 5 collections on first call."""
    global _chroma_client, _chroma_collections
    if _chroma_client is not None:
        return _chroma_client
    if not CHROMA_AVAILABLE:
        return None
    cfg = load_config()
    chroma_path = cfg.get("chromadb_path",
                          os.path.join(os.path.dirname(__file__), "../memory/chromadb"))
    os.makedirs(chroma_path, exist_ok=True)
    _chroma_client = chromadb.PersistentClient(path=chroma_path)
    # Ensure all 5 collections exist with cosine metric
    for short_key, col_name in COLLECTIONS.items():
        _chroma_collections[short_key] = _chroma_client.get_or_create_collection(
            name=col_name,
            metadata={"hnsw:space": "cosine"},
        )
    return _chroma_client

def get_collection(short_key_or_name: str):
    """
    Return a ChromaDB collection by short key ("producer") or full name
    ("producer_memory_index"). Returns None if ChromaDB unavailable OR if
    the name is not a recognised schema collection.

    HARD REJECT: any name not in the 5-collection schema returns None.
    No arbitrary collection creation from user/API input.
    This prevents collection sprawl and blocks untrusted collection names.
    """
    get_chroma_client()  # ensure initialised
    if not _chroma_client:
        return None
    # Try short key first (e.g. "producer")
    if short_key_or_name in _chroma_collections:
        return _chroma_collections[short_key_or_name]
    # Try full name (e.g. "producer_memory_index")
    for short_key, col in _chroma_collections.items():
        if col.name == short_key_or_name:
            return col
    # Unknown collection — hard reject, do not create
    return None

def get_chroma():
    """
    Legacy helper — returns (client, legacy conductor_memory collection).
    Only kept for any code that hasn't been migrated yet.
    New code should use get_collection(short_key) instead.
    """
    client = get_chroma_client()
    if not client:
        return None, None
    try:
        legacy_col = client.get_or_create_collection(LEGACY_COLLECTION)
        return client, legacy_col
    except Exception:
        return client, None

# ── CONFIG ────────────────────────────────────────────────────────────────────

# ── PHASE D — SESSION ID + REQUEST ID ────────────────────────────────────────
# SESSION_ID is a per-startup UUID that links all ActionProofs + black-box log
# entries in one bridge lifetime.  It resets on bridge restart.
_SESSION_ID = uuid.uuid4().hex[:16]

def _new_request_id() -> str:
    """Return a fresh per-request ID (8-char hex).  Used for log correlation."""
    return uuid.uuid4().hex[:8]

def _new_action_id() -> str:
    """Return a fresh per-action ID (12-char hex)."""
    return uuid.uuid4().hex[:12]


def _parse_bool_strict(value, param_name: str) -> "tuple":
    """
    Strict boolean parser for action endpoint body params.

    Accepts:
        Python bool True/False  — from JSON true/false decoded by json.loads
        Strings "true"/"false"  — case-insensitive

    Rejects everything else:
        integers (0, 1), None, "yes", "no", "0", "1", empty strings,
        or any other arbitrary string.

    Returns:
        (parsed_bool: bool, "")          — on success
        (None,         error_msg: str)   — on failure; caller must return 400

    Motivation: bool("false") == True in Python, which is a footgun when
    JSON-encoded string "false" leaks in (e.g., from curl -d or form posts).
    This parser prevents that class of bug entirely.
    """
    if isinstance(value, bool):
        return value, ""
    if isinstance(value, str):
        lv = value.strip().lower()
        if lv == "true":
            return True, ""
        if lv == "false":
            return False, ""
    return None, (
        f"'{param_name}' must be a JSON boolean (true or false), got: {value!r}. "
        f"Strings 'true'/'false' are also accepted. "
        f"Do not send integers, 'yes', 'no', '0', '1', or other values."
    )


def _parse_confirm_strict(value) -> "tuple":
    """
    Strict parser for the optional 'confirm' field in action endpoints.

    Differs from _parse_bool_strict in one key way:
        absent (None) → (False, "")   — no error; absence means not confirmed
        bool           → (bool,  "")  — JSON true/false accepted directly
        "true"/"false" → (bool,  "")  — case-insensitive strings accepted
        anything else  → (None, msg)  — caller must return 400

    Specifically rejects: "yes", "no", "maybe", integers (0, 1), lists, dicts,
    or any other non-boolean, non-string value.

    Motivation: bool("false") == True in Python.  Sending confirm="false" must
    leave the gate closed, not open it.  This function prevents that entire
    class of bug on all destructive endpoints.
    """
    if value is None:
        return False, ""
    if isinstance(value, bool):
        return value, ""
    if isinstance(value, str):
        lv = value.strip().lower()
        if lv == "true":
            return True, ""
        if lv == "false":
            return False, ""
    return None, (
        f"'confirm' must be a JSON boolean (true or false), got: {value!r}. "
        "Strings 'true'/'false' are accepted. "
        "Integers, 'yes', 'no', 'maybe', and other values are not."
    )


# ─────────────────────────────────────────────────────────────────────────────

BRIDGE_PORT = 4611   # TEST-BUILD uses 4611 — old personal build uses 4601

# Ableton MCP — TCP connection (bschoepke remote script)
ABLETON_HOST = "localhost"
ABLETON_PORT = 16619

# Context files served/written by bridge
ABLETON_MD     = os.path.join(os.path.dirname(__file__), "../app/ableton.md")
ERRORS_MD      = os.path.join(os.path.dirname(__file__), "../errors.md")
SYSTEM_PROMPT  = os.path.join(os.path.dirname(__file__), "../app/system_prompt.md")

# NotebookLM CLI — third-party notebooklm-py
NOTEBOOKLM_CANDIDATES = [
    "/opt/homebrew/var/pipx/venvs/notebooklm-py/bin/notebooklm",
    "/usr/local/bin/notebooklm",
    os.path.expanduser("~/.local/bin/notebooklm"),
]

# Audio Analyzer CLI (Rust, compiled)
AUDIO_ANALYZER_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "audio-analyzer"),  # bundled in tools/
    os.path.expanduser("~/.local/bin/audio-analyzer"),
]

# ChromaDB — local persistent memory, no API key required
# PluginBridge — loaded inside Ableton; we detect via Ableton connectivity

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "conductor_bridge_config.json")

# ── HELPERS ───────────────────────────────────────────────────────────────────

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return json.load(f)
    return {}

def save_config(cfg):
    with open(CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

def find_binary(candidates, config_key=None):
    """Return first existing binary from candidates, or saved config path."""
    cfg = load_config()
    if config_key and cfg.get(config_key):
        p = cfg[config_key]
        if os.path.exists(p):
            return p
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def ableton_connected():
    """Try TCP handshake with Ableton MCP on port 16619."""
    try:
        s = socket.create_connection((ABLETON_HOST, ABLETON_PORT), timeout=1.0)
        s.close()
        return True
    except Exception:
        return False

def notebooklm_path():
    return find_binary(NOTEBOOKLM_CANDIDATES, "notebooklm_bin")

def audio_analyzer_path():
    return find_binary(AUDIO_ANALYZER_CANDIDATES, "audio_analyzer_bin")

def cors_headers(handler):
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")

# ── ABLETON MCP TCP CLIENT ────────────────────────────────────────────────────

def ableton_execute(code: str, timeout: float = 10.0):
    """
    Send a Python code string to Ableton MCP over TCP and return the response.
    Protocol: newline-delimited JSON  { "type": "execute", "code": "..." }
    Response: standard format { ok, source, data, verified, error }
    """
    payload = json.dumps({"type": "execute", "code": code}) + "\n"
    try:
        with socket.create_connection((ABLETON_HOST, ABLETON_PORT), timeout=timeout) as s:
            s.sendall(payload.encode("utf-8"))
            s.settimeout(timeout)
            buf = b""
            while True:
                chunk = s.recv(4096)
                if not chunk:
                    break
                buf += chunk
                if b"\n" in buf:
                    break
            line = buf.split(b"\n")[0].decode("utf-8", errors="replace")
            raw = json.loads(line) if line.strip() else {"ok": True}
            return {
                "ok":       raw.get("ok", "error" not in raw),
                "source":   "ableton",
                "data":     raw,
                "verified": False,  # caller must verify by reading back the value
                "error":    raw.get("error", None)
            }
    except socket.timeout:
        return {"ok": False, "source": "ableton", "data": {}, "verified": False, "error": "Ableton MCP timeout"}
    except ConnectionRefusedError:
        return {"ok": False, "source": "ableton", "data": {}, "verified": False, "error": "Ableton MCP not reachable — is Ableton open with MCP loaded?"}
    except Exception as e:
        return {"ok": False, "source": "ableton", "data": {}, "verified": False, "error": str(e)}

# ── REQUEST HANDLER ───────────────────────────────────────────────────────────

class ConductorHandler(BaseHTTPRequestHandler):

    def _send_json(self, data, code=200):
        body = json.dumps(data).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        cors_headers(self)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        cors_headers(self)
        self.end_headers()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        params = dict(urllib.parse.parse_qsl(parsed.query))

        # ── GET /ping ────────────────────────────────────────────────────────
        if path == "/ping":
            self._send_json({"ok": True, "version": "1.9", "port": BRIDGE_PORT})

        # ── GET /status ──────────────────────────────────────────────────────
        elif path == "/status":
            nlm = notebooklm_path()
            aa = audio_analyzer_path()
            status = {
                "bridge":         "connected",
                "ableton":        "connected" if ableton_connected() else "disconnected",
                "notebooklm":     "ready" if nlm else "not_installed",
                "notebooklm_bin": nlm or "",
                "audio_analyzer": "ready" if aa else "not_installed",
                "audio_analyzer_bin": aa or "",
                "memory":         "ready" if CHROMA_AVAILABLE else "not_installed",
                "pluginbridge":   "check_ableton", # only valid if Ableton connected
                "semantic_router": "ready" if ROUTER_AVAILABLE else "fallback",
            }
            self._send_json(status)

        # ── GET /notebooklm?q=... ────────────────────────────────────────────
        elif path == "/notebooklm":
            q = params.get("q", "").strip()
            if not q:
                return self._send_json({"error": "no query — use ?q=your+question"}, 400)
            nlm = notebooklm_path()
            if not nlm:
                return self._send_json({"error": "NotebookLM CLI not found. Install notebooklm-py or set path in setup."}, 503)
            try:
                result = subprocess.run(
                    [nlm, "ask", q],
                    capture_output=True, text=True, timeout=60
                )
                self._send_json({
                    "ok": True,
                    "result": result.stdout.strip(),
                    "stderr": result.stderr.strip(),
                })
            except subprocess.TimeoutExpired:
                self._send_json({"error": "NotebookLM query timed out (60s)"}, 504)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /analyze?path=/tmp/file.wav ──────────────────────────────────
        elif path == "/analyze":
            file_path = params.get("path", "")
            if not file_path:
                return self._send_json({"error": "no path — use ?path=/absolute/path.wav"}, 400)
            if not os.path.exists(file_path):
                return self._send_json({"error": f"file not found: {file_path}"}, 404)
            aa = audio_analyzer_path()
            if not aa:
                return self._send_json({"error": "audio-analyzer CLI not found"}, 503)
            try:
                result = subprocess.run(
                    [aa, file_path],
                    capture_output=True, text=True, timeout=30
                )
                self._send_json({"ok": True, "result": result.stdout.strip()})
            except subprocess.TimeoutExpired:
                self._send_json({"error": "audio-analyzer timed out (30s)"}, 504)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /memory?q=...&collection=producer ────────────────────────────
        # collection param: short key ("producer") or full name. Defaults to
        # "producer" (producer_memory_index) for backward compat.
        elif path == "/memory":
            q          = params.get("q", "").strip()
            n          = int(params.get("n", 3))
            coll_param = params.get("collection", "producer").strip()
            if not q:
                return self._send_json({"error": "no query — use ?q=your+question"}, 400)
            if not CHROMA_AVAILABLE:
                return self._send_json({"error": "chromadb not installed"}, 503)
            try:
                col = get_collection(coll_param)
                if col is None:
                    return self._send_json({"error": f"unknown collection: {coll_param}"}, 400)
                if col.count() == 0:
                    return self._send_json({"ok": True, "memories": [], "count": 0,
                                            "collection": col.name})
                results   = col.query(query_texts=[q], n_results=min(n, col.count()),
                                      include=["documents", "distances", "metadatas"])
                docs      = results.get("documents", [[]])[0]
                distances = results.get("distances",  [[]])[0]
                metas     = results.get("metadatas",  [[]])[0]
                items = [
                    {
                        "text":       doc,
                        "similarity": round(max(0.0, 1.0 - dist), 3),
                        "metadata":   meta or {},
                    }
                    for doc, dist, meta in zip(docs, distances, metas)
                ]
                self._send_json({
                    "ok": True, "memories": [i["text"] for i in items],
                    "items": items, "count": len(items), "collection": col.name,
                })
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /config ──────────────────────────────────────────────────────
        elif path == "/config":
            self._send_json(load_config())

        # ── GET /context/ableton ─────────────────────────────────────────────
        elif path == "/context/ableton":
            try:
                with open(ABLETON_MD, "r") as f:
                    content = f.read()
                self._send_json({"ok": True, "content": content})
            except FileNotFoundError:
                self._send_json({"error": "ableton.md not found"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /route?q=... ──────────────────────────────────────────────────
        # Returns the routing decision for a given message without executing it.
        # Powers the Auto mode indicator in the UI.
        # Routes: notebooklm | ableton | memory | analyzer | direct
        elif path == "/route":
            q = params.get("q", "").strip()
            if not q:
                return self._send_json({"error": "no query — use ?q=your+message"}, 400)
            destination = route_message(q)
            self._send_json({
                "ok":          True,
                "route":       destination,
                "router":      "semantic" if ROUTER_AVAILABLE else "fallback",
                "query":       q,
            })

        # ── GET /risk/rules ───────────────────────────────────────────────────
        # Returns the backend risk taxonomy so the frontend can generate its
        # emergency risky-action regex from the same source. Prevents drift.
        # Response: {action_categories, high_risk_plugin_terms, freeform_patterns}
        elif path == "/risk/rules":
            try:
                from rag.risk_taxonomy import get_risk_rules_payload
                self._send_json(get_risk_rules_payload())
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /context/session ──────────────────────────────────────────────
        # LAYER B: Session context — Producer DNA + project state + tool health.
        # UI fetches this ONCE at session start and on state changes (Ableton
        # connects/disconnects, project changes). NOT called per message.
        elif path == "/context/session":
            nlm = notebooklm_path()
            aa  = audio_analyzer_path()
            status = {
                "ableton":        "connected" if ableton_connected() else "disconnected",
                "notebooklm":     "ready" if nlm else "not_installed",
                "audio_analyzer": "ready" if aa else "not_installed",
                "memory":         "ready" if CHROMA_AVAILABLE else "not_installed",
                "pluginbridge":   "check_ableton",
            }
            try:
                from rag.context_pack_builder import build_session_pack
                result = build_session_pack(status)
                result["status"] = status   # pass raw status back so UI can track changes
                self._send_json(result)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /context/pack?q=... ───────────────────────────────────────────
        # LAYER C: Per-message context — ChromaDB + operator card + mode.
        # UI calls this on EVERY message send. q= is the user's message.
        elif path == "/context/pack":
            q = params.get("q", "").strip()
            try:
                from rag.context_pack_builder import build_message_pack
                result = build_message_pack(q)
                # C2 — best-effort audit log (never blocks response)
                try:
                    from rag.context_pack_logger import log_pack
                    log_pack(q, result)
                except Exception:
                    pass
                self._send_json(result)
            except Exception as e:
                try:
                    from rag.context_pack_logger import log_pack_error
                    log_pack_error(q, str(e))
                except Exception:
                    pass
                self._send_json({"error": str(e)}, 500)

        # ── GET /context/system_prompt ────────────────────────────────────────
        # Returns app/system_prompt.md for UI to use as Anthropic system param.
        # Fetched once on page load and cached in JS.
        elif path == "/context/system_prompt":
            try:
                with open(SYSTEM_PROMPT, "r") as f:
                    content = f.read()
                self._send_json({"ok": True, "content": content})
            except FileNotFoundError:
                self._send_json({"error": "system_prompt.md not found"}, 404)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── GET /session/state ────────────────────────────────────────────────
        # Read-only live snapshot of Ableton session state via TCP 16619.
        # Uses ableton_execute() (v2 flat protocol) — no new adapter.
        # state_completeness tells callers exactly what is/isn't available.
        # Clips, devices, and routing are NOT read — marked "not_available_v1"
        # so callers never mistake absent data for empty data.
        elif path == "/session/state":
            if not ableton_connected():
                return self._send_json({
                    "ok":               False,
                    "ableton_connected": False,
                    "error":            "Ableton not connected",
                }, 503)

            # Single eval expression — all reliable state in one TCP round-trip.
            _main_code = (
                "{"
                "'tempo': song.tempo, "
                "'time_signature': "
                    "str(song.signature_numerator) + '/' + str(song.signature_denominator), "
                "'playing': bool(song.is_playing), "
                "'record': bool(song.record_mode), "
                "'tracks': [{"
                    "'index': i, "
                    "'name': t.name, "
                    "'type': 'midi' if getattr(t, 'has_midi_input', False) else ('audio' if getattr(t, 'has_audio_input', False) else 'unknown'), "
                    "'muted': bool(t.mute), "
                    "'soloed': bool(getattr(t, 'solo', False)), "
                    "'arm': bool(getattr(t, 'arm', False))"
                "} for i, t in enumerate(song.tracks)], "
                "'return_tracks': [{"
                    "'index': i, "
                    "'name': t.name"
                "} for i, t in enumerate(song.return_tracks)]"
                "}"
            )
            main_resp = ableton_execute(_main_code)
            if not main_resp.get("ok"):
                return self._send_json({
                    "ok":               False,
                    "ableton_connected": True,
                    "source":           "ableton_mcp",
                    "error":            main_resp.get("error") or "Failed to read session state",
                }, 502)

            state = (main_resp.get("data") or {}).get("result")
            if not isinstance(state, dict):
                return self._send_json({
                    "ok":               False,
                    "ableton_connected": True,
                    "source":           "ableton_mcp",
                    "error":            "Unexpected LOM response — state was not a dict",
                }, 502)

            # Selected track — best-effort via exec (try/except inside LOM).
            # Must never raise 500: if this read fails, selected_track = null.
            _sel_code = (
                "try:\n"
                "    result = song.view.selected_track.name\n"
                "except Exception:\n"
                "    result = None\n"
            )
            sel_resp  = ableton_execute(_sel_code)
            sel_raw   = (sel_resp.get("data") or {}).get("result") if sel_resp.get("ok") else None
            selected_track = sel_raw if isinstance(sel_raw, str) else None

            return self._send_json({
                "ok":               True,
                "ableton_connected": True,
                "source":           "ableton_mcp",
                "tempo":            state.get("tempo"),
                "time_signature":   state.get("time_signature"),
                "playing":          state.get("playing"),
                "record":           state.get("record"),
                "selected_track":   selected_track,
                "tracks":           state.get("tracks", []),
                "return_tracks":    state.get("return_tracks", []),
                "state_completeness": {
                    "tracks":       "full",
                    "return_tracks": "full",
                    "tempo":        "full",
                    "selected_track": "best_effort",
                    "clips":        "not_available_v1",
                    "devices":      "not_available_v1",
                    "routing":      "not_available_v1",
                },
            })

        else:
            self._send_json({"error": f"unknown endpoint: {path}"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        try:
            body = json.loads(self.rfile.read(content_len)) if content_len else {}
        except json.JSONDecodeError:
            body = {}

        # ── POST /ableton ─────────────────────────────────────────────────────
        if path == "/ableton":
            code = body.get("code", "").strip()
            if not code:
                return self._send_json({"error": "no code — send { \"code\": \"song.tempo\" }"}, 400)
            if not ableton_connected():
                return self._send_json({"error": "Ableton MCP not reachable — open Ableton with MCP loaded"}, 503)
            result = ableton_execute(code)
            self._send_json(result)

        # ── POST /memory ──────────────────────────────────────────────────────
        # Body: {
        #   "text":       required  — the memory string to store
        #   "collection": REQUIRED  — short key (producer|project|plugin|failure|audio)
        #                             or full collection name. No default — caller must choose.
        #   "metadata":   optional  — dict of extra metadata fields (merged with schema defaults)
        # }
        # Rejects writes that: omit collection, target unknown collection, or fail
        # validate_metadata(). Silent weak writes are not allowed.
        elif path == "/memory":
            text       = body.get("text", "").strip()
            coll_param = body.get("collection", "").strip()   # NO default — required
            extra_meta = body.get("metadata", {}) or {}
            # ── Memory write contract ──────────────────────────────────────────
            # Every caller MUST include: mode, collection, valid metadata, source_type.
            # See system_prompt.md § MEMORY WRITE CONTRACT for the full rule.
            req_mode   = body.get("mode", "").strip()         # REQUIRED — hard 400 if absent
            if not req_mode:
                return self._send_json({
                    "error": "mode required",
                    "reason": (
                        "All POST /memory callers must include 'mode' "
                        "(the request classifier mode string, e.g. INTERN_WRITE_SAFE). "
                        "Without mode the FREEFORM guard and routing validation cannot be enforced. "
                        "Contract: {mode, collection, text, metadata{source_type,...}}"
                    ),
                }, 400)
            if not text:
                return self._send_json({"error": "no text — send { \"text\": \"...\" }"}, 400)
            if not coll_param:
                return self._send_json({
                    "error": "collection required — specify short key: producer|project|plugin|failure|audio"
                }, 400)
            # FREEFORM write guard — project-session history must not be written
            # when Ableton is disconnected or the query was off-topic (non-music).
            # Producer/plugin/failure/audio collections are cross-project and remain open.
            _PROJECT_COLL_KEYS = {"project", "project_session_index"}
            if req_mode == "FREEFORM_GENERAL" and coll_param in _PROJECT_COLL_KEYS:
                return self._send_json({
                    "error": "freeform_write_blocked",
                    "reason": (
                        "Project-session history cannot be written in FREEFORM mode. "
                        "Use the 'producer' collection for cross-session preferences, "
                        "or reconnect Ableton to enter SESSION mode before writing project history."
                    ),
                }, 400)
            if not CHROMA_AVAILABLE:
                return self._send_json({"error": "chromadb not installed"}, 503)
            try:
                col = get_collection(coll_param)
                if col is None:
                    return self._send_json({"error": f"unknown collection: {coll_param}"}, 400)
                # Build metadata with schema defaults
                meta = make_metadata(col.name, extra_meta)
                # Validate — reject invalid writes instead of silently storing weak memory
                if SCHEMA_AVAILABLE:
                    from rag.memory_schema import validate_metadata as _vm
                    valid, errors = _vm(col.name, meta)
                    if not valid:
                        return self._send_json({
                            "error": "metadata validation failed",
                            "errors": errors,
                            "collection": col.name,
                        }, 400)
                mem_id = f"mem_{int(time.time() * 1000)}"
                col.add(documents=[text], ids=[mem_id], metadatas=[meta])
                # C3 write-time: mark similar existing memories as superseded
                # so they are filtered at retrieval without needing any
                # read-time check to catch them first.
                superseded_ids: list = []
                try:
                    from rag.corrective_check import find_superseded_by_new
                    superseded_ids = find_superseded_by_new(col, text, mem_id)
                except Exception:
                    pass
                resp = {"ok": True, "id": mem_id, "collection": col.name}
                if superseded_ids:
                    resp["superseded"] = superseded_ids
                self._send_json(resp)
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── POST /config ──────────────────────────────────────────────────────
        elif path == "/config":
            cfg = load_config()
            cfg.update(body)
            save_config(cfg)
            self._send_json({"ok": True, "saved": body})

        # ── POST /context/ableton ─────────────────────────────────────────────
        # AI writes a confirmed fix pattern to ableton.md on the spot
        # Body: { "task": "...", "failed": "...", "fix": "..." }
        elif path == "/context/ableton":
            task  = body.get("task", "").strip()
            failed = body.get("failed", "").strip()
            fix   = body.get("fix", "").strip()
            if not task or not fix:
                return self._send_json({"error": "send { task, failed, fix }"}, 400)
            try:
                entry = f"\n| {task} | {failed} | {fix} |\n"
                with open(ABLETON_MD, "r") as f:
                    content = f.read()
                # Append to Known Failure Patterns table
                marker = "| Task | Known Failure | Confirmed Fix |"
                if marker in content:
                    # find end of table and insert before the closing ---
                    insert_at = content.rfind("\n---", content.index(marker))
                    content = content[:insert_at] + entry + content[insert_at:]
                else:
                    content += f"\n{entry}"
                with open(ABLETON_MD, "w") as f:
                    f.write(content)
                self._send_json({"ok": True, "written": entry.strip()})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── POST /session/save ────────────────────────────────────────────────
        # PLACEHOLDER — not yet implemented
        # Triggered by Cmd+S detection in Ableton
        # Body: { project_uuid, project_name, als_path, stage, bpm, key, tracks, notes }
        # Logic: rolling window of 5 saves, oldest dropped on new save
        # See: LIMITATIONS.md → SESSION SAVE LOGIC
        elif path == "/session/save":
            self._send_json({"ok": False, "error": "session/save not yet implemented — see LIMITATIONS.md"}, 501)

        # ── GET /session/load ─────────────────────────────────────────────────
        # PLACEHOLDER — not yet implemented
        # Triggered on Conductor launch when valid Project UUID found
        # Returns: last saved session state for this project
        # See: LIMITATIONS.md → SESSION SAVE LOGIC
        elif path == "/session/load":
            self._send_json({"ok": False, "error": "session/load not yet implemented — see LIMITATIONS.md"}, 501)

        # ── POST /errors ──────────────────────────────────────────────────────
        # AI silently logs every failure, hallucination, or user correction
        # Body: { "task": "...", "attempted": "...", "failed": "...", "fixed": "...", "ref_updated": "..." }
        elif path == "/errors":
            task      = body.get("task", "unknown task")
            attempted = body.get("attempted", "").strip()
            failed    = body.get("failed", "").strip()
            fixed     = body.get("fixed", "").strip()
            ref       = body.get("ref_updated", "").strip()
            if not attempted or not failed:
                return self._send_json({"error": "send { task, attempted, failed, fixed, ref_updated }"}, 400)
            try:
                timestamp = time.strftime("%Y-%m-%d %H:%M")
                entry = (
                    f"\n### {timestamp} — {task}\n"
                    f"**Attempted:** {attempted}\n"
                    f"**Failed:** {failed}\n"
                    f"**Fixed:** {fixed or 'not yet resolved'}\n"
                    f"**Reference updated:** {ref or 'none'}\n"
                )
                with open(ERRORS_MD, "r") as f:
                    content = f.read()
                marker = "## ACTIVE LOG"
                if marker in content:
                    insert_at = content.index(marker) + len(marker)
                    content = content[:insert_at] + "\n" + entry + content[insert_at:]
                else:
                    content += entry
                with open(ERRORS_MD, "w") as f:
                    f.write(content)
                self._send_json({"ok": True, "logged": entry.strip()})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        # ── POST /action/track_volume ─────────────────────────────────────────
        # Phase D Slice 1 — verified track volume write with readback proof.
        #
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "volume":     required  — normalized 0.0–1.0
        #   "session_id": optional  — caller session ID (defaults to bridge SESSION_ID)
        #   "project_id": optional  — project name for proof record
        # }
        #
        # Returns:
        #   ok=True  + proof_id + VERIFIED|ALREADY_CORRECT  → action confirmed
        #   ok=False + error_code                           → not confirmed
        #
        # Rule: ok=True ONLY when readback confirms the intended value.
        #       Never return ok=True on FAILED, UNVERIFIED, or PARTIAL.
        elif path == "/action/track_volume":
            from rag.bridge_errors    import BridgeErrorCode, error_response, ok_response
            from rag.never_do_check   import check as _ndc_check, NeverDoDecision
            from rag.black_box_log    import (log_requested, log_verified,
                                              log_failed, log_unverified,
                                              log_never_do_blocked)
            from rag.action_proof     import create_proof, VerificationStatus
            from rag.readback         import verify_track_volume, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            # ── Input validation ──────────────────────────────────────────────
            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required — send {'track': 'TrackName'}",
                                   request_id=request_id, action_id=action_id),
                    400,
                )

            volume_raw = body.get("volume")
            if volume_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "volume is required — send {'volume': 0.0–1.0}",
                                   request_id=request_id, action_id=action_id),
                    400,
                )
            try:
                volume_f = float(volume_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"volume must be a float 0.0–1.0, got: {volume_raw!r}",
                                   request_id=request_id, action_id=action_id),
                    400,
                )
            if not (0.0 <= volume_f <= 1.0):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"volume out of range: {volume_f} — must be 0.0–1.0",
                                   request_id=request_id, action_id=action_id),
                    400,
                )

            target_str = f"track:{track}"

            # ── Never-do preflight ────────────────────────────────────────────
            # Execute ONLY when decision is ALLOW.  Every other decision — hard
            # block, confirmation required, clarify required, unknown — refuses
            # the write and returns before any Ableton call.
            ndc_decision, ndc_rule = _ndc_check(
                "SET_TRACK_VOLUME",
                {"target": str(track)},
            )
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked(
                    "SET_TRACK_VOLUME", target_str, decision_value,
                    request_id=request_id, action_id=action_id,
                    session_id=session_id, rule_text=ndc_rule,
                )
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec   = BridgeErrorCode.SECURITY_NEVER_DO_BLOCK
                    _ndc_msg  = f"Action blocked by never-do rules. Rule: {ndc_rule}"
                    _ndc_http = 403
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec   = BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED
                    _ndc_msg  = f"Action requires explicit confirmation. Rule: {ndc_rule}"
                    _ndc_http = 403
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec   = BridgeErrorCode.SECURITY_CLARIFY_REQUIRED
                    _ndc_msg  = f"Action intent unclear — clarify before executing. Rule: {ndc_rule}"
                    _ndc_http = 400
                else:
                    # Unknown decision — fail closed, no write
                    _ndc_ec   = BridgeErrorCode.SECURITY_NEVER_DO_BLOCK
                    _ndc_msg  = f"Unknown never-do decision {ndc_decision!r} — failing closed."
                    _ndc_http = 403
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg,
                                   decision=decision_value,
                                   rule_text=ndc_rule,
                                   request_id=request_id,
                                   action_id=action_id,
                                   session_id=session_id),
                    _ndc_http,
                )

            # ── Ableton connectivity check ────────────────────────────────────
            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable — open Ableton with MCP loaded",
                                   request_id=request_id, action_id=action_id),
                    503,
                )

            # ── Log action requested ──────────────────────────────────────────
            log_requested(
                "SET_TRACK_VOLUME", target_str,
                request_id=request_id, action_id=action_id, session_id=session_id,
            )

            # ── Readback verification loop ────────────────────────────────────
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay",
                                  0.25))
            try:
                rb = verify_track_volume(
                    track, volume_f, ableton_execute,
                    stabilization_delay=delay,
                )
            except BeforeStateCaptureError as bsce:
                log_failed(
                    "SET_TRACK_VOLUME", target_str,
                    BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                    request_id=request_id, action_id=action_id,
                    message=str(bsce),
                )
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED,
                                   str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False),
                    500,
                )
            except Exception as exc:
                log_failed(
                    "SET_TRACK_VOLUME", target_str,
                    BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                    request_id=request_id, action_id=action_id,
                    message=str(exc),
                )
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id),
                    500,
                )

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            # ── User-facing summary ───────────────────────────────────────────
            if str(vstat) == "VERIFIED":
                summary = (
                    f"Track '{track}' volume set to {volume_f:.3f} "
                    f"— confirmed by readback."
                )
            elif str(vstat) == "ALREADY_CORRECT":
                summary = (
                    f"Track '{track}' volume was already {volume_f:.3f} "
                    f"— no change needed."
                )
            elif str(vstat) == "UNVERIFIED":
                summary = (
                    f"Track '{track}' volume write sent but readback unavailable "
                    f"— cannot confirm. Do not tell the user done."
                )
            else:  # FAILED
                summary = (
                    f"Track '{track}' volume change could not be confirmed: "
                    f"{rb.get('message', '')} — not marking as done."
                )

            # ── Create ActionProof ────────────────────────────────────────────
            proof = create_proof(
                action_type         = "SET_TRACK_VOLUME",
                target              = target_str,
                intended_value      = volume_f,
                before_state        = rb.get("before_state", {}),
                after_state         = rb.get("after_state", {}),
                verification_status = str(vstat),
                undo_eligible       = undo_eligible,
                user_facing_summary = summary,
                action_id           = action_id,
                request_id          = request_id,
                session_id          = session_id,
                project_id          = project_id,
            )

            # ── Black box log ─────────────────────────────────────────────────
            if is_confirmed:
                log_verified(
                    "SET_TRACK_VOLUME", target_str, proof.proof_id,
                    str(vstat), request_id=request_id,
                    action_id=action_id, session_id=session_id,
                )
            elif str(vstat) == "UNVERIFIED":
                log_unverified(
                    "SET_TRACK_VOLUME", target_str, proof.proof_id,
                    request_id=request_id,
                    action_id=action_id, session_id=session_id,
                )
            else:
                log_failed(
                    "SET_TRACK_VOLUME", target_str,
                    rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                    proof_id=proof.proof_id,
                    request_id=request_id,
                    action_id=action_id, session_id=session_id,
                    message=rb.get("message", ""),
                )

            self._send_json({
                "ok":                  is_confirmed,
                "proof_id":            proof.proof_id,
                "action_id":           action_id,
                "request_id":          request_id,
                "session_id":          session_id,
                "verification_status": str(vstat),
                "error_code":          rb.get("error_code", ""),
                "before_state":        rb.get("before_state", {}),
                "after_state":         rb.get("after_state", {}),
                "undo_eligible":       undo_eligible,
                "user_facing_summary": summary,
                "message":             rb.get("message", ""),
            })

        # ── POST /action/track_pan ────────────────────────────────────────────
        # Phase D Slice 2 — verified track pan write with readback proof.
        #
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "pan":        required  — normalized 0.0–1.0  (0=left, 0.5=center, 1=right)
        #   "session_id": optional
        #   "project_id": optional
        # }
        elif path == "/action/track_pan":
            from rag.bridge_errors    import BridgeErrorCode, error_response
            from rag.never_do_check   import check as _ndc_check, NeverDoDecision
            from rag.black_box_log    import (log_requested, log_verified,
                                              log_failed, log_unverified,
                                              log_never_do_blocked)
            from rag.action_proof     import create_proof
            from rag.readback         import verify_track_pan, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required — send {'track': 'TrackName'}",
                                   request_id=request_id, action_id=action_id), 400)

            pan_raw = body.get("pan")
            if pan_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "pan is required — send {'pan': 0.0–1.0}",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                pan_f = float(pan_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"pan must be a float 0.0–1.0, got: {pan_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)
            if not (0.0 <= pan_f <= 1.0):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"pan out of range: {pan_f} — must be 0.0–1.0",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_PAN", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_PAN", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg,
                                   decision=decision_value,
                                   rule_text=ndc_rule,
                                   request_id=request_id, action_id=action_id,
                                   session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable — open Ableton with MCP loaded",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_PAN", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)

            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_pan(track, pan_f, ableton_execute,
                                      stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_PAN", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_PAN", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' pan set to {pan_f:.3f} — confirmed by readback."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' pan was already {pan_f:.3f} — no change needed."
            elif str(vstat) == "UNVERIFIED":
                summary = (f"Track '{track}' pan write sent but readback unavailable "
                           f"— cannot confirm. Do not tell the user done.")
            else:
                summary = (f"Track '{track}' pan change could not be confirmed: "
                           f"{rb.get('message', '')} — not marking as done.")

            proof = create_proof(
                action_type="SET_TRACK_PAN", target=target_str,
                intended_value=pan_f,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id,
            )

            if is_confirmed:
                log_verified("SET_TRACK_PAN", target_str, proof.proof_id,
                             str(vstat), request_id=request_id,
                             action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_PAN", target_str, proof.proof_id,
                               request_id=request_id,
                               action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_PAN", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id,
                           request_id=request_id, action_id=action_id, session_id=session_id,
                           message=rb.get("message", ""))

            self._send_json({
                "ok":                  is_confirmed,
                "proof_id":            proof.proof_id,
                "action_id":           action_id,
                "request_id":          request_id,
                "session_id":          session_id,
                "verification_status": str(vstat),
                "error_code":          rb.get("error_code", ""),
                "before_state":        rb.get("before_state", {}),
                "after_state":         rb.get("after_state", {}),
                "undo_eligible":       undo_eligible,
                "user_facing_summary": summary,
                "message":             rb.get("message", ""),
            })

        # ── POST /action/track_mute ───────────────────────────────────────────
        # Phase D Slice 2 — verified track mute write with readback proof.
        #
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "mute":       required  — true | false
        #   "session_id": optional
        #   "project_id": optional
        # }
        elif path == "/action/track_mute":
            from rag.bridge_errors    import BridgeErrorCode, error_response
            from rag.never_do_check   import check as _ndc_check, NeverDoDecision
            from rag.black_box_log    import (log_requested, log_verified,
                                              log_failed, log_unverified,
                                              log_never_do_blocked)
            from rag.action_proof     import create_proof
            from rag.readback         import verify_track_mute, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required — send {'track': 'TrackName'}",
                                   request_id=request_id, action_id=action_id), 400)

            mute_raw = body.get("mute")
            if mute_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "mute is required — send {'mute': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            mute_bool, mute_err = _parse_bool_strict(mute_raw, "mute")
            if mute_bool is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   mute_err, request_id=request_id,
                                   action_id=action_id), 400)
            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_MUTE", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_MUTE", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg,
                                   decision=decision_value,
                                   rule_text=ndc_rule,
                                   request_id=request_id, action_id=action_id,
                                   session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable — open Ableton with MCP loaded",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_MUTE", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)

            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_mute(track, mute_bool, ableton_execute,
                                       stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_MUTE", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_MUTE", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            mute_word = "muted" if mute_bool else "unmuted"
            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' {mute_word} — confirmed by readback."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' was already {mute_word} — no change needed."
            elif str(vstat) == "UNVERIFIED":
                summary = (f"Track '{track}' mute write sent but readback unavailable "
                           f"— cannot confirm. Do not tell the user done.")
            else:
                summary = (f"Track '{track}' mute change could not be confirmed: "
                           f"{rb.get('message', '')} — not marking as done.")

            proof = create_proof(
                action_type="SET_TRACK_MUTE", target=target_str,
                intended_value=mute_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id,
            )

            if is_confirmed:
                log_verified("SET_TRACK_MUTE", target_str, proof.proof_id,
                             str(vstat), request_id=request_id,
                             action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_MUTE", target_str, proof.proof_id,
                               request_id=request_id,
                               action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_MUTE", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id,
                           request_id=request_id, action_id=action_id, session_id=session_id,
                           message=rb.get("message", ""))

            self._send_json({
                "ok":                  is_confirmed,
                "proof_id":            proof.proof_id,
                "action_id":           action_id,
                "request_id":          request_id,
                "session_id":          session_id,
                "verification_status": str(vstat),
                "error_code":          rb.get("error_code", ""),
                "before_state":        rb.get("before_state", {}),
                "after_state":         rb.get("after_state", {}),
                "undo_eligible":       undo_eligible,
                "user_facing_summary": summary,
                "message":             rb.get("message", ""),
            })

        # ── POST /action/track_solo ───────────────────────────────────────────
        # Phase D Slice 2 — verified track solo write with readback proof.
        #
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "solo":       required  — true | false
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Note: solo is session-level exclusive in Ableton.  This endpoint
        # verifies only the TARGET track's solo flag, not the full session state.
        elif path == "/action/track_solo":
            from rag.bridge_errors    import BridgeErrorCode, error_response
            from rag.never_do_check   import check as _ndc_check, NeverDoDecision
            from rag.black_box_log    import (log_requested, log_verified,
                                              log_failed, log_unverified,
                                              log_never_do_blocked)
            from rag.action_proof     import create_proof
            from rag.readback         import verify_track_solo, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required — send {'track': 'TrackName'}",
                                   request_id=request_id, action_id=action_id), 400)

            solo_raw = body.get("solo")
            if solo_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "solo is required — send {'solo': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            solo_bool, solo_err = _parse_bool_strict(solo_raw, "solo")
            if solo_bool is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   solo_err, request_id=request_id,
                                   action_id=action_id), 400)
            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_SOLO", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_SOLO", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg,
                                   decision=decision_value,
                                   rule_text=ndc_rule,
                                   request_id=request_id, action_id=action_id,
                                   session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable — open Ableton with MCP loaded",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_SOLO", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)

            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_solo(track, solo_bool, ableton_execute,
                                       stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_SOLO", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_SOLO", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            solo_word = "soloed" if solo_bool else "unsoloed"
            if str(vstat) == "VERIFIED":
                summary = (f"Track '{track}' {solo_word} — confirmed by readback "
                           f"(target track only).")
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' was already {solo_word} — no change needed."
            elif str(vstat) == "UNVERIFIED":
                summary = (f"Track '{track}' solo write sent but readback unavailable "
                           f"— cannot confirm. Do not tell the user done.")
            else:
                summary = (f"Track '{track}' solo change could not be confirmed: "
                           f"{rb.get('message', '')} — not marking as done.")

            proof = create_proof(
                action_type="SET_TRACK_SOLO", target=target_str,
                intended_value=solo_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id,
            )

            if is_confirmed:
                log_verified("SET_TRACK_SOLO", target_str, proof.proof_id,
                             str(vstat), request_id=request_id,
                             action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_SOLO", target_str, proof.proof_id,
                               request_id=request_id,
                               action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_SOLO", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id,
                           request_id=request_id, action_id=action_id, session_id=session_id,
                           message=rb.get("message", ""))

            self._send_json({
                "ok":                  is_confirmed,
                "proof_id":            proof.proof_id,
                "action_id":           action_id,
                "request_id":          request_id,
                "session_id":          session_id,
                "verification_status": str(vstat),
                "error_code":          rb.get("error_code", ""),
                "before_state":        rb.get("before_state", {}),
                "after_state":         rb.get("after_state", {}),
                "undo_eligible":       undo_eligible,
                "user_facing_summary": summary,
                "message":             rb.get("message", ""),
            })

        # ── POST /action/undo ─────────────────────────────────────────────────
        # Phase D Slice 4 — compensating undo for a verified track action.
        #
        # Body: {
        #   "proof_id":   optional* — ActionProof ID (preferred reference)
        #   "action_id":  optional* — action ID (fallback if no proof_id)
        #   "confirm":    optional  — bool: if true, undo even when drift detected
        #   "session_id": optional  — caller session ID
        #   "project_id": optional  — project name
        #
        #   * At least one of proof_id or action_id must be supplied.
        # }
        #
        # Rules:
        #   - Original proof must be VERIFIED or ALREADY_CORRECT
        #   - action_type must be one of SET_TRACK_VOLUME | SET_TRACK_PAN |
        #     SET_TRACK_MUTE | SET_TRACK_SOLO
        #   - before_state must be non-empty on the original proof
        #   - drift: current live state is compared to original after_state;
        #     if they differ, DRIFT_DETECTED (409) is returned unless confirm=true
        #   - undo creates a NEW ActionProof (action_type = UNDO_{original_type})
        #   - original proof is NEVER modified
        #   - undo_eligible is always False on the new proof (no undo-of-undo)
        elif path == "/action/undo":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.action_proof   import read_all_proofs
            from rag.undo_engine    import execute_undo, UndoValidationError
            from rag.black_box_log  import log_requested

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            proof_id_raw  = str(body.get("proof_id")  or "").strip()
            action_id_raw = str(body.get("action_id") or "").strip()

            # parse confirm — absent=False, bool/string accepted, anything else→400
            confirm, confirm_err = _parse_confirm_strict(body.get("confirm"))
            if confirm is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   confirm_err, request_id=request_id), 400)

            # ── Require at least one reference ───────────────────────────────
            if not proof_id_raw and not action_id_raw:
                return self._send_json(
                    error_response(
                        BridgeErrorCode.UNDO_PROOF_NOT_FOUND,
                        "undo requires proof_id or action_id — both were empty.",
                        request_id=request_id,
                    ),
                    400,
                )

            # ── Look up proof ─────────────────────────────────────────────────
            proofs = read_all_proofs()
            proof  = None
            if proof_id_raw:
                proof = next(
                    (p for p in proofs if p.get("proof_id") == proof_id_raw),
                    None,
                )
                if proof is None:
                    return self._send_json(
                        error_response(
                            BridgeErrorCode.UNDO_PROOF_NOT_FOUND,
                            f"proof_id {proof_id_raw!r} not found in "
                            "action_proof_log.jsonl. "
                            "Verify the proof_id from the original action response.",
                            request_id=request_id,
                        ),
                        404,
                    )
            else:
                proof = next(
                    (p for p in proofs if p.get("action_id") == action_id_raw),
                    None,
                )
                if proof is None:
                    return self._send_json(
                        error_response(
                            BridgeErrorCode.UNDO_PROOF_NOT_FOUND,
                            f"action_id {action_id_raw!r} not found in "
                            "action_proof_log.jsonl.",
                            request_id=request_id,
                        ),
                        404,
                    )

            target_str = proof.get("target", "")

            # ── Ableton connectivity check ────────────────────────────────────
            if not ableton_connected():
                return self._send_json(
                    error_response(
                        BridgeErrorCode.BRIDGE_TIMEOUT,
                        "Ableton MCP not reachable — open Ableton with MCP loaded",
                        request_id=request_id,
                    ),
                    503,
                )

            # ── Log undo requested ────────────────────────────────────────────
            log_requested(
                f"UNDO_{proof.get('action_type', '')}",
                f"undo:{target_str}",
                request_id       = request_id,
                action_id        = action_id,
                session_id       = session_id,
                original_proof_id = proof.get("proof_id", ""),
            )

            # ── Execute undo ──────────────────────────────────────────────────
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))

            try:
                result = execute_undo(
                    proof,
                    ableton_execute,
                    confirm             = confirm,
                    stabilization_delay = delay,
                    request_id          = request_id,
                    session_id          = session_id,
                    project_id          = project_id,
                    action_id           = action_id,
                )
            except UndoValidationError as uve:
                return self._send_json(
                    error_response(
                        uve.bridge_error_code,
                        str(uve),
                        request_id        = request_id,
                        original_proof_id = proof.get("proof_id", ""),
                    ),
                    400,
                )
            except Exception as exc:
                return self._send_json(
                    error_response(
                        BridgeErrorCode.STATE_VERIFICATION_FAILED,
                        f"Unexpected error during undo: {exc}",
                        request_id        = request_id,
                        original_proof_id = proof.get("proof_id", ""),
                    ),
                    500,
                )

            undo_proof = result["undo_proof"]

            # ── Drift blocked (no confirm) — 409 Conflict ─────────────────────
            if result["drift_detected"] and not confirm:
                return self._send_json(
                    {
                        "ok":                  False,
                        "error_code":          BridgeErrorCode.STATE_DRIFT_COLLISION.value,
                        "error":               result["message"],
                        "drift_detected":      True,
                        "drift_state":         result["drift_state"],
                        "undo_proof_id":       undo_proof.proof_id,
                        "original_proof_id":   result["original_proof_id"],
                        "verification_status": result["verification_status"],
                        "request_id":          request_id,
                        "hint":                "Pass confirm=true to undo despite drift.",
                    },
                    409,
                )

            # ── Success or write failure ──────────────────────────────────────
            vstat  = result["verification_status"]
            is_ok  = vstat in ("VERIFIED", "ALREADY_CORRECT")
            self._send_json({
                "ok":                  is_ok,
                "undo_proof_id":       undo_proof.proof_id,
                "original_proof_id":   result["original_proof_id"],
                "verification_status": vstat,
                "drift_detected":      result["drift_detected"],
                "drift_state":         result.get("drift_state", {}),
                "before_state":        undo_proof.before_state,
                "after_state":         undo_proof.after_state,
                "user_facing_summary": undo_proof.user_facing_summary,
                "error_code":          result.get("error_code", ""),
                "request_id":          request_id,
                "session_id":          session_id,
            })

        # ═══════════════════════════════════════════════════════════════════════
        # ACTION EXPANSION — SLICE 1 (Track / Recording)
        # ═══════════════════════════════════════════════════════════════════════

        # ── POST /action/track_arm ─────────────────────────────────────────────
        elif path == "/action/track_arm":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_arm, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required — send {'track': 'TrackName'}",
                                   request_id=request_id, action_id=action_id), 400)

            arm_raw = body.get("arm")
            if arm_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "arm is required — send {'arm': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            arm_bool = bool(arm_raw)
            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("ARM_TRACK", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("ARM_TRACK", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("ARM_TRACK", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_arm(track, arm_bool, ableton_execute,
                                      stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("ARM_TRACK", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("ARM_TRACK", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' {'armed' if arm_bool else 'unarmed'} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' was already {'armed' if arm_bool else 'unarmed'} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track '{track}' arm write sent but readback unavailable."
            else:
                summary = f"Track '{track}' arm change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="ARM_TRACK", target=target_str,
                intended_value=arm_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("ARM_TRACK", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("ARM_TRACK", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("ARM_TRACK", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_monitor ─────────────────────────────────────────
        elif path == "/action/track_monitor":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_monitor, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            mode_raw = body.get("mode")
            if mode_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "mode is required — 0=In, 1=Auto, 2=Off",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                mode_int = int(mode_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"mode must be 0, 1, or 2, got: {mode_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)
            if mode_int not in (0, 1, 2):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"mode must be 0 (In), 1 (Auto), or 2 (Off), got: {mode_int}",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_MONITOR", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_MONITOR", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_MONITOR", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            _mode_names = {0: "In", 1: "Auto", 2: "Off"}
            try:
                rb = verify_track_monitor(track, mode_int, ableton_execute,
                                          stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_MONITOR", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_MONITOR", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error during readback: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            mn = _mode_names.get(mode_int, str(mode_int))
            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' monitoring set to {mn} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' monitoring was already {mn} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track '{track}' monitor write sent but readback unavailable."
            else:
                summary = f"Track '{track}' monitor change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="SET_TRACK_MONITOR", target=target_str,
                intended_value=mode_int,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("SET_TRACK_MONITOR", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_MONITOR", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_MONITOR", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_rename ──────────────────────────────────────────
        elif path == "/action/track_rename":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import (verify_track_rename, _read_track_index,
                                             BeforeStateCaptureError)

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required (name or 0-based index)",
                                   request_id=request_id, action_id=action_id), 400)

            new_name = body.get("name") or body.get("new_name")
            if not new_name:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "name is required — send {'name': 'NewTrackName'}",
                                   request_id=request_id, action_id=action_id), 400)
            new_name = str(new_name)
            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("RENAME_TRACK", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("RENAME_TRACK", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            # Resolve track name → index (index-stable for rename undo)
            if isinstance(track, str):
                track_idx = _read_track_index(track, ableton_execute)
            else:
                track_idx = int(track)
            if track_idx is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   f"Track {track!r} not found in session",
                                   request_id=request_id, action_id=action_id), 404)

            # Use index-based target for undo stability
            index_target = f"track:{track_idx}"

            log_requested("RENAME_TRACK", index_target,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_rename(track_idx, new_name, ableton_execute,
                                         stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("RENAME_TRACK", index_target,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("RENAME_TRACK", index_target,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            # Rename undo not supported — name changes make original target ambiguous
            # without careful index tracking; deferred to a later slice.
            undo_eligible = False

            old_name = rb.get("before_state", {}).get("name", str(track))
            if str(vstat) == "VERIFIED":
                summary = f"Track renamed from '{old_name}' to '{new_name}' — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track was already named '{new_name}' — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track rename sent but readback unavailable."
            else:
                summary = f"Track rename failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="RENAME_TRACK", target=index_target,
                intended_value=new_name,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("RENAME_TRACK", index_target, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("RENAME_TRACK", index_target, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("RENAME_TRACK", index_target,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_color ───────────────────────────────────────────
        elif path == "/action/track_color":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_color, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            color_raw = body.get("color")
            if color_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "color is required — integer in Ableton 0xRRGGBB format",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                color_int = int(color_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"color must be an integer, got: {color_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_COLOR", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_COLOR", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_COLOR", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_color(track, color_int, ableton_execute,
                                        stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_COLOR", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_COLOR", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))
            after_color  = rb.get("after_state", {}).get("color", color_int)

            if str(vstat) == "VERIFIED":
                summary = rb.get("message", f"Track '{track}' color set to #{after_color:06X}.")
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' color was already #{after_color:06X} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track '{track}' color write sent but readback unavailable."
            else:
                summary = f"Track '{track}' color change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="SET_TRACK_COLOR", target=target_str,
                intended_value=color_int,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("SET_TRACK_COLOR", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_COLOR", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_COLOR", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_create ──────────────────────────────────────────
        # Body: {
        #   "type":       optional  — "midi" (default) or "audio"
        #   "name":       optional  — name to assign after creation
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Notes:
        #   - create_audio_track() has a known LOM serialization error; track IS created.
        #     Verified by track count increase.
        #   - undo_eligible=False — structural change, no compensating restore.
        #   - Batch (> _BATCH_THRESHOLD): use /action/tracks_create_multiple.
        elif path == "/action/track_create":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_create, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track_type = str(body.get("type", "midi")).lower()
            track_name = str(body.get("name") or "")
            if track_type not in ("midi", "audio"):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"type must be 'midi' or 'audio', got: {track_type!r}",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"new_{track_type}_track:{track_name or 'unnamed'}"

            ndc_decision, ndc_rule = _ndc_check("CREATE_TRACK", {
                "target": target_str, "track_count": 1})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("CREATE_TRACK", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("CREATE_TRACK", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_create(track_type, ableton_execute,
                                          stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("CREATE_TRACK", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("CREATE_TRACK", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            new_idx      = rb.get("after_state", {}).get("new_track_index")

            # Rename verification — separate from creation proof.
            # Creation proof attests only to count change; rename is verified
            # independently and reported in user_facing_summary + rename_status.
            rename_vstat = None
            if is_confirmed and track_name and new_idx is not None:
                from rag.readback import verify_track_rename
                try:
                    ren_rb = verify_track_rename(new_idx, track_name, ableton_execute,
                                                  stabilization_delay=delay)
                    rename_vstat = ren_rb["verification_status"]
                except BeforeStateCaptureError:
                    rename_vstat = "UNVERIFIED"
                except Exception:
                    rename_vstat = "FAILED"

            if str(vstat) == "VERIFIED":
                if track_name:
                    if rename_vstat in ("VERIFIED", "ALREADY_CORRECT"):
                        name_part = f" '{track_name}'"
                    elif rename_vstat == "UNVERIFIED":
                        name_part = f" (rename to '{track_name}' unverified)"
                    elif rename_vstat == "FAILED":
                        name_part = f" (rename to '{track_name}' failed — track created unnamed)"
                    else:
                        name_part = ""
                else:
                    name_part = ""
                summary = (
                    f"{track_type.upper()} track{name_part} created at index "
                    f"{new_idx} — confirmed."
                )
            elif str(vstat) == "UNVERIFIED":
                summary = "Track create sent but count readback unavailable."
            else:
                summary = f"Track create failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="CREATE_TRACK", target=target_str,
                intended_value=track_type,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,  # structural change
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("CREATE_TRACK", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("CREATE_TRACK", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("CREATE_TRACK", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "rename_status": rename_vstat,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_delete ──────────────────────────────────────────
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "confirm":    required  — must be true; gate requires explicit confirmation
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Rules:
        #   - undo_eligible=False — no compensating restore via LOM
        #   - confirm=true is REQUIRED; without it → 403 SECURITY_CONFIRMATION_REQUIRED
        #   - Verify by track count decrease
        elif path == "/action/track_delete":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_delete, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            confirm, confirm_err = _parse_confirm_strict(body.get("confirm"))
            if confirm is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   confirm_err, request_id=request_id,
                                   action_id=action_id), 400)

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"track:{track}"

            # Never-do preflight — DELETE_TRACK is REQUIRE_CONFIRMATION
            # confirm=True in the body bypasses REQUIRE_CONFIRMATION gate only
            ndc_decision, ndc_rule = _ndc_check("DELETE_TRACK", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                bypass_ok = (
                    ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION and confirm
                )
                if not bypass_ok:
                    decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                    log_never_do_blocked("DELETE_TRACK", target_str, decision_value,
                                         request_id=request_id, action_id=action_id,
                                         session_id=session_id, rule_text=ndc_rule)
                    if ndc_decision == NeverDoDecision.HARD_BLOCK:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                    elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                            f"Track delete requires confirm=true. Track: '{track}'", 403)
                    elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                            f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                    else:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                    return self._send_json(
                        error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                       rule_text=ndc_rule, request_id=request_id,
                                       action_id=action_id, session_id=session_id), _ndc_http)
                # else: bypass_ok — confirmed, continue

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("DELETE_TRACK", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_delete(track, ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("DELETE_TRACK", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("DELETE_TRACK", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            track_name   = rb.get("before_state", {}).get("track_name", str(track))

            if str(vstat) == "VERIFIED":
                summary = (
                    f"Track '{track_name}' deleted — confirmed. "
                    "This cannot be undone by Conductor."
                )
            elif str(vstat) == "UNVERIFIED":
                summary = f"Delete sent but count readback unavailable."
            else:
                summary = f"Track delete failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="DELETE_TRACK", target=target_str,
                intended_value=str(track),
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("DELETE_TRACK", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("DELETE_TRACK", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("DELETE_TRACK", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_duplicate ───────────────────────────────────────
        elif path == "/action/track_duplicate":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_duplicate, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            target_str = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("DUPLICATE_TRACK", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("DUPLICATE_TRACK", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("DUPLICATE_TRACK", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_duplicate(track, ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("DUPLICATE_TRACK", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("DUPLICATE_TRACK", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            src_name     = rb.get("before_state", {}).get("source_track_name", str(track))
            new_idx      = rb.get("after_state", {}).get("new_track_index")

            if str(vstat) == "VERIFIED":
                summary = (
                    f"Track '{src_name}' duplicated at index {new_idx}. "
                    "Undo not available for structural changes."
                )
            elif str(vstat) == "UNVERIFIED":
                summary = f"Duplicate sent but count readback unavailable."
            else:
                summary = f"Track duplicate failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="DUPLICATE_TRACK", target=target_str,
                intended_value=str(track),
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("DUPLICATE_TRACK", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("DUPLICATE_TRACK", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("DUPLICATE_TRACK", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/return_track_create ───────────────────────────────────
        elif path == "/action/return_track_create":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_return_track_create, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            target_str = "return_track:new"

            ndc_decision, ndc_rule = _ndc_check("CREATE_RETURN_TRACK", {"target": target_str})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("CREATE_RETURN_TRACK", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing. Rule: {ndc_rule}", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("CREATE_RETURN_TRACK", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_return_track_create(ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("CREATE_RETURN_TRACK", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("CREATE_RETURN_TRACK", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            new_r_idx    = rb.get("after_state", {}).get("new_return_track_index")

            if str(vstat) == "VERIFIED":
                summary = f"Return track created at index {new_r_idx} — confirmed."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Return track create sent but count readback unavailable."
            else:
                summary = f"Return track create failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="CREATE_RETURN_TRACK", target=target_str,
                intended_value="return_track",
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("CREATE_RETURN_TRACK", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("CREATE_RETURN_TRACK", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("CREATE_RETURN_TRACK", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/tracks_create_multiple ───────────────────────────────
        # Body: {
        #   "count":      required  — number of tracks to create (int, 1–20)
        #   "type":       optional  — "midi" (default) or "audio"
        #   "names":      optional  — list of names, parallel to count
        #   "confirm":    required when count > 3 (batch threshold)
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Rules:
        #   - count > 3: REQUIRE_CONFIRMATION; needs confirm=true in body
        #   - Each track creation is individually verified
        #   - Returns all per-track results + overall ok
        #   - undo_eligible=False for all created tracks
        elif path == "/action/tracks_create_multiple":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision, _BATCH_THRESHOLD
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import (verify_track_create, verify_track_rename,
                                            _read_track_count, BeforeStateCaptureError)

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            confirm, confirm_err = _parse_confirm_strict(body.get("confirm"))
            if confirm is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   confirm_err, request_id=request_id,
                                   action_id=action_id), 400)

            count_raw = body.get("count")
            if count_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "count is required — number of tracks to create",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                track_count = int(count_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"count must be an integer, got: {count_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)
            if not (1 <= track_count <= 20):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"count must be 1–20, got: {track_count}",
                                   request_id=request_id, action_id=action_id), 400)

            track_type = str(body.get("type", "midi")).lower()
            if track_type not in ("midi", "audio"):
                track_type = "midi"
            names_list = body.get("names") or []
            target_str = f"batch_create:{track_count}_{track_type}_tracks"

            # Never-do preflight — batch escalates when count > threshold
            ndc_decision, ndc_rule = _ndc_check("CREATE_TRACK", {
                "target": target_str, "track_count": track_count})
            if ndc_decision != NeverDoDecision.ALLOW:
                bypass_ok = (
                    ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION and confirm
                )
                if not bypass_ok:
                    decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                    log_never_do_blocked("CREATE_TRACK", target_str, decision_value,
                                         request_id=request_id, action_id=action_id,
                                         session_id=session_id, rule_text=ndc_rule)
                    if ndc_decision == NeverDoDecision.HARD_BLOCK:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                    elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                            f"Creating {track_count} tracks at once — send confirm=true to proceed.",
                            403)
                    elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                            f"Action intent unclear. Rule: {ndc_rule}", 400)
                    else:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                    return self._send_json(
                        error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                       rule_text=ndc_rule, request_id=request_id,
                                       action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("BATCH_CREATE_TRACKS", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))

            # Read batch-level before_state before any creates
            batch_before_count = _read_track_count(ableton_execute)
            batch_before_state = (
                {"track_count": batch_before_count}
                if batch_before_count is not None
                else {}
            )

            # Create tracks sequentially — each verified individually
            results     = []
            all_ok      = True
            for i in range(track_count):
                name_i = names_list[i] if i < len(names_list) else ""
                per_target = f"new_{track_type}_track_{i}:{name_i or 'unnamed'}"
                try:
                    rb_i = verify_track_create(track_type, ableton_execute,
                                               stabilization_delay=delay)
                except BeforeStateCaptureError as bsce:
                    rb_i = {
                        "verification_status": "FAILED",
                        "before_state": {}, "after_state": {},
                        "error_code": BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                        "intended_value": track_type,
                        "message": str(bsce),
                    }
                except Exception as exc:
                    rb_i = {
                        "verification_status": "FAILED",
                        "before_state": {}, "after_state": {},
                        "error_code": BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                        "intended_value": track_type,
                        "message": str(exc),
                    }
                vstat_i   = rb_i["verification_status"]
                ok_i      = vstat_i in ("VERIFIED", "ALREADY_CORRECT")
                new_idx_i = rb_i.get("after_state", {}).get("new_track_index")

                # Rename verification — separate from creation proof (same honesty
                # contract as /action/track_create)
                rename_vstat_i = None
                if ok_i and name_i and new_idx_i is not None:
                    try:
                        ren_rb_i = verify_track_rename(new_idx_i, name_i,
                                                        ableton_execute,
                                                        stabilization_delay=delay)
                        rename_vstat_i = ren_rb_i["verification_status"]
                    except BeforeStateCaptureError:
                        rename_vstat_i = "UNVERIFIED"
                    except Exception:
                        rename_vstat_i = "FAILED"

                if ok_i:
                    proof_i = create_proof(
                        action_type="CREATE_TRACK",
                        target=per_target,
                        intended_value=track_type,
                        before_state=rb_i.get("before_state", {}),
                        after_state=rb_i.get("after_state", {}),
                        verification_status=vstat_i,
                        undo_eligible=False,
                        user_facing_summary=rb_i.get("message", ""),
                        action_id=f"{action_id}_{i}", request_id=request_id,
                        session_id=session_id, project_id=project_id)
                    log_verified("CREATE_TRACK", per_target,
                                 proof_i.proof_id, vstat_i,
                                 request_id=request_id, action_id=f"{action_id}_{i}",
                                 session_id=session_id)
                    results.append({
                        "track_index": i, "ok": True,
                        "proof_id": proof_i.proof_id,
                        "new_track_index": new_idx_i,
                        "name": name_i,
                        "rename_status": rename_vstat_i,
                        "verification_status": vstat_i,
                    })
                else:
                    all_ok = False
                    log_failed("CREATE_TRACK", per_target,
                               rb_i.get("error_code",
                                        BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                               request_id=request_id, action_id=f"{action_id}_{i}",
                               session_id=session_id,
                               message=rb_i.get("message", ""))
                    results.append({
                        "track_index": i, "ok": False,
                        "verification_status": vstat_i,
                        "error_code": rb_i.get("error_code", ""),
                        "message": rb_i.get("message", ""),
                        "name": name_i,
                    })

            created = sum(1 for r in results if r["ok"])
            # Batch after_state derived from created count
            batch_after_count = (
                (batch_before_count + created)
                if batch_before_count is not None
                else None
            )
            batch_after_state = (
                {"track_count": batch_after_count, "tracks_created": created}
                if batch_after_count is not None
                else {"tracks_created": created}
            )
            batch_vstat = "VERIFIED" if all_ok else "FAILED"

            summary = (
                f"{created}/{track_count} {track_type.upper()} tracks created — "
                f"{'all confirmed' if all_ok else 'some failed'}. "
                "Undo not available for structural changes."
            )

            # Top-level ActionProof covers the entire batch
            batch_proof = create_proof(
                action_type="BATCH_CREATE_TRACKS",
                target=target_str,
                intended_value=track_count,
                before_state=batch_before_state,
                after_state=batch_after_state,
                verification_status=batch_vstat,
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if all_ok:
                log_verified("BATCH_CREATE_TRACKS", target_str,
                             batch_proof.proof_id, batch_vstat,
                             request_id=request_id, action_id=action_id,
                             session_id=session_id)
            else:
                log_failed("BATCH_CREATE_TRACKS", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           proof_id=batch_proof.proof_id,
                           request_id=request_id, action_id=action_id,
                           session_id=session_id,
                           message=f"{created}/{track_count} tracks created")

            self._send_json({
                "ok": all_ok,
                "proof_id": batch_proof.proof_id,
                "verification_status": batch_vstat,
                "before_state": batch_before_state,
                "after_state": batch_after_state,
                "undo_eligible": False,
                "tracks_requested": track_count,
                "tracks_created": created,
                "results": results,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "user_facing_summary": summary,
            })

        # ── POST /action/track_route ───────────────────────────────────────────
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "routing":    required  — output routing display name (str)
        #   "confirm":    required  — SET_TRACK_ROUTE is REQUIRE_CONFIRMATION;
        #                            must be true to proceed
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Rules:
        #   - undo_eligible=True  (restore before routing on undo)
        #   - confirm=true is REQUIRED without it → 403
        elif path == "/action/track_route":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_route, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            confirm, confirm_err = _parse_confirm_strict(body.get("confirm"))
            if confirm is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   confirm_err,
                                   request_id=request_id, action_id=action_id), 400)

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            routing = body.get("routing")
            if not routing:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "routing is required — supply the output routing display name",
                                   request_id=request_id, action_id=action_id), 400)

            routing_str = str(routing).strip()
            target_str  = f"track:{track}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_ROUTE", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                bypass_ok = (ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION and confirm)
                if not bypass_ok:
                    decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                    log_never_do_blocked("SET_TRACK_ROUTE", target_str, decision_value,
                                         request_id=request_id, action_id=action_id,
                                         session_id=session_id, rule_text=ndc_rule)
                    if ndc_decision == NeverDoDecision.HARD_BLOCK:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                    elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                            f"Output routing change requires confirm=true. Track: '{track}'", 403)
                    elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                            f"Action intent unclear — clarify before executing.", 400)
                    else:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                    return self._send_json(
                        error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                       rule_text=ndc_rule, request_id=request_id,
                                       action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            # Pre-flight: validate routing destination is in available_output_routing_types
            # before any write.  Gracefully degrades if the check itself fails (e.g. track not
            # found → empty list → skip) so verify_track_route can raise BeforeStateCaptureError.
            try:
                if isinstance(track, int):
                    _avail_code = (
                        f"[rt.display_name for rt in "
                        f"song.tracks[{track}].available_output_routing_types]"
                    )
                else:
                    _esc_n = str(track).replace("\\", "\\\\").replace('"', '\\"')
                    _avail_code = (
                        f"next(("
                        f"[rt.display_name for rt in t.available_output_routing_types] "
                        f"for t in song.tracks if t.name == \"{_esc_n}\"), [])"
                    )
                _avail_resp = ableton_execute(_avail_code)
                if _avail_resp.get("ok"):
                    _available = _avail_resp.get("data", {}).get("result")
                    if (isinstance(_available, list)
                            and len(_available) > 0
                            and routing_str not in _available):
                        log_failed("SET_TRACK_ROUTE", target_str,
                                   BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE.value,
                                   request_id=request_id, action_id=action_id,
                                   message=f"routing '{routing_str}' not in available_output_routing_types")
                        return self._send_json(
                            error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                           f"Routing '{routing_str}' is not available for track "
                                           f"'{track}'. No write sent.",
                                           request_id=request_id, action_id=action_id,
                                           undo_eligible=False), 400)
            except Exception:
                pass  # availability check failure → graceful degradation; proceed to verify

            log_requested("SET_TRACK_ROUTE", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_route(track, routing_str, ableton_execute,
                                        stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_ROUTE", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_ROUTE", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' output routing set to '{routing_str}' — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' output routing was already '{routing_str}' — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track '{track}' routing write sent but readback unavailable."
            else:
                summary = f"Track '{track}' routing change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="SET_TRACK_ROUTE", target=target_str,
                intended_value=routing_str,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("SET_TRACK_ROUTE", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_ROUTE", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_ROUTE", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/track_send ────────────────────────────────────────────
        # Body: {
        #   "track":      required  — track name (str) or 0-based index (int)
        #   "send":       required  — send slot index (int, 0-based)
        #   "value":      required  — normalized level 0.0–1.0
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Rules:
        #   - undo_eligible=True  (restore before send level)
        elif path == "/action/track_send":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_track_send, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            send_raw = body.get("send")
            if send_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "send is required — 0-based send slot index",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                send_idx = int(send_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"send must be an integer, got: {send_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)

            if send_idx < 0:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"send index must be >= 0, got: {send_idx}",
                                   request_id=request_id, action_id=action_id), 400)

            value_raw = body.get("value")
            if value_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "value is required — normalized 0.0–1.0",
                                   request_id=request_id, action_id=action_id), 400)
            try:
                send_value = float(value_raw)
            except (TypeError, ValueError):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"value must be numeric, got: {value_raw!r}",
                                   request_id=request_id, action_id=action_id), 400)

            if not (0.0 <= send_value <= 1.0):
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"value must be in range 0.0–1.0, got: {send_value!r}",
                                   request_id=request_id, action_id=action_id), 400)

            # target encodes track + send index for undo lookup
            target_str = f"track:{track}:send:{send_idx}"

            ndc_decision, ndc_rule = _ndc_check("SET_TRACK_SEND", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("SET_TRACK_SEND", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Action requires explicit confirmation. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.CLARIFY_REQUIRED:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CLARIFY_REQUIRED,
                        f"Action intent unclear — clarify before executing.", 400)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("SET_TRACK_SEND", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_track_send(track, send_idx, send_value, ableton_execute,
                                       stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("SET_TRACK_SEND", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("SET_TRACK_SEND", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Track '{track}' send[{send_idx}] set to {send_value:.3f} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Track '{track}' send[{send_idx}] was already {send_value:.3f} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Track '{track}' send[{send_idx}] write sent but readback unavailable."
            else:
                summary = f"Track '{track}' send[{send_idx}] change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="SET_TRACK_SEND", target=target_str,
                intended_value=send_value,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("SET_TRACK_SEND", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("SET_TRACK_SEND", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("SET_TRACK_SEND", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/transport_play ────────────────────────────────────────
        # Body: {session_id, project_id}
        # Rules:
        #   - undo_eligible=False (play position cannot be meaningfully restored)
        elif path == "/action/transport_play":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_transport_play, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            target_str = "song"

            ndc_decision, ndc_rule = _ndc_check("TRANSPORT_PLAY", {})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("TRANSPORT_PLAY", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                _ndc_ec = BridgeErrorCode.SECURITY_NEVER_DO_BLOCK
                _ndc_msg = f"Action blocked by never-do rules. Rule: {ndc_rule}"
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), 403)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("TRANSPORT_PLAY", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_transport_play(ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("TRANSPORT_PLAY", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("TRANSPORT_PLAY", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")

            if str(vstat) == "VERIFIED":
                summary = "Playback started — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = "Transport was already playing — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = "Playback started but is_playing could not be confirmed."
            else:
                summary = f"Playback failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="TRANSPORT_PLAY", target=target_str,
                intended_value=True,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("TRANSPORT_PLAY", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("TRANSPORT_PLAY", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("TRANSPORT_PLAY", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/transport_stop ────────────────────────────────────────
        # Body: {session_id, project_id}
        # Rules:
        #   - undo_eligible=False
        elif path == "/action/transport_stop":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_transport_stop, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            target_str = "song"

            ndc_decision, ndc_rule = _ndc_check("TRANSPORT_STOP", {})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("TRANSPORT_STOP", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                return self._send_json(
                    error_response(BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                                   f"Action blocked. Rule: {ndc_rule}", decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), 403)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("TRANSPORT_STOP", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_transport_stop(ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("TRANSPORT_STOP", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("TRANSPORT_STOP", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")

            if str(vstat) == "VERIFIED":
                summary = "Playback stopped — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = "Transport was already stopped — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = "Stop sent but is_playing could not be confirmed."
            else:
                summary = f"Stop failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="TRANSPORT_STOP", target=target_str,
                intended_value=False,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("TRANSPORT_STOP", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("TRANSPORT_STOP", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("TRANSPORT_STOP", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/transport_record ──────────────────────────────────────
        # Body: {
        #   "record":     required  — bool (True = enable record mode)
        #   "confirm":    required  — TRANSPORT_RECORD is REQUIRE_CONFIRMATION
        #   "session_id": optional
        #   "project_id": optional
        # }
        # Rules:
        #   - undo_eligible=False (toggling record_mode back is low-value vs risk)
        elif path == "/action/transport_record":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_transport_record, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")
            confirm, confirm_err = _parse_confirm_strict(body.get("confirm"))
            if confirm is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   confirm_err,
                                   request_id=request_id, action_id=action_id), 400)

            record_raw = body.get("record")
            if record_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "record is required — send {'record': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            record_bool, rec_err = _parse_bool_strict(record_raw, "record")
            if record_bool is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE, rec_err,
                                   request_id=request_id, action_id=action_id), 400)

            target_str = "song"

            ndc_decision, ndc_rule = _ndc_check("TRANSPORT_RECORD", {})
            if ndc_decision != NeverDoDecision.ALLOW:
                bypass_ok = (ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION and confirm)
                if not bypass_ok:
                    decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                    log_never_do_blocked("TRANSPORT_RECORD", target_str, decision_value,
                                         request_id=request_id, action_id=action_id,
                                         session_id=session_id, rule_text=ndc_rule)
                    if ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                            "Transport record requires confirm=true.", 403)
                    else:
                        _ndc_ec, _ndc_msg, _ndc_http = (
                            BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                            f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                    return self._send_json(
                        error_response(_ndc_ec, _ndc_msg,
                                       decision=getattr(ndc_decision, "value", str(ndc_decision)),
                                       rule_text=ndc_rule, request_id=request_id,
                                       action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("TRANSPORT_RECORD", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_transport_record(record_bool, ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("TRANSPORT_RECORD", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("TRANSPORT_RECORD", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            mode_str     = "enabled" if record_bool else "disabled"

            if str(vstat) == "VERIFIED":
                summary = f"Record mode {mode_str} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Record mode was already {mode_str} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Record mode write sent but readback unavailable."
            else:
                summary = f"Record mode change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="TRANSPORT_RECORD", target=target_str,
                intended_value=record_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=False,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("TRANSPORT_RECORD", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("TRANSPORT_RECORD", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("TRANSPORT_RECORD", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": False,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/transport_loop ────────────────────────────────────────
        # Body: {loop: bool, session_id, project_id}
        # Rules:
        #   - undo_eligible=True  (restore before loop state)
        elif path == "/action/transport_loop":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_transport_loop, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            loop_raw = body.get("loop")
            if loop_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "loop is required — send {'loop': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            loop_bool, loop_err = _parse_bool_strict(loop_raw, "loop")
            if loop_bool is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE, loop_err,
                                   request_id=request_id, action_id=action_id), 400)

            target_str = "song"

            ndc_decision, ndc_rule = _ndc_check("TRANSPORT_LOOP", {})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("TRANSPORT_LOOP", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                return self._send_json(
                    error_response(BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                                   f"Action blocked. Rule: {ndc_rule}", decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), 403)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("TRANSPORT_LOOP", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_transport_loop(loop_bool, ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("TRANSPORT_LOOP", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("TRANSPORT_LOOP", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Loop {'enabled' if loop_bool else 'disabled'} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Loop was already {'on' if loop_bool else 'off'} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = "Loop write sent but readback unavailable."
            else:
                summary = f"Loop change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="TRANSPORT_LOOP", target=target_str,
                intended_value=loop_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("TRANSPORT_LOOP", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("TRANSPORT_LOOP", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("TRANSPORT_LOOP", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/transport_metronome ───────────────────────────────────
        # Body: {metronome: bool, session_id, project_id}
        # Rules:
        #   - undo_eligible=True  (restore before metronome state)
        elif path == "/action/transport_metronome":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_transport_metronome, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            metro_raw = body.get("metronome")
            if metro_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "metronome is required — send {'metronome': true|false}",
                                   request_id=request_id, action_id=action_id), 400)
            metro_bool, metro_err = _parse_bool_strict(metro_raw, "metronome")
            if metro_bool is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE, metro_err,
                                   request_id=request_id, action_id=action_id), 400)

            target_str = "song"

            ndc_decision, ndc_rule = _ndc_check("TRANSPORT_METRONOME", {})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("TRANSPORT_METRONOME", target_str, decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                return self._send_json(
                    error_response(BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                                   f"Action blocked. Rule: {ndc_rule}", decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), 403)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("TRANSPORT_METRONOME", target_str,
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_transport_metronome(metro_bool, ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("TRANSPORT_METRONOME", target_str,
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("TRANSPORT_METRONOME", target_str,
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            is_confirmed = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))

            if str(vstat) == "VERIFIED":
                summary = f"Metronome {'enabled' if metro_bool else 'disabled'} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                summary = f"Metronome was already {'on' if metro_bool else 'off'} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = "Metronome write sent but readback unavailable."
            else:
                summary = f"Metronome change failed: {rb.get('message', '')}"

            proof = create_proof(
                action_type="TRANSPORT_METRONOME", target=target_str,
                intended_value=metro_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("TRANSPORT_METRONOME", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("TRANSPORT_METRONOME", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("TRANSPORT_METRONOME", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /action/plugin_bypass ─────────────────────────────────────────
        # Body: {
        #   "track":       required — track name (str) or 0-based index (int)
        #   "device_name": required — partial device name (case-insensitive substring)
        #   "bypass":      required — bool; true=bypass (is_active=False), false=activate
        #   "session_id":  optional
        #   "project_id":  optional
        # }
        # Rules:
        #   - undo_eligible=True when VERIFIED or ALREADY_CORRECT
        #   - verification_source: ableton_lom
        #   - NeverDo: ALLOW by default (no REQUIRE_CONFIRMATION gate)
        elif path == "/action/plugin_bypass":
            from rag.bridge_errors  import BridgeErrorCode, error_response
            from rag.never_do_check import check as _ndc_check, NeverDoDecision
            from rag.black_box_log  import (log_requested, log_verified,
                                             log_failed, log_unverified,
                                             log_never_do_blocked)
            from rag.action_proof   import create_proof
            from rag.readback       import verify_plugin_bypass, BeforeStateCaptureError

            request_id = _new_request_id()
            action_id  = _new_action_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            track = body.get("track")
            if track is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TRACK_ABSENT,
                                   "track is required",
                                   request_id=request_id, action_id=action_id), 400)

            device_name = body.get("device_name")
            if not device_name:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "device_name is required — partial name for matching",
                                   request_id=request_id, action_id=action_id), 400)

            bypass_raw = body.get("bypass")
            if bypass_raw is None:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   "bypass is required — bool: true=bypass, false=activate",
                                   request_id=request_id, action_id=action_id), 400)

            if isinstance(bypass_raw, bool):
                bypass_bool = bypass_raw
            elif isinstance(bypass_raw, str):
                if bypass_raw.lower() == "true":
                    bypass_bool = True
                elif bypass_raw.lower() == "false":
                    bypass_bool = False
                else:
                    return self._send_json(
                        error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                       f"bypass must be true or false, got: {bypass_raw!r}",
                                       request_id=request_id, action_id=action_id), 400)
            else:
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PARAM_OUT_OF_RANGE,
                                   f"bypass must be a boolean, got: {type(bypass_raw).__name__}",
                                   request_id=request_id, action_id=action_id), 400)
            is_active_val   = not bypass_bool   # bypass=True → is_active=False
            device_name_str = str(device_name).strip()

            ndc_decision, ndc_rule = _ndc_check("PLUGIN_BYPASS", {"target": str(track)})
            if ndc_decision != NeverDoDecision.ALLOW:
                decision_value = getattr(ndc_decision, "value", str(ndc_decision))
                log_never_do_blocked("PLUGIN_BYPASS", f"track:{track}", decision_value,
                                     request_id=request_id, action_id=action_id,
                                     session_id=session_id, rule_text=ndc_rule)
                if ndc_decision == NeverDoDecision.HARD_BLOCK:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Action blocked by never-do rules. Rule: {ndc_rule}", 403)
                elif ndc_decision == NeverDoDecision.REQUIRE_CONFIRMATION:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_CONFIRMATION_REQUIRED,
                        f"Plugin bypass requires confirm=true. Track: '{track}'", 403)
                else:
                    _ndc_ec, _ndc_msg, _ndc_http = (
                        BridgeErrorCode.SECURITY_NEVER_DO_BLOCK,
                        f"Unknown never-do decision {ndc_decision!r} — failing closed.", 403)
                return self._send_json(
                    error_response(_ndc_ec, _ndc_msg, decision=decision_value,
                                   rule_text=ndc_rule, request_id=request_id,
                                   action_id=action_id, session_id=session_id), _ndc_http)

            if not ableton_connected():
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_TIMEOUT,
                                   "Ableton MCP not reachable",
                                   request_id=request_id, action_id=action_id), 503)

            log_requested("PLUGIN_BYPASS", f"track:{track}",
                          request_id=request_id, action_id=action_id, session_id=session_id)
            cfg   = load_config()
            delay = float(cfg.get("readback_stabilization_delay", 0.25))
            try:
                rb = verify_plugin_bypass(track, device_name_str, is_active_val,
                                          ableton_execute, stabilization_delay=delay)
            except BeforeStateCaptureError as bsce:
                log_failed("PLUGIN_BYPASS", f"track:{track}",
                           BridgeErrorCode.STATE_CAPTURE_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(bsce))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_CAPTURE_FAILED, str(bsce),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 500)
            except Exception as exc:
                log_failed("PLUGIN_BYPASS", f"track:{track}",
                           BridgeErrorCode.STATE_VERIFICATION_FAILED.value,
                           request_id=request_id, action_id=action_id, message=str(exc))
                return self._send_json(
                    error_response(BridgeErrorCode.STATE_VERIFICATION_FAILED,
                                   f"Unexpected error: {exc}",
                                   request_id=request_id, action_id=action_id), 500)

            vstat        = rb["verification_status"]
            matched_name = rb.get("matched_device_name") or device_name_str
            target_str   = f"track:{track}:device:{matched_name}"

            # Device not found — return 400 before creating any proof
            if rb.get("error_code") == BridgeErrorCode.BRIDGE_PLUGIN_ABSENT.value:
                log_failed("PLUGIN_BYPASS", target_str,
                           BridgeErrorCode.BRIDGE_PLUGIN_ABSENT.value,
                           request_id=request_id, action_id=action_id,
                           message=rb.get("message", ""))
                return self._send_json(
                    error_response(BridgeErrorCode.BRIDGE_PLUGIN_ABSENT,
                                   rb.get("message", f"Device '{device_name_str}' not found"),
                                   request_id=request_id, action_id=action_id,
                                   undo_eligible=False), 400)

            is_confirmed  = str(vstat) in ("VERIFIED", "ALREADY_CORRECT")
            undo_eligible = is_confirmed and bool(rb.get("before_state"))
            action_word   = "bypassed" if not is_active_val else "activated"

            if str(vstat) == "VERIFIED":
                summary = f"Device '{matched_name}' on '{track}' {action_word} — confirmed."
            elif str(vstat) == "ALREADY_CORRECT":
                already = "already bypassed" if not is_active_val else "already active"
                summary = f"Device '{matched_name}' on '{track}' was {already} — no change."
            elif str(vstat) == "UNVERIFIED":
                summary = f"Bypass write sent for '{matched_name}' but readback unavailable."
            else:
                summary = f"Bypass failed for '{matched_name}': {rb.get('message', '')}"

            proof = create_proof(
                action_type="PLUGIN_BYPASS", target=target_str,
                intended_value=bypass_bool,
                before_state=rb.get("before_state", {}),
                after_state=rb.get("after_state", {}),
                verification_status=str(vstat),
                undo_eligible=undo_eligible,
                user_facing_summary=summary,
                action_id=action_id, request_id=request_id,
                session_id=session_id, project_id=project_id)

            if is_confirmed:
                log_verified("PLUGIN_BYPASS", target_str, proof.proof_id, str(vstat),
                             request_id=request_id, action_id=action_id, session_id=session_id)
            elif str(vstat) == "UNVERIFIED":
                log_unverified("PLUGIN_BYPASS", target_str, proof.proof_id,
                               request_id=request_id, action_id=action_id, session_id=session_id)
            else:
                log_failed("PLUGIN_BYPASS", target_str,
                           rb.get("error_code", BridgeErrorCode.STATE_VERIFICATION_FAILED.value),
                           proof_id=proof.proof_id, request_id=request_id,
                           action_id=action_id, session_id=session_id, message=rb.get("message", ""))

            self._send_json({
                "ok": is_confirmed, "proof_id": proof.proof_id,
                "action_id": action_id, "request_id": request_id, "session_id": session_id,
                "verification_status": str(vstat),
                "error_code": rb.get("error_code", ""),
                "matched_device_name": matched_name,
                "before_state": rb.get("before_state", {}),
                "after_state": rb.get("after_state", {}),
                "undo_eligible": undo_eligible,
                "user_facing_summary": summary,
                "message": rb.get("message", ""),
            })

        # ── POST /feedback ────────────────────────────────────────────────────
        # Phase D Slice 3 — user feedback on a completed write action.
        #
        # Body: {
        #   "feedback_type": required — KEEP | UNDO | TOO_MUCH | NOT_ENOUGH |
        #                               WRONG_DIRECTION
        #   "proof_id":      optional* — ActionProof ID (from action_proof_log)
        #   "action_id":     optional* — action ID (from action_log or proof)
        #   "session_id":    optional  — caller session ID
        #   "project_id":    optional  — project name
        #   "message":       optional  — human note
        #
        #   * At least one of proof_id or action_id must be supplied.
        # }
        #
        # Rules:
        #   - proof_id must exist in action_proof_log.jsonl if supplied
        #   - action_id must exist in action_log or action_proof_log if proof_id absent
        #   - promotion_eligible is always False in Slice 3
        #   - does NOT write to ChromaDB; does NOT touch Phase C logs
        elif path == "/feedback":
            from rag.bridge_errors import BridgeErrorCode, error_response
            from rag.feedback import (
                create_feedback, FeedbackValidationError,
                ALLOWED_FEEDBACK_TYPES,
            )

            request_id = _new_request_id()
            session_id = body.get("session_id") or _SESSION_ID
            project_id = str(body.get("project_id") or "")

            feedback_type_raw = str(body.get("feedback_type") or "").strip()
            if not feedback_type_raw:
                return self._send_json(
                    error_response(
                        BridgeErrorCode.FEEDBACK_INVALID_TYPE,
                        "feedback_type is required — one of: "
                        f"{sorted(ALLOWED_FEEDBACK_TYPES)}",
                        request_id=request_id,
                    ),
                    400,
                )

            proof_id  = str(body.get("proof_id")  or "").strip()
            action_id = str(body.get("action_id") or "").strip()
            message   = str(body.get("message")   or "").strip()

            try:
                record = create_feedback(
                    feedback_type_raw,
                    proof_id   = proof_id,
                    action_id  = action_id,
                    request_id = request_id,
                    session_id = session_id,
                    project_id = project_id,
                    message    = message,
                )
            except FeedbackValidationError as fve:
                return self._send_json(
                    error_response(
                        fve.bridge_error_code,
                        str(fve),
                        request_id=request_id,
                    ),
                    400,
                )
            except Exception as exc:
                return self._send_json(
                    error_response(
                        BridgeErrorCode.STATE_VERIFICATION_FAILED,
                        f"Unexpected error storing feedback: {exc}",
                        request_id=request_id,
                    ),
                    500,
                )

            self._send_json({
                "ok":                            True,
                "feedback_id":                   record.feedback_id,
                "proof_id":                      record.proof_id,
                "action_id":                     record.action_id,
                "feedback_type":                 record.feedback_type,
                "request_id":                    request_id,
                "session_id":                    session_id,
                "verification_status_at_feedback": record.verification_status_at_feedback,
                "promotion_eligible":             record.promotion_eligible,
                "message":                       record.message,
            })

        else:
            self._send_json({"error": f"unknown endpoint: {path}"}, 404)

    def log_message(self, fmt, *args):
        # Compact log: timestamp + route only
        msg = fmt % args
        print(f"  [{time.strftime('%H:%M:%S')}] {msg}", flush=True)

# ── MAIN ──────────────────────────────────────────────────────────────────────

def seed_failure_cases():
    """
    Vault seeder — idempotent. Safe to call on every startup.

    Reads conductor-vault/failure-cases/ableton_lom_failures.md and upserts
    each ## F00N section into failure_cases_index with a STABLE ID (vault_f001,
    vault_f002, …). Stable IDs mean:
      - Re-running repairs a partial collection without duplicates.
      - Updating the vault markdown updates the stored document on next start.
      - Collection count > 0 is NOT a skip signal — we always upsert.

    Returns the number of entries upserted (0 if vault file not found).
    """
    if not CHROMA_AVAILABLE:
        return 0

    col = get_collection("failure")
    if col is None:
        return 0

    vault_path = os.path.join(
        os.path.dirname(__file__), "..", "conductor-vault", "failure-cases", "ableton_lom_failures.md"
    )
    if not os.path.exists(vault_path):
        return 0

    with open(vault_path, "r", encoding="utf-8") as f:
        content = f.read()

    import re as _re

    # ── Purge stale IDs (time-based IDs from old seeder versions) ────────────
    # Stable IDs look like: vault_f001  (no timestamp suffix)
    # Stale IDs look like:  vault_f001_1779537210773
    _stable_pat = _re.compile(r"^vault_f\d+$")
    try:
        all_ids = col.get(include=[])["ids"]
        stale   = [i for i in all_ids if not _stable_pat.match(i)]
        if stale:
            col.delete(ids=stale)
    except Exception:
        pass

    # Split on --- separators (each failure = one section)
    sections = [s.strip() for s in content.split("\n---\n") if s.strip()]
    upserted = 0

    for section in sections:
        lines = section.splitlines()
        if not lines:
            continue

        title_line = lines[0].strip()
        if not title_line.startswith("## F"):
            continue  # skip preamble / footer

        code_match   = _re.match(r"## (F\d+)", title_line)
        failure_code = code_match.group(1) if code_match else ""
        if not failure_code:
            continue

        is_never_do   = any("never do" in l.lower() for l in lines)
        confirmed_fix = any(
            "confirmed" in l.lower() and "yes" in l.lower()
            for l in lines
        )

        meta = make_metadata("failure_cases_index", {
            "memory_level":    4 if is_never_do else 2,
            "source_type":     "confirmed_fix" if confirmed_fix else "lom_failure",
            "failure_code":    failure_code,
            "ableton_version": "12.4",
            "confirmed_fix":   confirmed_fix,
            "confidence":      1.0 if confirmed_fix else 0.8,
            "approved":        True,
        })

        # Stable ID — derived from failure code, not time-based.
        # upsert() updates document + metadata if ID already exists.
        stable_id = f"vault_{failure_code.lower()}"
        try:
            col.upsert(documents=[section], ids=[stable_id], metadatas=[meta])
            upserted += 1
        except Exception:
            pass

    return upserted


def main():
    print(f"""
╔══════════════════════════════════════════════╗
║       Conductor Bridge v2.0 (Phase D S6)     ║
║  http://localhost:{BRIDGE_PORT}  ·  Ctrl+C to stop   ║
╠══════════════════════════════════════════════╣
║  /ping                    → health check     ║
║  /status                  → all services     ║
║  /ableton                 → execute in LOM   ║
║  /notebooklm              → query NLM        ║
║  /analyze                 → audio analyzer   ║
║  GET  /memory             → search ChromaDB  ║
║  POST /memory             → save to ChromaDB ║
║  GET  /context/ableton    → load ableton.md  ║
║  POST /context/ableton    → write fix        ║
║  GET  /context/session    → session layer B  ║
║  GET  /context/pack       → message layer C  ║
║  GET  /context/system_prompt → system layer A║
║  POST /errors             → log silently     ║
║  GET  /route              → semantic routing ║
║  ─── Phase D (Slice 1–2: Mixer) ──────────  ║
║  POST /action/track_volume → verified write  ║
║  POST /action/track_pan    → verified write  ║
║  POST /action/track_mute   → verified write  ║
║  POST /action/track_solo   → verified write  ║
║  ─── Phase D (Action Expansion Slice 1) ───  ║
║  POST /action/track_arm    → arm/unarm track ║
║  POST /action/track_monitor → monitor mode  ║
║  POST /action/track_rename → rename track    ║
║  POST /action/track_color  → set color       ║
║  POST /action/track_create → create track    ║
║  POST /action/track_delete → delete (confirm)║
║  POST /action/track_duplicate → duplicate    ║
║  POST /action/return_track_create → return   ║
║  POST /action/tracks_create_multiple → batch ║
║  ─── Phase D (Action Expansion Slice 2) ───  ║
║  POST /action/track_route  → output routing  ║
║  POST /action/track_send   → send level      ║
║  POST /action/transport_play → start play    ║
║  POST /action/transport_stop → stop play     ║
║  POST /action/transport_record → record mode ║
║  POST /action/transport_loop → loop toggle   ║
║  POST /action/transport_metronome → metro    ║
║  POST /feedback            → store feedback  ║
╚══════════════════════════════════════════════╝
""", flush=True)

    # Check what's available on startup
    ableton_ok = ableton_connected()
    nlm = notebooklm_path()
    aa = audio_analyzer_path()
    print(f"  Ableton MCP (:{ABLETON_PORT}) : {'✅ Connected' if ableton_ok else '⚠️  Not connected — open Ableton'}")
    print(f"  NotebookLM CLI         : {'✅ ' + nlm if nlm else '⚠️  Not found'}")
    print(f"  Audio Analyzer CLI     : {'✅ Found' if aa else '⚠️  Not found'}")
    print(f"  ChromaDB Memory        : {'✅ Ready' if CHROMA_AVAILABLE else '⚠️  Not installed — run: pipx install chromadb'}")
    print(f"  Semantic Router        : {'✅ Ready (5 routes)' if ROUTER_AVAILABLE else '⚠️  Fallback mode — install sentence-transformers'}")
    print(f"  Context Pack Builder   : {'✅ Ready' if CONTEXT_PACK_AVAILABLE else '⚠️  Not available — check rag/context_pack_builder.py'}")

    # Seed failure_cases_index from vault if empty
    if CHROMA_AVAILABLE:
        get_chroma_client()   # initialise all 5 collections
        upserted = seed_failure_cases()
        if upserted > 0:
            print(f"  Vault seeder           : ✅ Upserted {upserted} failure cases → failure_cases_index (stable IDs)")
        else:
            print(f"  Vault seeder           : ✅ failure_cases_index up to date (vault file not found or ChromaDB unavailable)")
    print()

    server = HTTPServer(("localhost", BRIDGE_PORT), ConductorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  Bridge stopped.")
        server.server_close()

if __name__ == "__main__":
    main()
