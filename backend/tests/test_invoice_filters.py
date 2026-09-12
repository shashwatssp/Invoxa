"""
Tests for the invoice list filters (search / status / date range).

The endpoint wiring is verified with a capturing fake; the Python-side
search matcher in ``app.database`` is tested directly.
"""

import datetime as dt
from typing import ClassVar

import pytest
from app.auth.security import create_access_token
from app.database import _filter_by_search
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
    monkeypatch.setattr(
        auth_api, "get_user_by_email", lambda email: None
    )
    monkeypatch.setattr(deps, "get_user_by_id", lambda uid: store.rows.get(uid))
    return store


def _auth_header(users):
    """Create a user row directly and mint a token for it."""
    row = users.add("filter@example.com")
    token = create_access_token(row["id"], row["role"])
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------------------ DB search


class TestFilterBySearch:
    ROWS: ClassVar[list] = [
        {"invoice_number": "INV-001", "vendor_name": "Acme Corp"},
        {"invoice_number": "INV-002", "vendor_name": "Beta Traders"},
        {"invoice_number": None, "vendor_name": None},
    ]

    def test_matches_vendor_case_insensitive(self):
        matched = _filter_by_search(self.ROWS, "acme")
        assert [r["invoice_number"] for r in matched] == ["INV-001"]

    def test_matches_invoice_number(self):
        matched = _filter_by_search(self.ROWS, "inv-002")
        assert [r["vendor_name"] for r in matched] == ["Beta Traders"]

    def test_no_match_returns_empty(self):
        assert _filter_by_search(self.ROWS, "zzz") == []

    def test_blank_search_returns_all(self):
        assert len(_filter_by_search(self.ROWS, "   ")) == 3

    def test_null_fields_do_not_crash(self):
        matched = _filter_by_search(self.ROWS, "o")  # matches "Corp"
        assert len(matched) == 1


# --------------------------------------------------------- endpoint wiring


def test_filters_require_auth(users):
    assert client.get("/api/invoices?search=acme").status_code == 401


def test_filter_params_reach_database(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}

    def fake_get_invoices(user_id=None, folder_id=None, status=None,
                          date_from=None, date_to=None, search=None):
        captured.update(
            user_id=user_id,
            folder_id=folder_id,
            status=status,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        return [
            {
                "id": "inv-1",
                "vendor_id": None,
                "vendor_name": "Acme Corp",
                "invoice_number": "INV-001",
                "amount": 100.0,
                "due_date": None,
                "status": "flagged",
                "storage_path": "raw/a.pdf",
                "created_at": "2026-09-10T10:00:00+00:00",
                "created_by": user_id,
                "folder_id": None,
            }
        ]

    monkeypatch.setattr(inv_api, "get_invoices", fake_get_invoices)
    res = client.get(
        "/api/invoices",
        params={
            "search": "acme",
            "status": "flagged",
            "from": "2026-09-01",
            "to": "2026-09-30",
        },
        headers=_auth_header(users),
    )
    assert res.status_code == 200, res.text
    assert res.json()[0]["vendor_name"] == "Acme Corp"
    assert captured["search"] == "acme"
    assert captured["status"] == "flagged"
    assert captured["date_from"] == dt.date(2026, 9, 1)
    assert captured["date_to"] == dt.date(2026, 9, 30)
    assert captured["user_id"]


def test_no_filters_means_none(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}

    def fake_get_invoices(user_id=None, **kwargs):
        captured.update(kwargs, user_id=user_id)
        return []

    monkeypatch.setattr(inv_api, "get_invoices", fake_get_invoices)
    res = client.get("/api/invoices", headers=_auth_header(users))
    assert res.status_code == 200
    assert captured["search"] is None
    assert captured["status"] is None
    assert captured["date_from"] is None
    assert captured["date_to"] is None


def test_reversed_date_range_rejected(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(inv_api, "get_invoices", lambda **k: [])
    res = client.get(
        "/api/invoices",
        params={"from": "2026-09-30", "to": "2026-09-01"},
        headers=_auth_header(users),
    )
    assert res.status_code == 422


def test_search_capped_at_100_chars(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(inv_api, "get_invoices", lambda **k: [])
    res = client.get(
        "/api/invoices",
        params={"search": "x" * 101},
        headers=_auth_header(users),
    )
    assert res.status_code == 422


def test_invalid_date_rejected(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(inv_api, "get_invoices", lambda **k: [])
    res = client.get(
        "/api/invoices",
        params={"from": "not-a-date"},
        headers=_auth_header(users),
    )
    assert res.status_code == 422
