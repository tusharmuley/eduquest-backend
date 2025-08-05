from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from rest_framework.permissions import IsAuthenticated, AllowAny
from .models import Book, ChatHistory
from .utils.pdf_parser import extract_text_from_pdf, extract_text_from_docx
from .utils.website_parser import extract_text_from_website
from .utils.text_splitter import split_text
from .utils.embedder import get_embeddings
from .utils.qdrant_client import create_collection_if_needed, upsert_chunks, search_in_book
from .utils.llm_client import generate_answer
import time
import logging
from .utils.structured_loader import store_structured_data_to_postgres
import os
import pandas as pd
from .utils.structured_query import query_structured_data
import traceback
import sys


class UploadUniversalBookView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        file = request.data.get("file")
        title = request.data.get("title")
        subject = request.data.get("subject")
        website_url = request.data.get("website_url", "").strip()

        if not title or (not file and not website_url):
            return Response({"error": "File/website url and title are required."}, status=status.HTTP_400_BAD_REQUEST)

        extension = os.path.splitext(file.name)[1].lower() if file else None

        if file and extension in [".pdf", ".docx"]:
            book_type = "text"
        elif file and extension in [".csv", ".xlsx"]:
            book_type = "structured"
        elif website_url:
            book_type = "website"  # Treat websites as text source
        else:
            return Response({"error": "Unsupported file type."}, status=400)

        book = Book.objects.create(title=title, subject=subject, file=file, type=book_type,
                                   website_url=website_url if website_url else None)

        if book_type == "text":
            if extension == ".pdf":
                text = extract_text_from_pdf(book.file.path)
            elif extension == ".docx":
                # from .utils.docx_parser import extract_text_from_docx  # or wherever you place it
                text = extract_text_from_docx(book.file.path)
        
            # text = extract_text_from_pdf(book.file.path)
            # Step 2: Save OCR text to file for review/debug
            text_dump_path = f"ocr_output_book_{book.id}.txt"
            with open(text_dump_path, "w", encoding="utf-8") as f:
                f.write(text)
            print(f"📝 Extracted text saved to {text_dump_path}")
            
            chunks = split_text(text)
            vectors = get_embeddings(chunks)
            create_collection_if_needed()
            metadata = {"source": f"PDF: {book.title}"}
            upsert_chunks(chunks, vectors, book_id=book.id, metadata=metadata)

            return Response({
                "message": "PDF processed and embedded.",
                "book_id": book.id,
                "type": "text",
                "chunks": len(chunks)
            })

        elif book_type == "structured":
            try:
                if extension == ".csv":
                    df = pd.read_csv(book.file.path)
                    store_structured_data_to_postgres(df, book.id, "Sheet1")
                    return Response({
                        "message": "CSV parsed and stored.",
                        "book_id": book.id,
                        "rows": len(df),
                        "sheets": ["Sheet1"]
                    })
                else:
                    dfs = pd.read_excel(book.file.path, sheet_name=None)
                    for sheet_name, df in dfs.items():
                        store_structured_data_to_postgres(df, book.id, sheet_name)
                    return Response({
                        "message": "Excel sheets parsed.",
                        "book_id": book.id,
                        "sheets": list(dfs.keys())
                    })
            except Exception as e:
                return Response({"error": str(e)}, status=500)
            
        elif book_type == "website":
            try:
                text = extract_text_from_website(website_url)

                if len(text.strip()) < 50:
                    return Response({"error": f"Website has too little readable content.text :{text}", }, status=400)

                # Optional: Save scraped text
                text_dump_path = f"website_output_book_{book.id}.txt"
                with open(text_dump_path, "w", encoding="utf-8") as f:
                    f.write(text)
                print(f"🌐 Website text saved to {text_dump_path}")

                chunks = split_text(text)
                vectors = get_embeddings(chunks)
                create_collection_if_needed()
                # For website:
                metadata = {"source": f"Website: {website_url}"}
                upsert_chunks(chunks, vectors, book_id=book.id, metadata=metadata)

                return Response({
                    "message": "Website processed and embedded.",
                    "book_id": book.id,
                    "type": "website",
                    "chunks": len(chunks)
                })

            except Exception as e:
                return Response({"error": f"Website ingestion failed: {str(e)}"}, status=500)
            
    

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


