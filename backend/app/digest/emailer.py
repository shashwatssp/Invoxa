"""
Email the weekly digest via plain SMTP.

stdlib ``smtplib`` only — no new dependencies, no paid email API. Works
with a Gmail app password (SMTP_HOST=smtp.gmail.com, SMTP_PORT=465) or
any standard SMTP server. When SMTP is not configured the sender
reports it instead of raising, so the endpoint stays safe to call.
"""

from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

from app.digest.generator import Digest, generate_digest

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 30


def _smtp_config() -> dict | None:
    host = os.getenv("SMTP_HOST", "")
    user = os.getenv("SMTP_USER", "")
    password = os.getenv("SMTP_PASSWORD", "")
    if not (host and user and password):
        return None
    try:
        port = int(os.getenv("SMTP_PORT", "465"))
    except ValueError:
        port = 465
    return {"host": host, "port": port, "user": user, "password": password}


def build_digest_email_text(digest: Digest) -> str:
    """Plain-text email body from the deterministic lines + AI narrative."""
    lines = [f"Invoxa digest — the last {digest.window_days} days", ""]
    lines.extend(digest.summary_lines)
    if digest.narrative:
        lines.extend(["", digest.narrative])
    return "\n".join(lines)


def send_digest_email(user_id: str, to_email: str, window_days: int = 7) -> dict:
    """Generate the account's digest and email it. Never raises."""
    config = _smtp_config()
    if not config:
        return {
            "sent": False,
            "reason": (
                "Email is not configured. Set SMTP_HOST, SMTP_USER and "
                "SMTP_PASSWORD (a Gmail app password works) to enable this."
            ),
        }

    digest = generate_digest(window_days=window_days, user_id=user_id)

    message = EmailMessage()
    message["From"] = os.getenv("DIGEST_FROM") or config["user"]
    message["To"] = to_email
    message["Subject"] = f"Invoxa digest — the last {digest.window_days} days"
    message.set_content(build_digest_email_text(digest))

    try:
        if config["port"] == 465:
            with smtplib.SMTP_SSL(config["host"], config["port"], timeout=_TIMEOUT_SECONDS) as smtp:
                smtp.login(config["user"], config["password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(config["host"], config["port"], timeout=_TIMEOUT_SECONDS) as smtp:
                smtp.starttls()
                smtp.login(config["user"], config["password"])
                smtp.send_message(message)
    except Exception:
        logger.warning("Digest email to %s failed", to_email, exc_info=True)
        return {"sent": False, "reason": "The email could not be sent. Check the SMTP settings."}

    return {"sent": True, "digest": digest.to_dict()}
