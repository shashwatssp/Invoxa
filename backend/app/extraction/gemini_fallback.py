"""
Gemini vision API fallback for low-confidence extractions.

Only called when overall confidence drops below 0.3 (or when text
extraction produced nothing at all, e.g. image-only scanned PDFs).
The request always carries the extracted text and, whenever pages can
be rendered, also the page images so the model can read scans and
photos of invoices directly.
"""
import base64
import contextlib
import json

import httpx

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.extraction.ocr import render_page_images
from app.models.invoice import ExtractionResult

GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _build_prompt(text: str) -> str:
    """
    Build the Gemini prompt for invoice field extraction.

    The wording adapts to what is attached: plain text, page images,
    or both.
    """
    source = (
        "invoice text and the attached page images"
        if text.strip()
        else "the attached page images (a scan or photo of an invoice)"
    )
    return f"""
You are an expert Indian invoice data extraction assistant.
Extract the following fields from this {source}. Return ONLY valid JSON.

Fields to extract:
- vendor_name: name of the seller/vendor
- vendor_gstin: 15-character GSTIN number
- invoice_number: the invoice number
- invoice_date: date in DD/MM/YYYY format
- due_date: due date in DD/MM/YYYY format
- amount: total amount as a number (strip commas)
- tax_amount: total tax amount as a number
- total_amount: grand total as a number
- line_items: list of {{"description": str, "amount": float}} objects

Rules:
- If a field is not found, set it to null
- Amounts must be numbers, not strings
- GSTIN must be exactly 15 characters
- Be very precise with numbers and dates

Invoice text:
{text[:5000]}
"""


def _image_parts(images: list[tuple[str, bytes]]) -> list[dict]:
    """Encode rendered pages as Gemini ``inline_data`` parts."""
    parts: list[dict] = []
    for mime_type, image_bytes in images:
        parts.append(
            {
                "inline_data": {
                    "mime_type": mime_type,
                    "data": base64.b64encode(image_bytes).decode("ascii"),
                }
            }
        )
    return parts


def gemini_fallback(file_bytes: bytes, text: str) -> ExtractionResult | None:
    """
    Call Gemini vision API to extract invoice fields as fallback.

    Page images (rendered from the PDF, or the uploaded photo itself)
    are attached whenever they can be produced, so scanned invoices
    and WhatsApp photos extract correctly. Any API or parsing failure
    returns None so the pipeline falls back to its previous result.
    """
    if not GEMINI_API_KEY:
        return None

    prompt = _build_prompt(text)
    parts: list[dict] = [{"text": prompt}]
    # Image rendering must never block the text path.
    with contextlib.suppress(Exception):
        parts.extend(_image_parts(render_page_images(file_bytes)))

    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "parts": parts,
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0.1,
                        "maxOutputTokens": 2048,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        return None

    # Parse the response
    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"]
        # Extract JSON from response (may be wrapped in markdown)
        json_str = content.strip()
        json_str = json_str.removeprefix("```json")
        json_str = json_str.removesuffix("```")
        fields = json.loads(json_str.strip())
    except (KeyError, json.JSONDecodeError, IndexError):
        return None

    # Build ExtractionResult from Gemini response
    return ExtractionResult(
        engine="gemini",
        vendor_name=fields.get("vendor_name"),
        vendor_gstin=fields.get("vendor_gstin"),
        invoice_number=fields.get("invoice_number"),
        invoice_date=fields.get("invoice_date"),
        due_date=fields.get("due_date"),
        amount=fields.get("amount"),
        tax_amount=fields.get("tax_amount"),
        total_amount=fields.get("total_amount"),
        line_items=fields.get("line_items"),
        confidence=0.85,  # Gemini responses are generally high confidence
        overall_confidence=0.85,
        needs_review=False,
        raw_text=text,
    )
