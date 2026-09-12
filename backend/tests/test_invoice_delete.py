"""
Tests for the delete-invoice endpoint: ownership, cleanup call order,
and auth.
"""

import pytest
from app.auth.security import create_access_token
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


def _auth_header(users, email="delete@example.com"):
    row = users.add(email)
    token = create_access_token(row["id"], row["role"])
    return {"Authorization": f"Bearer {token}"}


def test_delete_owned_invoice_cleans_up(users, monkeypatch):
    import app.api.invoices as inv_api

    calls: list[str] = []
    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {
            "id": iid,
            "storage_path": "raw/a.pdf",
            "created_by": users.rows["user-1"]["id"],
        },
    )
    monkeypatch.setattr(
        inv_api, "delete_invoice_file", lambda path: calls.append(f"storage:{path}")
    )

    def fake_delete(invoice_id):
        calls.append(f"row:{invoice_id}")
        return True

    monkeypatch.setattr(inv_api, "delete_invoice", fake_delete)

    res = client.delete("/api/invoices/inv-1", headers=_auth_header(users))
    assert res.status_code == 204
    assert calls == ["storage:raw/a.pdf", "row:inv-1"]


def test_delete_unknown_invoice_404(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(inv_api, "get_invoice", lambda iid: None)
    res = client.delete("/api/invoices/missing", headers=_auth_header(users))
    assert res.status_code == 404


def test_delete_foreign_invoice_403(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": "someone-else"},
    )
    res = client.delete("/api/invoices/inv-1", headers=_auth_header(users))
    assert res.status_code == 403


def test_delete_requires_auth(users):
    assert client.delete("/api/invoices/inv-1").status_code == 401
