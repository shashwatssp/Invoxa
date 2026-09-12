"""Tests for authentication, route protection, and the receipt file endpoint.

Uses FastAPI's TestClient with the database layer faked in-memory. Patches
the names each importing module actually uses (they are imported at module
top level, e.g. ``from app.database import get_user_by_id``).
"""
import pytest
from app.auth import security
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


# --------------------------------------------------------------------- fakes

class UserStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}  # id -> row (with password_hash)
        self.by_email: dict[str, str] = {}  # email -> id
        self._n = 0

    def add(self, email, password, name=None, role="member"):
        self._n += 1
        uid = f"user-{self._n}"
        row = {
            "id": uid,
            "email": email,
            "password_hash": security.hash_password(password),
            "name": name,
            "role": role,
            "created_at": "2026-09-10T00:00:00+00:00",
        }
        self.rows[uid] = row
        self.by_email[email] = uid
        return row


@pytest.fixture
def users(monkeypatch):
    store = UserStore()

    import app.api.auth as auth_api
    import app.auth.dependencies as deps

    def fake_create_user(email, password_hash, name, role):
        row = store.add(email, "ignored", name, role)
        row["password_hash"] = password_hash
        return {k: v for k, v in row.items() if k != "password_hash"}

    monkeypatch.setattr(auth_api, "create_user", fake_create_user)
    monkeypatch.setattr(
        auth_api,
        "get_user_by_email",
        lambda email: store.rows.get(store.by_email.get(email)),
    )
    monkeypatch.setattr(
        deps, "get_user_by_id", lambda uid: store.rows.get(uid)
    )
    return store


def _signup(email="up@example.com", role="member", password="s3cretPass!"):
    return client.post(
        "/api/auth/signup",
        json={"email": email, "password": password, "name": "Test", "role": role},
    )


# ------------------------------------------------------------------- signup

def test_signup_returns_token_and_user(users):
    res = _signup()
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["token"]
    assert body["user"]["email"] == "up@example.com"
    assert body["user"]["role"] == "member"
    assert "password_hash" not in body["user"]


def test_signup_duplicate_email_conflict(users):
    assert _signup().status_code == 201
    res = _signup()
    assert res.status_code == 409


def test_signup_short_password_rejected(users):
    res = client.post(
        "/api/auth/signup", json={"email": "x@example.com", "password": "short"}
    )
    assert res.status_code == 422


# -------------------------------------------------------------------- login

def test_login_success(users):
    _signup(email="login@example.com", password="RightPass123")
    res = client.post(
        "/api/auth/login", json={"email": "login@example.com", "password": "RightPass123"}
    )
    assert res.status_code == 200
    assert res.json()["token"]


def test_login_wrong_password(users):
    _signup(email="login2@example.com", password="RightPass123")
    res = client.post(
        "/api/auth/login", json={"email": "login2@example.com", "password": "WrongPass123"}
    )
    assert res.status_code == 401


def test_login_unknown_email(users):
    res = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": "whatever1"}
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------- me

def test_me_with_token(users):
    signup = _signup().json()
    res = client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {signup['token']}"}
    )
    assert res.status_code == 200
    assert res.json()["email"] == "up@example.com"


def test_me_without_token(users):
    assert client.get("/api/auth/me").status_code == 401


def test_me_with_garbage_token(users):
    res = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert res.status_code == 401


# -------------------------------------------------------- protected routes

def test_invoices_require_auth(users):
    assert client.get("/api/invoices").status_code == 401
    assert client.get("/api/digest").status_code == 401
    assert client.get("/api/review/queue").status_code == 401
    assert client.get("/api/export/preview").status_code == 401


def test_invoices_list_with_token(users, monkeypatch):
    import app.api.invoices as inv_api
    monkeypatch.setattr(inv_api, "get_invoices", lambda *args, **kwargs: [])
    signup = _signup().json()
    res = client.get(
        "/api/invoices", headers={"Authorization": f"Bearer {signup['token']}"}
    )
    assert res.status_code == 200
    assert res.json() == []


def test_upload_stamps_created_by(users, monkeypatch):
    import app.api.invoices as inv_api

    captured = {}

    def fake_create_invoice(storage_path, vendor_id=None, created_by=None, folder_id=None):
        captured["created_by"] = created_by
        return "inv-123"

    monkeypatch.setattr(inv_api, "upload_invoice", lambda b, n: f"raw/{n}")
    monkeypatch.setattr(inv_api, "create_invoice", fake_create_invoice)

    class FakeResult:
        vendor_gstin = None
        needs_review = False
        overall_confidence = 0.9
        invoice_number = None
        amount = None
        total_amount = None
        due_date = None

    monkeypatch.setattr(inv_api, "extract_from_invoice", lambda b, iid: FakeResult())
    monkeypatch.setattr(inv_api, "save_extraction_result", lambda iid, r: None)
    monkeypatch.setattr(inv_api, "update_invoice_fields", lambda *a, **k: None)
    monkeypatch.setattr(inv_api, "update_invoice_status", lambda *a, **k: None)

    signup = _signup().json()
    res = client.post(
        "/api/invoices/upload",
        files={"file": ("receipt.pdf", b"%PDF-1.4 fake", "application/pdf")},
        headers={"Authorization": f"Bearer {signup['token']}"},
    )
    assert res.status_code == 200, res.text
    assert captured["created_by"] == signup["user"]["id"]


