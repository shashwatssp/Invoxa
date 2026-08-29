"""
Review queue API endpoints.

GET  /api/review/queue               - All pending review items
POST /api/review/{review_id}/resolve - Approve or reject a review item
POST /api/review/{review_id}/correct - Log a correction and resolve the item
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.database import get_review_queue, resolve_review_item
from app.review.corrections import apply_correction_to_invoice, log_correction

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


class ReviewCorrectionRequest(BaseModel):
    field_name: str
    new_value: str


@router.post("/review/{review_id}/correct")
async def correct_and_resolve(review_id: str, payload: ReviewCorrectionRequest):
    """
    Submit a human correction for one field of the flagged invoice,
    persist it to the corrections table, and mark the review item approved.
    """
    try:
        correction = log_correction(
            review_id=review_id,
            field_name=payload.field_name,
            new_value=payload.new_value,
        )
        apply_correction_to_invoice(correction)
        resolve_review_item(review_id, approved=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "reviewed", "correction": correction.model_dump()}
