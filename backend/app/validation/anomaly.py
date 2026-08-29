"""
Anomaly detection for invoice data.
Checks for data integrity issues: amount mismatches, missing fields, date anomalies.
"""
from datetime import datetime
from typing import Any

from app.models.invoice import ExtractionResult


def detect_anomalies(result: ExtractionResult) -> list[str]:
    """
    Analyze extraction results for anomalies.
    Returns a list of anomaly descriptions (empty = no anomalies).
    """
    anomalies = []

    # 1. Missing critical fields
    if result.invoice_number is None:
        anomalies.append("missing_invoice_number")
    if result.amount is None:
        anomalies.append("missing_total_amount")
    if result.vendor_gstin is None:
        anomalies.append("missing_vendor_gstin")

    # 2. Amount mismatch: line items + tax != grand total
    if result.line_items and result.total_amount:
        line_total = sum(
            item.get("amount", 0) for item in result.line_items
            if isinstance(item.get("amount"), (int, float))
        )
        tax_total = result.tax_amount or 0
        expected_total = line_total + tax_total
        total = result.total_amount
        if abs(expected_total - total) > 1.0:
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
                now = datetime.now()
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
    Parse Indian date formats (DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY).
    """
    for fmt in ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"]:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None


def should_flag_for_review(result: ExtractionResult) -> bool:
    """
    Determine if an invoice should be flagged for manual review.
    Flags if low confidence or any anomalies detected.
    """
    confidence_threshold = 0.7
    if result.overall_confidence is not None and result.overall_confidence < confidence_threshold:
        return True

    anomalies = detect_anomalies(result)
    if anomalies:
        return True

    return False
