"""
Auto expense categorization via Gemini.

Given the already-extracted invoice fields, asks Gemini to pick one
expense category. Entirely optional: returns None whenever the API key
is missing, the request fails, or the model answers with anything
outside the known category list - the invoice simply stays
uncategorized and the user can pick one by hand.
"""

import json

import httpx

from app.config import GEMINI_API_KEY, GEMINI_MODEL

CATEGORY_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
_TIMEOUT_SECONDS = 15

# Fixed list shown in the UI and accepted by the API; Gemini must pick
# from exactly these.
CATEGORIES = [
    "office_supplies",
    "travel",
    "software",
    "utilities",
    "raw_materials",
    "marketing",
    "professional_services",
    "rent",
    "food",
    "logistics",
    "fuel",
    "repairs",
    "other",
]
_CATEGORY_SET = set(CATEGORIES)


def _build_prompt(vendor_name: str | None, invoice_number: str | None,
                  total_amount: float | None, line_items: list[dict] | None) -> str:
    return (
        "You are an Indian bookkeeping assistant. Categorize this purchase "
        "invoice into exactly ONE expense category from this list:\n"
        f"{json.dumps(CATEGORIES)}\n\n"
        "Return ONLY a JSON object: {\"category\": \"<one of the list>\"}\n\n"
        f"Vendor: {vendor_name or 'unknown'}\n"
        f"Invoice number: {invoice_number or 'unknown'}\n"
        f"Total amount INR: {total_amount if total_amount is not None else 'unknown'}\n"
        f"Line items: {json.dumps(line_items[:10]) if line_items else 'unknown'}"
    )


def ai_category(
    vendor_name: str | None,
    invoice_number: str | None,
    total_amount: float | None,
    line_items: list[dict] | None = None,
) -> str | None:
    """Ask Gemini for the expense category; None on any failure."""
    if not GEMINI_API_KEY:
        return None

    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
            response = client.post(
                CATEGORY_API_URL,
                params={"key": GEMINI_API_KEY},
                json={
                    "contents": [
                        {
                            "parts": [
                                {
                                    "text": _build_prompt(
                                        vendor_name, invoice_number, total_amount, line_items
                                    )
                                }
                            ]
                        }
                    ],
                    "generationConfig": {
                        "temperature": 0,
                        "maxOutputTokens": 64,
                        "thinkingConfig": {"thinkingBudget": 0},
                    },
                },
            )
            response.raise_for_status()
            data = response.json()
    except Exception:  # network / quota / API failure -> uncategorized
        return None

    try:
        content = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        content = content.removeprefix("```json").removesuffix("```").strip()
        category = json.loads(content).get("category")
    except (KeyError, IndexError, TypeError, ValueError, AttributeError):
        return None

    if isinstance(category, str) and category.strip() in _CATEGORY_SET:
        return category.strip()
    return None
