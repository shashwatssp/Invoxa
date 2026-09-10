"""
Environment configuration loader.
Never logs secrets. Loads from .env at repo root.
"""
import os
import secrets
from pathlib import Path

# Load .env from repo root (two levels up from this file)
_ENV_PATH = Path(__file__).resolve().parent.parent.parent / ".env"

if _ENV_PATH.exists():
    from dotenv import load_dotenv
    load_dotenv(_ENV_PATH)


def get_required(name: str) -> str:
    """Get a required environment variable or raise."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def get_optional(name: str, default: str = "") -> str:
    """Get an optional environment variable with a default."""
    return os.getenv(name, default)


# --- Supabase ---
SUPABASE_URL = get_required("SUPABASE_URL")
SUPABASE_PUBLISHABLE_KEY = get_required("SUPABASE_PUBLISHABLE_KEY")
SUPABASE_SERVICE_KEY = get_required("SUPABASE_SERVICE_KEY")
SUPABASE_JWKS_URL = get_optional("SUPABASE_JWKS_URL")

# --- Gemini (fallback only) ---
GEMINI_API_KEY = get_optional("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"
CONFIDENCE_THRESHOLD = 0.7  # fall back to Gemini below this

# --- App ---
APP_NAME = "Invoxa"
DEBUG = os.getenv("DEBUG", "false").lower() == "true"


def _jwt_secret() -> str:
    """Resolve the JWT signing secret.

    Priority: SECRET_KEY env var > persisted .jwt_secret file (created once
    on first run so tokens survive restarts) > ephemeral random key.
    """
    env_value = os.getenv("SECRET_KEY")
    if env_value:
        return env_value
    key_file = _ENV_PATH.parent / ".jwt_secret"
    try:
        if key_file.exists():
            stored = key_file.read_text().strip()
            if stored:
                return stored
        key = secrets.token_hex(32)
        key_file.write_text(key)
        return key
    except OSError:
        # Read-only FS etc.: fall back to an ephemeral key.
        return secrets.token_hex(32)


SECRET_KEY = _jwt_secret()
TOKEN_EXPIRE_HOURS = int(get_optional("TOKEN_EXPIRE_HOURS", "24") or 24)
