"""
Phase 2 feature tests: auto categorization, due-soon, vendor summary,
monthly spend, detail-page field editing, and the GST summary export.
"""

import datetime as dt

import pytest
from app.auth.security import create_access_token
from app.categorization.gemini import ai_category
from app.database import filter_due_soon, monthly_spend, vendor_spend_summary
from app.export.gst_summary import summarize_rows
from app.main import app
from app.models.invoice import Correction
from fastapi.testclient import TestClient

client = TestClient(app)


class UserStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._n = 0

    def add(self, email):
        self._n += 1
        uid = f"user-{self._n}"
        self.rows[uid] = {
            "id": uid,
            "email": email,
            "name": "Test",
            "role": "member",
            "created_at": "2026-09-10T00:00:00+00:00",
        }
        return self.rows[uid]


@pytest.fixture
def users(monkeypatch):
    store = UserStore()

    import app.api.auth as auth_api
    import app.auth.dependencies as deps

    monkeypatch.setattr(
        auth_api, "create_user", lambda email, password_hash, name, role: store.add(email)
    )
    monkeypatch.setattr(auth_api, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(deps, "get_user_by_id", lambda uid: store.rows.get(uid))
    return store


def _auth_header(users, email="p2@example.com"):
    row = users.add(email)
    return {"Authorization": f"Bearer {create_access_token(row['id'], row['role'])}"}


# ------------------------------------------------------------ categorization


class TestAiCategory:
    def test_no_key_returns_none(self, monkeypatch):
        import app.categorization.gemini as cat

        monkeypatch.setattr(cat, "GEMINI_API_KEY", "")
        assert ai_category("Acme", "INV-1", 500.0) is None

    def test_unknown_category_rejected(self, monkeypatch):
        import app.categorization.gemini as cat

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"category": "cryptocurrency"}'}]}}
                    ]
                }

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                return _FakeResponse()

        monkeypatch.setattr(cat, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(cat.httpx, "Client", lambda **kw: _FakeClient())
        assert ai_category("Acme", "INV-1", 500.0) is None

    def test_known_category_accepted(self, monkeypatch):
        import app.categorization.gemini as cat

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"category": "travel"}'}]}}
                    ]
                }

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                return _FakeResponse()

        monkeypatch.setattr(cat, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(cat.httpx, "Client", lambda **kw: _FakeClient())
        assert ai_category("Acme", "INV-1", 500.0) == "travel"


def test_upload_auto_categorizes(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}

    class FakeResult:
        vendor_gstin = None
        vendor_name = "Acme"
        invoice_number = "INV-9"
        needs_review = False
        overall_confidence = 0.9
        invoice_date = None
        due_date = None
        amount = 500.0
        tax_amount = None
        total_amount = 500.0
        line_items = None
        engine = "rules"

    monkeypatch.setattr(inv_api, "upload_invoice", lambda b, n: f"raw/{n}")
    monkeypatch.setattr(inv_api, "create_invoice", lambda *a, **k: "inv-9")
    monkeypatch.setattr(inv_api, "extract_from_invoice", lambda b, iid: FakeResult())
    monkeypatch.setattr(inv_api, "save_extraction_result", lambda iid, r: None)
    monkeypatch.setattr(inv_api, "update_invoice_fields", lambda iid, fields: captured.update(fields))
    monkeypatch.setattr(inv_api, "update_invoice_status", lambda *a, **k: None)

    def fake_ai_category(**kwargs):
        return "office_supplies"

    monkeypatch.setattr(inv_api, "ai_category", fake_ai_category)

    res = client.post(
        "/api/invoices/upload",
        files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_auth_header(users),
    )
    assert res.status_code == 200, res.text
    assert captured.get("category") == "office_supplies"
    assert res.json()["category"] == "office_supplies"


def test_category_endpoint_sets_and_validates(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}
    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": users.rows["user-1"]["id"]},
    )
    monkeypatch.setattr(
        inv_api, "update_invoice_fields", lambda iid, fields: captured.update(fields)
    )

    header = _auth_header(users)
    res = client.patch("/api/invoices/inv-1/category", json={"category": "travel"}, headers=header)
    assert res.status_code == 200
    assert captured["category"] == "travel"

    res = client.patch("/api/invoices/inv-1/category", json={"category": "yachts"}, headers=header)
    assert res.status_code == 422

    res = client.patch("/api/invoices/inv-1/category", json={"category": None}, headers=header)
    assert res.status_code == 200 and res.json()["category"] is None