def build_conversational_prompt(history: list, user_prompt: str, intents: list, context: str) -> str:
    base = "You are a helpful assistant.\n\n"

    if "greet" in intents:
        base += "User greeted you. Just respond politely.\n"
    elif "summary" in intents:
        base += "Summarize the content below.\n"
    elif "translate" in intents:
        base += "Translate the content below into Hindi or Marathi.\n"
    elif "mcq" in intents:
        base += "Create 10 MCQs from the content.\n"
    elif "numerical" in intents:
        base += "Explain numerical or percentage-related info.\n"
    elif "definition" in intents:
        base += "Define the term or concept from the content.\n"
    elif "book_meta" in intents:
        base += "Answer metadata-related questions using context below.\n"
    else:
        base += "Answer using only the given context.\n"

    # Add memory history
    for msg in history[-5:]:  # Last 5 turns
        role = msg["role"].capitalize()
        base += f"{role}: {msg['text']}\n"

    base += f"User: {user_prompt}\n\nContext:\n{context}\n\nAnswer:"
    return base


class SearchInBookView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        prompt = request.data.get("prompt", "").strip()
        book_id = request.data.get("book_id")
        user = request.user

        if not prompt or not book_id:
            return Response({"error": "Prompt and book_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            intents = classify_prompt_intents(prompt)
            book = Book.objects.get(id=book_id)

            # 🧠 Structured data flow
            if book.type == "structured":
                if "numerical" in intents or "qa" in intents:
                    result = query_structured_data(book_id, prompt)
                    return Response({
                        "answer": result,
                        "confidence": "medium",
                        "matched_chunks": []
                    })
                else:
                    return Response({
                        "answer": "Only numerical/QA supported for structured data.",
                        "confidence": "low",
                        "matched_chunks": []
                    })

            # ✋ Greet shortcut
            if "greet" in intents:
                answer = generate_answer(f"User: {prompt}\nAI:")
                return Response({
                    "answer": answer,
                    "confidence": "high",
                    "matched_chunks": []
                })

            # 📜 Fetch memory
            chat_history, _ = ChatHistory.objects.get_or_create(user=user, book=book)
            memory = chat_history.messages

            # 🔍 Vector search
            vector = get_embeddings([prompt])[0]
            results = search_in_book(prompt_vector=vector, book_id=int(book_id), top_k=10)
            # chunks = [hit.payload["text"] for hit in results]
            chunks = []
            citations = []

            for hit in results:
                payload = hit.payload
                text = payload.get("text", "")
                chunk_index = payload.get("chunk_index")
                source = payload.get("source", f"Book {book_id}")

                citation = f"{source}, Chunk {chunk_index}"
                citations.append(citation)
                chunks.append(text)

            if not chunks:
                return Response({
                    "answer": "No chunks found in the document.",
                    "confidence": "low",
                    "matched_chunks": []
                })

            # 🔁 Rerank
            matched_chunks = chunks[:5] if any(i in intents for i in ["summary", "translate", "mcq", "book_meta"]) else rerank_chunks_by_llm(prompt, chunks)

            if not matched_chunks:
                return Response({
                    "answer": "No relevant answer found.",
                    "confidence": "low",
                    "matched_chunks": []
                })

            # 🧠 Final LLM prompt
            context = "\n\n".join(matched_chunks)
            final_prompt = build_conversational_prompt(memory, prompt, intents, context)
            answer = generate_answer(final_prompt)

            # 💾 Update memory
            memory.append({"role": "user", "text": prompt})
            memory.append({"role": "ai", "text": answer})
            chat_history.messages = memory[-10:]  # Limit to last 10
            chat_history.save()

            return Response({
                "answer": answer,
                "confidence": "high",
                "matched_chunks": matched_chunks,
                "citations": citations[:len(matched_chunks)],  # Align with top matched
            })

        except Exception as e:
            exc_type, exc_obj, tb = sys.exc_info()
            traceback.print_exc()
            return Response({
                "error": str(e),
                "line": tb.tb_lineno
            }, status=500)    
        
        
        

# @api_view(["POST"])
# @permission_classes([IsAuthenticated])
# def clear_chat_history(request):
#     book_id = request.data.get("book_id")
#     ChatHistory.objects.filter(user=request.user, book_id=book_id).delete()
#     return Response({"message": "Chat history cleared."})


class ChatHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, book_id):
        try:
            chat, _ = ChatHistory.objects.get_or_create(user=request.user, book_id=book_id)
            return Response({"messages": chat.messages})
        except Exception as e:
            return Response({"error": str(e)}, status=500)
        
    
    def delete(self, request, book_id):
            try:
                ChatHistory.objects.filter(user=request.user, book_id=book_id).delete()
                return Response({"message": "Chat history cleared."})
            except Exception as e:
                return Response({"error": str(e)}, status=500)