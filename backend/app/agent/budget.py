"""
Daily Gemini call accounting + append-only agent audit trail.

Both live in tables created by ``migrations/0007_agent_audit.sql``.
Every function
here is best-effort: if the tables are missing or the database is
briefly unavailable, the agent degrades to its per-run caps only —
the rest of the product is never blocked — and the miss is logged.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from typing import Any

from app.digest.generator import IST
from app.supabase import get_client

logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


def daily_limit() -> int:
    """Gemini calls per day the agent layer may spend (free-tier headroom)."""
    return _env_int("AGENT_DAILY_GEMINI_CALLS", 240)


def _today_ist() -> str:
    return dt.datetime.now(IST).date().isoformat()


def calls_today() -> int:
    """Model calls already spent today (0 when accounting is unavailable)."""
    try:
        result = (
            get_client()
            .table("gemini_usage")
            .select("calls")
            .eq("day", _today_ist())
            .limit(1)
            .execute()
        )
        return int(result.data[0]["calls"]) if result.data else 0
    except Exception:
        logger.warning("Gemini usage lookup failed; assuming 0 used", exc_info=True)
        return 0


def remaining_today() -> int:
    return max(0, daily_limit() - calls_today())


def log_agent_event(user_id: str, event: str, detail: dict[str, Any] | None = None) -> None:
    """Append one audit row. Silent best-effort: never raises."""
    try:
        get_client().table("agent_audit").insert(
            {"user_id": user_id, "event": event, "detail": detail or {}}
        ).execute()
    except Exception:
        logger.warning("Agent audit write failed for event=%s", event, exc_info=True)


def record_model_calls(count: int, user_id: str, event: str) -> None:
    """Add ``count`` model calls to today's usage and audit the event."""
    try:
        spent = calls_today()
        get_client().table("gemini_usage").upsert(
            {
                "day": _today_ist(),
                "calls": spent + count,
                "updated_at": dt.datetime.now(dt.UTC)
                .replace(tzinfo=None)
                .isoformat(timespec="seconds"),
            }
        ).execute()
    except Exception:
        logger.warning("Gemini usage update failed", exc_info=True)
    log_agent_event(user_id, event, {"model_calls": count})
