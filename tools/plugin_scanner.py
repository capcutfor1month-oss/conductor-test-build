#!/usr/bin/env python3
"""
Conductor Plugin Scanner
────────────────────────
Runs at install time. Scans macOS plugin directories for VST3, AU, and VST.
Matches against known_plugins.json. Asks 4 anchor questions.
Writes conductor-vault/studio/Studio Inventory.md automatically.

Usage:
  python3 plugin_scanner.py
  python3 plugin_scanner.py --dry-run    (scan only, no file write, no questions)
  python3 plugin_scanner.py --rescan     (force rescan even if inventory exists)
"""

import json
import os
import plistlib
import sys
import time
from pathlib import Path

# ── PATHS ─────────────────────────────────────────────────────────────────────

SCANNER_DIR   = Path(__file__).parent
REPO_ROOT     = SCANNER_DIR.parent
KNOWN_PLUGINS = REPO_ROOT / "data" / "known_plugins.json"
VAULT_DIR     = REPO_ROOT / "conductor-vault"
INVENTORY_OUT = VAULT_DIR / "studio" / "Studio Inventory.md"

# macOS plugin scan paths
SCAN_PATHS = [
    Path("/Library/Audio/Plug-ins/VST3"),
    Path.home() / "Library/Audio/Plug-ins/VST3",
    Path("/Library/Audio/Plug-ins/Components"),
    Path.home() / "Library/Audio/Plug-ins/Components",
    Path("/Library/Audio/Plug-ins/VST"),
    Path.home() / "Library/Audio/Plug-ins/VST",
]

# Extensions to look for
PLUGIN_EXTENSIONS = {".vst3", ".component", ".vst"}

# Anchor plugin types — the 4 questions we ask
ANCHOR_TYPES = {
    "eq":         "Your primary EQ plugin",
    "compressor": "Your primary compressor",
    "reverb":     "Your primary reverb",
    "saturation": "Your primary saturation plugin",
}

# ── HELPERS ───────────────────────────────────────────────────────────────────

def load_known_plugins():
    if not KNOWN_PLUGINS.exists():
        print(f"  ⚠️  known_plugins.json not found at {KNOWN_PLUGINS}")
        return []
    with open(KNOWN_PLUGINS) as f:
        data = json.load(f)
    return data.get("plugins", [])


def scan_plugins():
    """
    Recursively walk all scan paths. For each plugin:
    - Read Info.plist metadata (name, manufacturer, type)
    - Returns dict: stem → {path, ext, display_name, manufacturer, inferred_type, bundle_id}
    Handles vendor subfolders (e.g. VST3/Soundtoys/Decapitator.vst3).
    """
    found = {}  # stem → enriched dict
    for base in SCAN_PATHS:
        if not base.exists():
            continue
        for ext in PLUGIN_EXTENSIONS:
            for entry in base.rglob(f"*{ext}"):
                stem = entry.stem
                if stem in found:
                    continue
                meta = read_plugin_metadata(entry)
                found[stem] = {
                    "path":          str(entry),
                    "ext":           ext,
                    "display_name":  meta["display_name"]  if meta else stem,
                    "manufacturer":  meta["manufacturer"]  if meta else "Unknown",
                    "inferred_type": meta["inferred_type"] if meta else "fx",
                    "bundle_id":     meta["bundle_id"]     if meta else "",
                }
    return found


# ── TYPE KEYWORD MAP ─────────────────────────────────────────────────────────
# Used to infer plugin type from its name when not in known_plugins.json.
# Order matters — more specific patterns first.

