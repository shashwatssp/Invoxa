"""
Application logging setup.

stdlib logging with a compact single-line format. Configured once at
import time in ``app.main``; modules use ``logging.getLogger(__name__)``.
Level is controlled by the ``LOG_LEVEL`` environment variable (default
INFO) so production can be turned up to DEBUG without a code change.
"""

from __future__ import annotations

import logging
import os

_CONFIGURED = False


def configure_logging() -> None:
    """Idempotently configure root logging for the app."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    # Keep noisy library loggers at WARNING even when the app is DEBUG.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    _CONFIGURED = True
