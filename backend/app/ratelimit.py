"""
In-memory sliding-window rate limiter for AI-costly endpoints.

Uploads and re-extractions can each spend Gemini free-tier quota
(~250 requests/day), so runaway frontend loops or accidental retries
must be stopped before they reach the pipeline. Buckets are keyed by
account id (single-account product). On Vercel's serverless runtime
each instance keeps its own counters — this is a soft guard against
abuse and bugs, not a global accounting system. Limits are configurable
per bucket via ``RATE_LIMIT_<BUCKET>_PER_HOUR`` (default 60/hour).
"""

from __future__ import annotations

import logging
import os
import threading
import time
from collections import deque

from fastapi import HTTPException

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 3600
_buckets: dict[tuple[str, str], deque[float]] = {}
_lock = threading.Lock()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "")
    try:
        return max(1, int(raw))
    except ValueError:
        return default


def _limit_for(bucket: str) -> int:
    return _env_int(f"RATE_LIMIT_{bucket.upper()}_PER_HOUR", 60)


def _prune_stale(window_start: float) -> None:
    """Drop buckets with no recent hits so the dict cannot grow unbounded."""
    if len(_buckets) < 1024:
        return
    stale = [
        key
        for key, hits in _buckets.items()
        if not hits or hits[-1] <= window_start
    ]
    for key in stale:
        del _buckets[key]


def check_rate_limit(bucket: str, key: str, *, now: float | None = None) -> None:
    """Record one hit for ``(bucket, key)`` or raise HTTP 429."""
    timestamp = time.time() if now is None else now
    limit = _limit_for(bucket)
    window_start = timestamp - _WINDOW_SECONDS
    with _lock:
        hits = _buckets.setdefault((bucket, key), deque())
        while hits and hits[0] <= window_start:
            hits.popleft()
        if len(hits) >= limit:
            logger.warning(
                "Rate limit exceeded: bucket=%s limit=%d/hour", bucket, limit
            )
            raise HTTPException(
                status_code=429,
                detail="Too many requests. Please try again in a little while.",
            )
        hits.append(timestamp)
        _prune_stale(window_start)
