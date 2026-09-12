"""
Tests for the AI digest narrative (Gemini, optional) and its fallbacks.

The narrative must NEVER break the digest: any failure yields None and
the template summary lines remain the source of truth.
"""

from app.digest import generator, narrative
from app.digest.generator import generate_digest


def _invoice_rows():
    return [
        {
            "id": "inv-1",
            "invoice_number": "INV-001",
            "vendor_name": "Acme Corp",
            "amount": 5000.0,
            "status": "auto_approved",
            "due_date": "2026-09-20",
            "created_at": "2026-09-10T10:00:00",
        },
        {
            "id": "inv-2",
            "invoice_number": "INV-002",
            "vendor_name": "Beta Traders",
            "amount": 1500.0,
            "status": "flagged",
            "due_date": None,
            "created_at": "2026-09-11T10:00:00",
        },
    ]


class TestAiNarrative:
    def test_no_key_returns_none(self, monkeypatch):
        monkeypatch.setattr(narrative, "GEMINI_API_KEY", "")
        assert narrative.ai_narrative({}, _invoice_rows()) is None

    def test_api_failure_returns_none(self, monkeypatch):
        class _BoomClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                raise RuntimeError("network down")

        monkeypatch.setattr(narrative, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(narrative.httpx, "Client", lambda **kw: _BoomClient())
        assert narrative.ai_narrative({"invoices_processed": 2}, _invoice_rows()) is None

    def test_malformed_response_returns_none(self, monkeypatch):
        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"unexpected": "shape"}

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                return _FakeResponse()

        monkeypatch.setattr(narrative, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(narrative.httpx, "Client", lambda **kw: _FakeClient())
        assert narrative.ai_narrative({"invoices_processed": 2}, _invoice_rows()) is None

    def test_successful_narrative(self, monkeypatch):
        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": "  You processed 2 invoices worth 6,500 INR.  "
                                    }
                                ]
                            }
                        }
                    ]
                }

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                return _FakeResponse()

        monkeypatch.setattr(narrative, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(narrative.httpx, "Client", lambda **kw: _FakeClient())
        text = narrative.ai_narrative({"invoices_processed": 2}, _invoice_rows())
        assert text == "You processed 2 invoices worth 6,500 INR."

    def test_prompt_carries_only_compact_invoice_data(self, monkeypatch):
        captured: dict = {}

        class _FakeResponse:
            def raise_for_status(self):
                pass

            def json(self):
                return {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

        class _FakeClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, url, **kwargs):
                captured["json"] = kwargs.get("json")
                return _FakeResponse()

        monkeypatch.setattr(narrative, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(narrative.httpx, "Client", lambda **kw: _FakeClient())
        narrative.ai_narrative({"invoices_processed": 2}, _invoice_rows())

        prompt = captured["json"]["contents"][0]["parts"][0]["text"]
        assert "Acme Corp" in prompt
        assert "storage_path" not in prompt  # raw internals stay out of prompts


class TestGenerateDigestIntegration:
    def test_narrative_set_when_ai_available(self, monkeypatch):
        monkeypatch.setattr(generator, "get_invoices", lambda user_id=None: _invoice_rows())
        monkeypatch.setattr(
            generator, "ai_narrative", lambda digest_dict, invoices: "AI summary text"
        )
        digest = generate_digest(window_days=7)
        assert digest.narrative == "AI summary text"
        assert digest.narrative_source == "gemini"
        assert digest.summary_lines  # template lines still present

    def test_falls_back_to_template_lines(self, monkeypatch):
        monkeypatch.setattr(generator, "get_invoices", lambda user_id=None: _invoice_rows())
        monkeypatch.setattr(generator, "ai_narrative", lambda digest_dict, invoices: None)
        digest = generate_digest(window_days=7)
        assert digest.narrative is None
        assert digest.narrative_source == "template"
        assert digest.summary_lines

    def test_ai_never_raises(self, monkeypatch):
        """An exploding ai_narrative must not break the digest."""
        monkeypatch.setattr(generator, "get_invoices", lambda user_id=None: _invoice_rows())

        def _explode(*a, **k):
            raise RuntimeError("boom")

        monkeypatch.setattr(generator, "ai_narrative", _explode)
        digest = generate_digest(window_days=7)
        assert digest.narrative is None
        assert digest.narrative_source == "template"
        assert digest.summary_lines


def test_digest_endpoint_contract():
    """The digest dict exposes the narrative fields for the frontend."""
    digest = generator.Digest()
    data = digest.to_dict()
    assert "narrative" in data
    assert "narrative_source" in data
    assert data["narrative"] is None
    assert data["narrative_source"] == "template"
