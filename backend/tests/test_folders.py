"""Tests for the folder API (organizing uploads).

Uses FastAPI's TestClient with the database layer faked in-memory, matching
the test_auth.py pattern. Isolation is the headline: two accounts can use
folder ids interchangeably but never see or touch each other's folders.
"""
import pytest
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class FolderStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._n = 0

    def add(self, owner_id: str, name: str) -> dict:
        self._n += 1
        row = {
            "id": f"folder-{self._n}",
            "owner_id": owner_id,
            "name": name,
            "created_at": "2026-09-11T00:00:00+00:00",
        }
        self.rows[row["id"]] = row
        return row

    def owned(self, folder_id: str, owner_id: str):
        row = self.rows.get(folder_id)
        return row if row and row["owner_id"] == owner_id else None


@pytest.fixture
def store():
    return FolderStore()


@pytest.fixture
def accounts(monkeypatch, store):
    """Two signed-up accounts with the folder DB layer faked."""
    import app.api.auth as auth_api
    import app.api.folders as folders_api
    import app.auth.dependencies as deps

    seq = {"n": 0}

    def fake_create_user(email, password_hash, name, role):
        seq["n"] += 1
        uid = f"user-{seq['n']}"
        deps_row = {
            "id": uid, "email": email, "password_hash": password_hash,
            "name": name, "role": role, "created_at": "2026-09-11T00:00:00+00:00",
        }
        store.__dict__.setdefault("_users", {})[uid] = deps_row
        return {k: v for k, v in deps_row.items() if k != "password_hash"}

    monkeypatch.setattr(auth_api, "create_user", fake_create_user)
    monkeypatch.setattr(
        auth_api, "get_user_by_email",
        lambda email: next(
            (r for r in store.__dict__.get("_users", {}).values() if r["email"] == email),
            None,
        ),
    )
    monkeypatch.setattr(
        deps, "get_user_by_id",
        lambda uid: store.__dict__.get("_users", {}).get(uid),
    )

    monkeypatch.setattr(
        folders_api, "list_folders",
        lambda owner_id: [r for r in store.rows.values() if r["owner_id"] == owner_id],
    )
    monkeypatch.setattr(
        folders_api, "get_folder", lambda folder_id, owner_id: store.owned(folder_id, owner_id)
    )
    monkeypatch.setattr(
        folders_api, "create_folder",
        lambda owner_id, name: store.add(owner_id, name),
    )
    def fake_rename(folder_id, owner_id, name):
        row = store.owned(folder_id, owner_id)
        if not row:
            return None
        row["name"] = name
        return row

    monkeypatch.setattr(folders_api, "rename_folder", fake_rename)
    monkeypatch.setattr(
        folders_api, "delete_folder",
        lambda folder_id, owner_id: bool(store.owned(folder_id, owner_id))
        and store.rows.pop(folder_id) is not None,
    )
    monkeypatch.setattr(folders_api, "folder_invoice_counts", lambda owner_id: {})

    def signup(email):
        res = client.post(
            "/api/auth/signup",
            json={"email": email, "password": "s3cretPass!", "name": "T", "role": "member"},
        )
        assert res.status_code == 201, res.text
        return res.json()

    return {"signup": signup}


def _auth(account):
    return {"Authorization": f"Bearer {account['token']}"}


def test_folders_require_auth():
    assert client.get("/api/folders").status_code == 401
    assert client.post("/api/folders", json={"name": "x"}).status_code == 401


def test_create_and_list_folders(accounts):
    acc = accounts["signup"]("f1@example.com")
    res = client.post("/api/folders", json={"name": "Client A"}, headers=_auth(acc))
    assert res.status_code == 201, res.text
    folder = res.json()
    assert folder["name"] == "Client A"
    assert folder["id"]

    res = client.get("/api/folders", headers=_auth(acc))
    assert res.status_code == 200
    folders = res.json()
    assert len(folders) == 1
    assert folders[0]["name"] == "Client A"
    assert folders[0]["invoice_count"] == 0


