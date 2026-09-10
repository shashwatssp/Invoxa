"""
Unit tests for the weekly digest generator.

Patches ``app.digest.generator.get_invoices`` so the tests don't need a
live Supabase connection.
"""
from datetime import UTC, datetime, timedelta

import pytest
from app.digest import generator
from app.digest.generator import (
    _coerce_amount,
    _due_soon,
    _parse_date,
    _top_vendors,
    generate_digest,
)


@pytest.fixture
def sample_invoices(monkeypatch):
    recent = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=2)
    old = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=30)
    data = [
        {
            "id": "inv-1",
            "vendor_id": "v-acme",
            "invoice_number": "INV-001",
            "amount": "7670.00",
            "due_date": recent.strftime("%Y-%m-%d"),
            "created_at": recent.isoformat(),
            "status": "auto_approved",
        },
        {
            "id": "inv-2",
            "vendor_id": "v-acme",
            "invoice_number": "INV-002",
            "amount": "123456.78",
        "due_date": (datetime.now(UTC).replace(tzinfo=None) + timedelta(days=2)).strftime("%Y-%m-%d"),
            "created_at": recent.isoformat(),
            "status": "flagged",
        },
        {
            "id": "inv-3",
            "vendor_id": None,
            "invoice_number": None,
            "amount": None,
            "due_date": None,
            "created_at": old.isoformat(),  # outside 7-day window
            "status": "pending",
        },
    ]
    monkeypatch.setattr(generator, "get_invoices", lambda user_id=None: data)
    return data


class TestParseDate:
    def test_iso(self):
        assert _parse_date("2024-08-30").isoformat().startswith("2024-08-30")

    def test_indian(self):
        assert _parse_date("30/08/2024").day == 30

    def test_none(self):
        assert _parse_date(None) is None

    def test_unparseable(self):
        assert _parse_date("nonsense") is None


class TestCoerceAmount:
    def test_float(self):
        assert _coerce_amount(100.0) == 100.0

    def test_string(self):
        assert _coerce_amount("1,234.56") == 0.0  # commas break float()

    def test_string_numeric(self):
        assert _coerce_amount("1234.56") == 1234.56

    def test_none(self):
        assert _coerce_amount(None) == 0.0


class TestTopVendors:
    def test_ranking(self, sample_invoices):
        top = _top_vendors(sample_invoices)
        # "v-acme" has the most spend
        assert top[0]["vendor"] == "v-acme"
        assert top[0]["total_amount"] == pytest.approx(131126.78, rel=1e-2)


class TestDueSoon:
    def test_includes_near_due(self, sample_invoices):
        soon = _due_soon(sample_invoices, days=5)
        assert any(item["invoice_number"] == "INV-002" for item in soon)

    def test_empty(self):
        assert _due_soon([], days=5) == []


class TestGenerateDigest:
    def test_counts_recent_only(self, sample_invoices):
        digest = generate_digest(window_days=7)
        # The "old" invoice (outside window) should be excluded.
        assert digest.invoices_processed == 2
        assert digest.flagged_for_review == 1
        assert digest.auto_approved == 1

    def test_total_amount(self, sample_invoices):
        digest = generate_digest(window_days=7)
        assert digest.total_amount == pytest.approx(131126.78, rel=1e-2)

    def test_to_dict_roundtrip(self, sample_invoices):
        digest = generate_digest(window_days=7)
        as_dict = digest.to_dict()
        assert as_dict["invoices_processed"] == 2
        assert isinstance(as_dict["summary_lines"], list)
        assert len(as_dict["summary_lines"]) >= 2

    def test_summary_lines_built(self, sample_invoices):
        digest = generate_digest(window_days=7)
        joined = "\n".join(digest.summary_lines)
        assert "Processed 2 invoices" in joined
        assert "auto-approved" in joined
