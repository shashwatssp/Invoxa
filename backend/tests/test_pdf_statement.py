"""Unit tests for the PDF statement builder (no Supabase needed)."""
import datetime as dt

import pymupdf
from app.export.pdf_statement import ROWS_PER_PAGE, _inr, build_pdf_statement


def _row(n: int, amount=None, created="2026-09-05T10:00:00+00:00", vendor="Vendor"):
    return {
        "id": f"inv-{n}",
        "vendor_name": vendor,
        "vendor_id": None,
        "invoice_number": f"INV-{n:04d}",
        "amount": amount,
        "due_date": None,
        "status": "auto_approved",
        "created_at": created,
        "folder_id": None,
    }


class TestInr:
    def test_simple(self):
        assert _inr(1000) == "Rs 1,000.00"

    def test_indian_grouping(self):
        assert _inr(1234567.0) == "Rs 12,34,567.00"
        assert _inr(12345678.0) == "Rs 1,23,45,678.00"

    def test_small(self):
        assert _inr(5.5) == "Rs 5.50"

    def test_zero(self):
        assert _inr(0) == "Rs 0.00"

    def test_none_is_zero(self):
        assert _inr(None) == "Rs 0.00"

    def test_negative(self):
        assert _inr(-1500.25) == "-Rs 1,500.25"


class TestBuildPdfStatement:
    def test_empty_rows_still_valid_pdf(self):
        pdf = build_pdf_statement([], period_label="Period: all time")
        assert pdf[:4] == b"%PDF"
        assert len(pdf) > 500

    def test_empty_state_page_mentions_no_invoices(self):
        pdf = build_pdf_statement([], period_label="Period: all time")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        text = doc[0].get_text()
        assert "No invoices in this period." in text
        assert "Page 1 of 1" in text

    def test_single_page_with_rows(self):
        rows = [_row(i, amount=100.0 * i) for i in range(1, 11)]
        pdf = build_pdf_statement(rows, period_label="Period: test")
        assert pdf[:4] == b"%PDF"
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        assert doc.page_count == 1
        text = doc[0].get_text()
        assert "INV-0001" in text
        assert "Rs 1,000.00" in text  # amount of the last row (100.0 * 10)
        assert "Total Rs 5,500.00" in text  # grand total: 100 * (1+2+...+10)

    def test_pagination_headers_repeat(self):
        rows = [_row(i, amount=1.0, created=f"2026-09-{(i % 28) + 1:02d}T10:00:00+00:00")
                for i in range(ROWS_PER_PAGE + 5)]
        pdf = build_pdf_statement(rows, period_label="Period: test")
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        assert doc.page_count == 2
        # Table header repeats on page 2.
        assert "Invoice #" in doc[1].get_text()
        assert "Page 2 of 2" in doc[1].get_text()

    def test_generated_at_is_respected(self):
        pdf = build_pdf_statement(
            [], period_label="P",
            generated_at=dt.datetime(2026, 9, 11, 8, 30),
        )
        doc = pymupdf.open(stream=pdf, filetype="pdf")
        assert "Generated 11 Sep 2026 08:30" in doc[0].get_text()
