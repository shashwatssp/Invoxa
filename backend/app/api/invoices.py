"""
Invoice API endpoints. All routes require a logged-in user.
Reads and file access are scoped to the owning account.
"""
import datetime as dt
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.categorization.gemini import CATEGORIES, ai_category
from app.database import (
    add_to_review_queue,
    create_invoice,
    delete_invoice,
    find_vendor_by_name,
    get_due_soon_rows,
    get_folder,
    get_invoice,
    get_invoices,
    get_latest_category_for_vendor,
    get_or_create_vendor,
    save_correction,
    save_extraction_result,
    update_invoice_fields,
    update_invoice_status,
)
from app.extraction.pipeline import extract_from_invoice
from app.models.invoice import Correction, ExtractionResult, InvoiceStatus
from app.review.corrections import edit_invoice_field, normalize_value
from app.supabase import delete_invoice_file, download_invoice, upload_invoice

router = APIRouter(prefix="/api")


def _load_owned_invoice(invoice_id: str, user: dict) -> dict:
    """Fetch an invoice and enforce ownership of the receipt file."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.get("created_by") and invoice["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your invoice")
    return invoice


def _iso_date(value: str | None) -> str | None:
    """Normalize an extracted DD/MM/YYYY date to ISO for the DB column."""
    if not value:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _write_back_canonical_fields(invoice_id: str, result: ExtractionResult) -> None:
    """Persist extracted key fields onto the invoices row so dashboards,
    digests and exports show real values instead of blanks."""
    fields: dict = {}
    if result.invoice_number:
        fields["invoice_number"] = result.invoice_number
    canonical_amount = result.total_amount or result.amount
    if canonical_amount is not None:
        fields["amount"] = float(canonical_amount)
    if result.tax_amount is not None:
        fields["tax_amount"] = float(result.tax_amount)
    due_date = _iso_date(result.due_date)
    if due_date:
        fields["due_date"] = due_date
    if result.line_items:
        fields["line_items"] = result.line_items
    update_invoice_fields(invoice_id, fields)


@router.get("/invoices")
async def list_invoices(
    folder_id: str | None = None,
    status: str | None = Query(None),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    search: str | None = Query(None, max_length=100),
    user=Depends(get_current_user),
):
    """List the account's invoices with optional filters.

    All filters are optional and combinable: folder, status, upload-date
    range (inclusive) and a case-insensitive search over invoice number
    and vendor name.
    """
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="'from' must be on or before 'to'.")
    return get_invoices(
        user["id"],
        folder_id=folder_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )


@router.get("/invoices/due-soon")
async def invoices_due_soon(
    days: int = Query(5, ge=1, le=90), user=Depends(get_current_user)
):
    """Account-wide unpaid invoices due within ``days`` (overdue included)."""
    return get_due_soon_rows(user["id"], days=days)


@router.get("/invoices/{invoice_id}/file")
async def invoice_file(invoice_id: str, user=Depends(get_current_user)):
    """Stream the original receipt PDF (owner only)."""
    invoice = _load_owned_invoice(invoice_id, user)
    try:
        file_bytes = download_invoice(invoice["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail="Could not load the receipt file.") from e
    if not file_bytes:
        raise HTTPException(status_code=404, detail="Receipt file not found")
    return Response(
        content=file_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="receipt-{invoice_id}.pdf"'},
    )


@router.get("/invoices/{invoice_id}/preview")
async def invoice_preview(invoice_id: str, user=Depends(get_current_user)):
    """Render page 1 of the stored receipt PDF as a PNG thumbnail (owner only)."""
    invoice = _load_owned_invoice(invoice_id, user)
    try:
        file_bytes = download_invoice(invoice["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail="Could not load the receipt file.") from e
    if not file_bytes:
        raise HTTPException(status_code=404, detail="Receipt file not found")
    try:
        import pymupdf

        doc = pymupdf.open(stream=file_bytes, filetype="pdf")
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=72)
        png_bytes = pix.tobytes("png")
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=422, detail="Could not render a preview.") from e
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.get("/invoices/{invoice_id}")
async def invoice_detail(invoice_id: str, user=Depends(get_current_user)):
    """Get single invoice detail with extraction fields."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/invoices/upload")
async def upload_and_register(
    file: UploadFile = File(...),
    folder_id: str | None = Form(None),
    user=Depends(get_current_user),
):
    """
    Upload an invoice file directly to Supabase Storage,
    create an invoice record, and trigger extraction.
    Optionally files the invoice into one of the account's folders.
    """
    file_bytes = await file.read()
    file_name = file.filename or "invoice.pdf"

    if folder_id and not get_folder(folder_id, user["id"]):
        raise HTTPException(status_code=404, detail="Folder not found")

    # Upload to Supabase Storage
    try:
        storage_path = upload_invoice(file_bytes, file_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}") from e

    # Create invoice record, stamped with the uploader
    invoice_id = create_invoice(storage_path, created_by=user["id"], folder_id=folder_id)

    # Trigger extraction
    result: ExtractionResult = extract_from_invoice(file_bytes, invoice_id)

    # Save extraction results
    save_extraction_result(invoice_id, result)

    # Write extracted key fields onto the invoice row so the dashboard,
    # digest and CSV export show real values.
    _write_back_canonical_fields(invoice_id, result)

    # Vendor association: by GSTIN when present, else vendor memory
    # (case-insensitive name match on previously seen vendors).
    vendor_id = None
    if result.vendor_gstin:
        vendor_id = get_or_create_vendor(
            gstin=result.vendor_gstin, name=result.vendor_name
        )
    elif result.vendor_name:
        known = find_vendor_by_name(result.vendor_name)
        if known:
            vendor_id = known["id"]
    if vendor_id:
        _db_update_vendor(invoice_id, vendor_id)

    # Auto expense categorization (Gemini, optional). Never blocks the
    # upload: any failure simply leaves the invoice uncategorized. When
    # AI has no answer, vendor memory kicks in: the category this vendor
    # was last seen with is reused.
    category = None
    try:
        category = ai_category(
            vendor_name=result.vendor_name,
            invoice_number=result.invoice_number,
            total_amount=result.total_amount or result.amount,
            line_items=result.line_items,
        )
    except Exception:  # categorization must never fail an upload
        category = None
    if not category and vendor_id:
        category = get_latest_category_for_vendor(vendor_id)
    if category:
        update_invoice_fields(invoice_id, {"category": category})

    # Update status and review queue with the REAL causes, not a generic label
    if result.needs_review:
        update_invoice_status(invoice_id, InvoiceStatus.FLAGGED)
        add_to_review_queue(
            invoice_id,
            reason="; ".join(result.review_reasons) or "Flagged for review",
        )
    else:
        update_invoice_status(invoice_id, InvoiceStatus.AUTO_APPROVED)

    return {
        "id": invoice_id,
        "storage_path": storage_path,
        "extraction": result,
        "category": category,
    }


