"""
Vendors API endpoints.

GET /api/vendors/summary     - Per-vendor spend totals, biggest spend first.
GET /api/vendors/summary.pdf - The same summary as a shareable A4 PDF.
"""
from fastapi import APIRouter, Depends, Response

from app.auth.dependencies import get_current_user
from app.database import vendor_spend_summary
from app.export.vendor_summary import build_vendor_summary_pdf

router = APIRouter(prefix="/api")


@router.get("/vendors/summary")
async def vendors_summary(user=Depends(get_current_user)):
    """Per-vendor spend summary (total, invoice count, last invoice date)."""
    return vendor_spend_summary(user["id"])


@router.get("/vendors/summary.pdf")
async def vendors_summary_pdf(user=Depends(get_current_user)):
    """The vendor spend summary as a PDF, ready to share on WhatsApp/email."""
    pdf_bytes = build_vendor_summary_pdf(user["id"], owner_email=user.get("email") or "")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=invoxa_vendors.pdf"},
    )
