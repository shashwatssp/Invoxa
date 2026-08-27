"""
CSV export API endpoints for Tally/Zoho compatibility.
"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

router = APIRouter(prefix="/api")


@router.get("/export/csv")
async def export_csv():
    """Generate CSV for Tally/Zoho import."""
    # Full implementation: Day 9
    csv_content = "vendor_name,invoice_number,amount,due_date,status\n"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoxa_export.csv"},
    )
