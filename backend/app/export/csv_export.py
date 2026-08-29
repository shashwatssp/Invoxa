"""
CSV export for Tally/Zoho.

Day 10 of the build plan will provide the full Tally/Zoho-compatible column mapping.
For now, this module exposes the smallest possible surface so the API endpoints in
``app.api.export`` compile and return a header-only CSV.  The detailed column mapping,
date formatting, and ledger-group lookups come in the dedicated Sprint #10 commit.
"""
from typing import Any

CSV_HEADERS = [
    "vendor_name",
    "vendor_gstin",
    "invoice_number",
    "invoice_date",
    "due_date",
    "amount",
    "tax_amount",
    "total_amount",
    "status",
]


def build_csv(status_filter: str | None = None) -> str:
    """
    Build the CSV body.  Returns just the header row during Sprint #6 because the
    detailed Tally/Zoho column layout is owned by Sprint #10.
    """
    return ",".join(CSV_HEADERS) + "\n"


def preview_csv_rows(status_filter: str | None = None) -> list[dict[str, Any]]:
    """Preview the rows the CSV export would emit (header-only placeholder)."""
    return [
        {"_placeholder": True, "message": "Detailed CSV preview will be available after Sprint #10."},
    ]