TYPE_KEYWORDS = [
    ("mastering",   ["mastering", "ozone", "maximizer", "t-racks", "wavelab", "final mix"]),
    ("eq",          ["eq", "equaliz", "equalise", " q ", "pro-q", "proq", "tilteq", "luftikus", "kirchhoff"]),
    ("compressor",  ["compressor", " comp ", "la-2a", "la2a", "1176", "ssl g", "optical",
                     "vca", "fet compressor", "presswerk", "transient"]),
    ("reverb",      ["reverb", " room", "hall ", "plate ", "shimmer", "supermassive",
                     "vintagerevb", "verbsuite", "convolution", "impulse response"]),
    ("saturation",  ["saturator", "saturation", "tape", "decapitator", "radiator",
                     "distortion", "overdrive", "exciter", "harmonic"]),
    ("delay",       ["delay", "echob", "echo boy", "pingpong", "ping-pong", "tape delay"]),
    ("synth",       ["synth", "synthesiz", "instrument", "serum", "massive", "diva",
                     "omnisphere", "phase plant", "pigments", "vital", "arp 2600",
                     "minimoog", "prophet", "juno", "dx7", "analog lab"]),
    ("fx",          ["chorus", "flanger", "phaser", "tremolo", "vibrato", "bitcrusher",
                     "pitch shift", "whammy", "formant", "vocoder", "modulation",
                     "microshift", "alterboy", "stutter"]),
]

AU_TYPE_MAP = {
    "aumu": "synth",   # MusicDevice = instrument
    "aumi": "synth",   # MusicDevice
    "aumf": "fx",      # MusicEffect (has MIDI input)
    "aufx": "fx",      # Effect (base — keyword refines further)
    "aufc": "utility", # FormatConverter
    "augn": "fx",      # Generator
}


def infer_type_from_name(name: str) -> str:
    """Infer plugin type from its display name using keyword matching."""
    nl = name.lower()
    for ptype, keywords in TYPE_KEYWORDS:
        for kw in keywords:
            if kw in nl:
                return ptype
    return "fx"  # safe fallback


def infer_manufacturer_from_bundle_id(bundle_id: str) -> str:
    """Extract a human-readable manufacturer from a bundle identifier."""
    KNOWN_MFRS = {
        "fabfilter": "FabFilter",
        "valhalla":  "Valhalla DSP",
        "izotope":   "iZotope",
        "soundtoys": "Soundtoys",
        "uaudio":    "UAD",
        "waves":     "Waves",
        "native-instruments": "Native Instruments",
        "ni-":       "Native Instruments",
        "arturia":   "Arturia",
        "spectrasonics": "Spectrasonics",
        "u-he":      "u-he",
        "xfer":      "Xfer Records",
        "kilohearts": "Kilohearts",
        "tokyo":     "Tokyo Dawn",
        "klanghelm": "Klanghelm",
        "dmgaudio":  "DMG Audio",
        "liquidsonics": "Liquidsonics",
        "softube":   "Softube",
        "soundradix": "Sound Radix",
        "cableguys": "Cableguys",
        "xlnaudio":  "XLN Audio",
        "plugin-alliance": "Plugin Alliance",
        "brainworx": "Brainworx",
        "slate":     "Slate Digital",
        "ssl":       "SSL",
        "eventide":  "Eventide",
        "lexicon":   "Lexicon",
    }
    bl = bundle_id.lower()
    for key, mfr in KNOWN_MFRS.items():
        if key in bl:
            return mfr
    # Fallback: extract second component of reverse-domain (com.fabfilter.xxx → FabFilter)
    parts = bundle_id.split(".")
    if len(parts) >= 2:
        return parts[1].replace("-", " ").title()
    return "Unknown"


