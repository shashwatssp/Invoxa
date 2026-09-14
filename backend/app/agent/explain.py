"""
Plain-English explanations for flagged invoices.

One bounded Gemini call per request (never per upload): given the
flag reasons and the extracted fields, the model explains what went
wrong and what the human should verify or fix. Returns None whenever
AI is unavailable so the UI falls back to the raw reason text.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.agent import budget
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.database import get_invoice, get_review_queue

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
_TIMEOUT_SECONDS = 30
_MAX_FIELDS_IN_PROMPT = 15


def _build_prompt(invoice: dict, reasons: list[str]) -> str:
    fields = [
        {"field": f.get("field_name"), "value": f.get("raw_value"), "confidence": f.get("confidence")}
        for f in (invoice.get("extraction_fields") or [])[:_MAX_FIELDS_IN_PROMPT]
    ]
    payload = {
        "invoice_number": invoice.get("invoice_number"),
        "amount": invoice.get("amount"),
        "due_date": invoice.get("due_date"),
        "flag_reasons": reasons or ["Flagged for review"],
        "extracted_fields": fields,
    }
    return (
        "You are Invoxa, a bookkeeping assistant for an Indian micro-business. "
        "An invoice was flagged for human review by the extraction pipeline. "
        "In 2-3 plain sentences (no markdown), explain: (1) why this invoice "
        "was most likely flagged, and (2) exactly what the owner should check "
        "on the original receipt before approving it. Be strictly factual — "
        "refer only to the JSON below, never invent details.\n\n"
        f"Flagged invoice data:\n{json.dumps(payload, default=str)}"
    )


def explain_flag(user_id: str, invoice_id: str) -> str | None:
    """Explain why ``invoice_id`` is flagged. None when AI is unavailable."""
    if not GEMINI_API_KEY:
        return None

    invoice = get_invoice(invoice_id)
    if not invoice:
        return None
    reasons = [
        item.get("reason") or ""
        for item in get_review_queue(user_id)
        if item.get("invoice_id") == invoice_id
    ]

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": _build_prompt(invoice, reasons)}]}],
                    "generationConfig": {
                        "temperature": 0.3,
                        "maxOutputTokens": 512,
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception:
        logger.warning("Flag explanation call failed", exc_info=True)
        return None

    budget.record_model_calls(1, user_id, "explain_flag")
    try:
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError, TypeError, AttributeError):
        return None
    return text or None
