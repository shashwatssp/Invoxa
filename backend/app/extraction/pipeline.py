"""
OCR-first extraction pipeline.
Full implementation in Day 3. This stub allows API imports to work.
"""
from app.models.invoice import ExtractionResult


def extract_from_invoice(file_bytes: bytes, invoice_id: str) -> ExtractionResult:
    """
    Run the extraction pipeline on an invoice file.

    Steps:
    1) PDF text-layer extraction via PyMuPDF (fitz) for speed
    2) If no text layer, Tesseract OCR on PyMuPDF-rendered images
    3) Regex rules extract vendor, invoice number, amount, GSTIN, due date, line items
    4) Confidence scoring (regex match + OCR confidence + checksum validation)
    5) If overall confidence < 0.7, fall back to Gemini vision API

    Full implementation: see Day 3.
    """
    return ExtractionResult(
        vendor_name=None,
        vendor_gstin=None,
        invoice_number=None,
        invoice_date=None,
        due_date=None,
        amount=None,
        tax_amount=None,
        total_amount=None,
        line_items=None,
        confidence=0.0,
        overall_confidence=0.0,
        needs_review=True,
        raw_text=None,
    )
