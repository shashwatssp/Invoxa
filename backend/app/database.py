"""
Database access layer.
Uses Supabase service key client for all operations.
"""
from typing import Any

from app.supabase import get_client
from app.models.invoice import Invoice, InvoiceStatus, ExtractionResult, Correction


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
    """Get a single invoice with extraction fields."""
    inv = _db().table("invoices").select(
        "id, vendor_id, invoice_number, amount, due_date, status, storage_path, created_at"
    ).eq("id", invoice_id).single().execute()

    if not inv.data:
        return None

    fields = _db().table("extraction_fields").select(
        "field_name, raw_value, confidence, created_at"
    ).eq("invoice_id", invoice_id).execute()

    inv.data["extraction_fields"] = fields.data or []
    return inv.data


def create_invoice(storage_path: str, vendor_id: str | None = None) -> str:
    """Create a new invoice record. Returns the invoice ID."""
    result = _db().table("invoices").insert({
        "storage_path": storage_path,
        "vendor_id": vendor_id,
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

    result = _db().table("vendors").select("id").eq("gstin", gstin).single().execute()
    if result.data:
        return result.data["id"]

    vendor_data = {"gstin": gstin}
    if name:
        vendor_data["name"] = name
    result = _db().table("vendors").insert(vendor_data).execute()
    return result.data[0]["id"]


# --- Review Queue ---

def add_to_review_queue(invoice_id: str, reason: str) -> None:
    """Add an invoice to the review queue."""
    _db().table("review_queue").insert({
        "invoice_id": invoice_id,
        "reason": reason,
        "status": "pending",
    }).execute()


def get_review_queue() -> list[dict]:
    """Get all invoices in the review queue."""
    result = _db().table("review_queue").select(
        "id, invoice_id, reason, status, created_at, invoices(status, vendor_id, invoice_number, amount)"
    ).eq("status", "pending").order("created_at", desc=True).execute()
    return result.data or []


def resolve_review_item(review_id: str, approved: bool) -> None:
    """Mark a review queue item as approved or rejected."""
    _db().table("review_queue").update({
        "status": "approved" if approved else "rejected",
    }).eq("id", review_id).execute()
