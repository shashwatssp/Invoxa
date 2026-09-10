"""
Invoice API endpoints. All routes require a logged-in user.
"""
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile

from app.auth.dependencies import get_current_user
from app.database import (
    add_to_review_queue,
    create_invoice,
    get_invoice,
    get_invoices,
    get_or_create_vendor,
    save_correction,
    save_extraction_result,
    update_invoice_status,
)
from app.extraction.pipeline import extract_from_invoice
from app.models.invoice import Correction, ExtractionResult, InvoiceStatus
from app.supabase import download_invoice, upload_invoice

router = APIRouter(prefix="/api")


@router.get("/invoices")
async def list_invoices(user=Depends(get_current_user)):
    """List all invoices with status."""
    return get_invoices()


@router.get("/invoices/{invoice_id}/file")
async def invoice_file(invoice_id: str, user=Depends(get_current_user)):
    """Stream the original receipt PDF for an invoice (requires login)."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
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


@router.get("/invoices/{invoice_id}")
async def invoice_detail(invoice_id: str, user=Depends(get_current_user)):
    """Get single invoice detail with extraction fields."""
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    return invoice


@router.post("/invoices/upload")
async def upload_and_register(file: UploadFile = File(...), user=Depends(get_current_user)):
    """
    Upload an invoice file directly to Supabase Storage,
    create an invoice record, and trigger extraction.
    """
    file_bytes = await file.read()
    file_name = file.filename or "invoice.pdf"

    # Upload to Supabase Storage
    try:
        storage_path = upload_invoice(file_bytes, file_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Storage upload failed: {e}") from e

    # Create invoice record, stamped with the uploader
    invoice_id = create_invoice(storage_path, created_by=user["id"])

    # Trigger extraction
    result: ExtractionResult = extract_from_invoice(file_bytes, invoice_id)

    # Save extraction results
    save_extraction_result(invoice_id, result)

    # Update invoice vendor if found
    if result.vendor_gstin:
        vendor_id = get_or_create_vendor(
            gstin=result.vendor_gstin, name=result.vendor_name
        )
        if vendor_id:
            _db_update_vendor(invoice_id, vendor_id)

    # Update status and review queue
    if result.needs_review:
        update_invoice_status(invoice_id, InvoiceStatus.FLAGGED)
        add_to_review_queue(
            invoice_id,
            reason=f"Low confidence fields detected (overall: {result.overall_confidence})"
        )
    else:
        update_invoice_status(invoice_id, InvoiceStatus.AUTO_APPROVED)

    return {"id": invoice_id, "storage_path": storage_path, "extraction": result}


@router.post("/invoices")
async def register_invoice(
    storage_path: str, vendor_id: str | None = None, user=Depends(get_current_user)
):
    """Register a new invoice after file uploaded to Storage."""
    invoice_id = create_invoice(storage_path, vendor_id, created_by=user["id"])
    return {"id": invoice_id, "storage_path": storage_path}


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
            reason=f"Low confidence fields detected (overall: {result.overall_confidence})"
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