def read_plugin_metadata(plugin_path: Path) -> dict:
    """
    Read Info.plist from a VST3 or AU bundle.
    Returns dict with: display_name, manufacturer, au_type, inferred_type
    Returns None if plist not found or unreadable.
    """
    plist_path = plugin_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return None

    try:
        with open(plist_path, "rb") as f:
            plist = plistlib.load(f)
    except Exception:
        return None

    display_name = plugin_path.stem
    manufacturer = ""
    au_type_code = ""

    # Extract from AudioComponents (AU/VST3 dual-format plugins)
    comps = plist.get("AudioComponents", [])
    if comps:
        c = comps[0]
        au_type_code = c.get("type", "")
        # "Manufacturer: Plugin Name" format
        full_name = c.get("name", "")
        if ":" in full_name:
            parts = full_name.split(":", 1)
            manufacturer = parts[0].strip()
            display_name = parts[1].strip()
        elif full_name:
            display_name = full_name

    # Manufacturer fallback from bundle ID
    bundle_id = plist.get("CFBundleIdentifier", "")
    if not manufacturer and bundle_id:
        manufacturer = infer_manufacturer_from_bundle_id(bundle_id)

    # Display name fallback from bundle keys
    if not display_name or display_name == plugin_path.stem:
        display_name = (plist.get("CFBundleDisplayName")
                        or plist.get("CFBundleName")
                        or plugin_path.stem)

    # Infer type: AU type code first, then name keywords
    inferred_type = AU_TYPE_MAP.get(au_type_code, None)
    if inferred_type in (None, "fx"):
        # Keyword inference wins over generic "fx"
        kw_type = infer_type_from_name(display_name)
        inferred_type = kw_type if kw_type != "fx" else (inferred_type or "fx")

    return {
        "display_name": display_name,
        "manufacturer": manufacturer or "Unknown",
        "au_type_code": au_type_code,
        "inferred_type": inferred_type,
        "bundle_id":    bundle_id,
    }


def normalize(name: str) -> str:
    """Strip spaces, hyphens, underscores and lowercase for fuzzy matching."""
    return name.lower().replace(" ", "").replace("-", "").replace("_", "")


def match_plugins(found_plugins, known):
    """
    Three-tier matching:
      Tier 1 — known_plugins.json: full metadata (type, risk, operator card, aliases)
      Tier 2 — metadata auto-detected: type from Info.plist, risk defaulted
      Tier 3 — truly unknown: no plist, no match

    Returns: (tier1_list, tier2_list, tier3_list)
    """
    tier1 = []
    remaining_stems = list(found_plugins.keys())

    # ── Tier 1: known_plugins.json ────────────────────────────────────────────
    for plugin in known:
        names_to_try = [plugin["name"]] + plugin.get("aliases", [])
        for stem in list(remaining_stems):
            meta    = found_plugins[stem]
            fn_lower = stem.lower()
            fn_norm  = normalize(stem)
            # Also try display_name from plist
            dn_lower = meta["display_name"].lower()
            dn_norm  = normalize(meta["display_name"])
            matched  = False

            for kname_raw in names_to_try:
                kname      = kname_raw.lower()
                kname_norm = normalize(kname_raw)
                if (kname == fn_lower or kname in fn_lower or fn_lower in kname
                        or kname_norm == fn_norm or kname_norm in fn_norm or fn_norm in kname_norm
                        or kname == dn_lower or kname in dn_lower
                        or kname_norm == dn_norm or kname_norm in dn_norm):
                    matched = True
                    break

            if matched:
                tier1.append({**plugin, "found_as": stem, "path": meta["path"],
                               "display_name": meta["display_name"],
                               "manufacturer_detected": meta["manufacturer"]})
                remaining_stems.remove(stem)
                break

    # ── Tier 2: metadata auto-detected ────────────────────────────────────────
    tier2 = []
    tier3 = []
    for stem in remaining_stems:
        meta = found_plugins[stem]
        if meta["inferred_type"] != "fx" or meta["manufacturer"] != "Unknown":
            # Has meaningful metadata
            tier2.append({
                "name":         meta["display_name"],
                "manufacturer": meta["manufacturer"],
                "type":         meta["inferred_type"],
                "risk":         "high" if meta["inferred_type"] == "mastering" else "medium"
                                if meta["inferred_type"] in ("eq","compressor","saturation","synth") else "low",
                "has_card":     False,
                "source":       "auto-detected",
                "found_as":     stem,
                "path":         meta["path"],
            })
        else:
            tier3.append({"name": stem, "display_name": meta["display_name"],
                          "path": meta["path"]})

    return tier1, tier2, tier3


