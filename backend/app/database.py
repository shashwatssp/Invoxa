"""
Database access layer.
Uses Supabase service key client for all operations.
"""

from app.models.invoice import Correction, ExtractionResult, InvoiceStatus
from app.supabase import get_client


def _db():
    """Get Supabase client."""
    return get_client()


# --- Invoices ---

def get_invoices() -> list[dict]:
    """List all invoices with status."""
    result = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, created_at"
    ).order("created_at", desc=True).execute()
    return result.data or []


def get_invoice(invoice_id: str) -> dict | None:
    """Get a single invoice with extraction fields.

    Uses limit(1) instead of .single() so an unknown id returns None
    (and the API returns a clean 404) instead of a PostgREST APIError.
    """
    inv = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, created_at"
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
) -> str:
    """Create a new invoice record. Returns the invoice ID."""
    result = _db().table("invoices").insert({
        "storage_path": storage_path,
        "vendor_id": vendor_id,
        "created_by": created_by,
        "status": "pending",
    }).execute()
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

def add_to_review_queue(invoice_id: str, reason: str) -> None:
    """Add an invoice to the review queue."""
    _db().table("review_queue").insert({
        "invoice_id": invoice_id,
        "reason": reason,
        "status": "pending",
    }).execute()


def get_review_queue() -> list[dict]:
    """Get all pending review items with their invoice info (incl. storage_path
    so the UI can fetch the receipt PDF without extra round-trips)."""
    result = _db().table("review_queue").select(
        "id, invoice_id, reason, status, created_at, "
        "invoices(status, vendor_id, invoice_number, amount, storage_path)"
    ).eq("status", "pending").order("created_at", desc=True).execute()
    return result.data or []


def resolve_review_item(
    review_id: str, approved: bool, reviewed_by: str | None = None
) -> None:
    """Mark a review queue item as approved or rejected."""
    _db().table("review_queue").update({
        "status": "approved" if approved else "rejected",
        "reviewed_by": reviewed_by,
    }).eq("id", review_id).execute()
