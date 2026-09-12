"""
OCR-first extraction pipeline.
Strategy: text-layer extraction (PyMuPDF/pdfplumber) -> regex rules -> confidence scoring -> Gemini fallback.
"""
from app.config import CONFIDENCE_THRESHOLD
from app.extraction.ocr import extract_text
from app.extraction.regex_rules import extract_all_fields
from app.models.invoice import ExtractionResult
from app.validation.anomaly import detect_anomalies, should_flag_for_review
from app.validation.duplicate import is_duplicate
from app.validation.gstin import validate_gstin

# Human-readable text for each anomaly code shown in the review queue.
ANOMALY_TEXT = {
    "missing_invoice_number": "Invoice number not found",
    "missing_total_amount": "Could not read the amount",
    "missing_vendor_gstin": "GSTIN missing on an Indian GST invoice",
    "amount_mismatch": "Line items do not add up to the total",
    "future_invoice_date": "Invoice date is in the future",
    "unparseable_invoice_date": "Could not read the dates",
    "due_date_before_invoice_date": "Due date is before the invoice date",
    "invalid_amount": "Amount is zero or negative",
    "very_low_confidence": "Text could barely be read",
}


def _friendly_anomaly(code: str) -> str:
    """Map an anomaly code (may carry a suffix after ': ') to readable text."""
    base = code.split(":", 1)[0].strip()
    return ANOMALY_TEXT.get(base, code)

# Relative importance of each field when scoring overall confidence.
# The overall score is the weighted mean over APPLICABLE fields only:
# a missing field is excluded from the denominator rather than scored 0,
# so a clean international invoice (no GSTIN) is not unfairly punished.
FIELD_WEIGHTS = {
    "total_amount": 0.35,
    "vendor_gstin": 0.20,
    "invoice_number": 0.20,
    "amount": 0.10,
    "tax_amount": 0.05,
    "invoice_date": 0.05,
    "due_date": 0.03,
    "vendor_name": 0.02,
}


def _parseable_date(value) -> bool:
    """True when the value parses as a sane DD/MM/YYYY-ish date."""
    if not value or not isinstance(value, str):
        return False
    from app.validation.anomaly import _parse_indian_date

    return _parse_indian_date(value) is not None


def compute_field_confidences(fields: dict, gstin_valid: bool, arithmetic_passes: bool) -> dict:
    """Evidence-weighted per-field confidence.

    Scores reflect HOW the value was found, not just presence:
    checksum-validated GSTIN > labeled amounts > plain regex hits.
    Missing fields are simply absent from the dict (not scored 0).
    """
    conf: dict[str, float] = {}

    if fields.get("vendor_gstin"):
        conf["vendor_gstin"] = 0.95 if gstin_valid else 0.4

    if fields.get("invoice_number"):
        conf["invoice_number"] = 0.9

    for key in ("invoice_date", "due_date"):
        if _parseable_date(fields.get(key)):
            conf[key] = 0.9

    if fields.get("total_amount"):
        anchor = fields.get("total_anchor")
        score = 0.92 if anchor == "grand" else 0.85
        if not arithmetic_passes:
            score = min(score, 0.5)
        conf["total_amount"] = score

    if fields.get("amount") is not None:
        conf["amount"] = 0.85

    if fields.get("tax_amount"):
        conf["tax_amount"] = 0.9

    if fields.get("vendor_name"):
        conf["vendor_name"] = 0.75

    return conf


def compute_overall_confidence(field_confidences: dict) -> float:
    """Weighted mean over the fields that were actually extracted."""
    if not field_confidences:
        return 0.0
    total_weight = sum(
        w for name, w in FIELD_WEIGHTS.items() if name in field_confidences
    )
    if total_weight == 0:
        return 0.0
    weighted = sum(
        field_confidences[name] * w
        for name, w in FIELD_WEIGHTS.items()
        if name in field_confidences
    )
    return round(weighted / total_weight, 2)


