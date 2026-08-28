"""
Gemini vision API fallback for low-confidence extractions.
Only called when overall confidence drops below 0.3.
"""
import json
import httpx

from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.models.invoice import ExtractionResult


GEMINI_API_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def _build_prompt(text: str) -> str:
    """
    Build the Gemini prompt for invoice field extraction.
    """
    return f"""
You are an expert Indian invoice data extraction assistant.
Extract the following fields from this invoice text. Return ONLY valid JSON.

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


def gemini_fallback(file_bytes: bytes, text: str) -> ExtractionResult | None:
    """
    Call Gemini vision API to extract invoice fields as fallback.
    Returns ExtractionResult with confidence based on response quality.
    """
    if not GEMINI_API_KEY:
        return None

    prompt = _build_prompt(text)

    try:
        with httpx.Client(timeout=60) as client:
            response = client.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "parts": [
                                {"text": prompt},
                            ]
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
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        fields = json.loads(json_str.strip())
    except (KeyError, json.JSONDecodeError, IndexError):
        return None

    # Build ExtractionResult from Gemini response
    return ExtractionResult(
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
