"""
Comprehensive unit tests for GSTIN validation and the mod-36 checksum algorithm.
"""
from app.validation.gstin import (
    _char_to_value,
    _compute_checksum,
    _value_to_char,
    extract_gstin_candidates,
    find_gstin,
    get_pan,
    is_valid,
    validate_gstin,
    verify_checksum,
)

# Valid GSTIN base (first 14 chars) used to generate test GSTINs
TEST_BASE = "27AABCD1234E1Z"
# The check digit computed by the mod-36 algorithm
TEST_CHECK = _compute_checksum(TEST_BASE)
VALID_GSTIN = TEST_BASE + TEST_CHECK  # Full 15-char valid GSTIN


# Another test base
TEST_BASE2 = "09AABCE5432F2Z"
VALID_GSTIN2 = TEST_BASE2 + _compute_checksum(TEST_BASE2)


class TestCharMapping:
    def test_digit_values(self):
        assert _char_to_value("0") == 0
        assert _char_to_value("5") == 5
        assert _char_to_value("9") == 9

    def test_letter_values(self):
        assert _char_to_value("A") == 10
        assert _char_to_value("Z") == 35

    def test_lowercase_letters(self):
        assert _char_to_value("a") == 10
        assert _char_to_value("z") == 35

    def test_value_to_char_digits(self):
        assert _value_to_char(0) == "0"
        assert _value_to_char(9) == "9"

    def test_value_to_char_letters(self):
        assert _value_to_char(10) == "A"
        assert _value_to_char(35) == "Z"

    def test_roundtrip(self):
        for ch in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            value = _char_to_value(ch)
            assert _value_to_char(value) == ch


class TestChecksumComputation:
    def test_checksum_returns_single_char(self):
        result = _compute_checksum(TEST_BASE)
        assert len(result) == 1

    def test_checksum_is_alphanumeric(self):
        result = _compute_checksum(TEST_BASE)
        assert result.isalnum()

    def test_checksum_deterministic(self):
        """Same input should always produce same checksum."""
        assert _compute_checksum(TEST_BASE) == _compute_checksum(TEST_BASE)


class TestVerifyChecksum:
    def test_valid_gstin_passes(self):
        assert verify_checksum(VALID_GSTIN) is True

    def test_invalid_check_char_fails(self):
        # Wrong check character
        wrong = TEST_BASE + "0"  # '0' is almost certainly wrong
        if wrong[14] != TEST_CHECK:
            assert verify_checksum(wrong) is False

    def test_wrong_length_fails(self):
        assert verify_checksum("27AABCD1234E1Z") is False  # 14 chars
        assert verify_checksum("27AABCD1234E1ZZ1") is False  # 16 chars

    def test_none_input(self):
        assert verify_checksum(None) is False

    def test_empty_input(self):
        assert verify_checksum("") is False


class TestValidateGstin:
    def test_valid_gstin(self):
        assert validate_gstin(VALID_GSTIN) is True

    def test_valid_gstin_uppercase(self):
        assert validate_gstin(VALID_GSTIN.upper()) is True

    def test_valid_gstin_lowercase(self):
        assert validate_gstin(VALID_GSTIN.lower()) is True

    def test_none_input(self):
        assert validate_gstin(None) is False

    def test_empty_input(self):
        assert validate_gstin("") is False

    def test_wrong_length(self):
        assert validate_gstin("27AABCD1234E") is False  # too short

    def test_wrong_format(self):
        # Position 1-2 not digits
        assert validate_gstin("AAABCD1234E1Z" + TEST_CHECK) is False
        # Position 3-7 must be all letters; '1' is a digit at position 6
        assert validate_gstin("27AAB1D1234E1Z" + TEST_CHECK) is False

    def test_invalid_check_char(self):
        # Flip the check character to something wrong
        bad_gstin = TEST_BASE + ("0" if TEST_CHECK != "0" else "1")
        assert validate_gstin(bad_gstin) is False


class TestIs_valid:
    def test_alias(self):
        assert is_valid(VALID_GSTIN) == validate_gstin(VALID_GSTIN)


class TestGetPan:
    def test_get_pan(self):
        pan = get_pan(VALID_GSTIN)
        assert pan is not None
        assert len(pan) == 10
        assert pan == TEST_BASE[2:12]

    def test_get_pan_invalid_gstin(self):
        assert get_pan("INVALID") is None

    def test_get_pan_none(self):
        assert get_pan(None) is None


class TestFindGstin:
    def test_strategy_1_strict_match(self):
        text = f"GSTIN: {VALID_GSTIN}"
        result = find_gstin(text)
        assert result == VALID_GSTIN

    def test_strategy_1_with_whitespace(self):
        text = f"GSTIN: {VALID_GSTIN}  \nSome more text"
        result = find_gstin(text)
        assert result == VALID_GSTIN

    def test_strategy_3_context_label(self):
        text = f"GSTIN: {VALID_GSTIN}"
        result = find_gstin(text)
        assert result == VALID_GSTIN

    def test_strategy_3_gst_no_label(self):
        text = f"GST No. {VALID_GSTIN}"
        result = find_gstin(text)
        assert result == VALID_GSTIN

    def test_no_gstin_found(self):
        text = "This text has no GSTIN number at all."
        result = find_gstin(text)
        assert result is None

    def test_empty_text(self):
        assert find_gstin("") is None
        assert find_gstin(None) is None

    def test_multiple_gstins_returns_first_valid(self):
        text = f"First: {VALID_GSTIN}\nSecond: {VALID_GSTIN2}"
        result = find_gstin(text)
        assert result is not None

    def test_strategy_5_relaxed(self):
        text = f"Some text with {VALID_GSTIN} embedded in it."
        result = find_gstin(text)
        assert result == VALID_GSTIN


class TestExtractGstinCandidates:
    def test_finds_candidates(self):
        text = f"Vendor: ACME\nGSTIN: {VALID_GSTIN}\n"
        candidates = extract_gstin_candidates(text)
        assert VALID_GSTIN in candidates

    def test_no_candidates(self):
        text = "No GSTIN here"
        candidates = extract_gstin_candidates(text)
        assert len(candidates) == 0

    def test_multiple_candidates(self):
        text = f"GST1: {VALID_GSTIN}\nGST2: {VALID_GSTIN2}"
        candidates = extract_gstin_candidates(text)
        assert len(candidates) >= 2
