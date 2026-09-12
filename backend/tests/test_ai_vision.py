"""
Tests for the Gemini vision fallback on scanned invoices.

Covers:
- ``render_page_images``: PDF pages and standalone photos (WhatsApp) are
  rendered to bounded-size JPEGs; garbage returns nothing.
- ``extract_from_invoice``: when text extraction produces nothing, the
  pipeline now tries Gemini vision before dead-ending in review.
- ``gemini_fallback``: the request carries page images as inline_data
  alongside the prompt.
"""

import base64
import io

import app.extraction.pipeline as pipeline
import fitz
import pytest
from app.extraction.gemini_fallback import gemini_fallback
from app.extraction.ocr import render_page_images
from app.models.invoice import ExtractionResult
from PIL import Image


def _one_page_pdf(pages: int = 1) -> bytes:
    doc = fitz.open()
    for i in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), f"GST INVOICE {i}\nTotal: Rs 1,234.00")
    return doc.tobytes()


# ------------------------------------------------------- render_page_images


class TestRenderPageImages:
    def test_pdf_renders_jpeg(self):
        images = render_page_images(_one_page_pdf())
        assert len(images) == 1
        mime, data = images[0]
        assert mime == "image/jpeg"
        assert data.startswith(b"\xff\xd8\xff")  # JPEG magic

    def test_respects_max_pages(self):
        images = render_page_images(_one_page_pdf(pages=3), max_pages=2)
        assert len(images) == 2

    def test_standalone_jpeg_photo(self):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), color=(200, 30, 30)).save(buf, format="JPEG")
        images = render_page_images(buf.getvalue())
        assert len(images) == 1
        mime, data = images[0]
        assert mime == "image/jpeg"
        assert data.startswith(b"\xff\xd8\xff")

    def test_standalone_png_photo(self):
        buf = io.BytesIO()
        Image.new("RGB", (64, 48), color=(30, 200, 30)).save(buf, format="PNG")
        images = render_page_images(buf.getvalue())
        assert len(images) == 1
        mime, _data = images[0]
        assert mime == "image/jpeg"  # re-encoded for a smaller payload

    def test_garbage_bytes_yield_nothing(self):
        assert render_page_images(b"definitely not a pdf") == []

    def test_downscales_large_pages(self):
        images = render_page_images(_one_page_pdf(), dpi=300, max_dimension=200)
        assert images  # still renders
        # Bounded payload: a 200px JPEG must stay small.
        assert len(images[0][1]) < 100_000


# --------------------------------------------------- pipeline vision path


class TestPipelineEmptyText:
    def test_empty_text_tries_vision_fallback(self, monkeypatch):
        """Scanned/image-only upload: Gemini vision result is returned."""
        monkeypatch.setattr(pipeline, "extract_text", lambda b: ("", False))
        gemini_result = ExtractionResult(
            vendor_name="Acme",
            total_amount=1234.0,
            confidence=0.85,
            overall_confidence=0.85,
            needs_review=False,
        )
        monkeypatch.setattr(pipeline, "gemini_fallback", lambda b, t: gemini_result)
        monkeypatch.setattr(pipeline, "GEMINI_FALLBACK_AVAILABLE", True)

        result = pipeline.extract_from_invoice(b"%PDF fake", "inv-1")
        assert result.vendor_name == "Acme"
        assert result.overall_confidence == 0.85
        assert result.needs_review is False

    def test_empty_text_without_gemini_flags_for_review(self, monkeypatch):
        """No Gemini available: same honest empty result as before."""
        monkeypatch.setattr(pipeline, "extract_text", lambda b: ("", False))
        monkeypatch.setattr(pipeline, "gemini_fallback", lambda b, t: None)
        monkeypatch.setattr(pipeline, "GEMINI_FALLBACK_AVAILABLE", True)

        result = pipeline.extract_from_invoice(b"%PDF fake", "inv-1")
        assert result.overall_confidence == 0.0
        assert result.needs_review is True
        assert result.raw_text is None

    def test_vision_failure_still_flags_for_review(self, monkeypatch):
        """Gemini unavailable entirely -> behaviour unchanged."""
        monkeypatch.setattr(pipeline, "extract_text", lambda b: ("", False))
        monkeypatch.setattr(pipeline, "GEMINI_FALLBACK_AVAILABLE", False)

        result = pipeline.extract_from_invoice(b"%PDF fake", "inv-1")
        assert result.needs_review is True
        assert result.overall_confidence == 0.0


# ------------------------------------------------- multimodal gemini request


class _FakeResponse:
    def raise_for_status(self):
        pass

    def json(self):
        return {
            "candidates": [
                {
                    "content": {
                        "parts": [
                            {"text": '```json\n{"vendor_name": "Acme"}\n```'}
                        ]
                    }
                }
            ]
        }


class _FakeClient:
    def __init__(self, capture, **kwargs):
        self._capture = capture

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def post(self, url, **kwargs):
        self._capture["json"] = kwargs.get("json")
        return _FakeResponse()


class TestGeminiFallbackMultimodal:
    def test_request_carries_page_images(self, monkeypatch):
        import app.extraction.gemini_fallback as gf

        capture: dict = {}
        monkeypatch.setattr(gf, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(gf.httpx, "Client", lambda **kw: _FakeClient(capture, **kw))

        result = gemini_fallback(_one_page_pdf(), "GST INVOICE\nTotal: Rs 1,234.00")
        assert result is not None
        assert result.vendor_name == "Acme"

        parts = capture["json"]["contents"][0]["parts"]
        assert "inline_data" in parts[1], "page image must be attached"
        inline = parts[1]["inline_data"]
        assert inline["mime_type"] == "image/jpeg"
        assert base64.b64decode(inline["data"]).startswith(b"\xff\xd8\xff")

    def test_empty_text_prompt_mentions_images(self, monkeypatch):
        import app.extraction.gemini_fallback as gf

        capture: dict = {}
        monkeypatch.setattr(gf, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(gf.httpx, "Client", lambda **kw: _FakeClient(capture, **kw))

        result = gemini_fallback(_one_page_pdf(), "")
        assert result is not None  # extraction still succeeds from the image
        prompt = capture["json"]["contents"][0]["parts"][0]["text"]
        assert "page images" in prompt

    def test_api_error_returns_none(self, monkeypatch):
        import app.extraction.gemini_fallback as gf

        class _BoomClient:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                raise RuntimeError("network down")

        monkeypatch.setattr(gf, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(gf.httpx, "Client", lambda **kw: _BoomClient())
        assert gemini_fallback(_one_page_pdf(), "text") is None

    def test_no_key_returns_none_without_network(self, monkeypatch):
        import app.extraction.gemini_fallback as gf

        monkeypatch.setattr(gf, "GEMINI_API_KEY", "")
        assert gemini_fallback(_one_page_pdf(), "text") is None


@pytest.mark.parametrize("mime", ["image/jpeg"])
def test_rendered_mime_types(mime):
    """Rendered pages are always JPEG for a bounded payload."""
    images = render_page_images(_one_page_pdf())
    assert images[0][0] == mime
