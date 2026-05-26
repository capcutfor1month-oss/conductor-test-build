"""
Conductor — Routed Retriever (C1)
──────────────────────────────────
Replaces the legacy _query_memory() which blindly searched conductor_memory
with no routing, no thresholds, and no structured evidence.

For each message the retriever:
  1. Looks up which collections to search (MODE_COLLECTION_MAP)
  2. Enforces RISKY_WRITE_RETRIEVAL_ORDER for risky actions (safety first)
  3. Queries each collection with similarity thresholds
  4. Level 4 (Never-Do) memories bypass threshold — always float to top
  5. Returns both retrieved and injected lists for debug transparency
  6. Injects NO_STRONG_MEMORY_MSG if nothing clears threshold — honest empty state

Called by build_message_pack() in context_pack_builder.py.
Never hardcodes collection names or thresholds — all from memory_schema.py.

ChromaDB metric: cosine (hnsw:space=cosine). All new collections are created
with this metric. similarity = 1.0 - distance (distance ∈ [0, 1] for cosine).
"""

import os
import sys
from dataclasses import dataclass, field
from typing import List

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, _ROOT)

from rag.memory_schema import (
    COLLECTIONS,
    COLLECTION_KEYS,
    MODE_COLLECTION_MAP,
    MEMORY_LEVELS,
    SIMILARITY_THRESHOLDS,
    LEVEL_4_BYPASSES_THRESHOLD,
    NO_STRONG_MEMORY_MSG,
    RISKY_WRITE_RETRIEVAL_ORDER,
    get_audio_freshness,
    AUDIO_FRESHNESS_WARNINGS,
)

CHROMA_PATH = os.path.join(_ROOT, "memory", "chromadb")

# ── DATA TYPES ────────────────────────────────────────────────────────────────

@dataclass
class EvidenceItem:
    """Single piece of retrieved or injected evidence."""
    text:         str
    collection:   str       # collection name, e.g. "producer_memory_index"
    similarity:   float     # 0.0–1.0, cosine similarity
    memory_level: int       # 1–4
    label:        str       # short source label shown in prompt + debug
    injected:     bool  = True   # True = went into prompt; False = retrieved but filtered
    reason:       str   = ""     # why skipped (populated when injected=False)
    # ── C4 Evidence Labels ────────────────────────────────────────────────────
    id:            str   = ""    # ChromaDB document ID
    confidence:    float = 0.0   # metadata confidence field (0.0–1.0)
    age_days:      float = -1.0  # days since created_at; -1 = unknown
    final_score:   float = 0.0   # composite score: semantic×0.60 + recency×0.30 + freq×0.10
    superseded_by: str   = ""    # ID of the newer memory that replaces this one
    rejected:      bool  = False # explicitly rejected by user (metadata.rejected=True)
    # ── C1 Step 1 — Evidence label completeness ───────────────────────────────
    source_type:          str        = "unknown"  # from metadata.source_type
    verification_status:  str        = "unknown"  # from metadata.verification_status
    bm25_score:           float      = 0.0        # BM25 keyword score (0 for semantic-only)
    reason_injected:      str        = ""         # "retrieval_match" | "not_injected"
    token_count:          int        = 0          # approximate: len(text) // 4
    project_id:           str        = ""         # from metadata.project_id
    session_id:           str        = ""         # from metadata.session_id
    plugin_id:            str        = ""         # from metadata.plugin_id
    freshness:            str        = "unknown"  # from metadata.freshness
    rescue_mode:          str | None = None       # "bm25" for BM25 rescue; None otherwise
    conflict_flag:        bool       = False      # True when C3 corrective check flags conflict


@dataclass
class RetrievalResult:
    """
    Full retrieval outcome for one message.

    .retrieved  — everything ChromaDB returned (shown in debug)
    .injected   — subset that cleared threshold (goes into prompt)
    .freeform   — True when mode is FREEFORM_GENERAL (no retrieval)
    .summary_text — formatted text injected into the prompt's memory section
    """
    retrieved:    List[EvidenceItem] = field(default_factory=list)
    injected:     List[EvidenceItem] = field(default_factory=list)
    mode:         str  = ""
    freeform:     bool = False
    summary_text: str  = ""


