"""
Weekly digest API endpoints.

GET  /api/digest              - Plain-English weekly summary (current 7-day window)
GET  /api/digest?days=N       - Summary for the last N days
POST /api/digest/email        - Email the digest (SMTP configured server-side)
"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import get_current_user
from app.digest.emailer import send_digest_email
from app.digest.generator import generate_digest
from app.ratelimit import check_rate_limit

router = APIRouter(prefix="/api")


class DigestEmailRequest(BaseModel):
    to_email: EmailStr
    days: int = Field(7, ge=1, le=90)


@router.get("/digest")
async def weekly_digest(
    days: int = Query(7, ge=1, le=90, description="Window size in days"),
    user=Depends(get_current_user),
):
    """Generate a plain-English weekly summary for this account."""
    digest = generate_digest(window_days=days, user_id=user["id"])
    return digest.to_dict()


@router.post("/digest/email")
async def email_digest(payload: DigestEmailRequest, user=Depends(get_current_user)):
    """Email the account's digest via server-side SMTP (rate limited)."""
    check_rate_limit("email", user["id"])
    return send_digest_email(user["id"], payload.to_email, payload.days)
