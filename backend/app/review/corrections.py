"""
Correction logging for the review queue.

When a reviewer corrects a field on a flagged invoice, the change must:

1.  Be persisted in the ``corrections`` table for auditability and retraining.
2.  Update the originating ``extraction_fields`` row so the same field on the
    same invoice reflects the human-verified value.
3.  For columns that live on ``invoices`` (e.g. ``invoice_number``,
    ``amount``) the canonical column is also patched.

This module is imported by ``app.api.review`` to provide the HTTP boundary -
see ``POST /api/review/{review_id}/correct``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.models.invoice import Correction
from app.supabase import get_client

# Fields that live directly on the invoices table.
INVOICE_LEVEL_FIELDS = {
    "invoice_number",
    "amount",
    "due_date",
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
        If ``field_name`` is empty or ``new_value`` is empty after trimming.
    """
    if not field_name or not field_name.strip():
        raise ValueError("field_name must be a non-empty string")
    if new_value is None or not str(new_value).strip():
        raise ValueError("new_value must be a non-empty string")

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
corrected_at=inserted.get("corrected_at") or datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds"),
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

    # 2. If the corrected field lives directly on the invoices table
    #    (invoice_number, amount, due_date), patch it there too so API
    #    consumers see the canonical human-verified value.
    if correction.field_name in INVOICE_LEVEL_FIELDS:
        client.table("invoices").update({
            correction.field_name: correction.new_value,
        }).eq("id", correction.invoice_id).execute()

    # Return the updated extraction_fields row for the caller.
    return _fetch_existing_field(client, correction.invoice_id, correction.field_name) or {}


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
