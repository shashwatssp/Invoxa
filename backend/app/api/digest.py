"""
Weekly digest API endpoint.

GET  /api/digest              - Plain-English weekly summary (current 7-day window)
GET  /api/digest?days=N       - Summary for the last N days

Emailing is deliberately client-side: the Account page opens the user's
email app (e.g. Gmail) via a ``mailto:`` link with the digest prefilled,
so there is no SMTP configuration to maintain anywhere.
"""
from fastapi import APIRouter, Depends, Query

from app.auth.dependencies import get_current_user
from app.digest.generator import generate_digest

router = APIRouter(prefix="/api")


@router.get("/digest")
async def weekly_digest(
    days: int = Query(7, ge=1, le=90, description="Window size in days"),
    user=Depends(get_current_user),
):
    """Generate a plain-English weekly summary for this account."""
    digest = generate_digest(window_days=days, user_id=user["id"])
    return digest.to_dict()
