"""
Phase A1 Step 2 — Vault Integrity Tests
========================================
Validates known_plugins.json, operator cards, and parameter maps
against the schemas in data/schemas/.

Rules:
- No chromadb import.
- No memory/ChromaDB access.
- All checks are pure file + JSON/text parsing.
- Operator card frontmatter validation runs only when frontmatter exists;
  missing frontmatter is a warning/skip, not a failure.
- parameter_map_file is optional; validated only when present.
- Shared card_file references are explicitly allowed.
"""

import json
import re
import sys
import warnings
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────────

_HERE = Path(__file__).parent
_ROOT = _HERE.parent  # TEST-BUILD/

_PLUGINS_JSON   = _ROOT / "data" / "known_plugins.json"
_SCHEMAS_DIR    = _ROOT / "data" / "schemas"
_VAULT_PLUGINS  = _ROOT / "conductor-vault" / "plugins"

_SCHEMA_PLUGIN  = _SCHEMAS_DIR / "plugin_metadata.schema.json"
_SCHEMA_CARD    = _SCHEMAS_DIR / "operator_card.schema.json"
_SCHEMA_PARAM   = _SCHEMAS_DIR / "parameter_map.schema.json"

# ── Constants from schema ──────────────────────────────────────────────────────

REQUIRED_FIELDS = [
    "name", "aliases", "natural_names", "manufacturer",
    "type", "risk", "has_card", "card_file",
]
VALID_RISKS     = {"low", "medium", "high"}
FUTURE_FIELDS   = {
    "plugin_id", "parameter_map_file", "generic_class_card_file",
    "operator_card_triggers", "version", "source_citations",
    "pluginbridge_name", "formats", "safety_tags", "vendor_url",
}
ALL_KNOWN_FIELDS = set(REQUIRED_FIELDS) | FUTURE_FIELDS

# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_plugins():
    """Load and return (raw_data, plugins_list). Raises on bad JSON."""
    raw = json.loads(_PLUGINS_JSON.read_text(encoding="utf-8"))
    return raw, raw.get("plugins", [])


def _parse_frontmatter(card_text: str):
    """
    Return parsed YAML frontmatter dict if the card starts with '---',
    else return None (no frontmatter present).
    Intentionally uses stdlib only — no PyYAML dependency required.
    Falls back to basic key:value parsing for simple frontmatter.
    """
    if not card_text.startswith("---"):
        return None
    # Find closing ---
    rest = card_text[3:]
    end = rest.find("\n---")
    if end == -1:
        return None
    block = rest[:end].strip()
    # Try PyYAML if available, else simple parse
    try:
        import yaml  # type: ignore
        return yaml.safe_load(block) or {}
    except ImportError:
        pass
    # Fallback: parse simple key: value pairs (no nesting)
    result = {}
    for line in block.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            result[k.strip()] = v.strip()
    return result


def _validate_frontmatter_field(key, value, card_schema_props):
    """
    Check a single frontmatter field value against the schema property definition.
    Returns None on pass, error string on failure.
    """
    prop = card_schema_props.get(key)
    if prop is None:
        return None  # unknown key — not in schema, ignore (additionalProperties allowed here)
    expected_type = prop.get("type")
    enum_vals     = prop.get("enum")
    if enum_vals and value not in enum_vals:
        return f"  field '{key}' value '{value}' not in enum {enum_vals}"
    if expected_type == "array" and not isinstance(value, list):
        return f"  field '{key}' should be array, got {type(value).__name__}"
    if expected_type == "string" and not isinstance(value, str):
        return f"  field '{key}' should be string, got {type(value).__name__}"
    if expected_type == "boolean" and not isinstance(value, bool):
        return f"  field '{key}' should be boolean, got {type(value).__name__}"
    return None


def _validate_param_map(path: Path, param_schema: dict):
    """
    Validate a parameter map JSON file against parameter_map.schema.json shape.
    Returns list of error strings (empty = pass).
    """
    errors = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"  cannot parse JSON: {e}"]
    if "plugin_id" not in data:
        errors.append("  missing required field: plugin_id")
    if "parameters" not in data:
        errors.append("  missing required field: parameters")
        return errors
    params = data["parameters"]
    if not isinstance(params, list) or len(params) == 0:
        errors.append("  'parameters' must be a non-empty array")
        return errors
    for i, p in enumerate(params):
        if "id" not in p:
            errors.append(f"  parameters[{i}] missing required field: id")
        if "name" not in p:
            errors.append(f"  parameters[{i}] missing required field: name")
        if "id" in p and not isinstance(p["id"], int):
            errors.append(f"  parameters[{i}].id must be integer")
        if "name" in p and not isinstance(p["name"], str):
            errors.append(f"  parameters[{i}].name must be string")
        if "risk" in p and p["risk"] not in VALID_RISKS:
            errors.append(f"  parameters[{i}].risk must be low|medium|high")
    return errors


# ── Test runner ────────────────────────────────────────────────────────────────

