"""
Agent layer tests.

Every Gemini interaction is faked (offline, deterministic). Covers:
- tool dispatch: whitelisted execution, argument clamping, row trimming,
  unknown-tool errors, tool-failure isolation
- the bounded loop: tool call -> functionResponse -> final answer,
  stop conditions on both caps, graceful quota/no-key/network paths
- API endpoints: auth required, account scoping on explain
"""

from datetime import UTC, datetime

import httpx
import pytest
from app.agent import budget as agent_budget
from app.agent import loop as agent_loop
from app.agent import tools as agent_tools
from app.auth.security import create_access_token
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


class _ScriptedError:
    """Scripted HTTP failure: raise_for_status raises for this status."""

    def __init__(self, status: int) -> None:
        self.status = status


def _scripted_client(monkeypatch, responses):
    """Patch loop.httpx so each POST returns the next scripted response.

    Script entries are JSON dicts, or ``_ScriptedError(status)`` to fail
    one HTTP attempt (which is what the loop's retry logic reacts to).
    """
    script = list(responses)

    class _FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            if isinstance(self.payload, _ScriptedError):
                response = httpx.Response(
                    self.payload.status,
                    request=httpx.Request("POST", "https://generativelanguage.test"),
                )
                response.raise_for_status()  # raises httpx.HTTPStatusError

        def json(self):
            return self.payload

    class _FakeClient:
        def __init__(self, **kwargs):
            self.captured: list[dict] = []

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def post(self, url, **kwargs):
            assert script, "Test script ran dry — loop made more calls than scripted"
            self.captured.append(kwargs.get("json"))
            return _FakeResponse(script.pop(0))

    import app.agent.loop as loop_mod

    fake = _FakeClient()
    monkeypatch.setattr(loop_mod.httpx, "Client", lambda **kw: fake)
    monkeypatch.setattr(loop_mod, "GEMINI_API_KEY", "test-key")
    return fake


def _function_call_content(name: str, args: dict) -> dict:
    return {
        "role": "model",
        "parts": [{"functionCall": {"name": name, "args": args}}],
    }


def _text_content(text: str) -> dict:
    return {"role": "model", "parts": [{"text": text}]}


# ------------------------------------------------------------------ tools


class TestToolDispatch:
    def test_unknown_tool_returns_error_not_raise(self):
        result = agent_tools.execute_tool("wire_money", {"amount": 1_000_000}, "user-1")
        assert "error" in result

    def test_due_soon_clamps_days(self, monkeypatch):
        captured: dict = {}

        def fake_due_soon(user_id, days):
            captured["days"] = days
            return []

        monkeypatch.setattr(agent_tools, "get_due_soon_rows", fake_due_soon)
        result = agent_tools.execute_tool("due_soon", {"days": 9999}, "user-1")
        assert captured["days"] == 90  # clamped to the documented max
        assert result["output"]["days"] == 90

    def test_due_soon_defaults_on_garbage_args(self, monkeypatch):
        captured: dict = {}

        def fake_due_soon(user_id, days):
            captured["days"] = days
            return []

        monkeypatch.setattr(agent_tools, "get_due_soon_rows", fake_due_soon)
        agent_tools.execute_tool("due_soon", {"days": "next week"}, "user-1")
        assert captured["days"] == 5

    def test_invoice_lists_are_trimmed(self, monkeypatch):
        monkeypatch.setattr(
            agent_tools,
            "get_invoices",
            lambda user_id, status=None, search=None: [
                {"id": str(i), "invoice_number": f"INV-{i}", "amount": float(i)} for i in range(50)
            ],
        )
        result = agent_tools.execute_tool("flagged_invoices", {}, "user-1")
        assert len(result["output"]["invoices"]) == 15
        assert result["output"]["count"] == 50

    def test_search_requires_query(self, monkeypatch):
        monkeypatch.setattr(agent_tools, "get_invoices", lambda *a, **k: [])
        result = agent_tools.execute_tool("search_invoices", {"query": "   "}, "user-1")
        assert "error" in result

    def test_tool_failure_is_isolated(self, monkeypatch):
        def _boom(*a, **k):
            raise RuntimeError("db down")

        monkeypatch.setattr(agent_tools, "vendor_spend_summary", _boom)
        result = agent_tools.execute_tool("vendor_spend", {}, "user-1")
        assert "error" in result

    def test_payables_by_vendor_sums_and_ranks(self, monkeypatch):
        monkeypatch.setattr(
            agent_tools,
            "payables_by_vendor",
            lambda user_id: [
                {"vendor": "Courier Co", "unpaid_total": 1200.5, "invoice_count": 2, "overdue_count": 1},
                {"vendor": "Small Traders", "unpaid_total": 99.0, "invoice_count": 1, "overdue_count": 0},
            ],
        )
        result = agent_tools.execute_tool("payables_by_vendor", {}, "user-1")
        assert result["output"]["total_unpaid_inr"] == 1299.5
        assert result["output"]["vendors"][0]["vendor"] == "Courier Co"

    def test_payables_is_whitelisted(self):
        names = {declaration["name"] for declaration in agent_tools.FUNCTION_DECLARATIONS}
        assert "payables_by_vendor" in names
        assert "payables_by_vendor" in agent_tools._EXECUTORS

    def test_gst_summary_splits_taxable_and_tax(self, monkeypatch):
        this_month = datetime.now(UTC).strftime("%Y-%m")
        monkeypatch.setattr(
            agent_tools,
            "get_invoices",
            lambda user_id: [
                {"created_at": f"{this_month}-02T10:00:00", "amount": 1180.0, "tax_amount": 180.0},
                {"created_at": f"{this_month}-09T10:00:00", "amount": 500.0, "tax_amount": None},
            ],
        )
        result = agent_tools.execute_tool("gst_tax_summary", {"months": 12}, "user-1")
        row = result["output"]["summary"][0]
        assert row["tax_amount"] == 180.0
        assert row["taxable_value"] == pytest.approx(1500.0)


