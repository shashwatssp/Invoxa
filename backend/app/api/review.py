"""
Review queue API endpoints.

GET  /api/review/queue               - All pending review items
POST /api/review/{review_id}/resolve - Approve or reject a review item
POST /api/review/{review_id}/correct - Log a correction and resolve the item
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.dependencies import get_current_user
from app.database import (
    get_review_item_owner,
    get_review_queue,
    resolve_review_item,
)
from app.review.corrections import apply_correction_to_invoice, log_correction

router = APIRouter(prefix="/api")


def _assert_same_account(review_id: str, user: dict) -> None:
    """Reviews may only touch invoices from the reviewer's own account."""
    owner = get_review_item_owner(review_id)
    if owner is None:
        return  # legacy row without an owner
    if owner != user["id"]:
        raise HTTPException(status_code=403, detail="Not your invoice")


@router.get("/review/queue")
async def review_queue(user=Depends(get_current_user)):
    """List this account's invoices flagged for review."""
    return get_review_queue(user["id"])


@router.post("/review/{review_id}/resolve")
async def resolve_review(review_id: str, approved: bool, user=Depends(get_current_user)):
    """Mark a review item as approved or rejected.

    Any logged-in user can review their own account's invoices: one user
    may both upload and approve.
    """
    _assert_same_account(review_id, user)
    resolve_review_item(review_id, approved, reviewed_by=user["id"])
    return {"status": "resolved", "approved": approved}


class ReviewCorrectionRequest(BaseModel):
    field_name: str
    new_value: str


@router.post("/review/{review_id}/correct")
async def correct_and_resolve(
    review_id: str, payload: ReviewCorrectionRequest, user=Depends(get_current_user)
):
    """
    Submit a human correction for one field of the flagged invoice,
    persist it to the corrections table, and mark the review item approved.
    """
    _assert_same_account(review_id, user)
    try:
        correction = log_correction(
            review_id=review_id,
            field_name=payload.field_name,
            new_value=payload.new_value,
        )
        apply_correction_to_invoice(correction)
        resolve_review_item(review_id, approved=True, reviewed_by=user["id"])
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {"status": "reviewed", "correction": correction.model_dump()}
