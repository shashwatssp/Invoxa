"""
Database access layer.
Uses Supabase service key client for all operations.
"""

import datetime as dt

from app.models.invoice import Correction, ExtractionResult, InvoiceStatus
from app.supabase import get_client


def _db():
    """Get Supabase client."""
    return get_client()


# --- Invoices ---

def get_invoices(
    user_id: str | None = None,
    folder_id: str | None = None,
    status: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    search: str | None = None,
) -> list[dict]:
    """List invoices, scoped to the owning account when ``user_id`` is given.

    Each row carries a flattened ``vendor_name`` (from the vendors embed)
    so dashboards and exports can show a human-readable name.
    Every filter is optional, so no params means "everything in the
    account" (existing callers behave exactly as before):
    ``folder_id`` narrows to one folder, ``status`` to one status,
    ``date_from``/``date_to`` bound the upload date inclusively, and
    ``search`` is a case-insensitive substring match on invoice number
    or vendor name.
    """
    query = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, "
        "created_at, created_by, folder_id, vendors(name)"
    ).order("created_at", desc=True)
    if user_id:
        query = query.eq("created_by", user_id)
    if folder_id:
        query = _apply_folder_filter(query, folder_id)
    if status:
        query = query.eq("status", status)
    if date_from:
        query = query.gte("created_at", f"{date_from.isoformat()}T00:00:00")
    if date_to:
        query = query.lte("created_at", f"{date_to.isoformat()}T23:59:59.999999")
    result = query.execute()
    rows = result.data or []
    for row in rows:
        embed = row.pop("vendors") or {}
        row["vendor_name"] = embed.get("name") if isinstance(embed, dict) else None
    if search:
        rows = _filter_by_search(rows, search)
    return rows


def _filter_by_search(rows: list[dict], search: str) -> list[dict]:
    """Case-insensitive substring match on invoice number or vendor name.

    Applied in Python because the vendor name comes from an embedded
    resource that the plain query builder cannot filter on portably.
    """
    needle = search.strip().lower()
    if not needle:
        return rows
    matched: list[dict] = []
    for row in rows:
        invoice_number = (row.get("invoice_number") or "").lower()
        vendor_name = (row.get("vendor_name") or "").lower()
        if needle in invoice_number or needle in vendor_name:
            matched.append(row)
    return matched


def _apply_folder_filter(query, folder_id: str):
    """Filter by folder; the sentinel value ``none`` means 'unfiled only'."""
    if folder_id == "none":
        return query.is_("folder_id", "null")
    return query.eq("folder_id", folder_id)


def fetch_export_rows(
    user_id: str | None = None,
    status_filter: str | None = None,
    date_from: dt.date | None = None,
    date_to: dt.date | None = None,
    folder_id: str | None = None,
    ids: list[str] | None = None,
) -> list[dict]:
    """Single source of truth for export/digest row fetching.

    Always scoped to the owning account when ``user_id`` is given; every
    filter is optional, so no params means "everything in the account"
    (exactly what the original exports did).
    Date bounds are inclusive and filter on upload date (``created_at``).
    """
    query = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, "
        "created_at, created_by, folder_id, vendors(name)"
    ).order("created_at", desc=True)
    if user_id:
        query = query.eq("created_by", user_id)
    if status_filter:
        query = query.eq("status", status_filter)
    if date_from:
        query = query.gte("created_at", f"{date_from.isoformat()}T00:00:00")
    if date_to:
        query = query.lte("created_at", f"{date_to.isoformat()}T23:59:59.999999")
    if folder_id:
        query = _apply_folder_filter(query, folder_id)
    if ids:
        query = query.in_("id", ids)
    result = query.execute()
    rows = result.data or []
    for row in rows:
        embed = row.pop("vendors") or {}
        row["vendor_name"] = embed.get("name") if isinstance(embed, dict) else None
    return rows


def update_invoice_fields(invoice_id: str, fields: dict) -> None:
    """Patch canonical invoice columns (e.g. invoice_number, amount, due_date)."""
    if not fields:
        return
    _db().table("invoices").update(fields).eq("id", invoice_id).execute()


def get_invoice(invoice_id: str) -> dict | None:
    """Get a single invoice with extraction fields.

    Uses limit(1) instead of .single() so an unknown id returns None
    (and the API returns a clean 404) instead of a PostgREST APIError.
    """
    inv = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, "
        "created_at, created_by"
    ).eq("id", invoice_id).limit(1).execute()

    if not inv.data:
        return None
    inv.data = inv.data[0]

    fields = _db().table("extraction_fields").select(
        "field_name, raw_value, confidence, created_at"
    ).eq("invoice_id", invoice_id).execute()

    inv.data["extraction_fields"] = fields.data or []
    return inv.data


