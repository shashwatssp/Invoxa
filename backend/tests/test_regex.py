"""
Unit tests for regex-based invoice field extraction.
Tests against synthetic Indian invoice text samples.
"""
import pytest
from app.extraction.regex_rules import (
    extract_invoice_number,
    extract_invoice_date,
    extract_due_date,
    extract_total_amount,
    extract_taxes,
    extract_vendor_name,
    extract_gstin_candidates,
    extract_all_fields,
)


SAMPLE_INVOICE_TEXT = """
ACME SUPPLIERS LLP
GSTIN: 27AABCCDDEEFFG
Invoice Number: INV-2024-001
Invoice Date: 15/08/2024
Due Date: 30/08/2024

Description                    Quantity   Rate      Amount
Widget A                       10         500.00    5,000.00
Widget B                       5          300.00    1,500.00

Sub Total: 6,500.00
CGST 9%: 585.00
SGST 9%: 585.00
Grand Total: 7,670.00
"""


class TestInvoiceNumber:
    def test_extract_invoice_number(self):
        result = extract_invoice_number(SAMPLE_INVOICE_TEXT)
        assert result == "INV-2024-001"

    def test_extract_invoice_number_hash_format(self):
        text = "Invoice # INV/2024/002\n"
        result = extract_invoice_number(text)
        assert result == "INV/2024/002"


class TestDates:
    def test_extract_invoice_date(self):
        result = extract_invoice_date(SAMPLE_INVOICE_TEXT)
        assert result == "15/08/2024"

    def test_extract_due_date(self):
        result = extract_due_date(SAMPLE_INVOICE_TEXT)
        assert result == "30/08/2024"


class TestAmount:
    def test_extract_total_amount(self):
        amount, raw = extract_total_amount(SAMPLE_INVOICE_TEXT)
        assert amount == 7670.00
        assert raw == "7,670.00"

    def test_extract_total_amount_lakh_grouping(self):
        text = "Grand Total: Rs. 1,23,456.78\n"
        amount, raw = extract_total_amount(text)
        assert amount == 123456.78


class TestTaxes:
    def test_extract_taxes(self):
        taxes = extract_taxes(SAMPLE_INVOICE_TEXT)
        assert taxes["cgst"] == 585.00
        assert taxes["sgst"] == 585.00
        assert taxes["igst"] is None


class TestVendorName:
    def test_extract_vendor_name(self):
        result = extract_vendor_name(SAMPLE_INVOICE_TEXT)
        assert result == "ACME SUPPLIERS LLP"


class TestGSTIN:
    def test_extract_gstin_candidates(self):
        candidates = extract_gstin_candidates(SAMPLE_INVOICE_TEXT)
        assert "27AABCCDDEEFFG" in candidates

    def test_strips_invalid_gstin(self):
        candidates = extract_gstin_candidates("Some text 12345 not a gstin")
        assert len(candidates) == 0


class TestExtractAllFields:
    def test_extract_all_fields(self):
        fields = extract_all_fields(SAMPLE_INVOICE_TEXT)
        assert fields["vendor_name"] == "ACME SUPPLIERS LLP"
        assert fields["invoice_number"] == "INV-2024-001"
        assert fields["invoice_date"] == "15/08/2024"
        assert fields["due_date"] == "30/08/2024"
        assert fields["total_amount"] == 7670.00
        assert fields["taxes"]["cgst"] == 585.00
        assert fields["taxes"]["sgst"] == 585.00
