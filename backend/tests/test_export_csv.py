"""
Unit tests for the CSV export module.

Patches ``app.export.csv_export.get_invoices`` so the tests exercise the
row mapping / formatting helpers without a live Supabase connection.
"""

import pytest
from app.export import csv_export
from app.export.csv_export import CSV_HEADERS


@pytest.fixture
def sample_invoices(monkeypatch):
    data = [
        {
            "id": "inv-1",
            "vendor_id": "v-1",
            "invoice_number": "INV-2026-001",
            "amount": 7670.00,
            "due_date": "2024-08-30",
            "created_at": "2026-09-03T00:00:00+00:00",
            "status": "auto_approved",
        },
        {
            "id": "inv-2",
            "vendor_id": "v-2",
            "invoice_number": "INV-2026-002",
            "amount": 123456.78,
            "due_date": "2024-09-15",
            "created_at": "2026-09-03T00:00:00+00:00",
            "status": "flagged",
        },
        {
            "id": "inv-3",
            "vendor_id": None,
            "invoice_number": None,
            "amount": None,
            "due_date": None,
            "created_at": "2026-09-03T00:00:00+00:00",
            "status": "pending",
        },
    ]
    monkeypatch.setattr(csv_export, "get_invoices", lambda user_id=None: data)
    return data


class TestFormat:
    def test_format_date_iso(self):
        assert csv_export._format_date("2024-08-30") == "30/08/2024"

    def test_format_date_indian(self):
        assert csv_export._format_date("30/08/2024") == "30/08/2024"

    def test_format_date_none(self):
        assert csv_export._format_date(None) == ""

    def test_format_date_unparseable(self):
        assert csv_export._format_date("not-a-date") == "not-a-date"

    def test_safe_amount_none(self):
        assert csv_export._safe_amount(None) == ""

    def test_safe_amount_integer(self):
        assert csv_export._safe_amount(1000) == "1000.00"

    def test_safe_amount_string(self):
        assert csv_export._safe_amount("7670.0") == "7670.00"

    def test_safe_amount_invalid(self):
        assert csv_export._safe_amount("abc") == ""


class TestRowFor:
    def test_maps_all_columns(self, sample_invoices):
        first = sample_invoices[0]
        row = csv_export._row_for(first)
        # Every header must be present in the row dict.
        assert set(CSV_HEADERS).issubset(row.keys())
        assert row["voucher_number"] == "INV-2026-001"
        assert row["amount"] == "7670.00"
        assert row["total_amount"] == "7670.00"
        assert row["status"] == "Auto Approved"
        assert row["date"] == "30/08/2024"

    def test_handles_missing_values(self, sample_invoices):
        row = csv_export._row_for(sample_invoices[2])
        assert row["voucher_number"] == ""
        assert row["amount"] == ""
        assert row["name"] == ""
        assert row["status"] == "Pending"


class TestBuildCsv:
    def test_header_present(self, sample_invoices):
        csv_text = csv_export.build_csv()
        first_line = csv_text.splitlines()[0]
        assert first_line == ",".join(CSV_HEADERS)

    def test_row_count(self, sample_invoices):
        csv_text = csv_export.build_csv()
        # header + 3 rows
        assert len(csv_text.splitlines()) == 4

    def test_status_filter(self, sample_invoices):
        csv_text = csv_export.build_csv(status_filter="flagged")
        rows = csv_text.splitlines()[1:]  # skip header
        assert len(rows) == 1
        assert "INV-2026-002" in rows[0]

    def test_empty_when_no_rows(self, monkeypatch):
        monkeypatch.setattr(csv_export, "get_invoices", lambda user_id=None: [])
        csv_text = csv_export.build_csv()
        # csv.DictWriter uses \r\n by default; compare line-normalized.
        assert csv_text.splitlines() == [",".join(CSV_HEADERS)]


class TestPreviewRows:
    def test_preview_matches_build(self, sample_invoices):
        rows = csv_export.preview_csv_rows()
        assert len(rows) == 3
        assert rows[0]["voucher_number"] == "INV-2026-001"
