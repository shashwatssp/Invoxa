"""
Weekly digest generation.

Sprint #11 will implement the real plain-English digest (totals per vendor,
anomalies flagged, due-soon invoices, etc.).  For Sprint #6 we expose a tiny
``Digest`` dataclass and a ``generate_digest`` function so the API endpoint
can compile and surface a useful JSON shape from day one.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any


@dataclass
class Digest:
    """Plain-English weekly summary."""
    window_days: int = 7
    generated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat(timespec="seconds"))
    invoices_processed: int = 0
    auto_approved: int = 0
    flagged_for_review: int = 0
    total_amount: float = 0.0
    summary_lines: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def generate_digest(window_days: int = 7) -> Digest:
    """
    Build a digest for the requested window.  Sprint #11 will replace this
    body with real aggregation queries; Sprint #6 keeps it deterministic so
    the API contract is stable.
    """
    digest = Digest(window_days=window_days)
    digest.summary_lines.append(
        f"Digest generator placeholder. Detailed stats will populate after Sprint #11."
    )
    return digest
