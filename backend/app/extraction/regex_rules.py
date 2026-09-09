"""
Regex-based field extraction rules for Indian invoices.
Handles GSTIN, invoice number, dates, amounts, taxes, vendor name, and line items.
All regex patterns are designed for typical Indian invoice formats.
"""
import re
from typing import Any

# --- Regex Patterns ---

# GSTIN: 15 chars - 2 digit state code + 5 letters + 4 digits + 1 letter + 1 digit/Z + 1 check char
GSTIN_PATTERN = re.compile(r"\b(\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d])\b")

# Invoice number (after "Invoice No", "Invoice Number", "Inv #" etc.)
INVOICE_NUMBER_PATTERN = re.compile(
r"(?:Invoice\s*(?:No|Number|#)\.?\s*[:-]?\s*)([A-Za-z0-9\/\-]+)",
    re.IGNORECASE,
)

# Date in DD/MM/YYYY or DD-MM-YYYY or DD.MM.YYYY format
DATE_PATTERN = re.compile(
    r"(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})"
)

# Amount: after "Grand Total", "Total", or "Amount" keywords
AMOUNT_PATTERN = re.compile(
    r"(?:Grand\s*Total|Total|Amount)[^₹\d]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
    re.IGNORECASE,
)

# Tax amounts: CGST, SGST, IGST, UTGST
TAX_PATTERN = re.compile(
    r"\b(CGST|SGST|IGST|UTGST)\b(?:\s*\d+%?\s*[:.,]?\s*)?[^₹\d\n]{0,10}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
    re.IGNORECASE,
)

# Vendor names: typically uppercase text before "GSTIN" keyword
VENDOR_PATTERN = re.compile(
    r"([A-Z][A-Z &,.()]+)\s*(?:GSTIN|GST\s*No\.?|GSTIN\s*No\.?)",
    re.IGNORECASE,
)


def _parse_amount(amount_str: str) -> float | None:
    """
    Parse an Indian-format amount string to float.
    Handles lakh grouping (e.g. "1,23,456.78" -> 123456.78).
    """
    if not amount_str:
        return None
    # Remove currency symbols, commas, spaces
    cleaned = re.sub(r"[,\s₹]", "", amount_str.strip())
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_gstin_candidates(text: str) -> list[str]:
    """
    Find all potential GSTIN strings in text.
    Uses structured regex pattern.
    """
    matches = GSTIN_PATTERN.findall(text)
    return [m.strip() for m in matches]


def extract_invoice_number(text: str) -> str | None:
    """Extract invoice number from text."""
    match = INVOICE_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def extract_dates(text: str) -> list[str]:
    """Extract all dates from text (DD/MM/YYYY format)."""
    matches = DATE_PATTERN.findall(text)
    return [m.strip() for m in matches]


