"""
Unit tests for duplicate invoice detection.
Tests amount similarity functions without requiring database access.
"""
import pytest
from app.validation.duplicate import _amount_similarity, _amounts_similar


class TestAmountsSimilar:
    def test_identical_amounts(self):
        assert _amounts_similar(100.0, 100.0, 0.95) is True

    def test_within_threshold(self):
        assert _amounts_similar(100.0, 100.01, 0.95) is True

    def test_outside_threshold(self):
        assert _amounts_similar(100.0, 150.0, 0.95) is False

    def test_both_zero(self):
        assert _amounts_similar(0.0, 0.0, 0.95) is True

    def test_one_zero(self):
        assert _amounts_similar(0.0, 100.0, 0.95) is False

    def test_negative_values(self):
        # Should still work with negatives (though unusual for invoices)
        assert _amounts_similar(-50.0, -50.0, 0.95) is True


class TestAmountSimilarity:
    def test_identical(self):
        assert _amount_similarity(100.0, 100.0) == 1.0

    def test_50_percent_difference(self):
        score = _amount_similarity(100.0, 200.0)
        assert score == 0.5

    def test_both_zero(self):
        assert _amount_similarity(0.0, 0.0) == 1.0

    def test_one_zero(self):
        assert _amount_similarity(0.0, 100.0) == 0.0

    def test_small_difference_high_similarity(self):
        score = _amount_similarity(1000.0, 1001.0)
        assert score > 0.99


class TestIsDuplicate:
    def test_no_gstin_returns_false(self):
        from app.validation.duplicate import is_duplicate
        # Without GSTIN, can't check for duplicates
        assert is_duplicate(None, "INV-001", 100.0) is False

    @pytest.mark.skipif(
        True,  # Skip because requires database access
        reason="Requires Supabase database connection"
    )
    def test_with_database(self):
        """This test requires a live Supabase connection."""
        pass