# ---------------------------------------------------------------- due soon


class TestDueSoon:
    def test_includes_overdue_and_upcoming_excludes_paid(self):
        today = dt.date(2026, 9, 12)
        rows = [
            {"id": "1", "due_date": "2026-09-08", "status": "auto_approved"},  # overdue
            {"id": "2", "due_date": "2026-09-14", "status": "pending"},  # within 5d
            {"id": "3", "due_date": "2026-09-30", "status": "pending"},  # too far
            {"id": "4", "due_date": "2026-09-10", "status": "reviewed"},  # paid
            {"id": "5", "due_date": "nonsense", "status": "pending"},  # unparseable
            {"id": "6", "due_date": None, "status": "pending"},  # no due date
        ]
        due = filter_due_soon(rows, days=5, today=today)
        assert [r["id"] for r in due] == ["1", "2"]
        assert due[0]["overdue"] is True
        assert due[1]["overdue"] is False

    def test_indian_date_format(self):
        today = dt.date(2026, 9, 12)
        rows = [{"id": "1", "due_date": "14/09/2026", "status": "pending"}]
        assert [r["id"] for r in filter_due_soon(rows, days=5, today=today)] == ["1"]


def test_due_soon_endpoint(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}
    monkeypatch.setattr(
        inv_api, "get_due_soon_rows", lambda user_id, days: captured.update(user_id=user_id, days=days) or [{"id": "1"}]
    )
    res = client.get("/api/invoices/due-soon", headers=_auth_header(users))
    assert res.status_code == 200
    assert res.json() == [{"id": "1"}]
    assert captured["days"] == 5


# ----------------------------------------------------------- vendor summary


