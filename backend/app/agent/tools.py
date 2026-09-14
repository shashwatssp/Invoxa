"""
Whitelisted, read-only tools for the Invoxa agent.

Every tool is a thin wrapper over the existing account-scoped database
helpers. Nothing here writes, deletes, sends, or spends: the agent can
only read data the signed-in account already owns. Results are trimmed
to bounded row counts so a single model turn stays small and cheap.

``FUNCTION_DECLARATIONS`` is the Gemini ``tools`` payload;
``execute_tool`` is the only dispatcher the loop may call — unknown
tool names return an error response instead of raising.
"""

from __future__ import annotations

import datetime as dt
import logging
from collections.abc import Callable
from typing import Any

from app.database import (
    category_spend,
    get_due_soon_rows,
    get_invoices,
    monthly_spend,
    vendor_spend_summary,
)

logger = logging.getLogger(__name__)

_MAX_ROWS = 15
_MAX_MONTHS = 24
_INVOICE_FIELDS = (
    "id",
    "invoice_number",
    "vendor_name",
    "amount",
    "tax_amount",
    "due_date",
    "status",
    "category",
    "created_at",
)


def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
    """Coerce a model-supplied argument to a safe integer range."""
    try:
        return max(low, min(high, int(value)))
    except (TypeError, ValueError):
        return default


def _trim_invoices(rows: list[dict], limit: int = _MAX_ROWS) -> list[dict]:
    """Keep only the fields (and row count) the model needs."""
    return [
        {field: row.get(field) for field in _INVOICE_FIELDS if row.get(field) is not None}
        for row in rows[:limit]
    ]


def tool_account_overview(user_id: str, args: dict) -> dict:
    """Counts and totals across the whole account, grouped by status."""
    invoices = get_invoices(user_id)
    counts: dict[str, int] = {}
    total = 0.0
    for row in invoices:
        status = row.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
        try:
            total += float(row.get("amount") or 0)
        except (TypeError, ValueError):
            continue
    return {
        "invoice_count": len(invoices),
        "total_amount_inr": round(total, 2),
        "by_status": counts,
    }


def tool_due_soon(user_id: str, args: dict) -> dict:
    """Unpaid invoices due within ``days`` (overdue included)."""
    days = _clamp_int(args.get("days"), default=5, low=1, high=90)
    rows = get_due_soon_rows(user_id, days=days)
    return {"days": days, "count": len(rows), "invoices": _trim_invoices(rows)}


def tool_vendor_spend(user_id: str, args: dict) -> dict:
    """Per-vendor spend totals, biggest first."""
    return {"vendors": vendor_spend_summary(user_id)[:_MAX_ROWS]}


def tool_category_spend(user_id: str, args: dict) -> dict:
    """Per-expense-category totals, biggest first."""
    return {"categories": category_spend(user_id)}


def tool_monthly_spend(user_id: str, args: dict) -> dict:
    """Invoiced amount per calendar month for the last ``months`` months."""
    months = _clamp_int(args.get("months"), default=6, low=1, high=_MAX_MONTHS)
    return {"months": months, "buckets": monthly_spend(user_id, months=months)}


def tool_flagged_invoices(user_id: str, args: dict) -> dict:
    """Invoices currently flagged for human review."""
    rows = get_invoices(user_id, status="flagged")
    return {"count": len(rows), "invoices": _trim_invoices(rows)}


def tool_search_invoices(user_id: str, args: dict) -> dict:
    """Search invoices by vendor name or invoice number substring."""
    query = str(args.get("query") or "").strip()[:100]
    if not query:
        return {"error": "Provide a search query."}
    rows = get_invoices(user_id, search=query)
    return {"query": query, "count": len(rows), "invoices": _trim_invoices(rows)}


