"""Tests for the optional export filters (period / folder / ids) and the
PDF statement endpoint.

The database-layer ``fetch_export_rows`` is faked; these tests verify that
the endpoints pass filters through correctly, validate input, keep results
account-scoped, and that the PDF endpoint emits a real PDF.
"""
import datetime as dt

import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

SAMPLE_ROWS = [
    {
        "id": "inv-1",
        "vendor_id": "v-1",
        "vendor_name": "Vendor One",
        "invoice_number": "INV-2026-001",
        "amount": 7670.00,
        "due_date": "2026-09-15",
        "status": "auto_approved",
        "created_at": "2026-09-05T10:00:00+00:00",
        "folder_id": "folder-1",
    },
    {
        "id": "inv-2",
        "vendor_id": None,
        "vendor_name": None,
        "invoice_number": None,
        "amount": 123456.78,
        "due_date": None,
        "status": "auto_approved",
        "created_at": "2026-09-08T10:00:00+00:00",
        "folder_id": None,
    },
]


@pytest.fixture
def authed(monkeypatch):
    """A signed-up account with the export query helper faked."""
    import app.api.auth as auth_api
    import app.api.export as export_api
    import app.auth.dependencies as deps

    rows = list(SAMPLE_ROWS)
    calls = []

    def fake_fetch(user_id=None, status_filter=None, date_from=None, date_to=None,
                   folder_id=None, ids=None):
        calls.append({
            "user_id": user_id, "status_filter": status_filter,
            "date_from": date_from, "date_to": date_to,
            "folder_id": folder_id, "ids": ids,
        })
        return list(rows)

    # The endpoints fetch via app.api.export; the csv/xlsx/tally builders
    # fetch via their own imported names -- patch them all.
    monkeypatch.setattr(export_api, "fetch_export_rows", fake_fetch)
    import app.export.csv_export as csv_export
    import app.export.tally_xml as tally_xml
    import app.export.xlsx_export as xlsx_export
    monkeypatch.setattr(csv_export, "fetch_export_rows", fake_fetch)
    monkeypatch.setattr(xlsx_export, "fetch_export_rows", fake_fetch)
    monkeypatch.setattr(tally_xml, "fetch_export_rows", fake_fetch)

    def fake_create_user(email, password_hash, name, role):
        return {
            "id": "user-1", "email": email, "name": name, "role": role,
            "created_at": "2026-09-11T00:00:00+00:00",
        }

    monkeypatch.setattr(auth_api, "create_user", fake_create_user)
    monkeypatch.setattr(
        auth_api, "get_user_by_email", lambda email: None
    )
    monkeypatch.setattr(
        deps, "get_user_by_id",
        lambda uid: {"id": "user-1", "email": "e@example.com", "name": "E",
                     "role": "member", "password_hash": "x",
                     "created_at": "2026-09-11T00:00:00+00:00"},
    )

    res = client.post(
        "/api/auth/signup",
        json={"email": "e@example.com", "password": "s3cretPass!", "name": "E", "role": "member"},
    )
    assert res.status_code == 201, res.text
    account = res.json()
    return {"account": account, "calls": calls, "rows": rows}


def _auth(account):
    return {"Authorization": f"Bearer {account['token']}"}


def test_export_filters_require_auth():
    assert client.get("/api/export/pdf").status_code == 401


def test_csv_passes_filters_through(authed):
    res = client.get(
        "/api/export/csv",
        params={"from": "2026-09-01", "to": "2026-09-30",
                "folder_id": "folder-1", "ids": "inv-1,inv-2"},
        headers=_auth(authed["account"]),
    )
    assert res.status_code == 200
    call = authed["calls"][-1]
    assert call["date_from"] == dt.date(2026, 9, 1)
    assert call["date_to"] == dt.date(2026, 9, 30)
    assert call["folder_id"] == "folder-1"
    assert call["ids"] == ["inv-1", "inv-2"]


def test_inverted_date_range_rejected(authed):
    res = client.get(
        "/api/export/csv",
        params={"from": "2026-09-30", "to": "2026-09-01"},
        headers=_auth(authed["account"]),
    )
    assert res.status_code == 422


def test_too_many_ids_rejected(authed):
    res = client.get(
        "/api/export/csv",
        params={"ids": ",".join(f"id-{i}" for i in range(501))},
        headers=_auth(authed["account"]),
    )
    assert res.status_code == 422


def test_preview_reports_count_and_total(authed):
    res = client.get("/api/export/preview", headers=_auth(authed["account"]))
    assert res.status_code == 200
    body = res.json()
    assert body["count"] == 2
    assert abs(body["total"] - (7670.00 + 123456.78)) < 0.01


def test_pdf_statement_download(authed):
    res = client.get(
        "/api/export/pdf",
        params={"from": "2026-09-01", "to": "2026-09-30"},
        headers=_auth(authed["account"]),
    )
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/pdf")
    assert res.content[:4] == b"%PDF"
    assert len(res.content) > 500
    # The period label is human-readable in the document metadata.
    assert "2026-09-01" in res.headers["content-disposition"]


def test_pdf_statement_is_account_scoped(authed):
    """The fetched rows are fetched with the caller's user id, always."""
    client.get("/api/export/pdf", headers=_auth(authed["account"]))
    call = authed["calls"][-1]
    assert call["user_id"] == authed["account"]["user"]["id"]
