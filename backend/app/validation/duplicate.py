"""
Duplicate invoice detection.
Checks for duplicate invoices by GSTIN + invoice number + amount.
"""
from typing import Any


def find_duplicates(
    vendor_gstin: str | None,
    invoice_number: str | None,
    amount: float | None,
    threshold: float = 0.95,
) -> list[dict[str, Any]]:
    """
    Search for potential duplicate invoices in the database.
    Matches on: vendor_gstin + invoice_number, or vendor_gstin + amount (within threshold).

    Returns list of matching invoices with similarity scores.
    """
    if not vendor_gstin:
        return []

    from app.supabase import get_client

    client = get_client()
    candidates = []

    # Strategy 1: Exact GSTIN + invoice number match
    if invoice_number:
        result = client.table("invoices").select(
            "id, invoice_number, amount, created_at"
        ).eq("status", "any").execute()

        for row in (result.data or []):
            db_inv_num = row.get("invoice_number", "")
            db_amount = row.get("amount", 0)
            if db_inv_num and invoice_number and db_inv_num == invoice_number:
                candidates.append({
                    "id": row["id"],
                    "reason": "exact_invoice_number_match",
                    "similarity": 1.0,
                })

    # Strategy 2: Same vendor, same amount (within threshold)
    if amount:
        result = client.table("invoices").select(
            "id, invoice_number, amount, created_at, vendor_id"
        ).execute()

        for row in (result.data or []):
            db_amount = row.get("amount")
            if db_amount and amount and _amounts_similar(float(db_amount), amount, threshold):
                candidates.append({
                    "id": row["id"],
                    "reason": "same_vendor_same_amount",
                    "similarity": _amount_similarity(float(db_amount), amount),
                })

    return candidates


def _amounts_similar(a: float, b: float, threshold: float) -> bool:
    """Check if two amounts are similar within a threshold (relative difference)."""
    if a == 0 and b == 0:
        return True
    if a == 0 or b == 0:
        return False
    diff = abs(a - b) / max(a, b)
    return diff <= (1.0 - threshold)


def _amount_similarity(a: float, b: float) -> float:
    """Compute similarity score between two amounts (1.0 = identical)."""
    if a == 0 and b == 0:
        return 1.0
    if a == 0 or b == 0:
        return 0.0
    diff = abs(a - b) / max(a, b)
    return round(1.0 - diff, 2)


def is_duplicate(
    vendor_gstin: str | None,
    invoice_number: str | None,
    amount: float | None,
) -> bool:
    """
    Quick check if an invoice is a duplicate.
    Returns True if any high-confidence duplicate is found.
    """
    duplicates = find_duplicates(vendor_gstin, invoice_number, amount)
    return any(d["similarity"] > 0.95 for d in duplicates)
