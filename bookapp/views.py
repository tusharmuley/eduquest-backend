from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Book
from .utils.pdf_parser import extract_text_from_pdf
from .utils.text_splitter import split_text
from .utils.embedder import get_embeddings
from .utils.qdrant_client import create_collection_if_needed, upsert_chunks, search_in_book
from .utils.llm_client import generate_answer
import time
import logging


class UploadBookView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        start = time.time()
        title = request.data.get("title")
        subject = request.data.get("subject")
        file = request.data.get("file")

        print("📥 Started book upload")

        book = Book.objects.create(title=title, subject=subject, file=file)

        # Step 1: Extract text
        t1 = time.time()
        full_text = extract_text_from_pdf(book.file.path)

        # Step 2: Save OCR text to file for review/debug
        text_dump_path = f"ocr_output_book_{book.id}.txt"
        with open(text_dump_path, "w", encoding="utf-8") as f:
            f.write(full_text)
        print(f"📝 Extracted text saved to {text_dump_path}")
        print(f"📄 PDF extracted in {time.time() - t1:.2f} seconds")

        # Step 3: Chunk
        t2 = time.time()
        chunks = split_text(full_text)
        print(f"✂️ Text split into {len(chunks)} chunks in {time.time() - t2:.2f} seconds")

        # Step 4: Embed
        t3 = time.time()
        vectors = get_embeddings(chunks)
        print(f"🧠 Embeddings generated in {time.time() - t3:.2f} seconds")

        # Step 5: Upsert to Qdrant
        t4 = time.time()
        print("📤 Uploading vectors to Qdrant...")
        create_collection_if_needed()
        upsert_chunks(chunks, vectors, book_id=book.id)
        print(f"✅ Qdrant upserted in {time.time() - t4:.2f} seconds")

        print(f"✅✅ Total upload process time: {time.time() - start:.2f} seconds")

        return Response({
            "message": "Book uploaded and embedded into Qdrant.",
            "book_id": book.id,
            "chunks_stored": len(chunks)
        })
    

    def get(self, request):
        books = Book.objects.all().order_by("-uploaded_at")
        data = [
            {
                "id": book.id,
                "title": book.title,
                "subject": book.subject,
                "filename": book.file.name,
                "uploaded_at": book.uploaded_at.strftime("%Y-%m-%d %H:%M:%S")
            }
            for book in books
        ]
        return JsonResponse(data, safe=False)

    def delete(self, request):
        book_id = request.query_params.get("book_id")
        if not book_id:
            return Response({"error": "book_id is required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            book = Book.objects.get(id=book_id)
            book.delete()
            return Response({"message": "Book deleted."}, status=status.HTTP_204_NO_CONTENT)
        except Book.DoesNotExist:
            return Response({"error": "Book not found."}, status=status.HTTP_404_NOT_FOUND)



#generate answer from book

import ast
# 🔍 LLM-based Intent Classification Prompt
INTENT_CLASSIFY_PROMPT = """
        Classify the following user prompt into one or more of the following types:
        - greet
        - summary
        - translate
        - mcq
        - numerical
        - definition
        - book_meta
        - qa

        If the user asks about the author, publisher, year, price, or anything related to the book’s details, classify as "book_meta".

        Respond only as a Python list like: ["summary", "translate"]

        Prompt: {user_prompt}
        Types:
        """

# 🧠 LLM-based intent classifier
def classify_prompt_intents(prompt: str) -> list:
    try:
        llm_prompt = INTENT_CLASSIFY_PROMPT.format(user_prompt=prompt)
        response = generate_answer(llm_prompt)
        intents = ast.literal_eval(response.strip())
        return intents if isinstance(intents, list) else ["qa"]
    except:
        return ["qa"]

# 🔁 Hybrid Reranker using LLM
def rerank_chunks_by_llm(prompt: str, chunks: list, top_n: int = 5) -> list:
    if not chunks:
        return []
    
    joined_chunks = "\n\n".join([f"Chunk {i+1}:\n{chunk}" for i, chunk in enumerate(chunks)])
    rerank_prompt = f"""
                You are an intelligent assistant. Rank the following chunks based on how relevant they are to the user's question.
                Return the top {top_n} chunk numbers as a Python list (e.g., [2, 1, 4]).

                User question: {prompt}

                Chunks:
                {joined_chunks}

                Top relevant chunks:
                """
    try:
        response = generate_answer(rerank_prompt)
        indices = ast.literal_eval(response.strip())
        return [chunks[i - 1] for i in indices if 1 <= i <= len(chunks)]
    except:
        return chunks[:top_n]

# 📦 Final prompt builder
def build_final_prompt(intents: list, context: str, user_prompt: str) -> str:
    base = "You are a helpful assistant.\n\n"

    if "greet" in intents:
        base += "User greeted you. Just respond politely to the greeting. Do not provide any other info.\n"
    elif "summary" in intents:
        base += "Your task is to generate a clear and concise summary of the given content.\n"
    elif "translate" in intents:
        base += "Translate the following content into Hindi or Marathi based on the user request.\n"
    elif "mcq" in intents:
        base += "Generate 10 MCQs (multiple choice questions) with 4 options each and highlight the correct one.\n"
    elif "numerical" in intents:
        base += "Extract and explain any numerical, amount, or percentage-related information from the content.\n"
    elif "definition" in intents:
        base += "Define or explain the given term or concept using only the provided content.\n"
    elif "book_meta" in intents:
        base += "Use the context below to answer metadata-related questions about the book, such as author, publisher, year, etc. Do not guess.\n"
    else:
        base += "Answer the user's question using only the context. If the answer is not found, reply with 'Not found in the document.'\n"

    base += f"\nContext:\n{context}\n\nUser question: {user_prompt}\n\nAnswer:"
    return base

# 🚀 Main RAG View with Hybrid Reranking
class SearchInBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        prompt = request.data.get("prompt", "").strip()
        book_id = request.data.get("book_id")

        if not prompt or not book_id:
            return Response({"error": "Prompt and book_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # 1. Classify prompt intent
            intents = classify_prompt_intents(prompt)

            # 2. Greet-only shortcut
            if "greet" in intents:
                final_prompt = build_final_prompt(intents, "", prompt)
                answer = generate_answer(final_prompt)
                return Response({
                    "answer": answer,
                    "confidence": "high",
                    "matched_chunks": []
                })

            # 3. Embed and semantic search (top 10 for reranking)
            vector = get_embeddings([prompt])[0]
            results = search_in_book(prompt_vector=vector, book_id=int(book_id), top_k=10)
            all_chunks = [hit.payload["text"] for hit in results]

            # 4. Rerank chunks if not summary/translate/mcq/book_meta
            if "book_meta" in intents or any(i in intents for i in ["summary", "translate", "mcq"]):
                matched_chunks = all_chunks[:5]
            else:
                matched_chunks = rerank_chunks_by_llm(prompt, all_chunks, top_n=5)

                if not matched_chunks:
                    return Response({
                        "answer": "Sorry, the answer is not available in the provided document.",
                        "confidence": "low",
                        "matched_chunks": []
                    })

            # 5. Final LLM prompt and response
            context = "\n\n".join(matched_chunks)
            final_prompt = build_final_prompt(intents, context, prompt)
            answer = generate_answer(final_prompt)

            return Response({
                "answer": answer,
                "confidence": "high",
                "matched_chunks": matched_chunks
            })

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)     