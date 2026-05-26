import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import chromadb
from rag.routed_retriever import CHROMA_PATH
from rag.corrective_check import find_superseded_by_new

client = chromadb.PersistentClient(path=CHROMA_PATH)
col = client.get_or_create_collection("producer_memory_index", metadata={"hnsw:space": "cosine"})

new_txt = "compress snare fast attack slow release parallel compression punch corrected improved"
new_id = "mem_1779560127522"

print("Running find_superseded_by_new directly...")
try:
    superseded_ids = find_superseded_by_new(col, new_txt, new_id)
    print(f"Success! Superseded IDs: {superseded_ids}")
except Exception as e:
    import traceback
    print("Exception thrown:")
    traceback.print_exc()
