"""
AI narrative for the weekly digest.

Turns the structured digest (counts, totals, top vendors, due soon)
into a short plain-English paragraph via Gemini. Entirely optional:
when no API key is configured, the request fails, or the model
returns nothing usable, ``ai_narrative`` returns None and the digest
keeps its template-generated summary lines.
"""

import json

import httpx

from app.config import GEMINI_API_KEY, GEMINI_MODEL

NARRATIVE_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
_TIMEOUT_SECONDS = 20
_MAX_INVOICES_IN_PROMPT = 20


def _compact_invoices(invoices: list[dict]) -> list[dict]:
    """Trim the invoice list to the fields the model needs."""
    trimmed = []
    for invoice in invoices[:_MAX_INVOICES_IN_PROMPT]:
        trimmed.append(
            {
                "invoice_number": invoice.get("invoice_number"),
                "vendor_name": invoice.get("vendor_name") or invoice.get("vendor_id"),
                "amount": invoice.get("amount"),
                "status": invoice.get("status"),
                "due_date": invoice.get("due_date"),
            }
        )
    return trimmed


def _build_prompt(payload: dict) -> str:
    return (
        "You are Invoxa, a bookkeeping assistant for a solo Indian business owner.\n"
        "Write a short plain-English status summary (2-3 sentences, no markdown,\n"
        "no bullet points) of the invoice activity described by the JSON below.\n"
        "Mention the total value in INR, what needs attention (flagged invoices,\n"
        "upcoming due dates) and anything notable about vendors. Be strictly\n"
        "factual: use only the numbers in the data, never invent figures.\n\n"
        "Activity data:\n"
        f"{json.dumps(payload, default=str)}"
    )


def ai_narrative(digest_dict: dict, invoices: list[dict]) -> str | None:
    """Ask Gemini for a 2-3 sentence narrative of the digest.

    Returns None whenever AI is unavailable so callers fall back to the
    deterministic summary lines.
    """
    if not GEMINI_API_KEY:
        return None

    payload = {
        "window_days": digest_dict.get("window_days"),
        "invoices_processed": digest_dict.get("invoices_processed"),
        "auto_approved": digest_dict.get("auto_approved"),
        "flagged_for_review": digest_dict.get("flagged_for_review"),
        "exported": digest_dict.get("exported"),
        "total_amount_inr": digest_dict.get("total_amount"),
        "top_vendors": digest_dict.get("top_vendors"),
        "due_soon": digest_dict.get("due_soon"),
        "due_soon_days": digest_dict.get("due_soon_days"),
        "invoices": _compact_invoices(invoices),
    }

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.post(
                NARRATIVE_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": _build_prompt(payload)}]}],
                    "generationConfig": {
                        "temperature": 0.4,
                        "maxOutputTokens": 512,
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception:  # network, API, quota - any failure means fallback
        return None

    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    if not text:
        return None
    return text
