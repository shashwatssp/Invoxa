"""Excel (XLSX) export.

Zoho Books, Excel and Google Sheets all import XLSX natively, so this
format mirrors the CSV columns and is generated in-memory with openpyxl.
"""
from __future__ import annotations

import datetime as dt
import io
from typing import Any

from openpyxl import Workbook

from app.database import fetch_export_rows
from app.export.csv_export import CSV_HEADERS, _format_date, _safe_amount


def _cell_value(header: str, invoice: dict[str, Any]) -> Any:
    status = (invoice.get("status") or "pending").replace("_", " ").title()
    mapping = {
        "date": _format_date(invoice.get("due_date") or invoice.get("created_at")),
        "voucher_type": "Invoice",
        "voucher_number": invoice.get("invoice_number") or "",
        "name": invoice.get("vendor_name") or invoice.get("vendor_id") or "",
        "gstin": "",
        "tax_amount": _safe_amount(invoice.get("tax_amount") or invoice.get("amount")),
        "amount": _safe_amount(invoice.get("amount")),
        "total_amount": _safe_amount(invoice.get("amount")),
        "narration": invoice.get("invoice_number") or "",
        "status": status,
    }
    return mapping[header]


def build_xlsx(
    status_filter: str | None = None,
    user_id: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    folder_id: str | None = None,
    ids: list[str] | None = None,
) -> bytes:
    """Render the invoice rows as an XLSX workbook, scoped to one account."""
    rows = fetch_export_rows(
        user_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        folder_id=folder_id,
        ids=ids,
    )

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Invoices"
    sheet.append(list(CSV_HEADERS))
    for invoice in rows:
        sheet.append([_cell_value(header, invoice) for header in CSV_HEADERS])

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
