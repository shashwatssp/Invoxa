"""
Account API endpoints.

GET /api/account/export - Everything in the account (profile, invoices,
folders, review queue) as a downloadable JSON file. User-initiated data
ownership export.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from app.auth.dependencies import get_current_user
from app.database import export_account_data

router = APIRouter(prefix="/api")


@router.get("/account/export")
async def account_export(user=Depends(get_current_user)):
    """Download everything in this account as one JSON file."""
    payload = export_account_data(user["id"])
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": "attachment; filename=invoxa_account_export.json"},
    )
