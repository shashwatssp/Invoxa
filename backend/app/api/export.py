"""
Export API endpoints for Tally/Zoho compatibility and PDF statements.

GET /api/export/csv      - Streams CSV download of approved invoices
GET /api/export/xlsx     - Excel (XLSX) for Zoho Books / Excel
GET /api/export/tally-xml - Tally Prime voucher import
GET /api/export/pdf      - Printable A4 statement
GET /api/export/preview  - JSON preview of the CSV rows (for the dashboard)

Every endpoint accepts OPTIONAL filters (status, from/to upload-date range,
folder, comma-separated ids); with no filters the behaviour is exactly the
original "everything in this account". All results stay scoped to the
logged-in account.
"""
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.auth.dependencies import get_current_user
from app.database import fetch_export_rows
from app.export.csv_export import build_csv, preview_csv_rows
from app.export.pdf_statement import build_pdf_statement
from app.export.tally_xml import build_tally_xml
from app.export.xlsx_export import build_xlsx

router = APIRouter(prefix="/api")

MAX_IDS = 500


def _parse_ids(ids: str | None) -> list[str] | None:
    """Parse a comma-separated id list; capped to keep queries sane."""
    if not ids:
        return None
    parsed = [part.strip() for part in ids.split(",") if part.strip()]
    if len(parsed) > MAX_IDS:
        raise HTTPException(status_code=422, detail=f"Too many ids (max {MAX_IDS}).")
    return parsed or None


def _validate_range(date_from: dt.date | None, date_to: dt.date | None) -> None:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="'from' must be on or before 'to'.")


def _period_label(date_from: dt.date | None, date_to: dt.date | None) -> str:
    if date_from and date_to:
        return f"Period: {date_from.strftime('%d %b %Y')} - {date_to.strftime('%d %b %Y')}"
    if date_from:
        return f"Period: from {date_from.strftime('%d %b %Y')}"
    if date_to:
        return f"Period: until {date_to.strftime('%d %b %Y')}"
    return "Period: all time"


@router.get("/export/csv")
async def export_csv(
    status: str | None = Query(None, description="Filter by invoice status (e.g. auto_approved, reviewed)"),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    folder_id: str | None = None,
    ids: str | None = None,
    user=Depends(get_current_user),
):
    """Generate a CSV download for Tally/Zoho import (this account only)."""
    _validate_range(date_from, date_to)
    csv_content = build_csv(
        status_filter=status, user_id=user["id"],
        date_from=date_from, date_to=date_to,
        folder_id=folder_id, ids=_parse_ids(ids),
    )
    filename = f"invoxa_export_{status or 'all'}.csv"
    return StreamingResponse(
        iter([csv_content]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/xlsx")
async def export_xlsx(
    status: str | None = Query(None),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    folder_id: str | None = None,
    ids: str | None = None,
    user=Depends(get_current_user),
):
    """Generate an Excel download for Zoho Books / Excel import."""
    _validate_range(date_from, date_to)
    xlsx_bytes = build_xlsx(
        status_filter=status, user_id=user["id"],
        date_from=date_from, date_to=date_to,
        folder_id=folder_id, ids=_parse_ids(ids),
    )
    filename = f"invoxa_export_{status or 'all'}.xlsx"
    return StreamingResponse(
        iter([xlsx_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/tally-xml")
async def export_tally_xml(
    status: str | None = Query(None),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    folder_id: str | None = None,
    ids: str | None = None,
    user=Depends(get_current_user),
):
    """Generate a Tally Prime XML voucher import (Gateway of Tally > Import)."""
    _validate_range(date_from, date_to)
    xml_content = build_tally_xml(
        status_filter=status, user_id=user["id"],
        date_from=date_from, date_to=date_to,
        folder_id=folder_id, ids=_parse_ids(ids),
    )
    filename = f"invoxa_tally_{status or 'all'}.xml"
    return StreamingResponse(
        iter([xml_content]),
        media_type="application/xml",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/pdf")
async def export_pdf(
    status: str | None = Query(None),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    folder_id: str | None = None,
    ids: str | None = None,
    user=Depends(get_current_user),
):
    """Generate a printable A4 statement PDF (this account only)."""
    _validate_range(date_from, date_to)
    rows = fetch_export_rows(
        user["id"],
        status_filter=status,
        date_from=date_from, date_to=date_to,
        folder_id=folder_id, ids=_parse_ids(ids),
    )
    pdf_bytes = build_pdf_statement(
        rows,
        period_label=_period_label(date_from, date_to),
        owner_email=user.get("email") or "",
    )
    filename = f"invoxa_statement_{date_from or 'all'}_{date_to or 'all'}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/export/preview")
async def export_preview(
    status: str | None = Query(None),
    date_from: dt.date | None = Query(None, alias="from"),
    date_to: dt.date | None = Query(None, alias="to"),
    folder_id: str | None = None,
    ids: str | None = None,
    user=Depends(get_current_user),
):
    """Return a JSON preview (rows, count, total) the exports would emit."""
    _validate_range(date_from, date_to)
    rows = preview_csv_rows(
        status_filter=status, user_id=user["id"],
        date_from=date_from, date_to=date_to,
        folder_id=folder_id, ids=_parse_ids(ids),
    )
    total = 0.0
    for row in rows:
        try:
            total += float(row.get("total_amount") or 0)
        except (TypeError, ValueError):
            continue
    return {
        "rows": rows,
        "count": len(rows),
        "total": round(total, 2),
    }
