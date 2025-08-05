# from langchain.text_splitter import RecursiveCharacterTextSplitter

# def split_text(text, chunk_size=800, chunk_overlap=100):
#     splitter = RecursiveCharacterTextSplitter(
#         chunk_size=chunk_size,
#         chunk_overlap=chunk_overlap,
#         separators=["\n\n", "\n", " ", ""]
#     )
#     return splitter.split_text(text)



import re
import nltk
from nltk.tokenize import sent_tokenize

nltk.download('punkt')
nltk.download('punkt_tab')


def split_text(text, chunk_size=800, chunk_overlap=100):
    """
    Sentence-aware chunking for EduQuest project.
    Keeps context, avoids mid-sentence breaks, and works across PDF, DOCX, and Website content.
    """
    # Clean and normalize text
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"\s+", " ", text).strip()

    sentences = sent_tokenize(text)

    chunks = []
    current_chunk = []
    current_length = 0

    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue

        if current_length + len(sentence) <= chunk_size:
            current_chunk.append(sentence)
            current_length += len(sentence)
        else:
            # Finalize current chunk
            chunk_text = " ".join(current_chunk).strip()
            if chunk_text:
                chunks.append(chunk_text)

            # Start new chunk with overlap (last 1 sentence)
            overlap_sentences = current_chunk[-1:]  # adjust if you want more overlap
            current_chunk = overlap_sentences + [sentence]
            current_length = sum(len(s) for s in current_chunk)

    # Add the last chunk
    if current_chunk:
        chunk_text = " ".join(current_chunk).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return chunks