# ---------------------------------------------------------------- loop


class TestAskLoop:
    def test_tool_then_answer(self, monkeypatch):
        captured: dict = {}

        def fake_due_soon(user_id, days):
            captured["user_id"] = user_id
            captured["days"] = days
            return [{"invoice_number": "INV-2", "amount": 500.0, "status": "pending"}]

        monkeypatch.setattr(agent_tools, "get_due_soon_rows", fake_due_soon)
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        recorded: list[tuple] = []
        monkeypatch.setattr(
            agent_loop.budget, "record_model_calls", lambda n, uid, ev: recorded.append((n, uid, ev))
        )

        _scripted_client(
            monkeypatch,
            [
                {"candidates": [{"content": _function_call_content("due_soon", {"days": 10})}]},
                {"candidates": [{"content": _text_content("INV-2 for Rs 500 is due in 10 days.")}]},
            ],
        )

        result = agent_loop.ask_invoxa("user-1", "What is due soon?")
        assert result["answer"] == "INV-2 for Rs 500 is due in 10 days."
        assert result["model_calls"] == 2
        assert result["tool_calls"] == [{"tool": "due_soon", "args": {"days": 10}}]
        assert captured["user_id"] == "user-1"  # account-scoped
        assert captured["days"] == 10
        assert len(recorded) == 2  # both model calls audited

    def test_unknown_tool_from_model_is_survived(self, monkeypatch):
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        _scripted_client(
            monkeypatch,
            [
                {"candidates": [{"content": _function_call_content("delete_everything", {})}]},
                {"candidates": [{"content": _text_content("I could not do that.")}]},
            ],
        )
        result = agent_loop.ask_invoxa("user-1", "do something unexpected")
        assert result["answer"] == "I could not do that."
        assert result["tool_calls"][0]["tool"] == "delete_everything"

    def test_loop_stops_at_tool_round_cap(self, monkeypatch):
        monkeypatch.setattr(agent_loop, "MAX_TOOL_ROUNDS", 3)
        monkeypatch.setattr(agent_loop, "MAX_MODEL_CALLS", 10)
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        # Endless function calls — the loop must terminate itself.
        endless = [
            {"candidates": [{"content": _function_call_content("vendor_spend", {})}]}
            for _ in range(50)
        ]
        _scripted_client(monkeypatch, endless)

        result = agent_loop.ask_invoxa("user-1", "keep calling tools forever")
        assert result["model_calls"] == 3
        assert "ran out of reasoning steps" in result["answer"]

    def test_quota_exhausted_short_circuits(self, monkeypatch):
        monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 0)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)

        def _must_not_be_called(**kwargs):
            raise AssertionError("network hit despite exhausted quota")

        import app.agent.loop as loop_mod

        monkeypatch.setattr(loop_mod.httpx, "Client", _must_not_be_called)
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert "daily AI allowance" in result["answer"]
        assert result["model_calls"] == 0

    def test_no_key_returns_configured_message(self):
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert "not configured" in result["answer"]
        assert result["model_calls"] == 0

    def test_429_is_retried_and_recovers(self, monkeypatch):
        """One transient 429 is retried in-place; the question still answers."""
        monkeypatch.setattr(agent_loop, "_RETRY_BACKOFF_SECONDS", 0)
        monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        _scripted_client(
            monkeypatch,
            [
                _ScriptedError(429),
                {"candidates": [{"content": _text_content("Recovered after retry.")}]},
            ],
        )
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert result["answer"] == "Recovered after retry."
        assert result["model_calls"] == 1

    def test_persistent_429_gets_clear_message(self, monkeypatch):
        """A 429 on both attempts surfaces the rate-limit copy, not a crash."""
        monkeypatch.setattr(agent_loop, "_RETRY_BACKOFF_SECONDS", 0)
        monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        _scripted_client(monkeypatch, [_ScriptedError(429), _ScriptedError(429)])
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert "busy" in result["answer"]
        assert "rate-limited" in result["answer"]
        assert result["model_calls"] == 1

    def test_server_error_is_retried_too(self, monkeypatch):
        """5xx responses share the retry path and recover the same way."""
        monkeypatch.setattr(agent_loop, "_RETRY_BACKOFF_SECONDS", 0)
        monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        _scripted_client(
            monkeypatch,
            [
                _ScriptedError(503),
                {"candidates": [{"content": _text_content("Back online.")}]},
            ],
        )
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert result["answer"] == "Back online."

    def test_network_failure_degrades_gracefully(self, monkeypatch):
        monkeypatch.setattr(agent_loop, "_RETRY_BACKOFF_SECONDS", 0)
        monkeypatch.setattr(agent_loop, "GEMINI_API_KEY", "test-key")
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 50)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)

        class _BoomClient:
            def __init__(self, **kw):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def post(self, *a, **k):
                raise RuntimeError("network down")

        import app.agent.loop as loop_mod

        monkeypatch.setattr(loop_mod.httpx, "Client", lambda **kw: _BoomClient())
        result = agent_loop.ask_invoxa("user-1", "anything")
        assert "could not reach" in result["answer"]

    def test_payables_aggregation_in_database(self, monkeypatch):
        """The database helper: unpaid only, grouped, overdue counted."""
        import app.database as db

        monkeypatch.setattr(
            db,
            "get_invoices",
            lambda user_id: [
                {"vendor_name": "Courier Co", "amount": 500.0, "status": "pending", "due_date": "2020-01-01"},
                {"vendor_name": "Courier Co", "amount": 250.0, "status": "flagged", "due_date": None},
                {"vendor_name": "Paid Ltd", "amount": 999.0, "status": "reviewed", "due_date": "2020-01-01"},
                {"vendor_name": "Exporter", "amount": 100.0, "status": "auto_approved", "due_date": "2099-01-01"},
            ],
        )
        rows = db.payables_by_vendor("user-1")
        assert rows == [
            {"vendor": "Courier Co", "unpaid_total": 750.0, "invoice_count": 2, "overdue_count": 1},
            {"vendor": "Exporter", "unpaid_total": 100.0, "invoice_count": 1, "overdue_count": 0},
        ]

    def test_remaining_budget_limits_model_calls(self, monkeypatch):
        """When only 2 calls of budget remain, the loop spends at most 2."""
        monkeypatch.setattr(agent_loop, "MAX_TOOL_ROUNDS", 8)
        monkeypatch.setattr(agent_loop.budget, "remaining_today", lambda: 2)
        monkeypatch.setattr(agent_loop.budget, "record_model_calls", lambda *a, **k: None)
        endless = [
            {"candidates": [{"content": _function_call_content("vendor_spend", {})}]}
            for _ in range(50)
        ]
        _scripted_client(monkeypatch, endless)

        result = agent_loop.ask_invoxa("user-1", "keep going")
        assert result["model_calls"] == 2


