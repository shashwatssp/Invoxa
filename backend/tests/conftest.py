"""
Shared fixtures.

The repo-root .env may carry a real GEMINI_API_KEY; tests must never
call the live API. An autouse fixture neutralizes every AI entry point
so suites stay fast, offline, and deterministic. Individual tests that
specifically exercise AI behavior re-patch these with their own fakes.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_ai_network(monkeypatch):
    import app.api.invoices as inv_api
    import app.digest.generator as digest_gen

    monkeypatch.setattr(inv_api, "ai_category", lambda *a, **k: None)
    monkeypatch.setattr(digest_gen, "ai_narrative", lambda *a, **k: None)
    yield