@router.post("/invoices")
async def register_invoice(
    storage_path: str, vendor_id: str | None = None, user=Depends(get_current_user)
):
    """Register a new invoice after file uploaded to Storage."""
    invoice_id = create_invoice(storage_path, vendor_id, created_by=user["id"])
    return {"id": invoice_id, "storage_path": storage_path}


class CategoryUpdate(BaseModel):
    category: str | None = None


@router.patch("/invoices/{invoice_id}/category")
async def set_invoice_category(
    invoice_id: str, payload: CategoryUpdate, user=Depends(get_current_user)
):
    """Set (or clear with null) the expense category of an owned invoice."""
    _load_owned_invoice(invoice_id, user)
    category = payload.category
    if category is not None:
        category = category.strip()
        if category and category not in CATEGORIES:
            raise HTTPException(status_code=422, detail="Unknown category.")
        category = category or None
    update_invoice_fields(invoice_id, {"category": category})
    return {"id": invoice_id, "category": category}


class InvoiceFieldEdit(BaseModel):
    field_name: str
    new_value: str


@router.patch("/invoices/{invoice_id}/fields")
async def edit_invoice_fields_endpoint(
    invoice_id: str, payload: InvoiceFieldEdit, user=Depends(get_current_user)
):
    """Edit one extracted field from the detail page (owned invoices only).

    The edit is logged in ``corrections`` (audit + accuracy tracking) and
    canonical ``invoices`` columns are updated so dashboards and exports
    immediately reflect the human-verified value. Amounts and dates are
    normalized with the shared correction helper.
    """
    _load_owned_invoice(invoice_id, user)
    field = payload.field_name.strip()
    value = payload.new_value.strip()

    try:
        value = normalize_value(field, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        correction = edit_invoice_field(invoice_id, field, value)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return correction.model_dump()


@router.delete("/invoices/{invoice_id}")
async def delete_invoice_endpoint(invoice_id: str, user=Depends(get_current_user)):
    """Delete an owned invoice, its file, and its review-queue entries."""
    invoice = _load_owned_invoice(invoice_id, user)
    if invoice.get("storage_path"):
        delete_invoice_file(invoice["storage_path"])
    delete_invoice(invoice_id)
    return Response(status_code=204)


@router.patch("/invoices/{invoice_id}/folder")
async def set_invoice_folder(
    invoice_id: str, folder_id: str | None = None, user=Depends(get_current_user)
):
    """Move an owned invoice into a folder (or unfile it with null)."""
    _load_owned_invoice(invoice_id, user)
    if folder_id and not get_folder(folder_id, user["id"]):
        raise HTTPException(status_code=404, detail="Folder not found")
    update_invoice_fields(invoice_id, {"folder_id": folder_id})
    return {"id": invoice_id, "folder_id": folder_id}


@router.post("/invoices/{invoice_id}/extract")
async def run_extraction(invoice_id: str, user=Depends(get_current_user)):
    """Trigger OCR extraction + validation for an invoice."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    try:
        file_bytes = download_invoice(invoice["storage_path"])
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Failed to download invoice: {e}") from e

    result: ExtractionResult = extract_from_invoice(file_bytes, invoice_id)

    save_extraction_result(invoice_id, result)

    if result.vendor_gstin:
        vendor_id = get_or_create_vendor(
            gstin=result.vendor_gstin, name=result.vendor_name
        )
        if vendor_id:
            _db_update_vendor(invoice_id, vendor_id)

    if result.needs_review:
        update_invoice_status(invoice_id, InvoiceStatus.FLAGGED)
        add_to_review_queue(
            invoice_id,
            reason="; ".join(result.review_reasons) or "Flagged for review",
        )
    else:
        update_invoice_status(invoice_id, InvoiceStatus.AUTO_APPROVED)

    return result


def _db_update_vendor(invoice_id: str, vendor_id: str):
    """Helper to set vendor_id on invoice."""
    from app.supabase import get_client
    get_client().table("invoices").update({"vendor_id": vendor_id}).eq("id", invoice_id).execute()


@router.post("/invoices/{invoice_id}/correct")
async def save_correction_endpoint(
    invoice_id: str, correction: Correction, user=Depends(get_current_user)
):
    """Save a human correction to an invoice field."""
    save_correction(invoice_id, correction)
    return {"status": "correction saved"}