def extract_due_date(text: str) -> str | None:
    """Extract the due date from text."""
    # Look for 'Due Date' keyword followed by a date
    due_match = re.search(
        r"Due\s*Date[^₹\d\n]{0,10}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if due_match:
        return due_match.group(1).strip()
    return None


def extract_invoice_date(text: str) -> str | None:
    """Extract the invoice date from text."""
    # Look for 'Invoice Date' keyword
    date_match = re.search(
        r"Invoice\s*Date[^₹\d\n]{0,10}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        return date_match.group(1).strip()
    return None


def extract_total_amount(text: str) -> tuple[float | None, str | None]:
    """
    Extract the total amount.
    Prefers 'Grand Total' keyword. Returns (amount, raw_value).
    """
    # Try Grand Total first
    grand_match = re.search(
        r"Grand\s*Total[^₹\d\n]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
        text,
        re.IGNORECASE,
    )
    if grand_match:
        raw = grand_match.group(1)
        return _parse_amount(raw), raw

    # Fall back to Total
    total_match = re.search(
        r"(?<!Grand\s)Total[^₹\d\n]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
        text,
        re.IGNORECASE,
    )
    if total_match:
        raw = total_match.group(1)
        return _parse_amount(raw), raw

    return None, None


def extract_taxes(text: str) -> dict[str, float | None]:
    """Extract CGST, SGST, IGST, UTGST tax amounts."""
    taxes = {"cgst": None, "sgst": None, "igst": None, "utgst": None}
    for match in TAX_PATTERN.finditer(text):
        tax_type = match.group(1).upper()
        amount = _parse_amount(match.group(2))
        key_mapping = {
            "CGST": "cgst",
            "SGST": "sgst",
            "IGST": "igst",
            "UTGST": "utgst",
        }
        if tax_type in key_mapping:
            taxes[key_mapping[tax_type]] = amount
    return taxes


# Common company suffixes used in a header-line vendor heuristic.
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(PVT|PRIVATE|LTD|LIMITED|LLP|LLC|INC|CORP|COMPANY|CO|ENTERPRISES|"
    r"TRADERS|INDUSTRIES|LOGISTICS|SOLUTIONS|SERVICES|AGENCIES)\b\.?",
    re.IGNORECASE,
)


def extract_vendor_name(text: str) -> str | None:
    """Extract vendor/seller name from text."""
    # Look for patterns like "Seller", "Vendor", "Supplier" with name
    for label in ["Seller", "Vendor", "Supplier", "From", "Sold by"]:
        pattern = rf"\b{label}\b[^A-Za-z\n]{{0,20}}([A-Z][A-Za-z &,.()]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()

    # Fallback: look for uppercase text before "GSTIN"
    match = VENDOR_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    # Fallback: the document header, i.e. one of the first few lines that looks
    # like a company name (contains a corporate suffix). This catches the
    # common layout where the business name is the first line of the PDF.
    for line in text.splitlines()[:6]:
        candidate = line.strip()
        if len(candidate) < 4 or len(candidate) > 80:
            continue
        if not _COMPANY_SUFFIX_RE.search(candidate):
            continue
        # Prefer lines that are predominantly uppercase (typical invoice header)
        letters = [c for c in candidate if c.isalpha()]
        if letters and sum(c.isupper() for c in letters) / len(letters) > 0.6:
            return candidate

    return None


def extract_line_items(text: str) -> list[dict[str, Any]]:
    """
    Extract line items from invoice text.
    This is a simplified extractor - looks for table-like patterns.
    """
    items = []
    # Simple pattern: description followed by amount
    # This is a placeholder that can be enhanced with pdfplumber table extraction
    lines = text.split("\n")
    for line in lines:
        # Look for lines that look like line items (have description + amount)
        amount_match = re.search(r"([\d,]+\.\d{2})", line)
        if amount_match and len(line.strip()) > 10:
            items.append({
                "description": line.strip()[:100],
                "amount": _parse_amount(amount_match.group(1)),
            })
    return items


def extract_all_fields(text: str) -> dict[str, Any]:
    """
    Extract all fields from invoice text using regex rules.
    Returns a dict of field_name -> value with basic structure.
    Confidence is assigned per field in the pipeline.
    """
    from app.validation.gstin import find_gstin

    gstin_candidates = extract_gstin_candidates(text)
    gstin = find_gstin(text) if gstin_candidates else None

    invoice_date = extract_invoice_date(text)
    due_date = extract_due_date(text)
    if not due_date:
        dates = extract_dates(text)
        due_date = dates[-1] if dates else None
    if not invoice_date and extract_dates(text):
        invoice_date = extract_dates(text)[0]

    total, _total_raw = extract_total_amount(text)
    taxes = extract_taxes(text)
    tax_total = sum(v for v in taxes.values() if v is not None)

    return {
        "vendor_name": extract_vendor_name(text),
        "vendor_gstin": gstin,
        "invoice_number": extract_invoice_number(text),
        "invoice_date": invoice_date,
        "due_date": due_date,
        "amount": total,
        "tax_amount": tax_total if tax_total > 0 else None,
        "total_amount": total,
        "line_items": extract_line_items(text),
        "taxes": taxes,
        "gstin_candidates": gstin_candidates,
    }