# ── CHROMADB HELPERS ──────────────────────────────────────────────────────────

def _get_collection(collection_name: str):
    """
    Get or create a ChromaDB collection with cosine similarity metric.

    hnsw:space=cosine means: distance = 1 - cosine_similarity
    so similarity = 1.0 - distance (clamped to [0, 1]).

    Returns None silently if ChromaDB is not installed or the collection fails.
    """
    try:
        import chromadb
        os.makedirs(CHROMA_PATH, exist_ok=True)
        client = chromadb.PersistentClient(path=CHROMA_PATH)
        return client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )
    except Exception:
        return None


def _query_collection(
    collection_name: str,
    message: str,
    n: int = 3,
    project_id: str = "",
) -> List[EvidenceItem]:
    """
    Query a single collection. Returns EvidenceItem list (unsorted, unfiltered).
    Applies a project_id WHERE filter for project_session_index if project_id is given.
    """
    col = _get_collection(collection_name)
    if col is None or col.count() == 0:
        return []

    where = None
    # Only filter by project_id for project-specific collection
    if project_id and collection_name == COLLECTIONS["project"]:
        where = {"project_id": {"$eq": project_id}}

    try:
        kwargs: dict = {
            "query_texts": [message],
            "n_results":   min(n, col.count()),
            "include":     ["documents", "distances", "metadatas"],
        }
        if where:
            kwargs["where"] = where
        results = col.query(**kwargs)
    except Exception:
        return []

    docs      = results.get("documents", [[]])[0]
    distances = results.get("distances",  [[]])[0]
    metas     = results.get("metadatas",  [[]])[0]
    ids       = results.get("ids",        [[]])[0]   # ChromaDB always returns IDs

    # Import age helper from memory_scoring (avoids duplicating the logic)
    from rag.memory_scoring import _age_days as _score_age_days

    items = []
    for doc, dist, meta, doc_id in zip(docs, distances, metas, ids):
        # cosine distance → similarity
        similarity = max(0.0, min(1.0, 1.0 - dist))
        meta       = meta or {}
        mem_level  = int(meta.get("memory_level", 1) or 1)

        # Short source label (shown in prompt + debug view)
        coll_key = COLLECTION_KEYS.get(collection_name, collection_name)
        label    = f"[{coll_key}]"

        # Audio gets freshness label
        if collection_name == COLLECTIONS["audio"]:
            analysis_time = meta.get("analysis_time", "")
            freshness     = get_audio_freshness(analysis_time)
            warning       = AUDIO_FRESHNESS_WARNINGS.get(freshness, "")
            label = f"[audio·{freshness}]" + (f" {warning}" if warning else "")

        created_at = str(meta.get("created_at", "") or "")

        item = EvidenceItem(
            text=doc,
            collection=collection_name,
            similarity=similarity,
            memory_level=mem_level,
            label=label,
            injected=True,         # will be overridden by _apply_threshold
            # C4 fields populated here from metadata
            id=str(doc_id or ""),
            confidence=float(meta.get("confidence", 0.0) or 0.0),
            age_days=_score_age_days(created_at),
        )
        # C1 Step 1 — completeness fields from metadata
        raw_st = str(meta.get("source_type", "") or "")
        item.source_type         = raw_st if raw_st else "unknown"
        raw_vs = str(meta.get("verification_status", "") or "")
        item.verification_status = raw_vs if raw_vs else "unknown"
        item.project_id          = str(meta.get("project_id",  "") or "")
        item.session_id          = str(meta.get("session_id",  "") or "")
        item.plugin_id           = str(meta.get("plugin_id",   "") or "")
        raw_fr = str(meta.get("freshness", "") or "")
        item.freshness           = raw_fr if raw_fr else "unknown"
        item.token_count         = max(1, len(doc or "") // 4)  # guard: ChromaDB can return None doc
        # rescue_mode / bm25_score / reason_injected / conflict_flag stay at defaults
        # Stash metadata fields used by _apply_threshold and score_item
        item._meta_rejected      = bool(meta.get("rejected",      False))
        item._meta_superseded_by = str( meta.get("superseded_by", "") or "")
        item._meta_created_at    = created_at
        item._meta_access_count  = int( meta.get("access_count",  0)  or 0)
        items.append(item)

    return items


# ── SCORING & FILTERING ───────────────────────────────────────────────────────

def _apply_threshold(items: List[EvidenceItem], collection_name: str) -> List[EvidenceItem]:
    """
    Mark items that should not be injected as injected=False.

    Filters:
    1. rejected=True in metadata    — user explicitly rejected this memory
    2. superseded_by != ""          — a newer memory has replaced this one
    3. similarity < threshold       — not relevant enough to inject
    Level 4 (Never-Do) bypasses the similarity threshold but still respects
    rejected=True and superseded_by (a Never-Do can be superseded in rare cases).
    """
    threshold = SIMILARITY_THRESHOLDS.get(collection_name, 0.35)
    for item in items:
        # Mirror _meta_* into the public C4 dataclass fields (for debug transparency)
        item.rejected      = bool(getattr(item, "_meta_rejected",      False))
        item.superseded_by = str( getattr(item, "_meta_superseded_by", "") or "")

        # These filters apply regardless of memory level
        if item.rejected:
            item.injected = False
            item.reason   = "explicitly rejected by user"
            continue
        if item.superseded_by:
            item.injected = False
            item.reason   = f"superseded by {item.superseded_by}"
            continue
        # Level 4 bypasses similarity threshold
        if item.memory_level == 4 and LEVEL_4_BYPASSES_THRESHOLD:
            item.injected = True
            continue
        if item.similarity < threshold:
            item.injected = False
            item.reason   = f"below threshold ({item.similarity:.2f} < {threshold})"
    # C1 Step 1 — set reason_injected after all injected flags are finalized
    for item in items:
        item.reason_injected = "retrieval_match" if item.injected else "not_injected"
    return items


def _sort_by_weight(items: List[EvidenceItem]) -> List[EvidenceItem]:
    """
    Sort injected items by temporal-weighted composite score (C2).
    Delegates to rag/memory_scoring.score_item():
        final = semantic × 0.60 + recency × 0.30 + frequency × 0.10
    Level 4 always floats to top (returns 9999).
    """
    from rag.memory_scoring import score_item
    return sorted(items, key=score_item, reverse=True)


# ── C5: HYBRID BM25 + SEMANTIC SEARCH ────────────────────────────────────────
# Semantic search (ChromaDB cosine) misses exact plugin/param/track/code names
# because embeddings blur them. BM25 keyword search rescues these cases.
#
# Strategy: "semantic-first with BM25 rescue"
#   1. Run semantic search (ChromaDB query) for top n_per_collection results.
#   2. Run BM25 on the full collection (fetched into memory — fast for <1000 docs).
#   3. Take BM25 hits NOT already in semantic results → add as BM25-rescue items
#      with a fixed similarity of BM25_RESCUE_SIMILARITY (above all thresholds).
#   4. Items found by both: keep semantic similarity (it's calibrated).
#   5. Apply existing _apply_threshold and C3 checks normally.
#
# Graceful fallback: if rank_bm25 is not installed, silently skip BM25 step.

BM25_RESCUE_SIMILARITY = 0.45  # above all collection thresholds (lowest is 0.30)
                                # below audio threshold (0.50) by design

# C6 — BM25 exact-match threshold: fraction of max batch score to qualify as
# "exact" rather than a partial rescue. 0.75 means top-25% of the batch.
BM25_EXACT_FRACTION = 0.75

try:
    from rank_bm25 import BM25Okapi as _BM25Okapi
    _BM25_AVAILABLE = True
except ImportError:
    _BM25_AVAILABLE = False


# ── C6: Enhanced BM25 tokenizer ───────────────────────────────────────────────

import re as _re
import hashlib as _hashlib


def _bm25_tokenize(text: str) -> list:
    """
    C6 enhanced BM25 tokenizer.

    Handles compound identifiers that naive whitespace splitting misses:
      Pro-Q       → ['pro', 'q', 'proq',  'pro-q']
      ProQ4       → ['proq4', 'pro', 'q4', '4']
      Ozone12     → ['ozone12', 'ozone', '12']
      F006        → ['f006', 'f', '006']
      BRIDGE_TIMEOUT_003 → ['bridge', 'timeout', '003', 'bridge_timeout_003']
      LowShelf_Gain      → ['lowshelf', 'low', 'shelf', 'gain']
      Kick_Bus_01        → ['kick', 'bus', '01', 'kick_bus_01']

    Returns a list (allows duplicates — same API as basic .split()).
    """
    text_lower = text.lower()
    tokens: list = []

    for word in text_lower.split():
        tokens.append(word)

        # Split on _, -, . separators
        parts = _re.split(r'[_\-\.]', word)
        if len(parts) > 1:
            for p in parts:
                if p:
                    tokens.append(p)
            # Also keep concatenated (no separator) form
            joined = _re.sub(r'[_\-\.]', '', word)
            if joined and joined != word:
                tokens.append(joined)

        # Split alpha runs from digit runs (e.g. "ozone12" → "ozone", "12")
        alpha_num = _re.findall(r'[a-z]+|[0-9]+', word)
        if len(alpha_num) > 1:
            tokens.extend(alpha_num)

    return tokens


def _bm25_rescue(
    collection_name: str,
    message: str,
    already_found_ids: set,
    n: int = 3,
) -> List[EvidenceItem]:
    """
    Run BM25 on the full collection and return items whose IDs are NOT in
    already_found_ids. These are exact-match "rescues" that semantic missed.

    Returns at most n items with similarity=BM25_RESCUE_SIMILARITY.
    """
    if not _BM25_AVAILABLE:
        return []

    col = _get_collection(collection_name)
    if col is None or col.count() == 0:
        return []

    try:
        all_data  = col.get(include=["documents", "metadatas"])
        all_docs  = all_data.get("documents", []) or []
        all_ids   = all_data.get("ids",       []) or []
        all_metas = all_data.get("metadatas", []) or []
    except Exception:
        return []

    if not all_docs:
        return []

    from rag.memory_scoring import _age_days as _score_age_days

    # C6 — use enhanced tokenizer for both corpus and query
    # Guard: ChromaDB can return None for missing documents; treat as empty string
    tokenised_corpus = [_bm25_tokenize(doc or "") for doc in all_docs]
    tokenised_query  = _bm25_tokenize(message)

    try:
        bm25   = _BM25Okapi(tokenised_corpus)
        scores = bm25.get_scores(tokenised_query)
    except Exception:
        return []

    # Sort by score, take top candidates, filter to IDs not already found
    indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)

    # C6 — bm25_exact threshold: top 75% of max positive score in this batch
    max_positive = indexed[0][1] if indexed and indexed[0][1] > 0 else 0.0
    bm25_exact_threshold = max_positive * BM25_EXACT_FRACTION if max_positive > 0 else float("inf")

    # C6 — dedup by content hash within this rescue batch
    seen_content_hashes: set = set()

    rescues: List[EvidenceItem] = []
    for idx, score in indexed:
        if score <= 0:
            break
        doc_id = all_ids[idx] if idx < len(all_ids) else ""
        if doc_id in already_found_ids:
            continue   # semantic already has it; no rescue needed

        doc  = all_docs[idx]

        # C6 — content-hash dedup (skip near-identical rescues with different IDs)
        # Guard: doc may be None if ChromaDB returned a null document
        content_hash = _hashlib.md5((doc or "").encode("utf-8", errors="replace")).hexdigest()[:16]
        if content_hash in seen_content_hashes:
            continue
        seen_content_hashes.add(content_hash)

        meta = (all_metas[idx] or {}) if idx < len(all_metas) else {}

        mem_level = int(meta.get("memory_level", 1) or 1)
        coll_key  = COLLECTION_KEYS.get(collection_name, collection_name)
        created_at = str(meta.get("created_at", "") or "")

        # C6 — label and rescue_mode distinguish exact vs partial BM25 rescue
        rescue_mode = "bm25_exact" if score >= bm25_exact_threshold else "bm25"
        label_tag   = f"{coll_key}·{rescue_mode}"

        item = EvidenceItem(
            text=doc,
            collection=collection_name,
            similarity=BM25_RESCUE_SIMILARITY,
            memory_level=mem_level,
            label=f"[{label_tag}]",
            injected=True,
            id=str(doc_id or ""),
            confidence=float(meta.get("confidence", 0.0) or 0.0),
            age_days=_score_age_days(created_at),
        )
        # C1 Step 1 — BM25-specific completeness fields
        item.rescue_mode  = rescue_mode
        item.bm25_score   = float(score)
        raw_st = str(meta.get("source_type", "") or "")
        item.source_type         = raw_st if raw_st else "unknown"
        raw_vs = str(meta.get("verification_status", "") or "")
        item.verification_status = raw_vs if raw_vs else "unknown"
        item.project_id          = str(meta.get("project_id",  "") or "")
        item.session_id          = str(meta.get("session_id",  "") or "")
        item.plugin_id           = str(meta.get("plugin_id",   "") or "")
        raw_fr = str(meta.get("freshness", "") or "")
        item.freshness           = raw_fr if raw_fr else "unknown"
        item.token_count         = max(1, len(doc or "") // 4)  # guard: ChromaDB can return None doc
        item._meta_rejected      = bool(meta.get("rejected",      False))
        item._meta_superseded_by = str( meta.get("superseded_by", "") or "")
        item._meta_created_at    = created_at
        item._meta_access_count  = int( meta.get("access_count",  0)  or 0)
        rescues.append(item)
        if len(rescues) >= n:
            break

    return rescues


# ── MAIN ENTRY POINT ──────────────────────────────────────────────────────────

def retrieve(
    message: str,
    mode: str,
    project_id: str = "",
    n_per_collection: int = 3,
) -> RetrievalResult:
    """
    Route retrieval based on mode. Enforce thresholds. Return structured evidence.

    Args:
        message:           The user's raw message text.
        mode:              Classified mode from request_mode_classifier.
        project_id:        Short hash of project name+BPM+key. Used to filter
                           project_session_index to current project only.
        n_per_collection:  Max results to fetch per collection before threshold.

    Returns:
        RetrievalResult with .retrieved, .injected, .freeform, .summary_text
    """
    result = RetrievalResult(mode=mode)

    # FREEFORM_GENERAL — check map first.
    # If the map is empty → skip all retrieval (strict non-music mode).
    # If the map has collections (e.g. producer_memory_index) → retrieve from
    # those only, giving cross-session producer preferences for general advice.
    # Project/session context is always excluded in FREEFORM regardless.
    if mode == "FREEFORM_GENERAL":
        freeform_cols = MODE_COLLECTION_MAP.get("FREEFORM_GENERAL", [])
        if not freeform_cols:
            result.freeform = True
            result.summary_text = ""
            return result
        # Partial retrieval — producer preferences only, no project/session context
        collections_to_search = freeform_cols
    else:
        collections_to_search = MODE_COLLECTION_MAP.get(mode, [])
        if not collections_to_search:
            result.summary_text = NO_STRONG_MEMORY_MSG
            return result

    # RISKY_WRITE uses a prescribed order (safety first, not alphabetical)
    if mode == "INTERN_WRITE_RISKY":
        ordered = [col for col, _ in RISKY_WRITE_RETRIEVAL_ORDER
                   if col in collections_to_search]
        # Append any remaining that weren't in the RISKY order (shouldn't happen, but safe)
        for col in collections_to_search:
            if col not in ordered:
                ordered.append(col)
    else:
        ordered = list(collections_to_search)

    all_retrieved: List[EvidenceItem] = []

    for collection_name in ordered:
        # Semantic search (primary)
        items = _query_collection(collection_name, message, n=n_per_collection, project_id=project_id)
        semantic_ids = {i.id for i in items if i.id}

        # C5: BM25 rescue — add exact-match hits that semantic missed
        rescues = _bm25_rescue(collection_name, message, already_found_ids=semantic_ids, n=n_per_collection)
        items.extend(rescues)

        items = _apply_threshold(items, collection_name)
        all_retrieved.extend(items)

    # C3: in-flight contradiction/supersession check — marks older near-duplicate
    # injected items as suppressed in-memory (does not write to ChromaDB).
    from rag.corrective_check import apply_corrective_check as _corrective
    all_retrieved = _corrective(all_retrieved)

    # C1 Step 1 — normalize reason_injected after C3.
    # _apply_threshold() sets reason_injected based on injected at threshold time.
    # C3 can later flip injected=True→False on items that cleared the threshold,
    # leaving reason_injected="retrieval_match" on a non-injected item — wrong.
    # Rule: if injected=False, reason_injected must never be "retrieval_match".
    # Also ensure skip_reason (item.reason) is populated for every suppressed item.
    for item in all_retrieved:
        if not item.injected:
            if item.reason_injected == "retrieval_match":
                item.reason_injected = "not_injected"
            if not item.reason:
                item.reason = "filtered"   # fallback if reason was never set

    # C4: stash final_score on EVERY retrieved item (injected and filtered alike)
    # so the debug view shows why filtered items scored lower.
    from rag.memory_scoring import score_items_debug as _score_debug
    for item in all_retrieved:
        item.final_score = round(_score_debug(item)["final"], 4)

    # C3 (spec) — Token budget: drop lowest-priority injected items when the
    # total token_count of the injected set exceeds DEFAULT_BUDGET_TOKENS.
    # Must run AFTER final_score is set (used for within-tier ordering).
    # Dropped items: injected=False, skip_reason="token_budget_exceeded".
    from rag.token_budget import apply_token_budget as _apply_budget
    _apply_budget(all_retrieved)

    # Rebuild injected set after C3 (global sort across all collections)
    all_injected = _sort_by_weight([i for i in all_retrieved if i.injected])

    result.retrieved = all_retrieved
    result.injected  = all_injected

    # Format for prompt injection
    if not all_injected:
        result.summary_text = NO_STRONG_MEMORY_MSG
    else:
        lines = []
        for item in all_injected:
            snippet = (item.text or "")[:200].replace("\n", " ")
            if len(item.text or "") > 200:
                snippet += "…"
            lines.append(f"{item.label} {snippet}")
        result.summary_text = "\n".join(lines)

    return result


# ── SELF-TEST ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        import chromadb
        chroma_ok = True
    except ImportError:
        chroma_ok = False

    print("── Routed Retriever self-test ──")
    print(f"  ChromaDB: {'✅ installed' if chroma_ok else '⚠  not installed — retrieval will return empty'}")

    test_cases = [
        ("how do I compress a dhol",            "MENTOR"),
        ("delete the kick track",               "INTERN_WRITE_RISKY"),
        ("set Pro-Q 4 band 2 to cut 3.4kHz",    "INTERN_WRITE_SAFE"),
        ("what's the current BPM",              "INTERN_READ"),
        ("what should I eat for lunch",         "FREEFORM_GENERAL"),
    ]

    for msg, mode in test_cases:
        result = retrieve(msg, mode)
        status = "FREEFORM" if result.freeform else f"{len(result.injected)} injected / {len(result.retrieved)} retrieved"
        print(f"  [{mode:22}] {msg[:45]:<45} → {status}")
        if result.summary_text and not result.freeform:
            preview = result.summary_text[:80].replace("\n", " | ")
            print(f"       inject: {preview}{'…' if len(result.summary_text) > 80 else ''}")

    print("\n  Done.")
