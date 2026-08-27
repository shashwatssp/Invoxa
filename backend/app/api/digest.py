"""
Weekly digest API endpoints.
"""
from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.get("/digest")
async def weekly_digest():
    """Generate plain-English weekly summary."""
    # Full implementation: Day 10
    return {"summary": "Weekly digest - implementation pending"}
