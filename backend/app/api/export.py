"""
CSV export API endpoints for Tally/Zoho compatibility.

GET /api/export/csv      - Streams CSV download of approved invoices
GET /api/export/preview  - JSON preview of the CSV rows (for the dashboard)
"""
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from app.auth.dependencies import get_current_user
from app.export.csv_export import build_csv, preview_csv_rows

router = APIRouter(prefix="/api")


@router.get("/export/csv")
async def export_csv(
    status: str | None = Query(None, description="Filter by invoice status (e.g. auto_approved, reviewed)"),
    user=Depends(get_current_user),
):
    """Generate a CSV download for Tally/Zoho import."""
    csv_content = build_csv(status_filter=status)
    filename = f"invoxa_export_{status or 'all'}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/preview")
async def export_preview(status: str | None = Query(None), user=Depends(get_current_user)):
    """Return a JSON preview of the rows that CSV export would emit."""
    return {"rows": preview_csv_rows(status_filter=status)}
