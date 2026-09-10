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

# "INVOICE: INV-100" style header labels (Contoso layouts)
INVOICE_HEADER_PATTERN = re.compile(
r"\bINVOICE\s*[:#]\s*([A-Za-z0-9][A-Za-z0-9\/\-]*)", re.IGNORECASE
)

# "No. INV-2026-0421 / R3" style document references (EU layouts)
DOC_NO_PATTERN = re.compile(
r"\bNo\.?\s+([A-Z]{2,}[\/-][A-Z0-9]+(?:[\/-][A-Z0-9]+)*)"
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


# Month-name date: "06 February 2026", "03 April 2026", "5 Apr 2026"
MONTH_NAME_DATE_PATTERN = re.compile(
r"(\d{1,2})(?:st|nd|rd|th)?\s+"
r"(January|February|March|April|May|June|July|August|September|October|"
r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
r"\.?\s+(\d{4})",
re.IGNORECASE,
)

_MONTH_NUMS = {
m.lower(): i
for i, m in enumerate(
["january", "february", "march", "april", "may", "june", "july",
"august", "september", "october", "november", "december"], start=1)
}
_MONTH_NUMS.update({
"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
"aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
})


def _normalize_month_name_date(match: re.Match) -> str | None:
    """Convert a month-name date match to a DD/MM/YYYY string."""
    day, month_name, year = match.group(1), match.group(2), match.group(3)
    month = _MONTH_NUMS.get(month_name.lower().rstrip("."))
    if not month:
        return None
    return f"{int(day):02d}/{month:02d}/{year}"


def extract_invoice_number(text: str) -> str | None:
    """Extract invoice number from text."""
    match = INVOICE_NUMBER_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    match = INVOICE_HEADER_PATTERN.search(text)
    if match:
        return match.group(1).strip()

    match = DOC_NO_PATTERN.search(text)
    if match:
        return match.group(1).strip()
    return None


def _normalize_numeric_date(raw: str) -> str | None:
    """
    Normalize a numeric date (DD/MM/YYYY, MM/DD/YYYY, DD-MM-YY, ...) to a
    canonical DD/MM/YYYY string. Day-first is preferred; when that would
    give an impossible month (US-style documents), the components swap.
    Returns None when no sane interpretation exists.
    """
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", raw.strip())
    if not m:
        return None
    a, b, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if year < 100:
        year += 2000
    for day, month in ((a, b), (b, a)):
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                import datetime as _dt

                _dt.date(year, month, day)
            except ValueError:
                continue
            return f"{day:02d}/{month:02d}/{year}"
    return None


def extract_dates(text: str) -> list[str]:
    """Extract all dates from text, normalized to DD/MM/YYYY."""
    dates = []
    for raw in DATE_PATTERN.findall(text):
        normalized = _normalize_numeric_date(raw)
        if normalized:
            dates.append(normalized)
    for match in MONTH_NAME_DATE_PATTERN.finditer(text):
        normalized = _normalize_month_name_date(match)
        if normalized:
            dates.append(normalized)
    return dates


def extract_due_date(text: str) -> str | None:
    """Extract the due date from text (digit or month-name formats)."""
    # Look for 'Due Date' / 'Due:' keyword followed by a date
    due_match = re.search(
        r"Due\s*Date[^₹\d\n]{0,10}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if due_match:
        return _normalize_numeric_date(due_match.group(1)) or due_match.group(1).strip()

    due_named = re.search(
        r"\bDue:?\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|"
        r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if due_named:
        return _normalize_month_name_date(due_named)
    return None


def extract_invoice_date(text: str) -> str | None:
    """Extract the invoice date from text (digit or month-name formats)."""
    # Look for 'Invoice Date' / 'Issued:' keyword
    date_match = re.search(
        r"Invoice\s*Date[^₹\d\n]{0,10}(\d{1,2}[\/\-.]\d{1,2}[\/\-.]\d{2,4})",
        text,
        re.IGNORECASE,
    )
    if date_match:
        return _normalize_numeric_date(date_match.group(1)) or date_match.group(1).strip()

    issued_named = re.search(
        r"\b(?:Issued|Issue\s*Date):?\s+(\d{1,2})(?:st|nd|rd|th)?\s+"
        r"(January|February|March|April|May|June|July|August|September|October|"
        r"November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
        r"\.?\s+(\d{4})",
        text,
        re.IGNORECASE,
    )
    if issued_named:
        return _normalize_month_name_date(issued_named)
    return None


def extract_total_amount(text: str) -> tuple[float | None, str | None, str | None]:
    """
    Extract the grand total amount.

    Returns (amount, raw_value, anchor) where anchor is 'grand' when the
    number was found next to 'Grand Total' (strongest signal), 'total'
    when next to a plain 'Total', or None when not found.
    """
    grand_match = re.search(
        r"Grand\s*Total[^₹\d\n]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
        text,
        re.IGNORECASE,
    )
    if grand_match:
        raw = grand_match.group(1)
        return _parse_amount(raw), raw, "grand"

    # "Total Price: 1075.70" (delivery-note layouts)
    price_match = re.search(
        r"Total\s*Price[^$₹\d\n]{0,20}(?:Rs\.?|INR|₹|$)?\s*([\d,]+\.\d{2})",
        text,
        re.IGNORECASE,
    )
    if price_match:
        raw = price_match.group(1)
        return _parse_amount(raw), raw, "total"

    # Plain "Total ... 1,202.58": must NOT be part of Subtotal, must NOT be
    # glued to another word (Total Pcs.), and must carry 2 decimals so
    # labels like "Total Pcs.: 66" never match.
    total_match = re.search(
        r"(?<![\w])(?<!Sub)(?<!Sub\s)(?<!Grand\s)"
        r"Total[^₹\d\n]{0,25}(?:Rs\.?|INR|₹|$)?\s*([\d,]+\.\d{2})",
        text,
        re.IGNORECASE,
    )
    if total_match:
        raw = total_match.group(1)
        return _parse_amount(raw), raw, "total"

    # "Amount Due" / "Balance Due" as a last resort (may include prior balance)
    due_match = re.search(
        r"(?:Amount|Balance)\s*Due[^$₹\d\n]{0,20}(?:Rs\.?|INR|₹|$)?\s*([\d,]+\.\d{2})",
        text,
        re.IGNORECASE,
    )
    if due_match:
        raw = due_match.group(1)
        return _parse_amount(raw), raw, "total"

    return None, None, None


def extract_subtotal(text: str) -> float | None:
    """Extract the pre-tax subtotal (labels: Subtotal / Net Amount / Taxable Value)."""
    match = re.search(
        r"(?:Sub\s*Total|Subtotal|Net\s*Amount|Taxable\s*(?:Value|Amount))"
        r"[^₹\d\n]{0,25}(?:Rs\.?|INR|₹)?\s*([\d,]+\.?\d{0,2})",
        text,
        re.IGNORECASE,
    )
    if match:
        return _parse_amount(match.group(1))
    return None


# Generic tax labels used on non-GST (international) invoices.
# The amount must not run into another digit (rejects VAT IDs like
# CHE-114.778.901) and the optional percentage must sit directly after
# the label so stray numbers are never picked up.
GENERIC_TAX_PATTERN = re.compile(
    r"\b(SALES\s*TAX|VALUE\s*ADDED\s*TAX|VAT)\b"
    r"(?:\s*\(\s*\d+(?:\.\d+)?\s*%\s*\)|\s*\d+(?:\.\d+)?\s*%)?"
    r"[^$₹\d\n]{0,10}(?:Rs\.?|INR|₹|\$|CHF|EUR|USD)?\s*([\d,]+\.\d{2})(?!\d)",
    re.IGNORECASE,
)


def extract_taxes(text: str) -> dict[str, float | None]:
    """Extract CGST, SGST, IGST, UTGST or generic (Sales Tax / VAT) amounts."""
    taxes = {"cgst": None, "sgst": None, "igst": None, "utgst": None, "other": None}
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

    if all(v is None for v in taxes.values()):
        generic = GENERIC_TAX_PATTERN.search(text)
        if generic:
            taxes["other"] = _parse_amount(generic.group(2))
    return taxes


# Common company suffixes used in a header-line vendor heuristic.
_COMPANY_SUFFIX_RE = re.compile(
    r"\b(PVT|PRIVATE|LTD|LIMITED|LLP|LLC|INC|CORP|COMPANY|CO|ENTERPRISES|"
    r"TRADERS|INDUSTRIES|LOGISTICS|SOLUTIONS|SERVICES|AGENCIES)\b\.?",
    re.IGNORECASE,
)


# Trailing document-title tokens that are not part of the company name.
_VENDOR_TITLE_RE = re.compile(
    r"\s*\b(TAX|SERVICE)?\s*INVOICE\s*$", re.IGNORECASE
)


def _clean_vendor_name(name: str) -> str:
    """Strip document-title suffixes like 'TAX INVOICE' from a vendor name."""
    return _VENDOR_TITLE_RE.sub("", name).strip()


def extract_vendor_name(text: str) -> str | None:
    """Extract vendor/seller name from text."""
    # Look for patterns like "Seller", "Vendor", "Supplier" with name
    for label in ["Seller", "Vendor", "Supplier", "From", "Sold by"]:
        pattern = rf"\b{label}\b[^A-Za-z\n]{{0,20}}([A-Z][A-Za-z &,.()]+)"
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return _clean_vendor_name(match.group(1).strip())

    # Fallback: look for uppercase text before "GSTIN"
    match = VENDOR_PATTERN.search(text)
    if match:
        return _clean_vendor_name(match.group(1).strip())

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
            return _clean_vendor_name(candidate)

    return None


# Summary/total lines that must never be mistaken for line items.
# Note: a generic word like 'Taxes' is NOT excluded - on some layouts
# (e.g. flight fee breakdowns) a '... Taxes' row IS a legitimate item.
_SUMMARY_LINE_RE = re.compile(
    r"(?i)\b(sub\s*total|subtotal|grand\s*total|total\b|amount\s*due|"
    r"balance\s*due|cgst|sgst|igst|utgst|sales\s*tax|vat\b|gst\b|"
    r"tax\s*amount|rounding|previous\s+unpaid|already\s+paid|advance\s+paid|"
    r"net\s+taxable|net\s+non|payment)\b"
)

# A section-subtotal caption printed on its own line, e.g. the Nordwind
# layout 'Hardware 2,988.00' followed by 'subtotal' on the next line.
_SUBTOTAL_CAPTION_RE = re.compile(r"(?i)^\s*(?:sub\s*total|subtotal)\s*$")

# A 2-decimal amount, optionally negative, not followed by more digits/%.
_AMOUNT_TOKEN_RE = re.compile(r"-?\d[\d,]*\.\d{2}(?!\d*%)")


def extract_line_items(text: str) -> list[dict[str, Any]]:
    """
    Extract line items from invoice text.

    A line is a line item only when it looks like a table row: it carries a
    textual description AND at least one 2-decimal amount, and it is not a
    summary row (subtotal / tax / total / balance). The item amount is the
    LAST amount on the line (the row total), which is what invoices print
    as the extended price.
    """
    items: list[dict[str, Any]] = []
    lines = [raw.strip() for raw in text.split("\n")]
    for idx, line in enumerate(lines):
        if len(line) < 8:
            continue
        if _SUMMARY_LINE_RE.search(line):
            continue
        # Skip amounts whose caption ('subtotal') lands on the NEXT line.
        next_line = next((ln for ln in lines[idx + 1:] if ln), "")
        if _SUBTOTAL_CAPTION_RE.match(next_line):
            continue
        if not re.search(r"[A-Za-z]{3}", line):
            continue  # no description
        amount_matches = _AMOUNT_TOKEN_RE.findall(line)
        if not amount_matches:
            continue
        items.append({
            "description": line[:100],
            "amount": _parse_amount(amount_matches[-1]),
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

    total, _total_raw, total_anchor = extract_total_amount(text)
    taxes = extract_taxes(text)
    tax_total = sum(v for v in taxes.values() if v is not None)

    # Subtotal: prefer an explicit label; otherwise derive from total - taxes
    # so the arithmetic check (subtotal + tax == total) can actually hold.
    subtotal = extract_subtotal(text)
    if subtotal is None and total is not None and tax_total > 0:
        subtotal = round(total - tax_total, 2)

    return {
        "vendor_name": extract_vendor_name(text),
        "vendor_gstin": gstin,
        "invoice_number": extract_invoice_number(text),
        "invoice_date": invoice_date,
        "due_date": due_date,
        "amount": subtotal,
        "tax_amount": tax_total if tax_total > 0 else None,
        "total_amount": total,
        "total_anchor": total_anchor,
        "line_items": extract_line_items(text),
        "taxes": taxes,
        "gstin_candidates": gstin_candidates,
        "has_gst_keywords": bool(
            re.search(r"GSTIN|CGST|SGST|IGST|UTGST", text, re.IGNORECASE)
        ),
    }
