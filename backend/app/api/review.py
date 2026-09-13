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
    backfill_review_queue,
    get_review_item_invoice_id,
    get_review_item_owner,
    get_review_queue,
    resolve_review_item,
    update_invoice_status,
)
from app.models.invoice import InvoiceStatus
from app.review.corrections import (
    apply_correction_to_invoice,
    log_correction,
    normalize_value,
)

router = APIRouter(prefix="/api")


def _assert_same_account(review_id: str, user: dict) -> None:
    """Reviews may only touch invoices from the reviewer's own account."""
    owner = get_review_item_owner(review_id)
    if owner is None:
        return  # legacy row without an owner
    if owner != user["id"]:
        raise HTTPException(status_code=403, detail="Not your invoice")


def _sync_invoice_status(review_id: str, approved: bool) -> None:
    """Keep the invoice row in sync with the review decision.

    Approved -> the invoice is 'reviewed' everywhere (dashboard, digest,
    exports). Rejected -> it stays 'flagged' so it keeps asking for
    attention on the dashboard.
    """
    invoice_id = get_review_item_invoice_id(review_id)
    if invoice_id:
        update_invoice_status(
            invoice_id,
            InvoiceStatus.REVIEWED if approved else InvoiceStatus.FLAGGED,
        )


@router.get("/review/queue")
async def review_queue(user=Depends(get_current_user)):
    """List this account's invoices flagged for review.

    Self-healing: flagged invoices that somehow lost their pending
    queue entry (e.g. resolved before status syncing existed) are
    re-enqueued first, so the queue always matches the dashboard's
    "needs review" count.
    """
    backfill_review_queue(user["id"])
    return get_review_queue(user["id"])


@router.post("/review/{review_id}/resolve")
async def resolve_review(review_id: str, approved: bool, user=Depends(get_current_user)):
    """Mark a review item as approved or rejected.

    Any logged-in user can review their own account's invoices: one user
    may both upload and approve.
    """
    _assert_same_account(review_id, user)
    resolve_review_item(review_id, approved, reviewed_by=user["id"])
    _sync_invoice_status(review_id, approved)
    return {"status": "resolved", "approved": approved}


class CorrectionItem(BaseModel):
    field_name: str
    new_value: str


class ReviewCorrectionRequest(BaseModel):
    """One or more field corrections in a single save.

    ``corrections`` is the batch form used by the correction sheet.
    The flat ``field_name``/``new_value`` pair is the legacy single-field
    form and is still accepted so older clients keep working.
    """

    field_name: str | None = None
    new_value: str | None = None
    corrections: list[CorrectionItem] | None = None


@router.post("/review/{review_id}/correct")
async def correct_and_resolve(
    review_id: str, payload: ReviewCorrectionRequest, user=Depends(get_current_user)
):
    """
    Submit human corrections for any number of fields of the flagged
    invoice, persist them to the corrections table, and mark the review
    item approved. Every value is normalized server-side (amounts and
    dates) before anything is written.
    """
    _assert_same_account(review_id, user)

    items = list(payload.corrections or [])
    if not items and payload.field_name is not None:
        items = [
            CorrectionItem(
                field_name=payload.field_name, new_value=payload.new_value or ""
            )
        ]
    if not items:
        raise HTTPException(status_code=400, detail="No corrections supplied.")

    # Normalize + validate everything BEFORE writing anything, so an
    # invalid value can never leave a half-applied batch behind.
    try:
        normalized = [
            CorrectionItem(
                field_name=item.field_name,
                new_value=normalize_value(item.field_name, item.new_value),
            )
            for item in items
        ]
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        applied: list[dict] = []
        for item in normalized:
            correction = log_correction(
                review_id=review_id,
                field_name=item.field_name,
                new_value=item.new_value,
            )
            apply_correction_to_invoice(correction)
            applied.append(correction.model_dump())
        resolve_review_item(review_id, approved=True, reviewed_by=user["id"])
        _sync_invoice_status(review_id, approved=True)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result: dict = {"status": "reviewed", "corrections": applied}
    if len(applied) == 1:
        # Legacy single-field response shape.
        result["correction"] = applied[0]
    return result
