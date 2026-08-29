"""
GSTIN validation module.
Direct implementation of the mod-36 Luhn checksum algorithm,
with python-stdnum as a cross-check when available.
5-strategy candidate finder for OCR-extracted text.

GSTIN format (15 characters):
  - Positions 1-2: 2-digit state code
  - Positions 3-12: 10-character PAN (5 letters + 4 digits + 1 letter)
  - Position 13: 1 entity code character
  - Position 14: 'Z' (constant for regular taxpayers, '2' for composition, etc.)
  - Position 15: 1 check character (mod-36 Luhn)

Mod-36 checksum algorithm:
  1. Map each of the first 14 characters to base-36 values (0-9 -> 0-9, A-Z -> 10-35)
  2. Multiply each value by weight factor (1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
  3. Sum all products
  4. Check digit = (36 - (sum % 36)) % 36
  5. Map back to character: 0-9 -> digit, 10-35 -> A-Z
"""
import re

try:
    from stdnum import in_ as india
    STDNUM_AVAILABLE = True
except ImportError:
    STDNUM_AVAILABLE = False

# GSTIN regex pattern (15 chars): 2 digits + 5 letters + 4 digits + 1 letter + 1 char + Z + 1 check
GSTIN_REGEX = re.compile(r"\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]")

# Weights for positions 1-14
_CHECKSUM_WEIGHTS = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14]


def _char_to_value(ch: str) -> int:
    """Map a character to its base-36 value: 0-9 -> 0-9, A-Z -> 10-35, a-z -> 10-35."""
    if ch.isdigit():
        return int(ch)
    return ord(ch.upper()) - ord("A") + 10


def _value_to_char(value: int) -> str:
    """Map a base-36 value back to character: 0-9 -> digit, 10-35 -> A-Z."""
    if value < 10:
        return str(value)
    return chr(ord("A") + value - 10)


def _compute_checksum(gstin_14: str) -> str:
    """
    Compute the mod-36 check character for the first 14 characters of a GSTIN.
    """
    total = 0
    for i, ch in enumerate(gstin_14):
        value = _char_to_value(ch)
        total += value * _CHECKSUM_WEIGHTS[i]

    check_value = (36 - (total % 36)) % 36
    return _value_to_char(check_value)


def verify_checksum(gstin: str) -> bool:
    """
    Verify the mod-36 check character of a GSTIN (first 14 chars -> 15th char).
    """
    if not gstin or len(gstin) != 15:
        return False

    gstin = gstin.strip().upper()
    computed = _compute_checksum(gstin[:14])
    return computed == gstin[14]


def validate_gstin(gstin: str) -> bool:
    """
    Validate a GSTIN: structural check + mod-36 checksum verification.
    Uses direct implementation, cross-checked with python-stdnum if available.
    """
    if not gstin or len(gstin) != 15:
        return False

    gstin = gstin.strip().upper()

    # Structural check: matches GSTIN regex pattern
    if not GSTIN_REGEX.match(gstin):
        return False

    # Primary validation: direct mod-36 checksum (authoritative)
    if verify_checksum(gstin):
        return True

    # If direct checksum fails, fall back to python-stdnum cross-check
    if STDNUM_AVAILABLE:
        try:
            return india.gstin.is_valid(gstin)
        except Exception:
            pass

    return False


def is_valid(gstin: str) -> bool:
    """Alias for validate_gstin."""
    return validate_gstin(gstin)


def get_pan(gstin: str) -> str | None:
    """Extract PAN (characters 3-12, i.e. indices 2-11) from a valid GSTIN."""
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


def extract_gstin_candidates(text: str) -> list[str]:
    """
    Find all potential GSTIN strings in text using regex.
    """
    matches = GSTIN_REGEX.findall(text.upper())
    return [m.strip() for m in matches]


def _fix_ocr_errors(text: str) -> str:
    """
    Fix common Tesseract OCR errors in GSTIN-like strings.
    """
    fixes = str.maketrans({
        "O": "0",  # O -> 0
        "I": "1",  # I -> 1
        "S": "5",  # S -> 5
        "B": "8",  # B -> 8
        "Z": "2",  # Z -> 2
    })
    return text.translate(fixes)


def _find_gstin_in_context(text: str) -> list[str]:
    """
    Find GSTIN candidates that appear near GST-related labels.
    """
    candidates = []
    pattern = re.compile(
        r"(?:GSTIN|GST\s*No\.?|GST\s*Number)[:]\s*([0-9A-Z]{15})",
        re.IGNORECASE,
    )
    matches = pattern.findall(text)
    candidates.extend(matches)
    return candidates
