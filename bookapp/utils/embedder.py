# utils/embedder.py

from huggingface_hub import InferenceClient
from django.conf import settings
import time

client = InferenceClient(model="sentence-transformers/all-MiniLM-L6-v2", token=settings.HF_TOKEN)

def get_embeddings(texts):
    print("🔁 Generating embeddings via Hugging Face API...")
    t = time.time()
    # Batch all texts at once
    response = client.feature_extraction(texts)
    vectors = response.tolist() if hasattr(response, 'tolist') else response
    print(f"🧠 Embedding completed in {time.time() - t:.2f} seconds")
    return vectors
