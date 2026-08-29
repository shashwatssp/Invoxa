"""
Weekly digest API endpoints.

GET /api/digest              - Plain-English weekly summary (current 7-day window)
GET /api/digest?days=N       - Summary for the last N days
"""
from fastapi import APIRouter, Query

from app.digest.generator import generate_digest

router = APIRouter(prefix="/api")


@router.get("/digest")
async def weekly_digest(days: int = Query(7, ge=1, le=90, description="Window size in days")):
    """Generate plain-English weekly summary."""
    digest = generate_digest(window_days=days)
    return digest.to_dict()
