import uuid
import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
import pickle
import os

# In-memory vector store
class InMemoryVectorStore:
    def __init__(self, persist_file="vector_store.pkl"):
        self.persist_file = persist_file
        self.data = []  # List of dicts: {'id': str, 'vector': np.array, 'payload': dict}
        self.load()

    def load(self):
        if os.path.exists(self.persist_file):
            with open(self.persist_file, 'rb') as f:
                self.data = pickle.load(f)
            print(f"📂 Loaded {len(self.data)} vectors from {self.persist_file}")

    def save(self):
        with open(self.persist_file, 'wb') as f:
            pickle.dump(self.data, f)
        print(f"💾 Saved {len(self.data)} vectors to {self.persist_file}")

    def upsert(self, points):
        for point in points:
            self.data.append({
                'id': point.id,
                'vector': np.array(point.vector),
                'payload': point.payload
            })
        self.save()

    def search(self, query_vector, filter_func=None, limit=5):
        if not self.data:
            return []
        
        vectors = np.array([d['vector'] for d in self.data])
        query_vec = np.array(query_vector).reshape(1, -1)
        similarities = cosine_similarity(query_vec, vectors)[0]
        
        # Get indices sorted by similarity (descending)
        sorted_indices = np.argsort(similarities)[::-1]
        
        results = []
        for idx in sorted_indices:
            if filter_func and not filter_func(self.data[idx]['payload']):
                continue
            results.append({
                'id': self.data[idx]['id'],
                'score': similarities[idx],
                'payload': self.data[idx]['payload']
            })
            if len(results) >= limit:
                break
        return results

# Mock PointStruct for compatibility
class PointStruct:
    def __init__(self, id, vector, payload):
        self.id = id
        self.vector = vector
        self.payload = payload

# Global store instance
store = InMemoryVectorStore()

COLLECTION_NAME = "books"  # Not needed, but keep for compatibility

def create_collection_if_needed(vector_dim=384):
    # No-op for in-memory
    print("🆕 In-memory vector store ready (no collection needed)")

def upsert_chunks(chunks, vectors, book_id, metadata=None):
    points = []
    for idx, (chunk, vec) in enumerate(zip(chunks, vectors)):
        payload = {
            "text": chunk,
            "book_id": int(book_id),
            "chunk_index": idx + 1
        }
        if metadata:
            payload.update(metadata)
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload=payload
            )
        )
    
    if not points:
        print("⚠️ No chunks to insert.")
        return

    store.upsert(points)
    print(f"✅ Inserted {len(points)} chunks into in-memory store")

def search_in_book(prompt_vector, book_id: int, top_k=5):
    def filter_func(payload):
        return payload.get('book_id') == book_id
    
    results = store.search(prompt_vector, filter_func=filter_func, limit=top_k)
    # Format to match Qdrant's output
    return [
        {
            'id': r['id'],
            'score': r['score'],
            'payload': r['payload']
        }
        for r in results
    ]
