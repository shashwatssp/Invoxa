"""
Phase 3 feature tests: category-spend report, account data export,
and vendor memory on upload (no GSTIN -> case-insensitive name match).
"""

import pytest
from app.auth.security import create_access_token
from app.database import category_spend, export_account_data
from app.main import app
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


def _auth_header(users, email="p3@example.com"):
    row = users.add(email)
    return {"Authorization": f"Bearer {create_access_token(row['id'], row['role'])}"}


# ------------------------------------------------------------ category spend


class TestCategorySpend:
    def test_groups_by_category_biggest_first(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(
            db,
            "get_invoices",
            lambda user_id: [
                {"category": "travel", "amount": 500.0},
                {"category": "software", "amount": 1200.0},
                {"category": "travel", "amount": 250.0},
                {"category": None, "amount": 80.0},  # uncategorized -> other
                {"category": "  ", "amount": 20.0},  # blank -> other
                {"amount": "bad", "category": "travel"},  # unparseable, ignored
            ],
        )
        rows = category_spend("user-1")
        assert rows[0] == {"category": "software", "total_spend": 1200.0}
        assert rows[1] == {"category": "travel", "total_spend": 750.0}
        assert rows[2]["category"] == "other"
        assert rows[2]["total_spend"] == pytest.approx(100.0)

    def test_endpoint_returns_rows(self, users, monkeypatch):
        import app.api.reports as reports_api

        monkeypatch.setattr(
            reports_api,
            "category_spend",
            lambda user_id: [{"category": "software", "total_spend": 42.0}],
        )
        res = client.get("/api/reports/category-spend", headers=_auth_header(users))
        assert res.status_code == 200
        assert res.json() == [{"category": "software", "total_spend": 42.0}]


# ------------------------------------------------------------ account export


class TestAccountExport:
    def test_shape_and_no_password_hash(self, monkeypatch):
        import app.database as db

        monkeypatch.setattr(
            db,
            "get_user_by_id",
            lambda uid: {"id": uid, "email": "a@b.c", "password_hash": "secret"},
        )
        monkeypatch.setattr(db, "list_folders", lambda uid: [{"id": "f1", "name": "Travel"}])
        monkeypatch.setattr(db, "get_review_queue", lambda uid: [{"id": "r1"}])
        monkeypatch.setattr(
            db, "get_invoices", lambda uid: [{"id": "inv1", "amount": 100.0}]
        )

        payload = export_account_data("user-1")
        assert "password_hash" not in payload["user"]
        assert payload["user"]["email"] == "a@b.c"
        assert payload["folders"] == [{"id": "f1", "name": "Travel"}]
        assert payload["invoices"][0]["id"] == "inv1"
        assert payload["review_queue"] == [{"id": "r1"}]
        assert "exported_at" in payload

    def test_endpoint_downloads_json(self, users, monkeypatch):
        import app.api.account as account_api

        monkeypatch.setattr(
            account_api,
            "export_account_data",
            lambda user_id: {"user": {"id": user_id}, "invoices": []},
        )
        res = client.get("/api/account/export", headers=_auth_header(users))
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/json")
        assert "attachment" in res.headers["content-disposition"]
        assert res.json()["user"]["id"] == users.rows["user-1"]["id"]


# ------------------------------------------------------------- vendor memory


def test_upload_vendor_memory_no_gstin(users, monkeypatch):
    """No GSTIN but a known vendor name: attach the vendor and inherit
    that vendor's last-used category when AI categorization is silent."""
    import app.api.invoices as inv_api

    captured: dict = {}

    class FakeResult:
        vendor_gstin = None
        vendor_name = "Acme Traders"
        invoice_number = "INV-7"
        needs_review = False
        overall_confidence = 0.9
        invoice_date = None
        due_date = None
        amount = 300.0
        tax_amount = None
        total_amount = 300.0
        line_items = None
        engine = "rules"

    monkeypatch.setattr(inv_api, "upload_invoice", lambda b, n: f"raw/{n}")
    monkeypatch.setattr(inv_api, "create_invoice", lambda *a, **k: "inv-7")
    monkeypatch.setattr(inv_api, "extract_from_invoice", lambda b, iid: FakeResult())
    monkeypatch.setattr(inv_api, "save_extraction_result", lambda iid, r: None)
    monkeypatch.setattr(inv_api, "update_invoice_fields", lambda iid, fields: captured.update(fields))
    monkeypatch.setattr(inv_api, "update_invoice_status", lambda *a, **k: None)
    monkeypatch.setattr(
        inv_api, "find_vendor_by_name", lambda name: {"id": "vendor-1", "name": name, "gstin": None}
    )
    monkeypatch.setattr(inv_api, "_db_update_vendor", lambda iid, vid: captured.update(vendor=vid))
    monkeypatch.setattr(
        inv_api, "get_latest_category_for_vendor", lambda vid: "office_supplies"
    )

    res = client.post(
        "/api/invoices/upload",
        files={"file": ("m.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_auth_header(users),
    )
    assert res.status_code == 200, res.text
    assert captured.get("vendor") == "vendor-1"
    assert captured.get("category") == "office_supplies"
    assert res.json()["category"] == "office_supplies"


def test_upload_unknown_vendor_stays_unfiled(users, monkeypatch):
    """No GSTIN and an unseen vendor name: no vendor row is attached and
    no category is guessed (AI disabled by the autouse conftest fixture)."""
    import app.api.invoices as inv_api

    captured: dict = {}

    class FakeResult:
        vendor_gstin = None
        vendor_name = "Brand New Vendor"
        invoice_number = "INV-8"
        needs_review = False
        overall_confidence = 0.9
        invoice_date = None
        due_date = None
        amount = 100.0
        tax_amount = None
        total_amount = 100.0
        line_items = None
        engine = "rules"

    monkeypatch.setattr(inv_api, "upload_invoice", lambda b, n: f"raw/{n}")
    monkeypatch.setattr(inv_api, "create_invoice", lambda *a, **k: "inv-8")
    monkeypatch.setattr(inv_api, "extract_from_invoice", lambda b, iid: FakeResult())
    monkeypatch.setattr(inv_api, "save_extraction_result", lambda iid, r: None)
    monkeypatch.setattr(inv_api, "update_invoice_fields", lambda iid, fields: captured.update(fields))
    monkeypatch.setattr(inv_api, "update_invoice_status", lambda *a, **k: None)
    monkeypatch.setattr(inv_api, "find_vendor_by_name", lambda name: None)

    res = client.post(
        "/api/invoices/upload",
        files={"file": ("n.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers=_auth_header(users),
    )
    assert res.status_code == 200, res.text
    assert "vendor" not in captured
    assert "category" not in captured
    assert res.json()["category"] is None


# --------------------------------------------- review corrections (batch)


def _patch_review_pipeline(monkeypatch, owner_id="user-1"):
    """Silence the storage layer behind the correction endpoint and
    capture everything it writes."""
    import app.api.review as review_api
    from app.models.invoice import Correction

    captured: dict = {"corrections": [], "resolved": [], "statuses": []}

    monkeypatch.setattr(review_api, "get_review_item_owner", lambda rid: owner_id)

    def fake_log(review_id, field_name, new_value):
        captured["corrections"].append(
            {"field_name": field_name, "new_value": new_value}
        )
        return Correction(
            invoice_id="inv-1",
            field_name=field_name,
            old_value=None,
            new_value=new_value,
        )

    monkeypatch.setattr(review_api, "log_correction", fake_log)
    monkeypatch.setattr(review_api, "apply_correction_to_invoice", lambda c: {})
    monkeypatch.setattr(
        review_api,
        "resolve_review_item",
        lambda rid, approved, reviewed_by: captured["resolved"].append((rid, approved)),
    )
    monkeypatch.setattr(review_api, "get_review_item_invoice_id", lambda rid: "inv-1")
    monkeypatch.setattr(
        review_api,
        "update_invoice_status",
        lambda iid, status: captured["statuses"].append(status.value),
    )
    return captured


class TestBatchCorrections:
    def test_applies_every_field_and_resolves_once(self, users, monkeypatch):
        captured = _patch_review_pipeline(monkeypatch)
        res = client.post(
            "/api/review/rq-1/correct",
            json={"corrections": [
                {"field_name": "amount", "new_value": "1,180.50"},
                {"field_name": "due_date", "new_value": "15/03/2026"},
            ]},
            headers=_auth_header(users),
        )
        assert res.status_code == 200, res.text
        # Amounts and dates were normalized server-side before writing.
        assert [c["new_value"] for c in captured["corrections"]] == ["1180.5", "2026-03-15"]
        assert captured["resolved"] == [("rq-1", True)]
        assert captured["statuses"] == ["reviewed"]
        assert len(res.json()["corrections"]) == 2

    def test_legacy_single_field_payload_still_works(self, users, monkeypatch):
        captured = _patch_review_pipeline(monkeypatch)
        res = client.post(
            "/api/review/rq-1/correct",
            json={"field_name": "amount", "new_value": "1180.00"},
            headers=_auth_header(users),
        )
        assert res.status_code == 200, res.text
        assert captured["corrections"] == [
            {"field_name": "amount", "new_value": "1180.0"}
        ]
        assert res.json()["correction"]["new_value"] == "1180.0"

    def test_invalid_amount_is_422_and_nothing_is_applied(self, users, monkeypatch):
        captured = _patch_review_pipeline(monkeypatch)
        res = client.post(
            "/api/review/rq-1/correct",
            json={"corrections": [{"field_name": "amount", "new_value": "lots"}]},
            headers=_auth_header(users),
        )
        assert res.status_code == 422
        # Nothing was written: the batch is validated before applying.
        assert captured["corrections"] == []
        assert captured["resolved"] == []

    def test_empty_payload_is_400(self, users, monkeypatch):
        _patch_review_pipeline(monkeypatch)
        res = client.post("/api/review/rq-1/correct", json={}, headers=_auth_header(users))
        assert res.status_code == 400

    def test_other_accounts_review_id_is_403(self, users, monkeypatch):
        _patch_review_pipeline(monkeypatch, owner_id="someone-else")
        res = client.post(
            "/api/review/rq-1/correct",
            json={"corrections": [{"field_name": "amount", "new_value": "10"}]},
            headers=_auth_header(users),
        )
        assert res.status_code == 403
