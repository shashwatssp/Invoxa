"""
Digest email tests.

SMTP is faked — nothing ever leaves the machine. Covers the
unconfigured path, body composition (deterministic lines + AI
narrative), and both send paths (SMTP_SSL and STARTTLS).
"""

from app.digest import emailer
from app.digest.generator import Digest


def _fake_digest() -> Digest:
    digest = Digest(window_days=7)
    digest.invoices_processed = 3
    digest.summary_lines = ["Processed 3 invoices in the last 7 days, worth 1,500.00 INR."]
    digest.narrative = None
    return digest


class TestSmtpConfig:
    def test_unconfigured_returns_none(self, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        assert emailer._smtp_config() is None

    def test_configured(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setenv("SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "app-password")
        config = emailer._smtp_config()
        assert config == {
            "host": "smtp.gmail.com",
            "port": 465,
            "user": "me@gmail.com",
            "password": "app-password",
        }

    def test_bad_port_falls_back_to_465(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setenv("SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        monkeypatch.setenv("SMTP_PORT", "not-a-port")
        assert emailer._smtp_config()["port"] == 465


class TestEmailBody:
    def test_body_contains_summary_lines(self):
        digest = _fake_digest()
        body = emailer.build_digest_email_text(digest)
        assert "Invoxa digest" in body
        assert "Processed 3 invoices" in body

    def test_body_includes_narrative_when_present(self):
        digest = _fake_digest()
        digest.narrative = "A calm week overall."
        body = emailer.build_digest_email_text(digest)
        assert "A calm week overall." in body


class TestSendDigestEmail:
    def test_unconfigured_reports_not_sent(self, monkeypatch):
        monkeypatch.delenv("SMTP_HOST", raising=False)
        monkeypatch.delenv("SMTP_USER", raising=False)
        monkeypatch.delenv("SMTP_PASSWORD", raising=False)
        result = emailer.send_digest_email("user-1", "owner@example.com")
        assert result["sent"] is False
        assert "not configured" in result["reason"]

    def test_ssl_send_path(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setenv("SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        monkeypatch.setenv("SMTP_PORT", "465")
        monkeypatch.setattr(emailer, "generate_digest", lambda window_days=7, user_id=None: _fake_digest())

        sent = {}

        class _FakeSmtp:
            def __init__(self, host, port, timeout=None):
                sent["host"] = host
                sent["port"] = port

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def login(self, user, password):
                sent["user"] = user

            def send_message(self, message):
                sent["to"] = message["To"]
                sent["subject"] = message["Subject"]

        monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", _FakeSmtp)
        result = emailer.send_digest_email("user-1", "owner@example.com")
        assert result["sent"] is True
        assert sent["to"] == "owner@example.com"
        assert sent["user"] == "me@gmail.com"
        assert sent["port"] == 465

    def test_starttls_send_path(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("SMTP_USER", "me@example.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        monkeypatch.setenv("SMTP_PORT", "587")
        monkeypatch.setattr(emailer, "generate_digest", lambda window_days=7, user_id=None: _fake_digest())

        calls = []

        class _FakeSmtp:
            def __init__(self, host, port, timeout=None):
                calls.append(("connect", host, port))

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def starttls(self):
                calls.append(("starttls",))

            def login(self, user, password):
                calls.append(("login",))

            def send_message(self, message):
                calls.append(("send",))

        monkeypatch.setattr(emailer.smtplib, "SMTP", _FakeSmtp)
        result = emailer.send_digest_email("user-1", "owner@example.com")
        assert result["sent"] is True
        assert ("starttls",) in calls
        assert ("send",) in calls

    def test_smtp_failure_reports_cleanly(self, monkeypatch):
        monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
        monkeypatch.setenv("SMTP_USER", "me@gmail.com")
        monkeypatch.setenv("SMTP_PASSWORD", "pw")
        monkeypatch.setattr(emailer, "generate_digest", lambda window_days=7, user_id=None: _fake_digest())

        class _BoomSmtp:
            def __init__(self, *a, **k):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def login(self, *a, **k):
                raise smtplib_error()

        def smtplib_error():
            import smtplib

            return smtplib.SMTPAuthenticationError(535, b"nope")

        monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", _BoomSmtp)
        result = emailer.send_digest_email("user-1", "owner@example.com")
        assert result["sent"] is False
        assert "could not be sent" in result["reason"]


def test_endpoint_requires_auth():
    from app.main import app
    from fastapi.testclient import TestClient

    client = TestClient(app)
    res = client.post("/api/digest/email", json={"to_email": "a@b.com"})
    assert res.status_code in (401, 403)
