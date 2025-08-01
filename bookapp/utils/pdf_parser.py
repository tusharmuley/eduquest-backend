import pytesseract
from pdf2image import convert_from_path
import pdfplumber
from multiprocessing import Pool
import os

# ✅ Top-level OCR function for Windows compatibility
def ocr(img):
    return pytesseract.image_to_string(img)

def extract_text_from_pdf(file_path):
    """
    Hybrid extractor: combines pdfplumber and OCR (page-wise fallback).
    Improves reliability for mixed PDFs.
    """
    extracted_text = []
    poppler_path = r"C:\poppler\Library\bin"  # adjust if needed

    try:
        with pdfplumber.open(file_path) as pdf:
            print(f"📄 Total pages: {len(pdf.pages)}")
            pages_needing_ocr = []

            for i, page in enumerate(pdf.pages):
                try:
                    page_text = page.extract_text()
                    if page_text and len(page_text.strip()) > 30:
                        print(f"✅ Page {i+1}: text extracted ({len(page_text.strip())} chars)")
                        extracted_text.append(page_text)
                    else:
                        print(f"⚠️ Page {i+1}: no text found – will use OCR")
                        pages_needing_ocr.append(i)
                        extracted_text.append("")  # placeholder
                except Exception as e:
                    print(f"❌ Error on page {i+1}: {e}")
                    pages_needing_ocr.append(i)
                    extracted_text.append("")

        # Step 2: OCR fallback for only the needed pages
        if pages_needing_ocr:
            print(f"🔍 Using OCR on {len(pages_needing_ocr)} pages...")
            images = convert_from_path(
                file_path, dpi=300, poppler_path=poppler_path,
                first_page=min(pages_needing_ocr)+1,
                last_page=max(pages_needing_ocr)+1
            )

            # Match image indexes to page indexes
            img_map = {page_num: img for page_num, img in zip(pages_needing_ocr, images)}

            with Pool() as pool:
                ocr_results = pool.map(ocr, [img_map[p] for p in pages_needing_ocr])

            for idx, page_num in enumerate(pages_needing_ocr):
                extracted_text[page_num] = ocr_results[idx]
                print(f"🧠 OCR Page {page_num+1}: {len(ocr_results[idx])} chars")

    except Exception as e:
        print(f"❌ Failed to extract PDF text: {e}")
        return ""

    return "\n".join(extracted_text).strip()