def create_invoice(
    storage_path: str,
    vendor_id: str | None = None,
    created_by: str | None = None,
    folder_id: str | None = None,
) -> str:
    """Create a new invoice record. Returns the invoice ID."""
    fields = {
        "storage_path": storage_path,
        "vendor_id": vendor_id,
        "created_by": created_by,
        "status": "pending",
    }
    if folder_id:
        fields["folder_id"] = folder_id
    result = _db().table("invoices").insert(fields).execute()
    return result.data[0]["id"]


def update_invoice_status(invoice_id: str, status: InvoiceStatus) -> None:
    """Update invoice status."""
    _db().table("invoices").update({"status": status.value}).eq("id", invoice_id).execute()


def save_extraction_result(invoice_id: str, result: ExtractionResult) -> None:
    """Save extraction results as individual extraction_fields rows."""
    fields_to_save = []
    for field_name, value in [
        ("vendor_name", result.vendor_name),
        ("vendor_gstin", result.vendor_gstin),
        ("invoice_number", result.invoice_number),
        ("invoice_date", result.invoice_date),
        ("due_date", result.due_date),
        ("amount", str(result.amount) if result.amount else None),
        ("tax_amount", str(result.tax_amount) if result.tax_amount else None),
        ("total_amount", str(result.total_amount) if result.total_amount else None),
    ]:
        if value is not None:
            fields_to_save.append({
                "invoice_id": invoice_id,
                "field_name": field_name,
                "raw_value": str(value),
                "confidence": result.confidence if hasattr(result, 'confidence') else result.overall_confidence,
            })

    if fields_to_save:
        _db().table("extraction_fields").insert(fields_to_save).execute()


def save_correction(invoice_id: str, correction: Correction) -> None:
    """Save a human correction."""
    _db().table("corrections").insert({
        "invoice_id": invoice_id,
        "field_name": correction.field_name,
        "old_value": correction.old_value,
        "new_value": correction.new_value,
    }).execute()


# --- Vendors ---

def get_or_create_vendor(gstin: str | None = None, name: str | None = None) -> str | None:
    """Look up a vendor by GSTIN, or create if not found. Returns vendor ID."""
    if not gstin:
        return None

    # limit(1) instead of .single(): an unseen GSTIN returns 0 rows and
    # must create a vendor, not raise PGRST116 ("0 rows" APIError -> HTTP 500).
    result = _db().table("vendors").select("id").eq("gstin", gstin).limit(1).execute()
    if result.data:
        return result.data[0]["id"]

    vendor_data = {"gstin": gstin}
    if name:
        vendor_data["name"] = name
    result = _db().table("vendors").insert(vendor_data).execute()
    return result.data[0]["id"]


# --- Folders ---

def list_folders(owner_id: str) -> list[dict]:
    """List the account's folders (id, name, created_at), oldest first."""
    result = _db().table("folders").select(
        "id, name, created_at"
    ).eq("owner_id", owner_id).order("created_at", desc=False).execute()
    return result.data or []


def get_folder(folder_id: str, owner_id: str) -> dict | None:
    """Return the folder when it exists AND belongs to this account."""
    result = _db().table("folders").select(
        "id, name, created_at"
    ).eq("id", folder_id).eq("owner_id", owner_id).limit(1).execute()
    return result.data[0] if result.data else None


def create_folder(owner_id: str, name: str) -> dict:
    """Create a folder for this account and return it."""
    result = _db().table("folders").insert({
        "owner_id": owner_id,
        "name": name,
    }).execute()
    return result.data[0]


def rename_folder(folder_id: str, owner_id: str, name: str) -> dict | None:
    """Rename a folder in the owning account; None when not found/owned."""
    result = _db().table("folders").update({"name": name}).eq(
        "id", folder_id
    ).eq("owner_id", owner_id).execute()
    return result.data[0] if result.data else None


def delete_folder(folder_id: str, owner_id: str) -> bool:
    """Delete a folder from the owning account. Invoices survive with
    folder_id set NULL by the database (ON DELETE SET NULL)."""
    result = _db().table("folders").delete().eq(
        "id", folder_id
    ).eq("owner_id", owner_id).execute()
    return bool(result.data)


