import pytesseract
from pdf2image import convert_from_path
import pdfplumber
from multiprocessing import Pool
import os

# ✅ Define OCR function at the top level (very important for Windows)
def ocr(img):
    return pytesseract.image_to_string(img)

def extract_text_from_pdf(file_path):
    """
    Extracts text from a PDF file.
    1. Try extracting with pdfplumber.
    2. If not enough text, fallback to OCR using Tesseract (parallelized).
    """
    text = ""
    is_text_found = False

    # Step 1: Try with pdfplumber
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    is_text_found = True
                    text += page_text + "\n"
    except Exception as e:
        print(f"❌ pdfplumber error: {e}")

    # Step 2: Fallback to OCR if no/excessively little text
    if not is_text_found or len(text.strip()) < 50:
        print("🧠 No text found – using OCR fallback")

        try:
            # Set correct Poppler path
            poppler_path = r"C:\poppler\Library\bin"
            print(f"🔍 Using Poppler path: {poppler_path}")

            images = convert_from_path(file_path, dpi=100, poppler_path=poppler_path)

            # Use multiprocessing Pool with top-level `ocr` function
            with Pool() as pool:
                results = pool.map(ocr, images)

            text = "\n".join(results)

        except Exception as e:
            print(f"❌ OCR error: {e}")

    return text.strip()
