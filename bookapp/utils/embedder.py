# utils/embedder.py

from sentence_transformers import SentenceTransformer
import time

model = SentenceTransformer("all-MiniLM-L6-v2")

def get_embeddings(texts):
    print("🔁 Generating embeddings in one go (model auto-batches)...")
    t = time.time()
    vectors = model.encode(texts, show_progress_bar=True).tolist()
    print(f"🧠 Embedding completed in {time.time() - t:.2f} seconds")
    return vectors
