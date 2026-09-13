"""
Reports API endpoints.

GET /api/reports/monthly-spend - Total invoiced amount per month
(oldest first, zeros filled) for the account.
"""
from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.database import monthly_spend

router = APIRouter(prefix="/api")


@router.get("/reports/monthly-spend")
async def reports_monthly_spend(
    months: int = Query(6, ge=1, le=24), user=Depends(get_current_user)
):
    """Monthly spend trend for the dashboard chart."""
    return monthly_spend(user["id"], months=months)
