"""
Hardening tests.

Covers the Commit-1 hardening work: the in-memory rate limiter, the
upload file-type gate, and the digest's IST clock (window and due-soon
boundaries must follow IST even though the server runs on UTC).
"""

from datetime import UTC, datetime

import pytest
from app.auth.security import create_access_token
from app.digest import generator
from app.digest.generator import _due_soon, generate_digest
from app.main import app
from app.ratelimit import _buckets, check_rate_limit
from fastapi import HTTPException
from fastapi.testclient import TestClient

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clean_buckets():
    _buckets.clear()
    yield
    _buckets.clear()


# ---------------------------------------------------------------- rate limit


class TestRateLimit:
    def test_allows_under_limit_then_429(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TESTRL_PER_HOUR", "2")
        check_rate_limit("testrl", "u1", now=1000.0)
        check_rate_limit("testrl", "u1", now=1001.0)
        with pytest.raises(HTTPException) as exc:
            check_rate_limit("testrl", "u1", now=1002.0)
        assert exc.value.status_code == 429

    def test_window_slides(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TESTSLIDE_PER_HOUR", "1")
        check_rate_limit("testslide", "u2", now=1000.0)
        # One hour later the first hit has fallen out of the window.
        check_rate_limit("testslide", "u2", now=4601.0)

    def test_buckets_are_per_key(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TESTKEY_PER_HOUR", "1")
        check_rate_limit("testkey", "user-a", now=1000.0)
        check_rate_limit("testkey", "user-b", now=1000.0)

    def test_garbage_env_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("RATE_LIMIT_TESTGARB_PER_HOUR", "not-a-number")
        check_rate_limit("testgarb", "u", now=1.0)  # default 60: no raise


# ------------------------------------------------------------- upload gate


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


def _auth_header(users):
    row = users.add("harden@example.com")
    return {"Authorization": f"Bearer {create_access_token(row['id'], row['role'])}"}


class TestUploadTypeGate:
    def test_rejects_text_file(self, users):
        res = client.post(
            "/api/invoices/upload",
            files={"file": ("notes.txt", b"hello world", "text/plain")},
            headers=_auth_header(users),
        )
        assert res.status_code == 422
        assert "Unsupported file type" in res.json()["detail"]

    def test_rejects_wrong_mime_even_with_pdf_name(self, users):
        res = client.post(
            "/api/invoices/upload",
            files={"file": ("invoice.pdf", b"hello", "text/plain")},
            headers=_auth_header(users),
        )
        assert res.status_code == 422

    def test_allows_generic_mime_with_pdf_extension(self, users, monkeypatch):
        """A .pdf upload with a generic MIME passes the gate and reaches storage."""
        import app.api.invoices as inv_api

        def _boom(*a, **k):
            raise RuntimeError("storage down")

        monkeypatch.setattr(inv_api, "upload_invoice", _boom)
        res = client.post(
            "/api/invoices/upload",
            files={"file": ("receipt.pdf", b"%PDF-1.4", "application/octet-stream")},
            headers=_auth_header(users),
        )
        # 502 = validation passed, storage attempt failed (as forced above).
        assert res.status_code == 502

    def test_rejects_before_storage(self, users, monkeypatch):
        """Rejection happens before any Storage call is attempted."""
        import app.api.invoices as inv_api

        called = False

        def _spy(*a, **k):
            nonlocal called
            called = True

        monkeypatch.setattr(inv_api, "upload_invoice", _spy)
        client.post(
            "/api/invoices/upload",
            files={"file": ("song.mp3", b"audio", "audio/mpeg")},
            headers=_auth_header(users),
        )
        assert called is False


# ---------------------------------------------------------------- IST clock


class TestIstClock:
    def test_ist_offset_applied(self):
        utc_now = datetime.now(UTC).replace(tzinfo=None)
        ist_now = generator._ist_now()
        delta_seconds = (ist_now - utc_now).total_seconds()
        # +05:30, with a tolerance for the two clock reads.
        assert 5 * 3600 + 25 * 60 <= delta_seconds <= 5 * 3600 + 35 * 60

    def test_generated_at_is_ist(self, monkeypatch):
        monkeypatch.setattr(generator, "get_invoices", lambda user_id=None: [])
        digest = generate_digest(window_days=7)
        generated = datetime.fromisoformat(digest.generated_at)
        ist_now = generator._ist_now()
        assert abs((ist_now - generated).total_seconds()) < 60

    def test_due_soon_cutoff_uses_ist_now(self, monkeypatch):
        fixed = datetime(2026, 9, 17, 8, 0, 0)  # 08:00 IST
        monkeypatch.setattr(generator, "_ist_now", lambda: fixed)
        within = [{"invoice_number": "A", "due_date": "2026-09-22", "status": "pending"}]
        assert [row["invoice_number"] for row in _due_soon(within, days=5)] == ["A"]
        beyond = [{"invoice_number": "B", "due_date": "2026-09-23", "status": "pending"}]
        assert _due_soon(beyond, days=5) == []
