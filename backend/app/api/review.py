"""
Review queue API endpoints.
"""
from fastapi import APIRouter

from app.database import get_review_queue, resolve_review_item

router = APIRouter(prefix="/api")


@router.get("/review/queue")
async def review_queue():
    """List all invoices flagged for review."""
    return get_review_queue()


@router.post("/review/{review_id}/resolve")
async def resolve_review(review_id: str, approved: bool):
    """Mark a review item as approved or rejected."""
    resolve_review_item(review_id, approved)
    return {"status": "resolved", "approved": approved}