# ------------------------------------------------------------- endpoints


class UserStore:
    def __init__(self):
        self.rows: dict[str, dict] = {}
        self._n = 0

    def add(self, email):
        self._n += 1
        uid = f"user-{self._n}"
        self.rows[uid] = {
            "id": uid,
            "email": email,
            "name": "Test",
            "role": "member",
            "created_at": "2026-09-10T00:00:00+00:00",
        }
        return self.rows[uid]


@pytest.fixture
def users(monkeypatch):
    store = UserStore()
    import app.api.auth as auth_api
    import app.auth.dependencies as deps

    monkeypatch.setattr(
        auth_api, "create_user", lambda email, password_hash, name, role: store.add(email)
    )
    monkeypatch.setattr(auth_api, "get_user_by_email", lambda email: None)
    monkeypatch.setattr(deps, "get_user_by_id", lambda uid: store.rows.get(uid))
    return store


def _auth_header(users):
    row = users.add("agent@example.com")
    return {"Authorization": f"Bearer {create_access_token(row['id'], row['role'])}"}


class TestAgentEndpoints:
    def test_ask_requires_auth(self):
        res = client.post("/api/agent/ask", json={"question": "hi"})
        assert res.status_code in (401, 403)

    def test_ask_happy_path(self, users, monkeypatch):
        import app.api.agent as agent_api

        monkeypatch.setattr(
            agent_api, "ask_invoxa", lambda uid, q: {"answer": f"echo {q}", "tool_calls": [], "model_calls": 1}
        )
        res = client.post(
            "/api/agent/ask", json={"question": "How much did I spend?"}, headers=_auth_header(users)
        )
        assert res.status_code == 200
        assert res.json()["answer"] == "echo How much did I spend?"

    def test_ask_rejects_blank_question(self, users):
        res = client.post("/api/agent/ask", json={"question": ""}, headers=_auth_header(users))
        assert res.status_code == 422

    def test_explain_enforces_ownership(self, users, monkeypatch):
        import app.api.agent as agent_api

        monkeypatch.setattr(
            agent_api,
            "get_invoice",
            lambda iid: {"id": iid, "created_by": "someone-else"},
        )
        res = client.post(
            "/api/agent/explain/inv-1",
            json={},
            headers=_auth_header(users),
        )
        assert res.status_code == 403

    def test_explain_unknown_invoice_404(self, users, monkeypatch):
        import app.api.agent as agent_api

        monkeypatch.setattr(agent_api, "get_invoice", lambda iid: None)
        res = client.post(
            "/api/agent/explain/inv-missing",
            json={},
            headers=_auth_header(users),
        )
        assert res.status_code == 404

    def test_explain_returns_null_when_ai_unavailable(self, users, monkeypatch):
        import app.api.agent as agent_api

        monkeypatch.setattr(
            agent_api,
            "get_invoice",
            lambda iid: {"id": iid, "created_by": users.rows["user-1"]["id"]},
        )
        monkeypatch.setattr(agent_api, "explain_flag", lambda uid, iid: None)
        res = client.post(
            "/api/agent/explain/inv-1",
            json={},
            headers=_auth_header(users),
        )
        assert res.status_code == 200
        assert res.json()["explanation"] is None


# ---------------------------------------------------------------- budget


class TestBudget:
    def test_daily_limit_env_override(self, monkeypatch):
        monkeypatch.setenv("AGENT_DAILY_GEMINI_CALLS", "12")
        assert agent_budget.daily_limit() == 12

    def test_daily_limit_garbage_env(self, monkeypatch):
        monkeypatch.setenv("AGENT_DAILY_GEMINI_CALLS", "lots")
        assert agent_budget.daily_limit() == 240

    def test_remaining_never_negative(self, monkeypatch):
        monkeypatch.setattr(agent_budget, "calls_today", lambda: 999_999)
        assert agent_budget.remaining_today() == 0
