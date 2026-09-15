"""
Payment-chase + correction-learning tests.

All Gemini interaction is faked. Chase drafts must stay draft-only
(never send), respect the per-run vendor cap, and fall back to a
deterministic template when AI is unavailable. Correction-learning
must surface past human fixes in the fallback prompt.
"""

from app.agent import chase as chase_mod
from app.extraction import gemini_fallback as gf


def _due_row(vendor: str, amount: float, overdue: bool = False, number: str = "INV-1") -> dict:
    return {
        "vendor_name": vendor,
        "invoice_number": number,
        "amount": amount,
        "due_date_parsed": "2026-09-10" if overdue else "2026-09-20",
        "due_date": "2026-09-10" if overdue else "2026-09-20",
        "status": "auto_approved",
        "overdue": overdue,
    }


class TestChaseDrafts:
    def test_template_fallback_when_no_ai(self, monkeypatch):
        monkeypatch.setattr(
            chase_mod, "get_due_soon_rows", lambda uid, days: [_due_row("Acme", 1180.0, overdue=True)]
        )
        result = chase_mod.draft_payment_chase("user-1")
        draft = result["drafts"][0]
        assert draft["vendor"] == "Acme"
        assert draft["source"] == "template"
        assert "Acme" in draft["message"]
        assert "Rs 1,180" in draft["message"]
        assert draft["whatsapp_url"].startswith("https://wa.me/?text=")
        assert result["vendors_found"] == 1

    def test_ai_path_when_available(self, monkeypatch):
        monkeypatch.setattr(
            chase_mod, "get_due_soon_rows", lambda uid, days: [_due_row("Beta", 500.0)]
        )
        monkeypatch.setattr(chase_mod, "GEMINI_API_KEY", "test-key")

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "Kindly pay Rs 500."}]}}]}

        class _FakeClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                return _FakeResponse()

        monkeypatch.setattr(chase_mod.httpx, "Client", lambda **kw: _FakeClient())
        result = chase_mod.draft_payment_chase("user-1")
        draft = result["drafts"][0]
        assert draft["source"] == "gemini"
        assert draft["message"] == "Kindly pay Rs 500."

    def test_ai_failure_falls_back_to_template(self, monkeypatch):
        monkeypatch.setattr(
            chase_mod, "get_due_soon_rows", lambda uid, days: [_due_row("Gamma", 900.0)]
        )
        monkeypatch.setattr(chase_mod, "GEMINI_API_KEY", "test-key")

        class _BoomClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                raise RuntimeError("network down")

        monkeypatch.setattr(chase_mod.httpx, "Client", lambda **kw: _BoomClient())
        result = chase_mod.draft_payment_chase("user-1")
        assert result["drafts"][0]["source"] == "template"
        assert "Gamma" in result["drafts"][0]["message"]

    def test_vendor_cap(self, monkeypatch):
        rows = [_due_row(f"Vendor-{i}", 100.0 + i, number=f"INV-{i}") for i in range(9)]
        monkeypatch.setattr(chase_mod, "get_due_soon_rows", lambda uid, days: rows)
        result = chase_mod.draft_payment_chase("user-1")
        assert result["vendors_found"] == 9
        assert len(result["drafts"]) == chase_mod.MAX_VENDORS_PER_RUN

    def test_overdue_counting(self, monkeypatch):
        rows = [
            _due_row("Acme", 100.0, overdue=True, number="A-1"),
            _due_row("Acme", 200.0, overdue=False, number="A-2"),
        ]
        monkeypatch.setattr(chase_mod, "get_due_soon_rows", lambda uid, days: rows)
        result = chase_mod.draft_payment_chase("user-1")
        draft = result["drafts"][0]
        assert draft["overdue_count"] == 1
        assert draft["invoice_count"] == 2
        assert draft["total_due"] == 300.0

    def test_empty_account(self, monkeypatch):
        monkeypatch.setattr(chase_mod, "get_due_soon_rows", lambda uid, days: [])
        result = chase_mod.draft_payment_chase("user-1")
        assert result["drafts"] == []
        assert result["vendors_found"] == 0


# ------------------------------------------------------- correction learning


class TestCorrectionLearning:
    def test_hints_in_prompt_when_present(self, monkeypatch):
        monkeypatch.setattr(
            gf,
            "get_recent_corrections",
            lambda limit=5: [
                {"field_name": "amount", "old_value": "1.234", "new_value": "1234.0"},
            ],
        )
        prompt = gf._build_prompt("some text")
        assert "Recent human corrections" in prompt
        assert "amount: 1.234 -> 1234.0" in prompt

    def test_no_hints_when_no_corrections(self, monkeypatch):
        monkeypatch.setattr(gf, "get_recent_corrections", lambda limit=5: [])
        prompt = gf._build_prompt("some text")
        assert "Recent human corrections" not in prompt

    def test_hint_lookup_failure_is_silent(self, monkeypatch):
        def _boom(limit=5):
            raise RuntimeError("db down")

        monkeypatch.setattr(gf, "get_recent_corrections", _boom)
        assert gf._correction_hints() == ""

    def test_fallback_end_to_end_with_hints(self, monkeypatch):
        """Full fallback call carries correction hints in the request prompt."""
        captured: dict = {}

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "candidates": [
                        {"content": {"parts": [{"text": '{"vendor_name": "Acme"}'}]}}
                    ]
                }

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, **kwargs):
                captured["json"] = kwargs.get("json")
                return _FakeResponse()

        monkeypatch.setattr(gf, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(
            gf,
            "get_recent_corrections",
            lambda limit=5: [
                {"field_name": "vendor_gstin", "old_value": "27AAAAA0000A", "new_value": "27AAAAA0000A1Z5"}
            ],
        )
        monkeypatch.setattr(gf, "render_page_images", lambda b: [])
        monkeypatch.setattr(gf.httpx, "Client", lambda **kw: _FakeClient())

        result = gf.gemini_fallback(b"%PDF fake", "GST INVOICE")
        assert result is not None and result.vendor_name == "Acme"
        prompt_text = captured["json"]["contents"][0]["parts"][0]["text"]
        assert "27AAAAA0000A1Z5" in prompt_text


# ----------------------------------------------------------------- endpoint


class TestChaseEndpoint:
    def test_requires_auth(self):
        from app.main import app
        from fastapi.testclient import TestClient

        client = TestClient(app)
        res = client.post("/api/agent/payment-chase")
        assert res.status_code in (401, 403)

    def test_happy_path_scoped_and_draft_only(self, monkeypatch):
        import app.api.agent as agent_api
        from app.main import app
        from fastapi.testclient import TestClient

        captured: dict = {}

        def fake_chase(user_id):
            captured["user_id"] = user_id
            return {"drafts": [], "vendors_found": 0, "note": "drafts only"}

        monkeypatch.setattr(agent_api, "draft_payment_chase", fake_chase)
        client = TestClient(app)
        res = client.post("/api/agent/payment-chase")  # unauthenticated -> rejected
        assert res.status_code in (401, 403)

        from app.auth.security import create_access_token

        headers = {"Authorization": "Bearer " + create_access_token("user-9", "member")}
        import app.auth.dependencies as deps

        monkeypatch.setattr(
            deps, "get_user_by_id", lambda uid: {"id": uid, "email": "x@example.com", "name": "X", "role": "member"}
        )
        res = client.post("/api/agent/payment-chase", headers=headers)
        assert res.status_code == 200
        assert captured["user_id"] == "user-9"