def test_same_folder_names_across_accounts_are_isolated(accounts, store):
    acc_a = accounts["signup"]("a@example.com")
    acc_b = accounts["signup"]("b@example.com")
    res_a = client.post("/api/folders", json={"name": "Same Name"}, headers=_auth(acc_a))
    res_b = client.post("/api/folders", json={"name": "Same Name"}, headers=_auth(acc_b))
    assert res_a.status_code == 201 and res_b.status_code == 201
    assert res_a.json()["id"] != res_b.json()["id"]

    list_a = client.get("/api/folders", headers=_auth(acc_a)).json()
    list_b = client.get("/api/folders", headers=_auth(acc_b)).json()
    assert len(list_a) == 1 and len(list_b) == 1
    assert list_a[0]["id"] == res_a.json()["id"]
    assert list_b[0]["id"] == res_b.json()["id"]


def test_rename_and_delete_owned_folder_only(accounts, store):
    acc_a = accounts["signup"]("ra@example.com")
    acc_b = accounts["signup"]("rb@example.com")
    folder_a = client.post("/api/folders", json={"name": "Mine"}, headers=_auth(acc_a)).json()

    # The other account cannot rename or delete a foreign folder.
    res = client.patch(
        f"/api/folders/{folder_a['id']}", json={"name": "Hacked"}, headers=_auth(acc_b)
    )
    assert res.status_code == 404
    res = client.delete(f"/api/folders/{folder_a['id']}", headers=_auth(acc_b))
    assert res.status_code == 404

    # The owner can rename, then delete.
    res = client.patch(
        f"/api/folders/{folder_a['id']}", json={"name": "Renamed"}, headers=_auth(acc_a)
    )
    assert res.status_code == 200 and res.json()["name"] == "Renamed"
    res = client.delete(f"/api/folders/{folder_a['id']}", headers=_auth(acc_a))
    assert res.status_code == 204
    assert store.rows == {}


def test_folder_name_validation(accounts):
    acc = accounts["signup"]("v@example.com")
    assert client.post("/api/folders", json={"name": ""}, headers=_auth(acc)).status_code == 422
    assert client.post("/api/folders", json={"name": "x" * 61}, headers=_auth(acc)).status_code == 422


def test_upload_into_folder(accounts, store, monkeypatch):
    import app.api.invoices as inv_api

    created = {}

    def fake_create_invoice(storage_path, vendor_id=None, created_by=None, folder_id=None):
        created["folder_id"] = folder_id
        created["created_by"] = created_by
        return "inv-777"

    monkeypatch.setattr(inv_api, "get_folder", lambda folder_id, owner_id: store.owned(folder_id, owner_id))
    monkeypatch.setattr(inv_api, "create_invoice", fake_create_invoice)
    monkeypatch.setattr(inv_api, "upload_invoice", lambda b, n: f"raw/{n}")

    class FakeResult:
        vendor_gstin = None
        needs_review = False
        overall_confidence = 0.9
        invoice_number = None
        amount = None
        tax_amount = None
        total_amount = None
        due_date = None

    monkeypatch.setattr(inv_api, "extract_from_invoice", lambda b, iid: FakeResult())
    monkeypatch.setattr(inv_api, "save_extraction_result", lambda iid, r: None)
    monkeypatch.setattr(inv_api, "update_invoice_fields", lambda *a, **k: None)
    monkeypatch.setattr(inv_api, "update_invoice_status", lambda *a, **k: None)

    acc = accounts["signup"]("u@example.com")
    other = accounts["signup"]("other@example.com")
    folder = client.post("/api/folders", json={"name": "Scans"}, headers=_auth(acc)).json()

    # Upload into own folder works and passes the folder down.
    res = client.post(
        "/api/invoices/upload",
        files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"folder_id": folder["id"]},
        headers=_auth(acc),
    )
    assert res.status_code == 200, res.text
    assert created["folder_id"] == folder["id"]

    # The other account's folder id is rejected (not owned -> 404).
    res = client.post(
        "/api/invoices/upload",
        files={"file": ("r.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"folder_id": folder["id"]},
        headers=_auth(other),
    )
    assert res.status_code == 404
