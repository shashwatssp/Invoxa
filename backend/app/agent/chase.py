"""
Payment-chase drafts.

Scans due-soon and overdue invoices (unpaid), groups them by vendor,
and drafts a polite WhatsApp reminder per vendor. DRAFTS ONLY — nothing
is ever sent automatically: the user taps a prefilled ``wa.me`` link
(same zero-cost, no-ToS-risk pattern as the vendor share menu).

One bounded Gemini call per vendor, at most 5 vendors per run; when AI
is unavailable a deterministic template keeps the feature working.
"""

from __future__ import annotations

import logging
import urllib.parse

import httpx

from app.agent import budget
from app.config import GEMINI_API_KEY, GEMINI_MODEL
from app.database import get_due_soon_rows

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
_TIMEOUT_SECONDS = 30
MAX_VENDORS_PER_RUN = 5


def _amount(row: dict) -> float:
    try:
        return float(row.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _template_draft(vendor: str, items: list[dict], total: float) -> str:
    due_dates = ", ".join(
        sorted({str(item.get("due_date_parsed") or item.get("due_date") or "") for item in items})[:3]
    )
    return (
        f"Hi {vendor}! A friendly reminder from our accounts desk: "
        f"{len(items)} invoice(s) totalling Rs {total:,.0f} are due "
        f"(due dates: {due_dates}). Could you please confirm the payment "
        f"timeline? Thank you!"
    )


def _ai_draft(vendor: str, items: list[dict], total: float) -> str | None:
    """One Gemini call for a natural reminder; None on any failure."""
    if not GEMINI_API_KEY:
        return None
    payload = {
        "vendor": vendor,
        "total_due_inr": round(total, 2),
        "overdue_count": sum(1 for item in items if item.get("overdue")),
        "invoices": [
            {
                "invoice_number": item.get("invoice_number"),
                "amount": item.get("amount"),
                "due_date": item.get("due_date_parsed") or item.get("due_date"),
            }
            for item in items[:10]
        ],
    }
    prompt = (
        "Write a short, polite WhatsApp payment reminder (2-3 sentences, no "
        "markdown) to send to a vendor. Indian business context, firm but "
        "friendly. Mention the total due in INR and the most important due "
        "date. Use only the JSON below, never invent figures.\n\n"
        f"Data: {payload}"
    )
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.post(
                GEMINI_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "temperature": 0.5,
                        "maxOutputTokens": 256,
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
        return data["candidates"][0]["content"]["parts"][0]["text"].strip() or None
    except Exception:
        logger.warning("Chase draft AI call failed for %s", vendor, exc_info=True)
        return None


def draft_payment_chase(user_id: str) -> dict:
    """Build per-vendor reminder drafts. Read-only; never sends anything."""
    rows = get_due_soon_rows(user_id, days=30)
    groups: dict[str, list[dict]] = {}
    for row in rows:
        name = row.get("vendor_name") or row.get("vendor_id") or "(unknown vendor)"
        groups.setdefault(name, []).append(row)

    remaining = budget.remaining_today()
    ai_used = 0
    drafts: list[dict] = []
    for vendor, items in list(groups.items())[:MAX_VENDORS_PER_RUN]:
        total = sum(_amount(item) for item in items)
        message = None
        if ai_used < min(remaining, MAX_VENDORS_PER_RUN):
            message = _ai_draft(vendor, items, total)
            if message:
                ai_used += 1
                budget.record_model_calls(1, user_id, "chase_draft")
        source = "gemini"
        if not message:
            message = _template_draft(vendor, items, total)
            source = "template"
        message = message.strip()
        drafts.append(
            {
                "vendor": vendor,
                "invoice_count": len(items),
                "overdue_count": sum(1 for item in items if item.get("overdue")),
                "total_due": round(total, 2),
                "invoice_numbers": [
                    item.get("invoice_number") for item in items if item.get("invoice_number")
                ][:15],
                "message": message,
                "whatsapp_url": f"https://wa.me/?text={urllib.parse.quote(message)}",
                "source": source,
            }
        )

    budget.log_agent_event(
        user_id, "chase_drafts", {"vendors": len(drafts), "ai_drafts": ai_used}
    )
    return {
        "drafts": drafts,
        "vendors_found": len(groups),
        "note": "Drafts only — nothing is sent until you tap a button.",
    }
