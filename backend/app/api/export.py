"""
CSV export API endpoints for Tally/Zoho compatibility.

GET /api/export/csv      - Streams CSV download of approved invoices
GET /api/export/preview  - JSON preview of the CSV rows (for the dashboard)
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.export.csv_export import build_csv, preview_csv_rows
from app.export.tally_xml import build_tally_xml
from app.export.xlsx_export import build_xlsx

router = APIRouter(prefix="/api")


@router.get("/export/csv")
async def export_csv(
    status: str | None = Query(None, description="Filter by invoice status (e.g. auto_approved, reviewed)"),
    user=Depends(get_current_user),
):
    """Generate a CSV download for Tally/Zoho import (this account only)."""
    csv_content = build_csv(status_filter=status, user_id=user["id"])
    filename = f"invoxa_export_{status or 'all'}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/xlsx")
async def export_xlsx(
    status: str | None = Query(None),
    user=Depends(get_current_user),
):
    """Generate an Excel download for Zoho Books / Excel import."""
    xlsx_bytes = build_xlsx(status_filter=status, user_id=user["id"])
    filename = f"invoxa_export_{status or 'all'}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/tally-xml")
async def export_tally_xml(
    status: str | None = Query(None),
    user=Depends(get_current_user),
):
    """Generate a Tally Prime XML voucher import (Gateway of Tally > Import)."""
    xml_content = build_tally_xml(status_filter=status, user_id=user["id"])
    filename = f"invoxa_tally_{status or 'all'}.xml"
    return StreamingResponse(
        iter([xml_content]),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/preview")
async def export_preview(status: str | None = Query(None), user=Depends(get_current_user)):
    """Return a JSON preview of the rows that CSV export would emit."""
    return {"rows": preview_csv_rows(status_filter=status, user_id=user["id"])}
