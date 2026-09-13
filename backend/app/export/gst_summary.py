"""
GST monthly summary export.

Groups invoices (same optional filters as every other export) by
calendar month and reports, per month:

    month, invoices, taxable_value, tax_amount, total_amount

- ``total_amount`` is the canonical invoice amount stored on the row.
- ``tax_amount`` is the extracted tax (where known).
- ``taxable_value`` is the remainder (total - tax); when tax is unknown
  the whole amount is treated as taxable, conservatively.

Output is a CSV string ready for a CA or the GST portal.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
from typing import Any

from app.database import fetch_export_rows

GST_HEADERS = ["month", "invoices", "taxable_value", "tax_amount", "total_amount"]


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def summarize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group invoice rows by upload month; months sorted oldest first."""
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        month = str(row.get("created_at") or "")[:7]
        if not month:
            continue
        group = groups.setdefault(
            month,
            {"month": month, "invoices": 0, "taxable_value": 0.0, "tax_amount": 0.0, "total_amount": 0.0},
        )
        total = _to_float(row.get("amount"))
        tax = _to_float(row.get("tax_amount"))
        group["invoices"] += 1
        group["total_amount"] += total
        group["tax_amount"] += tax
        group["taxable_value"] += max(total - tax, 0.0) if tax else total
    return [groups[key] for key in sorted(groups)]


def build_gst_summary(
    status_filter: str | None = None,
    user_id: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    folder_id: str | None = None,
    ids: list[str] | None = None,
) -> str:
    """Render the GST monthly summary CSV as a string (one account scope)."""
    rows = fetch_export_rows(
        user_id,
        status_filter=status_filter,
        date_from=date_from,
        date_to=date_to,
        folder_id=folder_id,
        ids=ids,
    )
    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=GST_HEADERS,
        extrasaction="ignore",
        lineterminator="\n",
    )
    writer.writeheader()
    for group in summarize_rows(rows):
        writer.writerow(
            {
                key: f"{group[key]:.2f}" if key in ("taxable_value", "tax_amount", "total_amount") else group[key]
                for key in GST_HEADERS
            }
        )
    return output.getvalue()
