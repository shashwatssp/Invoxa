"""
CSV export for Tally/Zoho.

Exports invoices as a CSV that Tally and Zoho Books can import.
The column layout follows the common Indian-accounting shape:

    Date, Voucher Type, Voucher Number, Name, Tax Amount,
    Amount, Total Amount, Narration, Status

Sprint #10 implements the full row mapping and date formatting; the API
endpoints in ``app.api.export`` call into these helpers.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from app.database import get_invoices

# Tally / Zoho-compatible column order.  Each row is written in this
# order so downstream accounting software can map fields predictably.
CSV_HEADERS = [
    "date",
    "voucher_type",
    "voucher_number",
    "name",
    "gstin",
    "tax_amount",
    "amount",
    "total_amount",
    "narration",
    "status",
]


def _format_date(value: str | datetime | None) -> str:
    """Render a date as ``DD/MM/YYYY``.  Empty when missing/unparseable."""
    if not value:
        return ""
    if isinstance(value, str):
        cleaned = value.replace("-", "").strip()
        try:
            parsed = datetime.strptime(cleaned[:8], "%Y%m%d")
            return parsed.strftime("%d/%m/%Y")
        except ValueError:
            try:
                parsed = datetime.strptime(cleaned, "%d/%m/%Y")
                return parsed.strftime("%d/%m/%Y")
            except ValueError:
                return value
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _safe_amount(value) -> str:
    """Render a numeric amount as a two-decimal string."""
    if value is None:
        return ""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return ""
    return f"{amount:.2f}"


def _row_for(invoice: dict[str, Any]) -> dict[str, Any]:
    """Map a Supabase invoice row to a Tally/Zoho CSV column."""
    status = (invoice.get("status") or "pending").replace("_", " ").title()
    return {
        "date": _format_date(invoice.get("due_date") or invoice.get("created_at")),
        "voucher_type": "Invoice",
        "voucher_number": invoice.get("invoice_number") or "",
        "name": invoice.get("vendor_name") or invoice.get("vendor_id") or "",
        "gstin": "",
        "tax_amount": _safe_amount(invoice.get("amount")),
        "amount": _safe_amount(invoice.get("amount")),
        "total_amount": _safe_amount(invoice.get("amount")),
        "narration": invoice.get("invoice_number") or "",
        "status": status,
    }


def fetch_export_rows(
    status_filter: str | None = None, user_id: str | None = None
) -> list[dict[str, Any]]:
    """Read invoice rows from Supabase, scoped to one account."""
    rows = get_invoices(user_id)
    if status_filter:
        rows = [r for r in rows if (r.get("status") or "") == status_filter]
    return [_row_for(r) for r in rows]


def build_csv(status_filter: str | None = None, user_id: str | None = None) -> str:
    """Render the full CSV body as a string, scoped to one account."""
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=CSV_HEADERS,
        extrasaction="ignore",
        lineterminator="\n",  # consistent across platforms
    )
    writer.writeheader()
    for row in fetch_export_rows(status_filter=status_filter, user_id=user_id):
        writer.writerow(row)
    return output.getvalue()


def preview_csv_rows(
    status_filter: str | None = None, user_id: str | None = None
) -> list[dict[str, Any]]:
    """Return the rows that ``build_csv`` would emit, as plain dicts."""
    return fetch_export_rows(status_filter=status_filter, user_id=user_id)
