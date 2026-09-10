from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    FLAGGED = "flagged"
    AUTO_APPROVED = "auto_approved"
    REVIEWED = "reviewed"
    EXPORTED = "exported"


class Vendor(BaseModel):
    id: str
    name: str
    gstin: str | None = None
    category: str | None = None
    created_at: datetime


class Invoice(BaseModel):
    id: str
    vendor_id: str | None = None
    invoice_number: str | None = None
    amount: float | None = None
    due_date: datetime | None = None
    status: InvoiceStatus = InvoiceStatus.PENDING
    storage_path: str
    created_at: datetime


class ExtractionField(BaseModel):
    id: str
    invoice_id: str
    field_name: str
    raw_value: str | None = None
    confidence: float | None = None
    created_at: datetime


class ExtractionResult(BaseModel):
    vendor_name: str | None = None
    vendor_gstin: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    amount: float | None = None
    tax_amount: float | None = None
    total_amount: float | None = None
    line_items: list[dict] | None = None
    confidence: float | None = None
    overall_confidence: float | None = None
    needs_review: bool = False
    review_reasons: list[str] = []
    raw_text: str | None = None


class Correction(BaseModel):
    invoice_id: str
    field_name: str
    old_value: str | None = None
    new_value: str
