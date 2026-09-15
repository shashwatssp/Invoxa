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

    import app.agent.budget as agent_budget
    import app.agent.chase as agent_chase
    import app.agent.explain as agent_explain
    import app.agent.loop as agent_loop

    # Agent entry points stay offline unless a test brings its own fake.
    monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "")
    monkeypatch.setattr(agent_explain, "GEMINI_API_KEY", "")
    monkeypatch.setattr(agent_chase, "GEMINI_API_KEY", "")
    # Budget accounting never touches the database in tests.
    monkeypatch.setattr(agent_budget, "calls_today", lambda: 0)
    monkeypatch.setattr(agent_budget, "log_agent_event", lambda *a, **k: None)
    monkeypatch.setattr(agent_budget, "record_model_calls", lambda *a, **k: None)

    # Correction-hint lookup in the Gemini fallback stays offline too.
    import app.extraction.gemini_fallback as gemini_fb

    monkeypatch.setattr(gemini_fb, "get_recent_corrections", lambda *a, **k: [])
    yield