# ------------------------------------------------------------ role checks

def _resolve_capture(users, monkeypatch):
    import app.api.review as review_api

    captured = {}

    def fake_resolve(review_id, approved, reviewed_by=None):
        captured["reviewed_by"] = reviewed_by

    monkeypatch.setattr(review_api, "resolve_review_item", fake_resolve)
    # Legacy rows have no owner; ownership is enforced in the endpoint.
    monkeypatch.setattr(review_api, "get_review_item_owner", lambda rid: None)
    # No invoice linked in this fake; the status sync is covered separately.
    monkeypatch.setattr(review_api, "get_review_item_invoice_id", lambda rid: None)
    monkeypatch.setattr(review_api, "update_invoice_status", lambda *a, **k: None)
    return captured


def test_resolve_marks_invoice_reviewed(users, monkeypatch):
    """Approval syncs the invoice status so the dashboard reflects it."""
    import app.api.review as review_api

    captured = {}

    def fake_resolve(review_id, approved, reviewed_by=None):
        pass

    monkeypatch.setattr(review_api, "resolve_review_item", fake_resolve)
    monkeypatch.setattr(review_api, "get_review_item_owner", lambda rid: None)
    monkeypatch.setattr(review_api, "get_review_item_invoice_id", lambda rid: "inv-9")

    def fake_update_status(invoice_id, status):
        captured["invoice_id"] = invoice_id
        captured["status"] = str(status)

    monkeypatch.setattr(review_api, "update_invoice_status", fake_update_status)

    member = _signup().json()
    res = client.post(
        "/api/review/rq-1/resolve?approved=true",
        headers={"Authorization": f"Bearer {member['token']}"},
    )
    assert res.status_code == 200
    assert captured["invoice_id"] == "inv-9"
    assert captured["status"] == "reviewed"


def test_any_user_can_resolve_and_is_stamped(users, monkeypatch):
    """One user can do everything: upload AND approve."""
    captured = _resolve_capture(users, monkeypatch)
    member = _signup().json()
    res = client.post(
        "/api/review/rq-1/resolve?approved=true",
        headers={"Authorization": f"Bearer {member['token']}"},
    )
    assert res.status_code == 200
    assert captured["reviewed_by"] == member["user"]["id"]


# ------------------------------------------------- receipt file endpoint

def test_invoice_file_returns_pdf(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api, "get_invoice", lambda iid: {"id": iid, "storage_path": "raw/x.pdf"}
    )
    monkeypatch.setattr(
        inv_api, "download_invoice", lambda path: b"%PDF-1.4 fake bytes"
    )
    signup = _signup().json()
    res = client.get(
        "/api/invoices/inv-1/file",
        headers={"Authorization": f"Bearer {signup['token']}"},
    )
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content.startswith(b"%PDF")


def test_invoice_file_requires_auth(users):
    assert client.get("/api/invoices/inv-1/file").status_code == 401


def test_invoice_file_unknown_invoice(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(inv_api, "get_invoice", lambda iid: None)
    signup = _signup().json()
    res = client.get(
        "/api/invoices/missing/file",
        headers={"Authorization": f"Bearer {signup['token']}"},
    )
    assert res.status_code == 404


# ------------------------------------------------- preview endpoint

def test_invoice_preview_returns_png(users, monkeypatch):
    from pathlib import Path

    import app.api.invoices as inv_api

    real_pdf = (
        Path(__file__).resolve().parent.parent / "test-assets" / "gst_invoice_a.pdf"
    ).read_bytes()
    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {"id": iid, "storage_path": "raw/x.pdf", "created_by": None},
    )
    monkeypatch.setattr(inv_api, "download_invoice", lambda path: real_pdf)
    signup = _signup().json()
    res = client.get(
        "/api/invoices/inv-1/preview",
        headers={"Authorization": f"Bearer {signup['token']}"},
    )
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "image/png"
    assert res.content.startswith(b"\x89PNG")


def test_invoice_file_forbidden_for_other_account(users, monkeypatch):
    import app.api.invoices as inv_api

    monkeypatch.setattr(
        inv_api,
        "get_invoice",
        lambda iid: {
            "id": iid,
            "storage_path": "raw/x.pdf",
            "created_by": "someone-else",
        },
    )
    signup = _signup().json()
    res = client.get(
        "/api/invoices/inv-1/file",
        headers={"Authorization": f"Bearer {signup['token']}"},
    )
    assert res.status_code == 403


def test_review_resolve_forbidden_for_other_account(users, monkeypatch):
    import app.api.review as review_api

    monkeypatch.setattr(
        review_api, "get_review_item_owner", lambda rid: "someone-else"
    )
    member = _signup().json()
    res = client.post(
        "/api/review/rq-1/resolve?approved=true",
        headers={"Authorization": f"Bearer {member['token']}"},
    )
    assert res.status_code == 403


# ------------------------------------------------------- security helpers

def test_password_hash_roundtrip():
    stored = security.hash_password("hunter22")
    assert stored != "hunter22"
    assert security.verify_password("hunter22", stored)
    assert not security.verify_password("hunter23", stored)


def test_token_roundtrip():
    token = security.create_access_token("user-1", "approver")
    payload = security.decode_access_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "approver"
    assert security.decode_access_token(token + "tampered") is None
