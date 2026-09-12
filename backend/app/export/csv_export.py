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
import datetime as dt
import io
from datetime import datetime
from typing import Any

from app.database import fetch_export_rows

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


def build_csv(
    status_filter: str | None = None,
    user_id: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    folder_id: str | None = None,
    ids: list[str] | None = None,
) -> str:
    """Render the full CSV body as a string, scoped to one account.

    All filters are optional; omitted filters broaden the result.
    """
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=CSV_HEADERS,
        extrasaction="ignore",
        lineterminator="\n",  # consistent across platforms
    )
    writer.writeheader()
    rows = fetch_export_rows(
        user_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        folder_id=folder_id,
        ids=ids,
    )
    for invoice in rows:
        writer.writerow(_row_for(invoice))
    return output.getvalue()


def preview_csv_rows(
    status_filter: str | None = None,
    user_id: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    folder_id: str | None = None,
    ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return the rows that ``build_csv`` would emit, as plain dicts."""
    output = build_csv(
        status_filter=status_filter,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        folder_id=folder_id,
        ids=ids,
    )
    return list(csv.DictReader(io.StringIO(output)))
