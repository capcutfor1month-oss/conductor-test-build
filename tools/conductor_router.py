#!/usr/bin/env python3
"""
Conductor Semantic Router
─────────────────────────
Fast embedding-based query routing for Conductor's Auto mode.
Routes user messages to the correct knowledge source without any LLM call.

Repo: https://github.com/aurelio-labs/semantic-router

Sources:
  notebooklm   → Deep technique, instruments, EQ, genre, orchestration
  ableton      → Live session state, tracks, routing, BPM, clips
  memory       → Past decisions, preferences, what to avoid
  analyzer     → Audio file analysis (key, BPM, LUFS, stereo)
  direct       → Simple factual questions, no tool needed

Usage:
  from semantic_router import route_message
  source = route_message("how do I EQ a dhol?")
  # → "notebooklm"
"""

import sys
import os

try:
    from semantic_router import Route, RouteLayer
    from semantic_router.encoders import HuggingFaceEncoder
    SEMANTIC_ROUTER_AVAILABLE = True
except ImportError:
    SEMANTIC_ROUTER_AVAILABLE = False
    # Stubs prevent NameError at module level when semantic_router is not installed.
    # Route definitions below succeed, but get_router() returns None so
    # route_message() always hits the fallback branch.
    class Route:
        def __init__(self, name="", utterances=None):
            self.name = name
    RouteLayer = None
    HuggingFaceEncoder = None

# ── ROUTE DEFINITIONS ─────────────────────────────────────────────────────────

# NotebookLM — deep technique, instruments, genre, orchestration, mixing
notebooklm_route = Route(
    name="notebooklm",
    utterances=[
        "how do I EQ a dhol",
        "what velocity should I use for legato strings",
        "how to program tabla rhythms",
        "what frequency range does a sitar sit in",
        "how to mix a Punjabi pop track",
        "what compression settings for kick drum",
        "how to voice a minor chord for strings",
        "what reverb should I use for cinematic brass",
        "how to layer Indian instruments with western orchestration",
        "what EQ curve for Hindi cinematic mix",
        "how to write a string melody",
        "what are the rules for taal in Indian classical",
        "how to use sidechain compression",
        "what LUFS target for Spotify",
        "how to master a track",
        "arrangement tips for Punjabi pop",
        "what plugins should I use for mixing",
        "how to get a warm analog sound",
        "what microphone technique for vocals",
        "how to tune a 808 bass",
    ],
)

# Ableton — live session state, tracks, routing, BPM, clips
ableton_route = Route(
    name="ableton",
    utterances=[
        "what is the current BPM",
        "what tracks do I have open",
        "show me all my tracks",
        "what devices are on the kick track",
        "is the strings bus routed correctly",
        "what is the tempo",
        "list all clips in the session",
        "what is the key of the project",
        "check the routing on the vocal bus",
        "is the sidechain connected",
        "show me the current session state",
        "what plugins are loaded",
        "is Ableton connected",
        "what is on track 3",
        "check the output routing",
        "what return tracks do I have",
        "is the master volume set correctly",
        "show me all midi clips",
        "what is playing right now",
        "check the monitoring state",
    ],
)

# Memory — past decisions, preferences, what to avoid
memory_route = Route(
    name="memory",
    utterances=[
        "what EQ settings worked last time",
        "what did I do for the dhol last session",
        "have I worked on this before",
        "what was my approach for Punjabi pop",
        "what do I usually do for kick compression",
        "remind me what worked for the strings",
        "remind me what I did for the kick",
        "remind me what I used for the vocals",
        "remind me how I mixed the bass",
        "remind me what settings I used",
        "what should I avoid based on past sessions",
        "what was the sidechain setting that worked",
        "do you remember how I mixed the vocals",
        "what was the reverb I used last time",
        "what are my personal mixing rules",
        "what did I decide about the arrangement",
        "what worked in my last session",
        "recall my preference for hi-hats",
        "what have I tried before for this",
        "what compression did I use last time",
        "what did I set the attack to",
        "what frequency did I cut on the dhol",
        "past session decisions",
        "what was working before",
        "remember what I tried for this",
    ],
)

# Audio Analyzer — file analysis, key, BPM, LUFS, stereo
analyzer_route = Route(
    name="analyzer",
    utterances=[
        "analyze this file",
        "what key is this audio in",
        "what is the BPM of this track",
        "check the LUFS of this mix",
        "analyze the stereo width",
        "is there a frequency clash in this file",
        "what does the spectrum look like",
        "check the low end of this WAV",
        "analyze the mix",
        "what is the dynamic range",
        "check mono compatibility",
        "analyze this recording",
        "what is the phase correlation",
        "detect the key of this sample",
        "scan this audio file",
    ],
)

# Direct — simple factual, no tool needed
direct_route = Route(
    name="direct",
    utterances=[
        "what is 440 Hz",
        "what does BPM stand for",
        "what is a compressor",
        "what is sidechain",
        "define reverb",
        "what is an LFO",
        "what does EQ mean",
        "what is a low pass filter",
        "what is MIDI",
        "what is a bus track",
        "what does LUFS mean",
        "what is stereo width",
        "what is a limiter",
        "what is a transient",
        "yes",
        "no",
        "ok",
        "thanks",
        "got it",
    ],
)

# ── ROUTER INIT ───────────────────────────────────────────────────────────────

_router = None

def get_router():
    """Initialise router once, reuse."""
    global _router
    if _router is None and SEMANTIC_ROUTER_AVAILABLE:
        encoder = HuggingFaceEncoder()
        _router = RouteLayer(
            encoder=encoder,
            routes=[
                notebooklm_route,
                ableton_route,
                memory_route,
                analyzer_route,
                direct_route,
            ],
        )
    return _router

# ── PUBLIC API ────────────────────────────────────────────────────────────────

def route_message(message: str) -> str:
    """
    Route a user message to the correct knowledge source.
    Returns one of: notebooklm | ableton | memory | analyzer | direct

    Falls back to "notebooklm" if router unavailable or no match found.
    """
    if not SEMANTIC_ROUTER_AVAILABLE:
        return "notebooklm"  # safe fallback

    try:
        router = get_router()
        result = router(message)
        if result.name:
            return result.name
        return "notebooklm"  # fallback if no match
    except Exception:
        return "notebooklm"  # never crash, always return something


# ── CLI TEST ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_messages = [
        "how do I EQ a dhol?",
        "what is the current BPM?",
        "what EQ worked last time?",
        "analyze this WAV file",
        "what does LUFS mean?",
        "how to mix Punjabi pop strings?",
        "show me all my tracks",
        "remind me what I did for the kick",
    ]

    print("\nConductor Semantic Router — Test\n" + "─" * 40)
    for msg in test_messages:
        source = route_message(msg)
        print(f"  [{source:12}]  {msg}")
    print()
