"""
Anomaly detection for invoice data.
Checks for data integrity issues: amount mismatches, missing fields, date anomalies.
"""
import re
from datetime import UTC, datetime

from app.models.invoice import ExtractionResult


def detect_anomalies(
    result: ExtractionResult, gstin_applicable: bool = False
) -> list[str]:
    """
    Analyze extraction results for anomalies.

    ``gstin_applicable`` should be True when the document appears to be an
    Indian GST document (GSTIN candidates or CGST/SGST/IGST keywords found).
    A missing GSTIN on international documents is normal, not an anomaly.

    Returns a list of anomaly descriptions (empty = no anomalies).
    """
    anomalies = []

    # 1. Missing critical fields. A missing SUBTOTAL is acceptable when the
    # line items reconcile with the grand total - the document is internally
    # consistent and the amount is trustworthy.
    if result.invoice_number is None:
        anomalies.append("missing_invoice_number")
    if result.amount is None and not _line_items_reconcile(result):
        anomalies.append("missing_total_amount")
    if result.vendor_gstin is None and gstin_applicable:
        anomalies.append("missing_vendor_gstin")

    # 2. Amount mismatch: line items must reconcile with either the grand
    # total (items + tax) or the subtotal (items alone, when per-line amounts
    # are tax-inclusive). Only trusted table rows reach this check because
    # extract_line_items skips summary/total lines.
    if result.line_items and result.total_amount:
        line_total = sum(
            item.get("amount", 0) for item in result.line_items
            if isinstance(item.get("amount"), (int, float))
        )
        tax_total = result.tax_amount or 0
        total = result.total_amount
        tolerance = max(1.0, 0.005 * float(total))
        matches_total = abs(line_total + tax_total - total) <= tolerance
        matches_subtotal = result.amount is not None and abs(
            line_total - result.amount
        ) <= tolerance
        if not matches_total and not matches_subtotal:
            anomalies.append(
                f"amount_mismatch: line_items={line_total:.2f}, tax={tax_total:.2f}, total={total:.2f}"
            )

    # 3. Date anomaly: invoice date is in the future
    if result.invoice_date:
        try:
            inv_date = _parse_indian_date(result.invoice_date)
            if inv_date is None:
                anomalies.append("unparseable_invoice_date")
            else:
                now = datetime.now(UTC).replace(tzinfo=None)
                if inv_date > now:
                    anomalies.append(f"future_invoice_date: {result.invoice_date}")
        except (ValueError, TypeError):
            anomalies.append("unparseable_invoice_date")

    # 4. Due date before invoice date
    if result.invoice_date and result.due_date:
        try:
            inv_date = _parse_indian_date(result.invoice_date)
            due_date = _parse_indian_date(result.due_date)
            if inv_date and due_date and due_date < inv_date:
                anomalies.append("due_date_before_invoice_date")
        except (ValueError, TypeError):
            pass

    # 5. Negative or zero amount
    if result.amount is not None and result.amount <= 0:
        anomalies.append(f"invalid_amount: {result.amount}")

    # 6. Very low overall confidence
    if result.overall_confidence is not None and result.overall_confidence < 0.3:
        anomalies.append(f"very_low_confidence: {result.overall_confidence}")

    return anomalies


def _parse_indian_date(date_str: str) -> datetime | None:
    """
    Parse numeric dates. Day-first (Indian) order is preferred; when that
    would give an impossible month, the components swap (US-style docs,
    e.g. 11/15/2019 -> Nov 15 2019). Also accepts 2-digit years.
    """
    m = re.fullmatch(
        r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", str(date_str).strip()
    )
    if m:
        a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if year < 100:
            year += 2000
        for day, month in ((a, b), (b, a)):
            if 1 <= month <= 12 and 1 <= day <= 31:
                try:
                    return datetime(year, month, day)
                except ValueError:
                    continue
        return None

    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _line_items_reconcile(result: ExtractionResult) -> bool:
    """True when extracted line items sum to the grand total (with or
    without tax), within tolerance."""
    if not result.line_items or result.total_amount is None:
        return False
    line_total = sum(
        item.get("amount", 0) for item in result.line_items
        if isinstance(item.get("amount"), (int, float))
    )
    total = float(result.total_amount)
    tolerance = max(1.0, 0.005 * total)
    with_tax = abs(line_total + (result.tax_amount or 0) - total) <= tolerance
    without_tax = abs(line_total - total) <= tolerance
    return with_tax or without_tax


def should_flag_for_review(
    result: ExtractionResult, gstin_applicable: bool = False
) -> bool:
    """
    Determine if an invoice should be flagged for manual review.
    Flags if confidence below 0.8 or any anomalies detected.
    """
    confidence_threshold = 0.8
    if result.overall_confidence is not None and result.overall_confidence < confidence_threshold:
        return True

    return bool(detect_anomalies(result, gstin_applicable=gstin_applicable))
