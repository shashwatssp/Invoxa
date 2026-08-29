"""
Correction logging helpers for the review queue.

Sprint #9 will own the full implementation: lookup by review_id, persist to the
``corrections`` table, then apply the corrected value onto the invoice and
recompute confidence.  For Sprint #6 we expose the minimum required types and
functions so ``app.api.review`` imports cleanly.
"""
from __future__ import annotations

from typing import Any

from app.models.invoice import Correction
from app.supabase import get_client


def log_correction(
    review_id: str,
    field_name: str,
    new_value: str,
) -> Correction:
    """
    Append a row to the ``corrections`` table for the invoice referenced by
    ``review_id``.  Returns the persisted Correction model.

    Sprint #6 raises NotImplementedError - the full happy path ships in
    Sprint #9 once the review-resolution flow is wired up.
    """
    raise NotImplementedError(
        "Correction logging ships in Sprint #9. Track via development_plan.md."
    )


def apply_correction_to_invoice(correction: Correction) -> dict[str, Any]:
    """
    Propagate a correction onto the originating extraction_fields row and the
    invoice.  Sprint #6 leaves this as a stub returning the untouched client
    reference; Sprint #9 will expand it.
    """
    return get_client()
