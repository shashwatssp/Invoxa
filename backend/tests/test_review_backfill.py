"""
Tests for review-queue self-healing (flagged invoices must always have
a pending review item) and the move-to-folder endpoint.
"""

import pytest
from app.auth.security import create_access_token
from app.database import _missing_flagged_invoice_ids
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


def _auth_header(users, email="review@example.com"):
    row = users.add(email)
    token = create_access_token(row["id"], row["role"])
    return {"Authorization": f"Bearer {token}"}


# ------------------------------------------------- backfill logic (pure)


class TestMissingFlagged:
    def test_flags_without_pending_item_are_missing(self):
        pending = [{"invoice_id": "inv-1"}]
        flagged = [{"id": "inv-1"}, {"id": "inv-2"}, {"id": "inv-3"}]
        assert _missing_flagged_invoice_ids(pending, flagged) == ["inv-2", "inv-3"]

    def test_no_flagged_means_nothing_missing(self):
        assert _missing_flagged_invoice_ids([{"invoice_id": "x"}], []) == []

    def test_none_rows_handled(self):
        assert _missing_flagged_invoice_ids(None, [{"id": "a"}]) == ["a"]
        assert _missing_flagged_invoice_ids([{"invoice_id": "a"}], None) == []

    def test_every_flagged_covered(self):
        pending = [{"invoice_id": "a"}, {"invoice_id": "b"}]
        flagged = [{"id": "a"}, {"id": "b"}]
        assert _missing_flagged_invoice_ids(pending, flagged) == []


# ------------------------------------------------------- endpoint wiring


def test_queue_backfills_before_listing(users, monkeypatch):
    import app.api.review as review_api

    calls: list[str] = []

    def fake_backfill(user_id):
        calls.append(user_id)
        return 1

    monkeypatch.setattr(review_api, "backfill_review_queue", fake_backfill)
    monkeypatch.setattr(
        review_api,
        "get_review_queue",
        lambda user_id: [{"id": "rq-1", "invoice_id": "inv-1", "reason": "r", "status": "pending"}],
    )
    res = client.get("/api/review/queue", headers=_auth_header(users))
    assert res.status_code == 200
    assert len(res.json()) == 1
    assert calls  # backfill ran with the account id


def test_queue_requires_auth(users):
    assert client.get("/api/review/queue").status_code == 401


# ---------------------------------------------------- move-to-folder API


def test_move_invoice_to_folder(users, monkeypatch):
    import app.api.invoices as inv_api

    captured: dict = {}

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": users.rows["user-1"]["id"]},
    )
    monkeypatch.setattr(inv_api, "get_folder", lambda fid, owner: {"id": fid, "name": "X"} if fid else None)

    def fake_update(invoice_id, fields):
        captured.update(invoice_id=invoice_id, fields=fields)

    monkeypatch.setattr(inv_api, "update_invoice_fields", fake_update)

    header = _auth_header(users)
    res = client.patch("/api/invoices/inv-1/folder", params={"folder_id": "fold-1"}, headers=header)
    assert res.status_code == 200
    assert res.json() == {"id": "inv-1", "folder_id": "fold-1"}
    assert captured["fields"] == {"folder_id": "fold-1"}

    # Unfiling: folder_id absent -> folder_id set to None.
    res = client.patch("/api/invoices/inv-1/folder", headers=header)
    assert res.status_code == 200
    assert captured["fields"] == {"folder_id": None}


def test_move_invoice_rejects_foreign_folder(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": users.rows["user-1"]["id"]},
    )
    monkeypatch.setattr(inv_api, "get_folder", lambda fid, owner: None)  # not owned

    res = client.patch(
        "/api/invoices/inv-1/folder",
        params={"folder_id": "someone-elses"},
        headers=_auth_header(users),
    )
    assert res.status_code == 404


def test_move_invoice_requires_ownership(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/a.pdf", "created_by": "someone-else"},
    )
    res = client.patch(
        "/api/invoices/inv-1/folder",
        params={"folder_id": "fold-1"},
        headers=_auth_header(users),
    )
    assert res.status_code == 403


def test_move_invoice_requires_auth(users):
    assert client.patch("/api/invoices/inv-1/folder").status_code == 401