def tool_gst_tax_summary(user_id: str, args: dict) -> dict:
    """Month-by-month tax totals (GST-visible view of recorded invoices)."""
    months = _clamp_int(args.get("months"), default=12, low=1, high=_MAX_MONTHS)
    cutoff_month = _month_shift(dt.date.today(), -(months - 1))
    buckets: dict[str, dict] = {}
    for row in get_invoices(user_id):
        month = str(row.get("created_at") or "")[:7]
        if not month or month < cutoff_month:
            continue
        bucket = buckets.setdefault(
            month, {"month": month, "invoices": 0, "taxable_value": 0.0, "tax_amount": 0.0}
        )
        try:
            amount = float(row.get("amount") or 0)
            tax = float(row.get("tax_amount") or 0)
        except (TypeError, ValueError):
            continue
        bucket["invoices"] += 1
        bucket["tax_amount"] += tax
        # Convention shared with the GST summary export: when no tax was
        # recorded the full amount is treated as taxable value.
        bucket["taxable_value"] += amount - tax if tax else amount
    summary = [buckets[key] for key in sorted(buckets)]
    for bucket in summary:
        bucket["taxable_value"] = round(bucket["taxable_value"], 2)
        bucket["tax_amount"] = round(bucket["tax_amount"], 2)
    return {"months": months, "summary": summary}


def _month_shift(base: dt.date, offset: int) -> str:
    total = base.year * 12 + (base.month - 1) + offset
    year, month = divmod(total, 12)
    return f"{year:04d}-{month + 1:02d}"


FUNCTION_DECLARATIONS = [
    {
        "name": "account_overview",
        "description": (
            "Counts and total value of all invoices in the account, grouped "
            "by status (pending, flagged, auto_approved, reviewed, exported)."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "due_soon",
        "description": (
            "Unpaid invoices due within the next N days, overdue included, "
            "soonest first. Use for 'what's due', 'what's late', 'chase who'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Look-ahead window in days (1-90, default 5).",
                }
            },
        },
    },
    {
        "name": "vendor_spend",
        "description": "Total spend and invoice count per vendor, biggest spend first.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "category_spend",
        "description": "Total spend per expense category, biggest first.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "monthly_spend",
        "description": "Total invoiced amount per calendar month for the last N months.",
        "parameters": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "How many months back (1-24, default 6).",
                }
            },
        },
    },
    {
        "name": "flagged_invoices",
        "description": "Invoices currently flagged and waiting for human review.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "search_invoices",
        "description": "Find invoices by a substring of the vendor name or invoice number.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search text (max 100 chars)."}
            },
            "required": ["query"],
        },
    },
    {
        "name": "gst_tax_summary",
        "description": (
            "Month-by-month taxable value and tax (GST) totals for the last N months."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "months": {
                    "type": "integer",
                    "description": "How many months back (1-24, default 12).",
                }
            },
        },
    },
]

_EXECUTORS: dict[str, Callable[[str, dict], dict]] = {
    "account_overview": tool_account_overview,
    "due_soon": tool_due_soon,
    "vendor_spend": tool_vendor_spend,
    "category_spend": tool_category_spend,
    "monthly_spend": tool_monthly_spend,
    "flagged_invoices": tool_flagged_invoices,
    "search_invoices": tool_search_invoices,
    "gst_tax_summary": tool_gst_tax_summary,
}


def execute_tool(name: str, args: dict, user_id: str) -> dict:
    """Run a whitelisted tool; unknown names and failures return errors.

    The returned dict is what goes back to the model as functionResponse.
    """
    executor = _EXECUTORS.get(name)
    if executor is None:
        logger.warning("Agent requested unknown tool: %s", name)
        return {"error": f"Unknown tool: {name}"}
    try:
        result = executor(user_id, dict(args or {}))
    except Exception:
        # Tool failure must never crash the loop or leak internals.
        logger.warning("Agent tool %s failed", name, exc_info=True)
        return {"error": "That data could not be loaded. Try a different question."}
    if isinstance(result, dict) and "error" in result:
        return result
    return {"output": result}
