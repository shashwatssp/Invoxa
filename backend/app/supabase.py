"""
Supabase client wrapper.
Uses SERVICE_KEY for all server-side operations.
"""
from supabase import create_client, Client

from app.config import (
    SUPABASE_URL,
    SUPABASE_SERVICE_KEY,
)


def get_supabase() -> Client:
    """Create and return a Supabase client with service key."""
    return create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)


# Module-level singleton for reuse
_supabase_client: Client | None = None


def get_client() -> Client:
    """Get or create the singleton Supabase client."""
    global _supabase_client
    if _supabase_client is None:
        _supabase_client = get_supabase()
    return _supabase_client


def close_client() -> None:
    """Clear the singleton client (called on shutdown)."""
    global _supabase_client
    if _supabase_client is not None:
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
    # Extract filename from path
    file_name = storage_path.split("/")[-1]
    return client.storage.from_(INVOICE_BUCKET).download(storage_path).decode("utf-8") if False else client.storage.from_(INVOICE_BUCKET).download(storage_path)
