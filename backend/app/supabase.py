"""
Supabase client wrapper.

Uses SERVICE_KEY for all server-side operations.  Imports the underlying
``supabase`` package lazily so that test environments without the package
installed can still exercise modules that only need to talk to the client
through dependency injection (e.g. ``app.review.corrections`` tests).
"""
from __future__ import annotations

import contextlib
import uuid
from typing import Any


def _create_supabase_client():
    """Lazy loader for ``supabase.create_client``.

    Imports happen inside the helper so that simply importing this module -
    or any module that imports it - does not require the ``supabase``
    package to be installed.
    """
    from supabase import create_client as _create_client

    from app.config import (
        SUPABASE_SERVICE_KEY,
        SUPABASE_URL,
    )
    return _create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


def get_supabase() -> Any:
    """Create and return a Supabase client with service key."""
    return _create_supabase_client()


# Module-level singleton for reuse
_supabase_client: Any = None


def get_client() -> Any:
    """Get or create the singleton Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase()
    return _supabase_client


def close_client() -> None:
    """Clear the singleton client (called on shutdown)."""
    global _supabase_client
    if _supabase_client is not None:
        with contextlib.suppress(Exception):  # swallow shutdown errors
            _supabase_client.auth.sign_out()
        _supabase_client = None


# Storage bucket
INVOICE_BUCKET = "invoices"


def _ensure_bucket(client: Any) -> None:
    """Create the invoice bucket if it does not exist (idempotent)."""
    try:
        buckets = client.storage.list_buckets()
        if not any(b.get("name") == INVOICE_BUCKET for b in (buckets or [])):
            client.storage.create_bucket(INVOICE_BUCKET)
    except Exception:
        # A failure here should not block invoice creation; upload errors
        # surface with a clear 502 from the API layer.
        pass


def upload_invoice(file_bytes: bytes, file_name: str) -> str:
    """Upload an invoice file to Supabase Storage. Returns the storage path.

    The object name is prefixed with a UUID so concurrent uploads of the same
    file name never collide (Storage returns 409 on overwrite attempts).
    """
    client = get_client()
    path = f"raw/{uuid.uuid4().hex}-{file_name}"
    try:
        client.storage.from_(INVOICE_BUCKET).upload(path, file_bytes)
    except Exception:
        # Most common cause on a fresh project: the bucket does not exist yet.
        _ensure_bucket(client)
        client.storage.from_(INVOICE_BUCKET).upload(path, file_bytes)
    return path


def download_invoice(storage_path: str) -> bytes:
    """Download an invoice file from Supabase Storage."""
    client = get_client()
    return client.storage.from_(INVOICE_BUCKET).download(storage_path)


def delete_invoice_file(storage_path: str) -> None:
    """Best-effort delete of the receipt file from Storage.

    A storage failure never blocks the invoice row deletion - the
    dashboard must stay consistent even if the object lingers.
    """
    client = get_client()
    with contextlib.suppress(Exception):
        client.storage.from_(INVOICE_BUCKET).remove([storage_path])
