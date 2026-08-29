"""
Unit tests for anomaly detection.
Tests detect_anomalies and should_flag_for_review without database access.
"""
import pytest
from app.models.invoice import ExtractionResult
from app.validation.anomaly import detect_anomalies, should_flag_for_review


def make_result(**kwargs) -> ExtractionResult:
    """Helper to create ExtractionResult with defaults."""
    defaults = {
        "vendor_name": "ACME Corp",
        "vendor_gstin": "27AABCD1234E1Z" + "A",
        "invoice_number": "INV-001",
        "invoice_date": "15/08/2024",
        "due_date": "30/08/2024",
        "amount": 1000.00,
        "tax_amount": 180.00,
        "total_amount": 1180.00,
        "line_items": [{"description": "Widgets", "amount": 1000.00}],
        "confidence": 0.85,
        "overall_confidence": 0.85,
        "needs_review": False,
        "raw_text": "sample text",
    }
    defaults.update(kwargs)
    return ExtractionResult(**defaults)


class TestMissingFields:
    def test_missing_invoice_number(self):
        result = make_result(invoice_number=None)
        anomalies = detect_anomalies(result)
        assert "missing_invoice_number" in anomalies

    def test_missing_amount(self):
        result = make_result(amount=None, total_amount=None)
        anomalies = detect_anomalies(result)
        assert "missing_total_amount" in anomalies

    def test_missing_gstin(self):
        result = make_result(vendor_gstin=None)
        anomalies = detect_anomalies(result)
        assert "missing_vendor_gstin" in anomalies

    def test_all_fields_present_no_anomalies(self):
        result = make_result()
        anomalies = detect_anomalies(result)
        assert len(anomalies) == 0


class TestAmountMismatch:
    def test_amount_mismatch(self):
        # Total should be 1180 but line items + tax = 1000 + 180 = 1180 (matches)
        result = make_result()
        anomalies = detect_anomalies(result)
        assert not any("amount_mismatch" in a for a in anomalies)

    def test_amount_mismatch_detected(self):
        # Total is 5000 but line items say 1000, tax 180 -> expected 1180
        result = make_result(total_amount=5000.00, amount=1000.00, tax_amount=180.00)
        anomalies = detect_anomalies(result)
        assert any("amount_mismatch" in a for a in anomalies)


class TestDateAnomalies:
    def test_future_date(self):
        result = make_result(invoice_date="15/08/2099", due_date="30/08/2099")
        anomalies = detect_anomalies(result)
        assert any("future_invoice_date" in a for a in anomalies)

    def test_due_date_before_invoice_date(self):
        result = make_result(invoice_date="30/08/2024", due_date="15/08/2024")
        anomalies = detect_anomalies(result)
        assert "due_date_before_invoice_date" in anomalies

    def test_valid_dates_no_anomaly(self):
        result = make_result(invoice_date="15/08/2024", due_date="30/08/2024")
        anomalies = detect_anomalies(result)
        assert not any("future_invoice_date" in a for a in anomalies)

    def test_unparseable_date(self):
        result = make_result(invoice_date="not-a-date")
        anomalies = detect_anomalies(result)
        assert "unparseable_invoice_date" in anomalies


class TestInvalidAmount:
    def test_negative_amount(self):
        result = make_result(amount=-100.00, total_amount=-100.00)
        anomalies = detect_anomalies(result)
        assert any("invalid_amount" in a for a in anomalies)

    def test_zero_amount(self):
        result = make_result(amount=0.0, total_amount=0.0)
        anomalies = detect_anomalies(result)
        assert any("invalid_amount" in a for a in anomalies)


class TestLowConfidence:
    def test_very_low_confidence(self):
        result = make_result(overall_confidence=0.2)
        anomalies = detect_anomalies(result)
        assert any("very_low_confidence" in a for a in anomalies)

    def test_normal_confidence(self):
        result = make_result(overall_confidence=0.8)
        anomalies = detect_anomalies(result)
        assert not any("very_low_confidence" in a for a in anomalies)


class TestShouldFlagForReview:
    def test_low_confidence_flagged(self):
        result = make_result(overall_confidence=0.5)
        assert should_flag_for_review(result) is True

    def test_high_confidence_no_flag(self):
        result = make_result(overall_confidence=0.9)
        assert should_flag_for_review(result) is False

    def test_missing_fields_flagged(self):
        result = make_result(invoice_number=None, overall_confidence=0.9)
        assert should_flag_for_review(result) is True

    def test_anomalies_flagged(self):
        result = make_result(total_amount=9999.00, overall_confidence=0.9)
        assert should_flag_for_review(result) is True
