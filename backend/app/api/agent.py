"""
Agent API endpoints.

POST /api/agent/ask              - natural-language question -> bounded tool-use answer
POST /api/agent/payment-chase    - draft (never send) WhatsApp payment reminders
POST /api/agent/explain/{invoice_id} - plain-English explanation of a flag

Both are authenticated, account-scoped, and rate limited. Neither can
mutate data: the agent layer is read-only by construction.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.agent.chase import draft_payment_chase
from app.agent.explain import explain_flag
from app.agent.loop import ask_invoxa
from app.auth.dependencies import get_current_user
from app.database import get_invoice
from app.ratelimit import check_rate_limit

router = APIRouter(prefix="/api")


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


@router.post("/agent/ask")
async def ask(payload: AskRequest, user=Depends(get_current_user)):
    """Answer one question about the account's invoice data."""
    check_rate_limit("agent", user["id"])
    return ask_invoxa(user["id"], payload.question)


@router.post("/agent/payment-chase")
async def payment_chase(user=Depends(get_current_user)):
    """Draft (never send) WhatsApp payment reminders for due/overdue invoices."""
    check_rate_limit("agent", user["id"])
    return draft_payment_chase(user["id"])


@router.post("/agent/explain/{invoice_id}")
async def explain(invoice_id: str, user=Depends(get_current_user)):
    """Explain why an owned invoice is flagged for review."""
    check_rate_limit("agent", user["id"])
    invoice = get_invoice(invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if invoice.get("created_by") and invoice["created_by"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your invoice")
    explanation = explain_flag(user["id"], invoice_id)
    return {"invoice_id": invoice_id, "explanation": explanation}
