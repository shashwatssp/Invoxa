"""
OCR and text extraction module.
Handles:
- PyMuPDF (fitz) for text-layer extraction and PDF-to-image rendering
- Tesseract OCR for scanned/image-only PDFs
- pdfplumber for layout-preserving table extraction
"""
import io
import shutil

import fitz  # PyMuPDF
import pdfplumber
import pytesseract
from PIL import Image


def _resolve_tesseract() -> None:
    """Point pytesseract at the Tesseract binary when it is not on PATH.

    Checks common Windows install locations (winget/UB-Mannheim layout).
    No-op on systems where ``tesseract`` is already discoverable.
    """
    if shutil.which("tesseract"):
        return
    import os

    candidates = [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            pytesseract.pytesseract.tesseract_cmd = path
            return


_resolve_tesseract()


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
    with io.BytesIO(file_bytes) as f, pdfplumber.open(f) as pdf:
        for page in pdf.pages:
            text += page.extract_text() or ""
    return text


def extract_tables_pdfplumber(file_bytes: bytes) -> list[list[list[str]]]:
    """
    Extract tables from PDF using pdfplumber.
    Returns list of tables (each table is list of rows, each row is list of cell strings).
    """
    tables = []
    with io.BytesIO(file_bytes) as f, pdfplumber.open(f) as pdf:
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


def _image_magic_type(file_bytes: bytes) -> str | None:
    """Return the MIME type when the bytes are a standalone image file."""
    if file_bytes.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    return None


def render_page_images(
    file_bytes: bytes,
    max_pages: int = 2,
    dpi: int = 200,
    max_dimension: int = 1600,
) -> list[tuple[str, bytes]]:
    """Render pages as JPEG images for vision APIs (e.g. Gemini).

    Accepts either a PDF (renders up to ``max_pages`` pages) or a standalone
    image file such as a WhatsApp photo (re-encoded to JPEG). Every image is
    downscaled so its longest side is at most ``max_dimension``, keeping the
    request payload bounded. Returns ``(mime_type, jpeg_bytes)`` tuples;
    an empty list means nothing renderable (unreadable file, non-image).
    """
    image_type = _image_magic_type(file_bytes)
    if image_type:
        try:
            img = Image.open(io.BytesIO(file_bytes)).convert("RGB")
        except Exception:
            return []
        candidates = [img]
    else:
        try:
            candidates = []
            with fitz.open(stream=file_bytes, filetype="pdf") as doc:
                for page in doc:
                    if len(candidates) >= max_pages:
                        break
                    mat = fitz.Matrix(dpi / 72, dpi / 72)
                    pix = page.get_pixmap(matrix=mat)
                    candidates.append(
                        Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                    )
        except Exception:  # non-PDF or unreadable bytes
            return []

    rendered: list[tuple[str, bytes]] = []
    for img in candidates[:max_pages]:
        longest = max(img.size)
        if longest > max_dimension:
            scale = max_dimension / longest
            img = img.resize(
                (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            )
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        rendered.append(("image/jpeg", buf.getvalue()))
    return rendered


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
        for _i, page in enumerate(doc):
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
    except Exception:  # intentionally fall through to next strategy
        pass

    # Fall back to PyMuPDF
    try:
        text = extract_text_pymupdf(file_bytes)
        if text and len(text.strip()) > 0:
            return text, False
    except Exception:  # intentionally fall through to OCR
        pass

    # Fall back to OCR (Tesseract). Skipped cleanly when the binary is
    # unavailable (e.g. serverless deployments) - the caller then flags
    # the empty extraction for review instead of failing the request.
    try:
        text = ocr_pdf(file_bytes)
    except Exception:  # no Tesseract binary / OCR runtime failure
        return "", False
    if text and len(text.strip()) > 0:
        return text, True

    return "", False