def ask_anchor(plugin_type, label, candidates):
    """
    Ask user to pick their primary plugin for this type.
    Returns the chosen plugin name or None.
    """
    if not candidates:
        print(f"  ⚪  No {plugin_type} plugins found in your library.")
        return None

    print(f"\n  {label}?")
    for i, p in enumerate(candidates[:8], 1):  # max 8 options
        card = "  [card ready]" if p.get("has_card") else ""
        print(f"    {i}. {p['name']} ({p['manufacturer']}){card}")
    print(f"    {len(candidates[:8]) + 1}. None / skip")

    while True:
        try:
            choice = input("  → Enter number: ").strip()
            idx = int(choice) - 1
            if idx == len(candidates[:8]):
                return None
            if 0 <= idx < len(candidates[:8]):
                return candidates[:8][idx]["name"]
        except (ValueError, IndexError):
            pass
        print("  Invalid choice. Try again.")


def write_inventory(tier1, tier2, tier3, anchors, total_found):
    """Write Studio Inventory.md to conductor-vault/studio/."""
    INVENTORY_OUT.parent.mkdir(parents=True, exist_ok=True)
    timestamp  = time.strftime("%Y-%m-%d")
    all_known  = tier1 + tier2
    type_order = ["eq", "compressor", "reverb", "saturation", "mastering", "synth", "fx", "utility", "delay"]

    lines = [
        "# Studio Inventory",
        (f"Generated: {timestamp}  |  Total plugins: {total_found}  |  "
         f"DB matched: {len(tier1)}  |  Auto-detected: {len(tier2)}  |  Unknown: {len(tier3)}"),
        "",
        "---",
        "",
        "## Anchor Plugins",
        "> Your primary plugin for each function. Full operator cards loaded for these.",
        "",
    ]

    anchor_labels = {
        "eq":         "Primary EQ",
        "compressor": "Primary Compressor",
        "reverb":     "Primary Reverb",
        "saturation": "Primary Saturation",
    }

    if any(anchors.values()):
        for atype, label in anchor_labels.items():
            chosen = anchors.get(atype)
            if chosen:
                match = next((p for p in all_known if p["name"] == chosen), None)
                card = "✅ operator card loaded" if (match and match.get("has_card")) else "⚪ no card yet"
                lines.append(f"- **{label}:** {chosen} — {card}")
            else:
                lines.append(f"- **{label}:** not set")
    else:
        lines.append("_No anchor plugins set. Run with --rescan to configure._")

    # ── Full library table (Tier 1 + Tier 2) ─────────────────────────────────
    lines += ["", "---", "", "## Full Plugin Library",
              "> ✅ = from database  |  🔍 = auto-detected from plugin metadata  |  ⭐ = anchor plugin",
              "", "| Plugin | Type | Manufacturer | Risk | Source |",
              "|---|---|---|---|---|"]

    sorted_all = sorted(
        all_known,
        key=lambda p: (type_order.index(p["type"]) if p["type"] in type_order else 99, p["name"])
    )
    for p in sorted_all:
        source_icon = "✅" if p.get("source") != "auto-detected" else "🔍"
        card_icon   = " ✅" if p.get("has_card") else ""
        anchor_flag = ""
        for atype, chosen in anchors.items():
            if chosen == p["name"]:
                anchor_flag = " ⭐"
                break
        lines.append(
            f"| {p['name']}{anchor_flag}{card_icon} | {p['type']} | {p['manufacturer']} | {p['risk']} | {source_icon} |"
        )

    # ── Tier 3: truly unknown (capped at 30) ─────────────────────────────────
    if tier3:
        shown    = sorted(tier3, key=lambda x: x["name"])[:30]
        overflow = len(tier3) - len(shown)
        lines += ["", "---", "", "## Unclassified Plugins",
                  f"> {len(tier3)} plugins with no metadata. Add to `data/known_plugins.json` if needed.",
                  "", "| Plugin | Path |", "|---|---|"]
        for p in shown:
            lines.append(f"| {p['name']} | `{p['path']}` |")
        if overflow > 0:
            lines.append(f"| _(+{overflow} more)_ | — |")

    lines += ["", "---", "",
              "_To rescan: `python3 tools/plugin_scanner.py --rescan`_",
              "_To add a plugin: edit `data/known_plugins.json` and rescan._"]

    with open(INVENTORY_OUT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n  ✅  Written → {INVENTORY_OUT}")


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    dry_run = "--dry-run" in sys.argv
    rescan  = "--rescan" in sys.argv

    print("""
╔══════════════════════════════════════════╗
║       Conductor Plugin Scanner           ║
║  Scans VST3 / AU / VST on your machine   ║
╚══════════════════════════════════════════╝
""")

    # Skip if inventory already exists and not rescanning
    if INVENTORY_OUT.exists() and not rescan and not dry_run:
        print(f"  ✅  Inventory already exists at {INVENTORY_OUT}")
        print("  Run with --rescan to regenerate.\n")
        return

    # Load known plugins
    known = load_known_plugins()
    print(f"  Known plugins database: {len(known)} entries")

    # Scan
    print("\n  Scanning plugin directories...")
    for path in SCAN_PATHS:
        status = "✅" if path.exists() else "⚪ (not found)"
        print(f"    {status}  {path}")

    found = scan_plugins()
    total = len(found)
    print(f"\n  Found {total} plugins on this machine.")

    if total == 0:
        print("\n  No plugins found. Check that Ableton / DAW plugins are installed.")
        return

    # Match — three tiers
    tier1, tier2, tier3 = match_plugins(found, known)
    total_classified = len(tier1) + len(tier2)
    print(f"  DB matched: {len(tier1)}  |  Auto-detected: {len(tier2)}  |  Unknown: {len(tier3)}")
    print(f"  Classification rate: {100 * total_classified // total}%")

    if dry_run:
        print("\n  [dry-run] DB matched:")
        for p in tier1:
            print(f"    ✅  {p['type']:12}  {p['name']} ({p['manufacturer']})")
        print("\n  [dry-run] Auto-detected (sample, first 20):")
        for p in tier2[:20]:
            print(f"    🔍  {p['type']:12}  {p['name']} ({p['manufacturer']})")
        if len(tier2) > 20:
            print(f"    ... +{len(tier2)-20} more auto-detected")
        print("\n  [dry-run] No files written.")
        return

    # Group tier1 + tier2 by type for anchor questions
    by_type = {}
    for p in tier1 + tier2:
        by_type.setdefault(p["type"], []).append(p)

    # Ask 4 anchor questions
    print("\n  ─────────────────────────────────────────")
    print("  4 quick questions to set your anchor plugins.")
    print("  These get full operator cards loaded.\n")

    anchors = {}
    for atype, label in ANCHOR_TYPES.items():
        candidates = by_type.get(atype, [])
        anchors[atype] = ask_anchor(atype, label, candidates)

    # Write inventory
    write_inventory(tier1, tier2, tier3, anchors, total)

    # Summary
    print("\n  ─────────────────────────────────────────")
    print("  Scan complete.\n")
    for atype, chosen in anchors.items():
        label = ANCHOR_TYPES[atype]
        print(f"  {label}: {chosen or 'not set'}")

    total_classified = len(tier1) + len(tier2)
    print(f"\n  Total plugins:     {total}")
    print(f"  DB matched:        {len(tier1)}")
    print(f"  Auto-detected:     {len(tier2)}")
    print(f"  Unclassified:      {len(tier3)}")
    print(f"  Classification:    {100 * total_classified // total}%")
    print()


if __name__ == "__main__":
    main()