def folder_invoice_counts(owner_id: str) -> dict[str, int]:
    """Count invoices per folder for this account, in one query."""
    result = _db().table("invoices").select(
        "folder_id"
    ).eq("created_by", owner_id).execute()
    counts: dict[str, int] = {}
    for row in result.data or []:
        fid = row.get("folder_id")
        if fid:
            counts[fid] = counts.get(fid, 0) + 1
    return counts


# --- Users ---

def create_user(email: str, password_hash: str, name: str | None, role: str) -> dict:
    """Create a user row and return it (without password hash)."""
    result = _db().table("users").insert({
        "email": email,
        "password_hash": password_hash,
        "name": name,
        "role": role,
    }).execute()
    row = result.data[0]
    row.pop("password_hash", None)
    return row


def get_user_by_email(email: str) -> dict | None:
    """Fetch a user by exact (lowercased) email, including password hash."""
    result = _db().table("users").select("*").eq("email", email).limit(1).execute()
    return result.data[0] if result.data else None


def get_user_by_id(user_id: str) -> dict | None:
    """Fetch a user by id, including password-hash-free public fields."""
    result = _db().table("users").select("*").eq("id", user_id).limit(1).execute()
    if not result.data:
        return None
    row = result.data[0]
    row.pop("password_hash", None)
    return row


# --- Review Queue ---

def _missing_flagged_invoice_ids(
    pending_rows: list[dict] | None, flagged_rows: list[dict] | None
) -> list[str]:
    """Flagged invoice ids that have no pending review item."""
    pending_ids = {row.get("invoice_id") for row in (pending_rows or [])}
    return [
        row["id"]
        for row in (flagged_rows or [])
        if row.get("id") not in pending_ids
    ]


def backfill_review_queue(user_id: str) -> int:
    """Ensure every flagged invoice has a pending review item.

    Restores the invariant "dashboard 'needs review' count == review
    queue length": older rows (resolved before approval synced the
    invoice status, or whose queue entry was lost) would otherwise
    show as needing review on the dashboard while the queue looked
    empty. Returns the number of items created.
    """
    pending = _db().table("review_queue").select("invoice_id").eq(
        "status", "pending"
    ).execute()
    flagged = _db().table("invoices").select("id").eq(
        "created_by", user_id
    ).eq("status", "flagged").execute()
    missing = _missing_flagged_invoice_ids(pending.data, flagged.data)
    if not missing:
        return 0
    _db().table("review_queue").insert([
        {"invoice_id": inv_id, "reason": "Flagged for review", "status": "pending"}
        for inv_id in missing
    ]).execute()
    return len(missing)


def add_to_review_queue(invoice_id: str, reason: str) -> None:
    """Add an invoice to the review queue."""
    _db().table("review_queue").insert({
        "invoice_id": invoice_id,
        "reason": reason,
        "status": "pending",
    }).execute()


def get_review_queue(user_id: str | None = None) -> list[dict]:
    """Get pending review items with their invoice info (incl. storage_path
    so the UI can fetch the receipt PDF without extra round-trips).

    Scoped to the owning account when ``user_id`` is given.
    """
    # !inner makes the created_by filter below eliminate parent rows
    # (PostgREST left-join embeds would otherwise only trim the embed).
    query = _db().table("review_queue").select(
        "id, invoice_id, reason, status, created_at, "
        "invoices!inner(status, vendor_id, invoice_number, amount, storage_path, created_by)"
    ).eq("status", "pending")
    if user_id:
        query = query.eq("invoices.created_by", user_id)
    result = query.order("created_at", desc=True).execute()
    return result.data or []


def get_review_item_owner(review_id: str) -> str | None:
    """Return the created_by (owner user id) of a review item's invoice."""
    result = _db().table("review_queue").select(
        "invoices(created_by)"
    ).eq("id", review_id).limit(1).execute()
    if not result.data:
        return None
    embed = (result.data[0].get("invoices") or {})
    return embed.get("created_by") if isinstance(embed, dict) else None


def get_review_item_invoice_id(review_id: str) -> str | None:
    """Return the invoice id a review item points at."""
    result = _db().table("review_queue").select(
        "invoice_id"
    ).eq("id", review_id).limit(1).execute()
    return result.data[0].get("invoice_id") if result.data else None


def resolve_review_item(
    review_id: str, approved: bool, reviewed_by: str | None = None
) -> None:
    """Mark a review queue item as approved or rejected."""
    _db().table("review_queue").update({
        "status": "approved" if approved else "rejected",
        "reviewed_by": reviewed_by,
    }).eq("id", review_id).execute()
