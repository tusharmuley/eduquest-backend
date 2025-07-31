import uuid
from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    Distance,
    VectorParams,
    Filter,
    FieldCondition,
    MatchValue,
    PayloadSchemaType
)

# Qdrant config
client = QdrantClient(
    url="https://417d4a71-3bc9-40e3-889b-edfddc81b2ca.us-west-1-0.aws.cloud.qdrant.io",
    api_key="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhY2Nlc3MiOiJtIn0.9zo8QJRj1TZXuGlJF76Y_kTVXOD0O57_AXYdA9fZzco"
)

COLLECTION_NAME = "books"


def create_collection_if_needed(vector_dim=384):
    existing_collections = [c.name for c in client.get_collections().collections]
    if COLLECTION_NAME not in existing_collections:
        print("🆕 Creating Qdrant collection and index...")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=vector_dim,
                distance=Distance.COSINE
            )
        )

    # ✅ Always try to create index if not present
    try:
        index_info = client.get_collection(collection_name=COLLECTION_NAME).payload_schema
        if "book_id" not in index_info:
            print("🔧 Creating payload index on book_id...")
            client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="book_id",
                field_schema=PayloadSchemaType.INTEGER
            )
    except Exception as e:
        print("⚠️ Could not check/create payload index:", e)



def upsert_chunks(chunks, vectors, book_id):
    points = []
    for chunk, vec in zip(chunks, vectors):
        points.append(
            PointStruct(
                id=str(uuid.uuid4()),
                vector=vec,
                payload={
                    "text": chunk,
                    "book_id": int(book_id)  # Ensure it's int, as index requires it
                }
            )
        )
    
    if not points:
        print("⚠️ No chunks to insert.")
        return

    client.upsert(
        collection_name=COLLECTION_NAME,
        points=points
    )


def search_in_book(prompt_vector, book_id: int, top_k=5):
    return client.search(
        collection_name=COLLECTION_NAME,
        query_vector=prompt_vector,
        limit=top_k,
        with_payload=True,
        query_filter=Filter(
            must=[
                FieldCondition(
                    key="book_id",
                    match=MatchValue(value=book_id)
                )
            ]
        )
    )
