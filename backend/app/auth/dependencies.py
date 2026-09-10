"""Request-level auth guards for FastAPI routes."""
from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request

from app.auth.security import decode_access_token
from app.database import get_user_by_id


def _bearer_token(request: Request) -> str | None:
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        token = auth.removeprefix("Bearer ").strip()
        return token or None
    return None


def get_current_user(request: Request) -> dict[str, Any]:
    """Resolve the requesting user from the Bearer token.

    Raises 401 when the token is missing/invalid or the user no longer exists.
    """
    token = _bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Session expired or invalid. Please log in again.")

    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="Account no longer exists.")
    return user


