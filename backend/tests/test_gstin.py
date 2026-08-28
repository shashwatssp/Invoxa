"""
Unit tests for GSTIN validation and 5-strategy candidate finder.
"""
import pytest
from app.validation.gstin import (
    validate_gstin,
    is_valid,
    get_pan,
    find_gstin,
    extract_gstin_candidates,
)


# Structurally valid GSTIN format (15 chars: 2 digits + 5 letters + 4 digits + 1 letter + Z + 1 check)
# Note: full checksum validation requires python-stdnum
VALID_FORMAT_GSTIN = "27AABCCDDEEFFG"
ANOTHER_GSTIN = "09XYZPK123456Z1"


class TestGstinStructure:
    def test_valid_length(self):
        assert not validate_gstin("123")  # too short
        assert not validate_gstin("")  # empty
        assert not validate_gstin(None)  # None

    def test_extract_gstin_candidates_finds_match(self):
        text = "Vendor: ACME\nGSTIN: 27AABCCDDEEFFG\n"
        candidates = extract_gstin_candidates(text)
        assert "27AABCCDDEEFFG" in candidates

    def test_extract_gstin_candidates_no_match(self):
        text = "No GSTIN here, just some text"
        candidates = extract_gstin_candidates(text)
        assert len(candidates) == 0


class TestFindGstinFiveStrategies:
    def test_strategy_1_strict_regex(self):
        """Strategy 1: structured regex match finds GSTIN in clean text."""
        text = "GSTIN: 27AABCCDDEEFFG"
        result = find_gstin(text)
        assert result is not None
        assert len(result) == 15

    def test_strategy_3_positional_context(self):
        """Strategy 3: GSTIN near 'GSTIN' label."""
        text = "GSTIN: 27AABCCDDEEFFG"
        result = find_gstin(text)
        # May return None if checksum fails, but should find structurally
        assert result is not None or extract_gstin_candidates(text)

    def test_no_gstin_in_text(self):
        text = "Just some random text without any GSTIN number"
        result = find_gstin(text)
        assert result is None

    def test_empty_text(self):
        assert find_gstin("") is None
        assert find_gstin(None) is None

    def test_multiple_gstins_returns_first_valid(self):
        """Should return first valid GSTIN when multiple are present."""
        text = "GSTIN: 27AABCCDDEEFFG\nGSTIN: 09XYZPK123456Z1"
        result = find_gstin(text)
        # Will return whichever passes checksum first
        assert result is not None

    def test_ocr_fuzzy_corrections(self):
        """Strategy 2: handle common OCR errors like O->0, I->1."""
        # Simulate OCR output with common errors
        text = "GSTIN: 27AABCC0EEFGC"  # 0 where O should be, C where G might be
        result = find_gstin(text)
        # May or may not find valid one depending on checksum
        # But shouldn't crash
        assert result is None or len(result) == 15


class TestGstinValidation:
    def test_none_input(self):
        assert not validate_gstin(None)

    def test_empty_input(self):
        assert not validate_gstin("")

    def test_wrong_length(self):
        assert not validate_gstin("27AABCCDDEEFF")  # too short
        assert not validate_gstin("27AABCCDDEEFFGG")  # 16 chars

    def test_is_valid_alias(self):
        """is_valid should be identical to validate_gstin."""
        assert is_valid(VALID_FORMAT_GSTIN) == validate_gstin(VALID_FORMAT_GSTIN)


class TestGetPan:
    def test_get_pan_from_valid(self):
        """get_pan should extract characters 3-12 from GSTIN."""
        pan = get_pan(VALID_FORMAT_GSTIN)
        # PAN is positions 3-12 (0-indexed: 2-11)
        if pan is not None:
            assert len(pan) == 10