def run_vault_integrity():
    passed   = 0
    failed   = 0
    warn_out = []

    def ok(label):
        nonlocal passed
        passed += 1
        print(f"  ✅ {label}")

    def fail(label, detail=""):
        nonlocal failed
        failed += 1
        msg = f"  ❌ {label}"
        if detail:
            msg += f"\n       {detail}"
        print(msg)

    def warn(label):
        warn_out.append(label)
        print(f"  ⚠️  {label}")

    # ── Load schemas ──────────────────────────────────────────────────────────
    print("\n── Schema files ──")
    try:
        plugin_schema   = json.loads(_SCHEMA_PLUGIN.read_text())
        card_schema     = json.loads(_SCHEMA_CARD.read_text())
        param_schema    = json.loads(_SCHEMA_PARAM.read_text())
        card_schema_props = card_schema.get("properties", {})
        ok("All three schema files load as valid JSON")
    except Exception as e:
        fail("Schema files load", str(e))
        print(f"\n  FATAL: cannot continue without schemas")
        return False

    # ── Load known_plugins.json ───────────────────────────────────────────────
    print("\n── T1: known_plugins.json structure ──")
    try:
        raw, plugins = _load_plugins()
        ok("known_plugins.json loads as valid JSON")
    except Exception as e:
        fail("known_plugins.json loads", str(e))
        return False

    if "plugins" in raw and isinstance(plugins, list):
        ok("Root has 'plugins' array")
    else:
        fail("Root has 'plugins' array",
             f"type={type(raw.get('plugins')).__name__}")

    if len(plugins) > 0:
        ok(f"plugins array is non-empty ({len(plugins)} entries)")
    else:
        fail("plugins array is non-empty")

    # ── T2: Required fields ───────────────────────────────────────────────────
    print("\n── T2: Required fields present on every plugin ──")
    missing_req = []
    for p in plugins:
        name = p.get("name", "<unnamed>")
        missing = [f for f in REQUIRED_FIELDS if f not in p]
        if missing:
            missing_req.append((name, missing))

    if not missing_req:
        ok(f"All {len(plugins)} plugins have all required fields")
    else:
        for name, m in missing_req:
            fail(f"{name} — missing: {m}")

    # ── T3: risk enum ────────────────────────────────────────────────────────
    print("\n── T3: risk is only low|medium|high ──")
    bad_risk = [(p.get("name","<unnamed>"), p.get("risk")) for p in plugins
                if p.get("risk") not in VALID_RISKS]
    if not bad_risk:
        ok(f"All {len(plugins)} plugins have valid risk value")
    else:
        for name, r in bad_risk:
            fail(f"{name} — invalid risk: '{r}'")

    # ── T4: array fields ─────────────────────────────────────────────────────
    print("\n── T4: aliases and natural_names are arrays of strings ──")
    array_errs = []
    for p in plugins:
        name = p.get("name","<unnamed>")
        for field in ("aliases", "natural_names"):
            val = p.get(field)
            if not isinstance(val, list):
                array_errs.append(f"{name}.{field} is {type(val).__name__}, expected list")
                continue
            bad_items = [i for i in val if not isinstance(i, str)]
            if bad_items:
                array_errs.append(f"{name}.{field} contains non-string items: {bad_items}")
    if not array_errs:
        ok(f"All {len(plugins)} plugins have valid aliases and natural_names arrays")
    else:
        for e in array_errs:
            fail(e)

    # ── T5: has_card=True → non-empty card_file ───────────────────────────────
    print("\n── T5: has_card=True requires non-empty card_file ──")
    card_errs = [p.get("name","<unnamed>") for p in plugins
                 if p.get("has_card") is True and not p.get("card_file","").strip()]
    if not card_errs:
        ok("All has_card=True plugins have non-empty card_file")
    else:
        for name in card_errs:
            fail(f"{name} — has_card=True but card_file is empty")

    # ── T6: card_file resolves on disk ───────────────────────────────────────
    print("\n── T6: card_file paths resolve in conductor-vault/plugins/ ──")
    card_plugins = [p for p in plugins if p.get("has_card")]
    resolve_errs = []
    for p in card_plugins:
        cf   = p["card_file"]
        path = _VAULT_PLUGINS / cf
        if not path.is_file():
            resolve_errs.append((p["name"], cf))
    if not resolve_errs:
        ok(f"All {len(card_plugins)} card_file paths resolve to existing files")
    else:
        for name, cf in resolve_errs:
            fail(f"{name} — card_file not found: conductor-vault/plugins/{cf}")

    # ── T7: shared card_file references are allowed ───────────────────────────
    print("\n── T7: shared card_file references allowed ──")
    from collections import Counter
    cf_counter = Counter(p["card_file"] for p in plugins if p.get("has_card"))
    shared = {cf: n for cf, n in cf_counter.items() if n > 1}
    if shared:
        for cf, n in shared.items():
            ok(f"Shared card '{cf}' used by {n} plugins — allowed")
    else:
        ok("No shared card_file references (or none yet) — rule passes")

    # ── T8: optional future fields validate type when present ─────────────────
    print("\n── T8: optional future fields validate type when present ──")
    future_type_map = {
        "plugin_id":               str,
        "parameter_map_file":      str,
        "generic_class_card_file": str,
        "operator_card_triggers":  list,
        "version":                 str,
        "source_citations":        list,
        "pluginbridge_name":       str,
        "formats":                 list,
        "safety_tags":             list,
        "vendor_url":              str,
    }
    future_errs = []
    future_found = []
    for p in plugins:
        for field, expected_type in future_type_map.items():
            if field in p:
                future_found.append(field)
                if not isinstance(p[field], expected_type):
                    future_errs.append(
                        f"{p.get('name','<unnamed>')}.{field}: "
                        f"expected {expected_type.__name__}, "
                        f"got {type(p[field]).__name__}"
                    )
    if future_errs:
        for e in future_errs:
            fail(e)
    elif future_found:
        ok(f"Future fields present and type-valid: {sorted(set(future_found))}")
    else:
        ok("No future fields present — schema passes (all optional)")

    # ── T9+T10: operator card frontmatter ─────────────────────────────────────
    print("\n── T9/T10: operator card frontmatter validation ──")
    card_paths = {(p["card_file"], _VAULT_PLUGINS / p["card_file"])
                  for p in plugins
                  if p.get("has_card") and (_VAULT_PLUGINS / p["card_file"]).is_file()}

    frontmatter_checked = 0
    frontmatter_errors  = []
    for cf, path in card_paths:
        text = path.read_text(encoding="utf-8")
        fm   = _parse_frontmatter(text)
        if fm is None:
            # T10: no frontmatter → warning/skip, not failure
            warn(f"No frontmatter in '{cf}' — skipping frontmatter validation")
            continue
        # T9: frontmatter exists → validate fields
        frontmatter_checked += 1
        for key, value in fm.items():
            err = _validate_frontmatter_field(key, value, card_schema_props)
            if err:
                frontmatter_errors.append(f"  {cf}: {err}")

    if frontmatter_errors:
        for e in frontmatter_errors:
            fail(e)
    elif frontmatter_checked > 0:
        ok(f"Frontmatter valid in {frontmatter_checked} card(s) that have it")
    else:
        ok("No cards have frontmatter yet — all skip cleanly (no failures)")

    # ── T11: parameter_map_file optional; validated if present ────────────────
    print("\n── T11: parameter_map_file optional; validated when present ──")
    param_map_plugins = [p for p in plugins if p.get("parameter_map_file","").strip()]
    if not param_map_plugins:
        ok("No plugin has parameter_map_file yet — optional field absent, passes")
    else:
        param_errs_all = []
        for p in param_map_plugins:
            pmf  = p["parameter_map_file"]
            path = _ROOT / pmf  # treat as relative to TEST-BUILD root
            if not path.is_file():
                param_errs_all.append(f"{p['name']}: parameter_map_file path not found: {pmf}")
                continue
            errs = _validate_param_map(path, param_schema)
            for e in errs:
                param_errs_all.append(f"{p['name']}: {e}")
        if param_errs_all:
            for e in param_errs_all:
                fail(e)
        else:
            ok(f"All {len(param_map_plugins)} parameter_map_file(s) resolve and validate")

    # ── T12: no chromadb import ───────────────────────────────────────────────
    print("\n── T12: chromadb not imported ──")
    this_file = Path(__file__).read_text(encoding="utf-8")
    if re.search(r"^\s*import chromadb", this_file, re.MULTILINE):
        fail("chromadb import found in this test file")
    elif re.search(r"^\s*from chromadb", this_file, re.MULTILINE):
        fail("chromadb import found in this test file")
    else:
        ok("chromadb not imported in test_vault_integrity.py")

    # ── T13: no memory/ChromaDB access ───────────────────────────────────────
    # Check for actual import or call syntax — not bare string occurrences,
    # which would cause self-referential false positives on this pattern list.
    print("\n── T13: no memory/ChromaDB access in this file ──")
    usage_patterns = [
        r"^\s*(import|from)\s+chromadb",   # import chromadb / from chromadb import ...
        r"\bPersistentClient\s*\(",         # instantiation
        r"\bEphemeralClient\s*\(",          # instantiation
        r"\bmemory_search\s*\(",            # API call
        r"\bmemory_add\s*\(",               # API call
    ]
    found_usage = [pat for pat in usage_patterns
                   if re.search(pat, this_file, re.MULTILINE)]
    if found_usage:
        fail(f"ChromaDB/memory usage found: {found_usage}")
    else:
        ok("No memory/ChromaDB import or call patterns found")

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n  Vault integrity: {passed} pass / {failed} fail"
          + (f" / {len(warn_out)} warnings" if warn_out else ""))
    return failed == 0


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("  Phase A1 Step 2 — Vault Integrity Tests")
    print("=" * 60)
    ok = run_vault_integrity()

    print("\n" + "=" * 60)
    if ok:
        print("  ✅ All vault integrity checks passed")
    else:
        print("  ❌ Some vault integrity checks failed")
    print("=" * 60)
    sys.exit(0 if ok else 1)
