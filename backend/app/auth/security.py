"""Password hashing and JWT token helpers.

- Passwords: PBKDF2-HMAC-SHA256 with a per-user random salt, 390k iterations
  (OWASP-recommended ballpark). Stored as ``pbkdf2_sha256$iterations$salt$hash``.
- Tokens: HS256 JWTs signed with SECRET_KEY, carrying ``sub`` (user id),
  ``role`` and ``exp``.
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Any

import jwt

from app.config import SECRET_KEY, TOKEN_EXPIRE_HOURS

_ITERATIONS = 390_000


def hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    """Constant-time verification of a password against a stored hash."""
    try:
        scheme, iterations, salt, digest = stored.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(candidate, digest)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: str, role: str) -> str:
    """Issue a signed JWT for a user."""
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": user_id,
        "role": role,
        "iat": now,
        "exp": now + TOKEN_EXPIRE_HOURS * 3600,
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT. Returns the payload or None if invalid/expired."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
    except jwt.InvalidTokenError:
        return None
    return payload if payload.get("sub") else None
