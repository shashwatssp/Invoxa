"""
OCR-first extraction pipeline.
Strategy: text-layer extraction (PyMuPDF/pdfplumber) -> regex rules -> confidence scoring -> Gemini fallback.
"""
from app.models.invoice import ExtractionResult
from app.extraction.ocr import extract_text
from app.extraction.regex_rules import extract_all_fields
from app.validation.gstin import validate_gstin
from app.config import CONFIDENCE_THRESHOLD


def _score_field(value, has_checksum=False):
    """
    Assign confidence score to a field.
    - 0.0 if missing
    - 0.7 if present with structural match (regex)
    - 0.9 if present with checksum/structural validation passed
    """
    if value is None:
        return 0.0
    if isinstance(value, (int, float)) and value > 0:
        return 0.7
    if isinstance(value, str) and len(value) > 0:
        if has_checksum:
            return 0.9
        return 0.7
    return 0.0


def compute_overall_confidence(fields):
    """
    Compute overall confidence from extracted fields.
    Weighted average: GSTIN (0.2), total amount (0.3), invoice number (0.2),
    vendor name (0.15), dates (0.1), taxes (0.05).
    """
    scores = []

    # GSTIN (weight 0.2)
    if fields.get("vendor_gstin"):
        scores.append(("gstin", 0.9, 0.2))
    else:
        scores.append(("gstin", 0.0, 0.2))

    # Total amount (weight 0.3)
    if fields.get("total_amount"):
        scores.append(("amount", 0.7, 0.3))
    else:
        scores.append(("amount", 0.0, 0.3))

    # Invoice number (weight 0.2)
    if fields.get("invoice_number"):
        scores.append(("invoice_number", 0.7, 0.2))
    else:
        scores.append(("invoice_number", 0.0, 0.2))

    # Vendor name (weight 0.15)
    if fields.get("vendor_name"):
        scores.append(("vendor_name", 0.7, 0.15))
    else:
        scores.append(("vendor_name", 0.0, 0.15))

    # Due date (weight 0.1)
    if fields.get("due_date"):
        scores.append(("due_date", 0.7, 0.1))
    else:
        scores.append(("due_date", 0.0, 0.1))

    # Taxes (weight 0.05)
    tax_found = any(v is not None for v in (fields.get("taxes") or {}).values())
    if tax_found:
        scores.append(("taxes", 0.7, 0.05))
    else:
        scores.append(("taxes", 0.0, 0.05))

    total_weight = sum(w for _, _, w in scores)
    weighted_score = sum(score * weight for _, score, weight in scores)

    if total_weight == 0:
        return 0.0

    return round(weighted_score / total_weight, 2)


def _arithmetic_validation(fields):
    """
    Validate that line items + tax amount equals total amount.
    Returns True if validation passes or cannot be performed.
    """
    total = fields.get("total_amount")
    amount = fields.get("amount")
    taxes = fields.get("taxes") or {}

    if total is None or amount is None:
        return True

    tax_total = sum(v for v in taxes.values() if v is not None)
    if tax_total > 0:
        expected_total = amount + tax_total
        difference = abs(expected_total - (total or 0))
        if difference > 1.0:
            return False

    return True


# Check if Gemini fallback is available (optional import)
try:
    from app.extraction.gemini_fallback import gemini_fallback
    GEMINI_FALLBACK_AVAILABLE = True
except ImportError:
    GEMINI_FALLBACK_AVAILABLE = False


def extract_from_invoice(file_bytes, invoice_id):
    """
    Run the full extraction pipeline on an invoice file.

    Steps:
    1) Extract text via PyMuPDF/pdfplumber (OCR fallback for scanned PDFs)
    2) Apply regex rules to extract all fields
    3) Validate GSTIN using checksum (python-stdnum)
    4) Perform arithmetic validation (line items + tax == total)
    5) Score field-level and overall confidence
    6) If overall confidence < threshold, fall back to Gemini vision API

    Returns ExtractionResult with all fields and confidence scores.
    """
    # Step 1: Extract text
    text, used_ocr = extract_text(file_bytes)

    if not text or not text.strip():
        return ExtractionResult(
            needs_review=True,
            overall_confidence=0.0,
            confidence=0.0,
            raw_text=None,
        )

    # Step 2: Extract fields via regex
    fields = extract_all_fields(text)

    # Step 3: Validate GSTIN via checksum
    gstin_valid = False
    if fields.get("vendor_gstin"):
        gstin_valid = validate_gstin(fields["vendor_gstin"])

    # Step 4: Arithmetic validation
    arithmetic_passes = _arithmetic_validation(fields)

    # Step 5: Compute confidence
    field_confidence = {
        "vendor_name": _score_field(fields.get("vendor_name")),
        "vendor_gstin": _score_field(fields.get("vendor_gstin"), has_checksum=gstin_valid),
        "invoice_number": _score_field(fields.get("invoice_number")),
        "invoice_date": _score_field(fields.get("invoice_date")),
        "due_date": _score_field(fields.get("due_date")),
        "amount": _score_field(fields.get("total_amount")),
        "tax_amount": _score_field(fields.get("tax_amount")),
    }

    overall = compute_overall_confidence(fields)

    # If arithmetic validation fails, lower the confidence
    if not arithmetic_passes:
        overall = min(overall, 0.5)

    # Step 6: Determine if review is needed
    needs_review = overall < CONFIDENCE_THRESHOLD or not gstin_valid

    # If still very low confidence, try Gemini fallback
    if needs_review and overall < 0.3 and GEMINI_FALLBACK_AVAILABLE:
        gemini_result = gemini_fallback(file_bytes, text)
        if gemini_result:
            result = gemini_result
            result.needs_review = result.overall_confidence < CONFIDENCE_THRESHOLD
            return result

    return ExtractionResult(
        vendor_name=fields.get("vendor_name"),
        vendor_gstin=fields.get("vendor_gstin"),
        invoice_number=fields.get("invoice_number"),
        invoice_date=fields.get("invoice_date"),
        due_date=fields.get("due_date"),
        amount=fields.get("amount"),
        tax_amount=fields.get("tax_amount"),
        total_amount=fields.get("total_amount"),
        line_items=fields.get("line_items"),
        confidence=min(field_confidence.values()) if field_confidence else 0.0,
        overall_confidence=overall,
        needs_review=needs_review,
        raw_text=text,
    )
