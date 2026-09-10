"""Vercel Python serverless entrypoint for the Invoxa API.

Vercel's Python runtime treats ``api/index.py`` as the catch-all function
and serves the FastAPI ASGI ``app`` directly. All routers already live
under the ``/api`` prefix, which matches the project-level rewrite that
routes ``/api/*`` to this service.
"""
import sys
from pathlib import Path

# Make the ``app`` package (project root = backend/) importable from api/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app

__all__ = ["app"]
