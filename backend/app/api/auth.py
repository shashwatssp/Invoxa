"""Auth API endpoints: signup, login, me."""
from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field

from app.auth.dependencies import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.database import create_user, get_user_by_email

router = APIRouter(prefix="/api/auth")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str | None = Field(default=None, max_length=120)
    role: str = Field(default="member", pattern="^(member|approver)$")


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


def _token_response(user_row: dict) -> dict:
    token = create_access_token(user_row["id"], user_row.get("role", "member"))
    return {"token": token, "user": user_row}


@router.post("/signup", status_code=201)
async def signup(payload: SignupRequest):
    """Create an account and return a token immediately."""
    email = payload.email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")

    if get_user_by_email(email):
        raise HTTPException(
            status_code=409, detail="An account with this email already exists. Try logging in."
        )

    user = create_user(
        email=email,
        password_hash=hash_password(payload.password),
        name=(payload.name or "").strip() or None,
        role=payload.role,
    )
    return _token_response(user)


@router.post("/login")
async def login(payload: LoginRequest):
    """Verify credentials and return a token."""
    email = payload.email.strip().lower()
    row = get_user_by_email(email)
    if not row or not verify_password(payload.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    row.pop("password_hash", None)
    return _token_response(row)


@router.get("/me")
async def me(user=Depends(get_current_user)):
    """Return the currently authenticated user."""
    return user
