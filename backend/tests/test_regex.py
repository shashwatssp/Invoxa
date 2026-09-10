"""
Unit tests for regex-based invoice field extraction.
Tests against synthetic Indian invoice text samples.
"""
from app.extraction.regex_rules import (
    extract_all_fields,
    extract_due_date,
    extract_gstin_candidates,
    extract_invoice_date,
    extract_invoice_number,
    extract_taxes,
    extract_total_amount,
    extract_vendor_name,
)

SAMPLE_INVOICE_TEXT = """
ACME SUPPLIERS LLP
GSTIN: 27AABCD1234E1Z5
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
        amount, raw, anchor = extract_total_amount(SAMPLE_INVOICE_TEXT)
        assert amount == 7670.00
        assert raw == "7,670.00"
        assert anchor == "grand"

    def test_extract_total_amount_lakh_grouping(self):
        text = "Grand Total: Rs. 1,23,456.78\n"
        amount, _raw, anchor = extract_total_amount(text)
        assert amount == 123456.78
        assert anchor == "grand"

    def test_us_date_fallback(self):
        # 15/11 is impossible as DD/MM month 11? No - it is valid. Use an
        # impossible day-first date: 11/15/2019 must read as Nov 15 2019.
        result = extract_invoice_date("INVOICE DATE: 11/15/2019")
        assert result == "15/11/2019"

    def test_generic_sales_tax(self):
        taxes = extract_taxes("Subtotal $100.00\nSALES TAX $10.00\nTOTAL $110.00\n")
        assert taxes["other"] == 10.00

    def test_generic_vat_with_percentage(self):
        taxes = extract_taxes("VAT 8.1% 420.02\nTOTAL DUE CHF 6,025.50\n")
        assert taxes["other"] == 420.02

    def test_vat_registration_number_not_tax(self):
        taxes = extract_taxes("VAT CHE-114.778.901 · IBAN CH93 0076 2011 6238 5295 7\n")
        assert taxes["other"] is None


class TestLineItems:
    def test_summary_lines_excluded(self):
        from app.extraction.regex_rules import extract_line_items

        text = "\n".join(
            [
                "LED TV 43 inch 2 18,500.00 37,000.00",
                "Subtotal: 39,450.00",
                "CGST 9%: 3,550.50",
                "Grand Total: 46,551.00",
            ]
        )
        items = extract_line_items(text)
        assert len(items) == 1
        assert items[0]["amount"] == 37000.00

    def test_section_subtotal_caption_on_next_line(self):
        from app.extraction.regex_rules import extract_line_items

        text = "Hardware 2,988.00\nsubtotal\nWidget 10.00 120.00\n"
        items = extract_line_items(text)
        assert len(items) == 1
        assert items[0]["amount"] == 120.00


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
        assert "27AABCD1234E1Z5" in candidates

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
