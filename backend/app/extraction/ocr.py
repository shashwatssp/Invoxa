"""
OCR and text extraction module.
Handles:
- PyMuPDF (fitz) for text-layer extraction and PDF-to-image rendering
- Tesseract OCR for scanned/image-only PDFs
- pdfplumber for layout-preserving table extraction
"""
import io
import fitz  # PyMuPDF
import pytesseract
import pdfplumber
from PIL import Image


def extract_text_pymupdf(file_bytes: bytes) -> str:
    """
    Extract text from PDF using PyMuPDF.
    Fast (0.01s/page) but minimal layout preservation.
    """
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


def extract_text_pdfplumber(file_bytes: bytes) -> str:
    """
    Extract text from PDF using pdfplumber.
    Preserves layout better, good for table extraction.
    """
    text = ""
    with io.BytesIO(file_bytes) as f:
        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
    return text


def extract_tables_pdfplumber(file_bytes: bytes) -> list[list[list[str]]]:
    """
    Extract tables from PDF using pdfplumber.
    Returns list of tables (each table is list of rows, each row is list of cell strings).
    """
    tables = []
    with io.BytesIO(file_bytes) as f:
        with pdfplumber.open(f) as pdf:
            for page in pdf.pages:
                page_tables = page.extract_tables()
                if page_tables:
                    tables.extend(page_tables)
    return tables


def render_page_to_image(file_bytes: bytes, page_num: int = 0, dpi: int = 300) -> Image.Image:
    """
    Render a PDF page to a PIL Image using PyMuPDF.
    """
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        page = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img


def ocr_image(image: Image.Image, lang: str = "eng+hin") -> str:
    """
    Run Tesseract OCR on a PIL Image.
    Uses --oem 1 (LSTM neural net only) and --psm 6 (block of text).
    """
    custom_config = "--oem 1 --psm 6"
    text = pytesseract.image_to_string(image, config=custom_config, lang=lang)
    return text


def ocr_pdf(file_bytes: bytes, lang: str = "eng+hin") -> str:
    """
    Full OCR pipeline for scanned PDFs:
    1. Render each page to image via PyMuPDF
    2. Run Tesseract OCR on each image
    """
    text = ""
    with fitz.open(stream=file_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc):
            mat = fitz.Matrix(300 / 72, 300 / 72)
            pix = page.get_pixmap(matrix=mat)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            page_text = pytesseract.image_to_string(
                img, config="--oem 1 --psm 6", lang=lang
            )
            text += page_text + "\n"
    return text


def extract_text(file_bytes: bytes, filename: str = "invoice.pdf") -> tuple[str, bool]:
    """
    Main text extraction entry point.
    Tries PyMuPDF text extraction first, falls back to Tesseract OCR.
    Returns (text, used_ocr) tuple.
    """
    # Try pdfplumber first (better layout preservation for text-layer PDFs)
    try:
        text = extract_text_pdfplumber(file_bytes)
        if text and len(text.strip()) > 0:
            return text, False
    except Exception:
        pass

    # Fall back to PyMuPDF
    try:
        text = extract_text_pymupdf(file_bytes)
        if text and len(text.strip()) > 0:
            return text, False
    except Exception:
        pass

    # Fall back to OCR (Tesseract)
    text = ocr_pdf(file_bytes)
    if text and len(text.strip()) > 0:
        return text, True

    return "", False
