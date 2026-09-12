"""
Weekly digest generation.

``generate_digest`` queries the Supabase invoices table (service key),
aggregates by status within a rolling window, and produces a plain-English
summary: count of processed invoices, totals, anomalies that need a
human look, and the top vendors by spend.

API contract: ``GET /api/digest?days=N`` -> JSON dict (see ``to_dict``).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from app.database import get_invoices
from app.digest.narrative import ai_narrative


@dataclass
class Digest:
    """Plain-English weekly summary."""
    window_days: int = 7
    generated_at: str = field(
default_factory=lambda: datetime.now(UTC).replace(tzinfo=None).isoformat(timespec="seconds")
    )
    invoices_processed: int = 0
    auto_approved: int = 0
    flagged_for_review: int = 0
    exported: int = 0
    total_amount: float = 0.0
    top_vendors: list[dict[str, Any]] = field(default_factory=list)
    due_soon_days: int = 5
    due_soon: list[dict[str, Any]] = field(default_factory=list)
    summary_lines: list[str] = field(default_factory=list)
    # AI-written narrative; None when Gemini is unavailable so the UI
    # falls back to the deterministic summary_lines.
    narrative: str | None = None
    narrative_source: str = "template"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _iso_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _window_start(window_days: int) -> datetime:
    return _iso_now() - timedelta(days=window_days)


def _count_by_status(invoices: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for invoice in invoices:
        status = invoice.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
    return counts


def _parse_date(value: Any) -> datetime | None:
    """Parse a date that may arrive as ISO ``YYYY-MM-DD`` or ``DD/MM/YYYY``."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.strptime(value[:10].replace("-", ""), "%Y%m%d")
        except ValueError:
            try:
                return datetime.strptime(value.strip(), "%d/%m/%Y")
            except ValueError:
                return None
    return None


def _coerce_amount(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _top_vendors(invoices: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    totals: dict[str, float] = {}
    for invoice in invoices:
        name = (
            invoice.get("vendor_name")
            or invoice.get("vendor_id")
            or "(unknown)"
        )
        amount = _coerce_amount(invoice.get("amount"))
        totals[name] = totals.get(name, 0.0) + amount
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    return [{"vendor": name, "total_amount": amount} for name, amount in ranked]


def _due_soon(invoices: list[dict[str, Any]], days: int) -> list[dict[str, Any]]:
    """Return invoices whose ``due_date`` falls within ``days`` from now."""
    cutoff = _iso_now() + timedelta(days=days)
    soon: list[dict[str, Any]] = []
    for invoice in invoices:
        due = _parse_date(invoice.get("due_date"))
        if due is None:
            continue
        if due <= cutoff:
            soon.append(
                {
                    "invoice_number": invoice.get("invoice_number"),
                    "due_date": invoice.get("due_date"),
                    "amount": invoice.get("amount"),
                    "status": invoice.get("status"),
                }
            )
    return sorted(soon, key=lambda item: item["due_date"] or "")


def _build_summary_lines(digest: Digest) -> list[str]:
    lines: list[str] = []
    lines.append(
        f"Processed {digest.invoices_processed} invoices in the last "
        f"{digest.window_days} days, worth {digest.total_amount:,.2f} INR."
    )
    lines.append(
        f"{digest.auto_approved} auto-approved, "
        f"{digest.flagged_for_review} flagged for review."
    )
    if digest.flagged_for_review:
        lines.append("Flagged invoices need human review.")
    if digest.due_soon:
        upcoming = ", ".join(
            str(item.get("invoice_number") or item.get("due_date", ""))
            for item in digest.due_soon
        )
        lines.append(
            f"{len(digest.due_soon)} invoice(s) due within "
            f"{digest.due_soon_days} days: {upcoming}"
        )
    else:
        lines.append("No invoices due in the next few days.")
    if digest.top_vendors:
        top = digest.top_vendors[0]
        lines.append(
            f"Top vendor by spend: {top['vendor']} "
            f"({top['total_amount']:,.2f} INR)."
        )
    return lines


def generate_digest(window_days: int = 7, user_id: str | None = None) -> Digest:
    """Build a digest for the requested rolling window, scoped to one account."""
    start = _window_start(window_days)
    all_invoices = get_invoices(user_id)
    # Filter to invoices created within the window.
    recent: list[dict[str, Any]] = []
    for invoice in all_invoices:
        created = _parse_date(invoice.get("created_at"))
        if created is None or created >= start:
            recent.append(invoice)

    counts = _count_by_status(recent)
    digest = Digest(
        window_days=window_days,
        invoices_processed=len(recent),
        auto_approved=counts.get("auto_approved", 0),
        flagged_for_review=counts.get("flagged", 0),
        exported=counts.get("exported", 0),
        total_amount=sum(_coerce_amount(i.get("amount")) for i in recent),
        top_vendors=_top_vendors(recent),
        due_soon_days=5,
        due_soon=_due_soon(recent, 5),
        summary_lines=[],
    )
    digest.summary_lines = _build_summary_lines(digest)

    # Optional AI narrative: never fails the digest; when Gemini is
    # unavailable the template lines above are the whole story.
    try:
        narrative = ai_narrative(digest.to_dict(), recent)
    except Exception:  # narrative is a bonus, never a dependency
        narrative = None
    if narrative:
        digest.narrative = narrative
        digest.narrative_source = "gemini"
    return digest
