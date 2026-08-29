"""
Supabase client wrapper.

Uses SERVICE_KEY for all server-side operations.  Imports the underlying
``supabase`` package lazily so that test environments without the package
installed can still exercise modules that only need to talk to the client
through dependency injection (e.g. ``app.review.corrections`` tests).
"""
from __future__ import annotations

import contextlib
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


def upload_invoice(file_bytes: bytes, file_name: str) -> str:
    """Upload an invoice file to Supabase Storage. Returns the storage path."""
    client = get_client()
    path = f"raw/{file_name}"
    client.storage.from_(INVOICE_BUCKET).upload(path, file_bytes)
    return path


def download_invoice(storage_path: str) -> bytes:
    """Download an invoice file from Supabase Storage."""
    client = get_client()
    return client.storage.from_(INVOICE_BUCKET).download(storage_path)