class TestVendorSummary:
    def test_aggregates_by_vendor(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(
            db,
            "get_invoices",
            lambda user_id: [
                {"vendor_name": "Acme", "amount": 500.0, "created_at": "2026-09-03T10:00:00"},
                {"vendor_name": "Acme", "amount": 250.5, "created_at": "2026-09-05T10:00:00"},
                {"vendor_name": "Beta", "amount": 1000.0, "created_at": "2026-09-01T10:00:00"},
                {"vendor_name": None, "amount": 10.0, "created_at": "2026-09-02T10:00:00"},
            ],
        )
        summary = vendor_spend_summary("user-1")
        assert summary[0]["vendor"] == "Beta"
        assert summary[0]["total_spend"] == 1000.0
        assert summary[1]["vendor"] == "Acme"
        assert summary[1]["total_spend"] == pytest.approx(750.5)
        assert summary[1]["invoice_count"] == 2
        assert summary[1]["last_invoice"] == "2026-09-05"


def test_vendor_summary_endpoint(users, monkeypatch):
    import app.api.vendors as vendors_api

    monkeypatch.setattr(
        vendors_api,
        "vendor_spend_summary",
        lambda user_id: [{"vendor": "Acme", "total_spend": 5.0, "invoice_count": 1}],
    )
    res = client.get("/api/vendors/summary", headers=_auth_header(users))
    assert res.status_code == 200
    assert res.json()[0]["vendor"] == "Acme"


# ----------------------------------------------------------- monthly spend


class TestMonthlySpend:
    def test_buckets_fill_six_months(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(db, "get_invoices", lambda user_id: [])
        buckets = monthly_spend("user-1", months=6)
        assert len(buckets) == 6
        assert buckets[-1]["month"] == dt.date.today().strftime("%Y-%m")
        assert all(bucket["total"] == 0.0 for bucket in buckets)

    def test_totals_by_month(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(
            db,
            "get_invoices",
            lambda user_id: [
                {"amount": 100.0, "created_at": "2026-08-15T10:00:00"},
                {"amount": 250.0, "created_at": "2026-08-20T10:00:00"},
                {"amount": 40.0, "created_at": "2026-09-02T10:00:00"},
                {"amount": 5.0, "created_at": "2025-01-01T10:00:00"},  # outside window
            ],
        )
        buckets = monthly_spend("user-1", months=6)
        by_month = {b["month"]: b for b in buckets}
        assert by_month["2026-08"]["total"] == 350.0
        assert by_month["2026-09"]["total"] == 40.0
        assert "2025-01" not in by_month


# ----------------------------------------------------------- field editing


def test_edit_field_on_detail_page(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}
    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": users.rows["user-1"]["id"]},
    )

    def fake_edit(invoice_id, field_name, new_value):
        captured.update(invoice_id=invoice_id, field_name=field_name, new_value=new_value)
        return Correction(
            invoice_id=invoice_id,
            field_name=field_name,
            old_value=None,
            new_value=new_value,
        )

    monkeypatch.setattr(inv_api, "edit_invoice_field", fake_edit)

    res = client.patch(
        "/api/invoices/inv-1/fields",
        json={"field_name": "total_amount", "new_value": "1,250.50"},
        headers=_auth_header(users),
    )
    assert res.status_code == 200
    assert captured["field_name"] == "total_amount"
    assert captured["new_value"] == "1250.5"  # commas stripped, float-normalized


def test_edit_field_rejects_bad_input(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": users.rows["user-1"]["id"]},
    )
    header = _auth_header(users)

    res = client.patch(
        "/api/invoices/inv-1/fields",
        json={"field_name": "vendor_name", "new_value": "Acme"},  # not editable
        headers=header,
    )
    assert res.status_code == 422

    res = client.patch(
        "/api/invoices/inv-1/fields",
        json={"field_name": "amount", "new_value": "lots"},
        headers=header,
    )
    assert res.status_code == 422

    res = client.patch(
        "/api/invoices/inv-1/fields",
        json={"field_name": "due_date", "new_value": "sometime"},
        headers=header,
    )
    assert res.status_code == 422


# ------------------------------------------------------------ GST summary


class TestGstSummary:
    def test_groups_by_month_with_tax(self):
        rows = [
            {"created_at": "2026-08-10T10:00:00", "amount": 1180.0, "tax_amount": 180.0},
            {"created_at": "2026-08-20T10:00:00", "amount": 590.0, "tax_amount": 90.0},
            {"created_at": "2026-09-05T10:00:00", "amount": 1000.0, "tax_amount": None},
        ]
        summary = summarize_rows(rows)
        assert len(summary) == 2
        aug = summary[0]
        assert aug["month"] == "2026-08"
        assert aug["invoices"] == 2
        assert aug["tax_amount"] == pytest.approx(270.0)
        assert aug["taxable_value"] == pytest.approx(1500.0)
        assert aug["total_amount"] == pytest.approx(1770.0)
        # No tax known: whole amount treated as taxable.
        assert summary[1]["taxable_value"] == pytest.approx(1000.0)

    def test_sorted_oldest_first(self):
        rows = [
            {"created_at": "2026-09-01T10:00:00", "amount": 10.0, "tax_amount": None},
            {"created_at": "2026-07-01T10:00:00", "amount": 20.0, "tax_amount": None},
        ]
        assert [g["month"] for g in summarize_rows(rows)] == ["2026-07", "2026-09"]


def test_gst_summary_endpoint(users, monkeypatch):
    import app.api.export as export_api

    monkeypatch.setattr(export_api, "build_gst_summary", lambda *a, **k: "month,invoices\n2026-09,2\n")
    res = client.get("/api/export/gst-summary", headers=_auth_header(users))
    assert res.status_code == 200
    assert res.text.startswith("month,invoices")
