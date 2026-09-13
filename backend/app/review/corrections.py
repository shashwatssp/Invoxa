"""
Correction logging for the review queue.

When a reviewer corrects a field on a flagged invoice, the change must:

1.  Be persisted in the ``corrections`` table for auditability and retraining.
2.  Update the originating ``extraction_fields`` row so the same field on the
    same invoice reflects the human-verified value.
3.  For columns that live on ``invoices`` (e.g. ``invoice_number``,
    ``amount``) the canonical column is also patched.

This module also owns value normalization for human-entered corrections:
``normalize_value`` turns "1,180.50" into a clean number and "15/03/2026"
into an ISO date so raw display strings never reach numeric/DATE columns.

This module is imported by ``app.api.review`` to provide the HTTP boundary -
see ``POST /api/review/{review_id}/correct``.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

from app.models.invoice import Correction
from app.supabase import get_client

# Fields whose corrected value is written back to the canonical invoices
# table so dashboards, digests and exports see the human-verified value.
INVOICE_LEVEL_FIELDS = {
    "invoice_number",
    "amount",
    "tax_amount",
    "total_amount",  # stored in invoices.amount (the canonical total)
    "due_date",
}

# Field name -> invoices column. Most fields share the name; the grand
# total is stored in the ``amount`` column (the table has no
# ``total_amount`` column). Fields absent from this map (e.g.
# ``invoice_date``, ``vendor_*``) live only in extraction_fields.
INVOICE_COLUMN_MAP = {
    "invoice_number": "invoice_number",
    "amount": "amount",
    "tax_amount": "tax_amount",
    "total_amount": "amount",
    "due_date": "due_date",
}

# Amount-style fields (currency typed by a human, possibly with symbols
# or thousand separators) and date-style fields handled by normalize_value.
_AMOUNT_FIELDS = {"amount", "tax_amount", "total_amount"}
_DATE_FIELDS = {"invoice_date", "due_date"}
_CURRENCY_NOISE = re.compile(r"[\u20b9\s,]")


def _normalize_amount(value: str) -> str:
    """"1,180.50" / "1 180.50" / "1180.50" -> "1180.5"."""
    cleaned = _CURRENCY_NOISE.sub("", value)
    try:
        return str(float(cleaned))
    except ValueError:
        raise ValueError(
            f"'{value.strip()}' is not a valid amount (e.g. 1180.50)"
        ) from None


def _normalize_date(value: str) -> str:
    """DD/MM/YYYY and DD-MM-YYYY -> ISO; ISO passes through."""
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(
        f"'{value.strip()}' is not a valid date (use DD/MM/YYYY or YYYY-MM-DD)"
    )


def normalize_value(field_name: str, value: str) -> str:
    """Normalize a human-entered correction to its canonical stored form.

    Amounts lose currency symbols/thousand separators and become plain
    floats ("1,180.50" -> "1180.5"); dates become ISO YYYY-MM-DD;
    everything else is returned trimmed. Raises ``ValueError`` with a
    user-facing message when an amount/date cannot be parsed.
    """
    field = (field_name or "").strip()
    raw = (value or "").strip()
    if field in _AMOUNT_FIELDS:
        return _normalize_amount(raw)
    if field in _DATE_FIELDS:
        return _normalize_date(raw)
    return raw

# Fields a user may edit from the invoice detail page (no review item
# needed). Vendor name/GSTIN are excluded on purpose: renaming a vendor
# touches the shared vendors table and needs its own flow.
EDITABLE_FIELDS = {
    "invoice_number",
    "invoice_date",
    "due_date",
    "amount",
    "tax_amount",
    "total_amount",
}

def _fetch_review_row(client: Any, review_id: str) -> dict[str, Any]:
    """
    Read the review_queue row for ``review_id``.  Raises LookupError if the
    review_id is not present.
    """
    response = (
        client.table("review_queue")
        .select("id, invoice_id, status")
        .eq("id", review_id)
        .single()
        .execute()
    )
    row = getattr(response, "data", None)
    if not row:
        raise LookupError(f"Review item {review_id} not found in review_queue")
    return row


def _fetch_existing_field(
    client: Any,
    invoice_id: str,
    field_name: str,
) -> dict[str, Any] | None:
    """Look up the extraction_fields row for ``(invoice_id, field_name)``."""
    response = (
        client.table("extraction_fields")
        .select("id, raw_value, confidence")
        .eq("invoice_id", invoice_id)
        .eq("field_name", field_name)
        .limit(1)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    return rows[0] if rows else None


def log_correction(
    review_id: str,
    field_name: str,
    new_value: str,
) -> Correction:
    """
    Persist the human correction into the ``corrections`` table and return a
    populated ``Correction`` model.

    Raises
    ------
    LookupError
        If ``review_id`` does not correspond to a queued review item.
    ValueError
        If ``field_name`` is empty, ``new_value`` is empty after trimming,
        or ``field_name`` is not in ``EDITABLE_FIELDS``.
    """
    if not field_name or not field_name.strip():
        raise ValueError("field_name must be a non-empty string")
    if new_value is None or not str(new_value).strip():
        raise ValueError("new_value must be a non-empty string")

    # Same whitelist as the detail-page edit flow: typos or unexpected
    # field names must not silently create junk extraction rows.
    if field_name.strip() not in EDITABLE_FIELDS:
        raise ValueError(f"Field '{field_name}' is not editable")

    client = get_client()
    row = _fetch_review_row(client, review_id)
    invoice_id = row["invoice_id"]

    # Capture the previous value (if any) so the audit row records the diff.
    previous_field = _fetch_existing_field(client, invoice_id, field_name)
    old_value = previous_field["raw_value"] if previous_field else None

    insert_payload = {
        "invoice_id": invoice_id,
        "field_name": field_name.strip(),
        "old_value": old_value,
        "new_value": str(new_value).strip(),
    }
    response = (
        client.table("corrections")
        .insert(insert_payload)
        .execute()
    )

    inserted = (getattr(response, "data", None) or [{}])[0]
    return Correction(
        invoice_id=invoice_id,
        field_name=field_name.strip(),
        old_value=old_value,
        new_value=str(new_value).strip(),
        # Provide a fallback timestamp if the DB didn't echo it back so the
        # returned model is always usable by API callers.
corrected_at=inserted.get("corrected_at") or datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds"),
    )


def apply_correction_to_invoice(correction: Correction) -> dict[str, Any]:
    """
    Propagate a correction onto the originating extraction_fields row and, if
    applicable, the corresponding ``invoices`` column.  Returns the updated
    extraction_fields row (or an empty dict if nothing existed yet).
    """
    client = get_client()

    # 1. Update the matching extraction_fields row, or insert a new one.
    existing = _fetch_existing_field(client, correction.invoice_id, correction.field_name)
    if existing:
        client.table("extraction_fields").update({
            "raw_value": correction.new_value,
            # Mark human-verified so reviewers can see it at a glance.
            "confidence": 1.0,
        }).eq("id", existing["id"]).execute()
    else:
        client.table("extraction_fields").insert({
            "invoice_id": correction.invoice_id,
            "field_name": correction.field_name,
            "raw_value": correction.new_value,
            "confidence": 1.0,
        }).execute()

    # 2. If the corrected field maps to a canonical invoices column
    #    (invoice_number, amount, tax_amount, due_date, and the grand
    #    total which is stored in ``amount``), patch it there too so API
    #    consumers see the human-verified value.
    column = INVOICE_COLUMN_MAP.get(correction.field_name)
    if column:
        client.table("invoices").update({
            column: correction.new_value,
        }).eq("id", correction.invoice_id).execute()

    # Return the updated extraction_fields row for the caller.
    return _fetch_existing_field(client, correction.invoice_id, correction.field_name) or {}


def edit_invoice_field(invoice_id: str, field_name: str, new_value: str) -> Correction:
    """Edit one field from the invoice detail page (no review item needed).

    Same guarantees as a review correction: logged in ``corrections``,
    written to the ``extraction_fields`` row (created when missing) with
    confidence 1.0, and canonical ``invoices`` columns patched.
    """
    field = (field_name or "").strip()
    if field not in EDITABLE_FIELDS:
        raise ValueError(f"Field '{field_name}' is not editable")
    value = str(new_value).strip()
    if not value:
        raise ValueError("new_value must be a non-empty string")

    client = get_client()
    previous = _fetch_existing_field(client, invoice_id, field)
    correction = Correction(
        invoice_id=invoice_id,
        field_name=field,
        old_value=previous["raw_value"] if previous else None,
        new_value=value,
    )
    client.table("corrections").insert({
        "invoice_id": correction.invoice_id,
        "field_name": correction.field_name,
        "old_value": correction.old_value,
        "new_value": correction.new_value,
    }).execute()
    apply_correction_to_invoice(correction)
    return correction


def has_pending_review(review_id: str) -> bool:
    """Convenience predicate used by the API to short-circuit on stale ids."""
    response = (
        get_client()
        .table("review_queue")
        .select("id, status")
        .eq("id", review_id)
        .limit(1)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    return bool(rows) and rows[0].get("status") == "pending"