def _arithmetic_validation(fields):
    """
    Validate that subtotal + tax equals grand total.

    Tolerates either Rs 1 or 0.5% rounding drift, whichever is larger.
    Returns True if validation passes or cannot be performed (either
    operand missing).
    """
    total = fields.get("total_amount")
    subtotal = fields.get("amount")
    taxes = fields.get("taxes") or {}

    if total is None or subtotal is None:
        return True

    tax_total = sum(v for v in taxes.values() if v is not None)
    if tax_total > 0:
        tolerance = max(1.0, 0.005 * float(total))
        if abs(subtotal + tax_total - float(total)) > tolerance:
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
    3) Validate GSTIN using checksum (python-stdnum + direct mod-36)
    4) Perform arithmetic validation (line items + tax == total)
    5) Compute field-level and overall confidence scores
    6) Check for anomalies and duplicates
    7) If overall confidence < threshold, fall back to Gemini vision API

    Returns ExtractionResult with all fields and confidence scores.
    """
    # Step 1: Extract text
    text, _used_ocr = extract_text(file_bytes)

    if not text or not text.strip():
        # Image-only scanned PDF (or OCR unavailable on the server).
        # Try Gemini vision on the page images before giving up, so
        # scans and photos still extract instead of dead-ending in review.
        if GEMINI_FALLBACK_AVAILABLE:
            gemini_result = gemini_fallback(file_bytes, "")
            if gemini_result:
                gemini_result.needs_review = (
                    gemini_result.overall_confidence < CONFIDENCE_THRESHOLD
                )
                return gemini_result
        return ExtractionResult(
            needs_review=True,
            overall_confidence=0.0,
            confidence=0.0,
            raw_text=None,
        )

    # Step 2: Extract fields via regex
    fields = extract_all_fields(text)

    # Step 3: Validate GSTIN via checksum. A GSTIN is only *expected* on
    # Indian GST documents; international invoices without one are fine.
    gstin_valid = False
    if fields.get("vendor_gstin"):
        gstin_valid = validate_gstin(fields["vendor_gstin"])
    gst_applicable = bool(fields.get("gstin_candidates")) or bool(
        fields.get("has_gst_keywords")
    )

    # Step 4: Arithmetic validation (subtotal + tax == grand total)
    arithmetic_passes = _arithmetic_validation(fields)

    # Step 5: Evidence-weighted confidence
    field_confidence = compute_field_confidences(fields, gstin_valid, arithmetic_passes)
    overall = compute_overall_confidence(field_confidence)

    # Build initial result
    result = ExtractionResult(
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
        needs_review=False,
        raw_text=text,
    )

    # Step 6: Duplicate check and honest, specific review reasons.
    has_duplicates = is_duplicate(
        result.vendor_gstin, result.invoice_number, result.total_amount
    )
    anomalies = detect_anomalies(result, gstin_applicable=gst_applicable)

    # Determine if review is needed: low overall confidence, real anomalies,
    # duplicates, or an Indian GST document without a valid GSTIN.
    needs_review = (
        should_flag_for_review(result, gstin_applicable=gst_applicable)
        or (gst_applicable and not gstin_valid)
        or has_duplicates
    )

    if needs_review:
        reasons = [_friendly_anomaly(code) for code in anomalies]
        if gst_applicable and not gstin_valid:
            reasons.append("GSTIN failed validation")
        if has_duplicates:
            reasons.append("Possible duplicate of an existing invoice")
        if overall < CONFIDENCE_THRESHOLD:
            reasons.append(
                f"Low extraction confidence ({round(overall * 100)}%)"
            )
        result.review_reasons = list(dict.fromkeys(reasons)) or ["Flagged for review"]

    # If still very low confidence, try Gemini fallback
    if needs_review and overall < 0.3 and GEMINI_FALLBACK_AVAILABLE:
        gemini_result = gemini_fallback(file_bytes, text)
        if gemini_result:
            gemini_result.needs_review = gemini_result.overall_confidence < CONFIDENCE_THRESHOLD
            return gemini_result

    result.needs_review = needs_review
    return result
