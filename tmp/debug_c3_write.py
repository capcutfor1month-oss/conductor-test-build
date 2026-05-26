import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import chromadb
from rag.routed_retriever import CHROMA_PATH
from rag.corrective_check import find_superseded_by_new, _jaccard, _tokens

client = chromadb.PersistentClient(path=CHROMA_PATH)
col = client.get_or_create_collection("producer_memory_index", metadata={"hnsw:space": "cosine"})

old_txt = "compress snare fast attack slow release parallel compression punch technique"
new_txt = "compress snare fast attack slow release parallel compression punch corrected improved"

# Let's see the count of items in collection
print(f"Total count: {col.count()}")

# Manual query to see distances
results = col.query(
    query_texts=[new_txt],
    n_results=5,
    include=["documents", "metadatas", "distances"]
)

docs = results.get("documents", [[]])[0]
dists = results.get("distances", [[]])[0]
ids = results.get("ids", [[]])[0]

print("\nChromaDB Query Results:")
for old_id, old_doc, dist in zip(ids, docs, dists):
    cosine_sim = 1.0 - dist
    jac = _jaccard(_tokens(new_txt), _tokens(old_doc or ""))
    print(f"  ID: {old_id}")
    print(f"    Doc:  {old_doc}")
    print(f"    Cosine Sim: {cosine_sim:.4f} (Threshold: 0.70)")
    print(f"    Jaccard:    {jac:.4f} (Threshold: 0.40)")
