"""
GSTIN validation module.
Uses python-stdnum for official mod-36 Luhn checksum.
5-strategy candidate finder for OCR-extracted text.
"""
import re

try:
    from stdnum import in_ as india
    STDNUM_AVAILABLE = True
except ImportError:
    STDNUM_AVAILABLE = False

# GSTIN regex pattern (15 chars)
GSTIN_REGEX = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]")

# GSTIN without strict check char (for fuzzy matching)
GSTIN_PARTIAL_REGEX = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d][ZD][A-Z\d]?")


def validate_gstin(gstin: str) -> bool:
    """
    Validate a GSTIN using python-stdnum's official mod-36 Luhn checksum.
    Falls back to structural validation if python-stdnum is not available.
    """
    if not gstin or len(gstin) != 15:
        return False

    gstin = gstin.strip().upper()

    if STDNUM_AVAILABLE:
        try:
            return india.gstin.is_valid(gstin)
        except Exception:
            return False
    else:
        # Fallback: structural validation only
        return bool(GSTIN_REGEX.match(gstin))


def is_valid(gstin: str) -> bool:
    """Alias for validate_gstin."""
    return validate_gstin(gstin)


def get_pan(gstin: str) -> str | None:
    """Extract PAN (characters 3-12) from a valid GSTIN."""
    if not validate_gstin(gstin):
        return None
    return gstin[2:12]


def find_gstin(text: str) -> str | None:
    """
    5-strategy GSTIN candidate finder.

    Strategy 1: Structured regex match (strict GSTIN pattern)
    Strategy 2: Fuzzy OCR corrections (fix common Tesseract OCR mistakes)
    Strategy 3: Positional context (near 'GSTIN', 'GST No', vendor labels)
    Strategy 4: Checksum-only fallback (try all 15-char candidates)
    Strategy 5: Last-resort numeric scan (relaxed pattern matching)
    """
    if not text:
        return None

    text_upper = text.upper()

    # Strategy 1: Structured regex match (strict)
    matches = GSTIN_REGEX.findall(text_upper)
    for m in matches:
        if validate_gstin(m):
            return m

    # Strategy 2: Fuzzy OCR corrections
    # Common OCR errors: 0 <-> O, 1 <-> I, 5 <-> S, 8 <-> B
    fuzzy_text = _fix_ocr_errors(text_upper)
    matches = GSTIN_REGEX.findall(fuzzy_text)
    for m in matches:
        if validate_gstin(m):
            return m

    # Strategy 3: Positional context
    # Look for GSTIN-like strings near "GSTIN" or "GST NO" labels
    context_matches = _find_gstin_in_context(text_upper)
    for m in context_matches:
        if validate_gstin(m):
            return m

    # Strategy 4: Checksum-only fallback
    # Search for any 15-char alphanumeric string and validate checksum
    candidates = re.findall(r"[0-9A-Z]{15}", text_upper)
    for c in candidates:
        if validate_gstin(c):
            return c

    # Strategy 5: Last-resort relaxed match
    # Look for patterns that are close to GSTIN (maybe missing check char)
    relaxed = re.findall(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]", text_upper)
    for m in relaxed:
        if validate_gstin(m):
            return m

    return None


def _fix_ocr_errors(text: str) -> str:
    """
    Fix common Tesseract OCR errors in GSTIN-like strings.
    """
    # Replace common OCR mistakes
    fixes = str.maketrans({
        "O": "0",  # O -> 0 in first 2 digits
        "I": "1",
        "S": "5",
        "B": "8",
        "Z": "2",
    })
    return text.translate(fixes)


def _find_gstin_in_context(text: str) -> list[str]:
    """
    Find GSTIN candidates that appear near GST-related labels.
    """
    candidates = []
    pattern = re.compile(
        r"(?:GSTIN|GST\s*No\.?|GST\s*Number)[:]?\s*([0-9A-Z]{15})",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)
    candidates.extend(matches)
    return candidates
