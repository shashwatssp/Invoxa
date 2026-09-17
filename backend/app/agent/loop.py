"""
Bounded Gemini function-calling loop.

The model may call any of the whitelisted read-only tools in
``app.agent.tools``; results go back as functionResponses until the
model answers in plain English. Hard safety rails:

- max 8 tool rounds and max 10 model calls per run (whichever hits
  first stops the loop — it can never run away),
- a daily Gemini-call budget checked before the first call,
- every tool execution is read-only and account-scoped,
- every run is written to the audit trail (best-effort).

Any Gemini/network failure degrades to a graceful answer, never an
exception reaching the user.
"""

from __future__ import annotations

import logging
import os
import time

import httpx

from app.agent import budget, tools
from app.config import GEMINI_API_KEY, GEMINI_MODEL

logger = logging.getLogger(__name__)

GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
)
_TIMEOUT_SECONDS = 25  # two sequential calls + retry must fit Vercel's 60s cap
_MAX_OUTPUT_TOKENS = 1024
_RETRY_BACKOFF_SECONDS = 2.5
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, "") or default))
    except ValueError:
        return default


MAX_TOOL_ROUNDS = _env_int("AGENT_MAX_TOOL_ROUNDS", 8)
MAX_MODEL_CALLS = _env_int("AGENT_MAX_MODEL_CALLS", 10)

_SYSTEM_PROMPT = (
    "You are Invoxa, a bookkeeping assistant for a solo Indian business owner. "
    "Answer questions about their invoices using ONLY the tools provided — "
    "never invent figures. Use a tool first when the question needs data, then "
    "answer concisely in plain English (2-4 sentences unless asked for detail). "
    "Amounts are INR. If the tools cannot answer the question, say so honestly. "
    "You can read data but you can never modify, send, or delete anything."
)


def _model_call(contents: list[dict]) -> tuple[dict | None, str | None]:
    """One generateContent call with a single retry on transient failures.

    The Gemini free tier is rate-limited per minute, and the model is
    called 2-3 times per question, so a 429/5xx/timeout is retried once
    after a short backoff. Returns ``(data, None)`` on success or
    ``(None, reason)`` on failure — never raises.
    """
    reason: str | None = None
    for attempt in range(2):
        try:
            with httpx.Client(timeout=_TIMEOUT_SECONDS) as client:
                response = client.post(
                    GEMINI_API_URL,
                    params={"key": GEMINI_API_KEY},
                    json={
                        "contents": contents,
                        "tools": [{"function_declarations": tools.FUNCTION_DECLARATIONS}],
                        "generationConfig": {
                            "temperature": 0.2,
                            "maxOutputTokens": _MAX_OUTPUT_TOKENS,
                            # Short tool-driven answers need no thinking budget.
                            "thinkingConfig": {"thinkingBudget": 0},
                        },
                    },
                )
                response.raise_for_status()
                return response.json(), None
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status == 429:
                reason = "rate_limited"
            elif status in _RETRYABLE_STATUS:
                reason = "server_error"
            else:
                logger.warning("Agent model call failed: HTTP %d", status)
                return None, reason or "unreachable"
        except Exception:
            reason = "unreachable"
        if attempt == 0:
            time.sleep(_RETRY_BACKOFF_SECONDS)
    logger.warning("Agent model call failed (%s) after retry", reason)
    return None, reason


def _candidate_content(data: dict) -> dict | None:
    try:
        return data["candidates"][0]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def _parts_text(content: dict) -> str:
    return " ".join(
        part.get("text", "") for part in content.get("parts", []) if "text" in part
    ).strip()


def _function_calls(content: dict) -> list[dict]:
    return [
        part["functionCall"]
        for part in content.get("parts", [])
        if isinstance(part.get("functionCall"), dict)
    ]


def ask_invoxa(user_id: str, question: str) -> dict:
    """Answer one natural-language question using bounded tool use.

    Returns ``{"answer", "tool_calls", "model_calls"}``. Never raises.
    """
    question = (question or "").strip()
    if not question:
        return {"answer": "Ask me anything about your invoices.", "tool_calls": [], "model_calls": 0}

    if not GEMINI_API_KEY:
        budget.log_agent_event(user_id, "ask_no_key", {"question_length": len(question)})
        return {
            "answer": "The AI assistant is not configured. Add GEMINI_API_KEY to enable it.",
            "tool_calls": [],
            "model_calls": 0,
        }

    remaining = budget.remaining_today()
    if remaining <= 0:
        budget.log_agent_event(user_id, "ask_quota_exhausted", {"question_length": len(question)})
        return {
            "answer": (
                "The daily AI allowance is used up (it resets at midnight IST). "
                "Everything else keeps working as usual."
            ),
            "tool_calls": [],
            "model_calls": 0,
        }

    contents: list[dict] = [
        {"role": "user", "parts": [{"text": f"{_SYSTEM_PROMPT}\n\nQuestion: {question}"}]}
    ]
    tool_calls_log: list[dict] = []
    model_calls = 0
    last_error: str | None = None

    for _round in range(MAX_TOOL_ROUNDS):
        if model_calls >= min(MAX_MODEL_CALLS, remaining):
            break
        data, last_error = _model_call(contents)
        model_calls += 1
        budget.record_model_calls(1, user_id, "ask")
        if data is None:
            answer = (
                "The AI is busy right now — the free tier is rate-limited per minute. "
                "Please try again in a minute."
                if last_error == "rate_limited"
                else "I could not reach the AI service just now. Please try again shortly."
            )
            return {"answer": answer, "tool_calls": tool_calls_log, "model_calls": model_calls}
        content = _candidate_content(data)
        if content is None:
            break
        contents.append(content)

        calls = _function_calls(content)
        if not calls:
            answer = _parts_text(content)
            budget.log_agent_event(
                user_id,
                "ask_answered",
                {"model_calls": model_calls, "tool_calls": len(tool_calls_log)},
            )
            return {
                "answer": answer or "I could not work out an answer to that. Try rephrasing?",
                "tool_calls": tool_calls_log,
                "model_calls": model_calls,
            }

        response_parts = []
        for call in calls:
            name = str(call.get("name") or "")
            args = call.get("args") or {}
            result = tools.execute_tool(name, args, user_id)
            tool_calls_log.append({"tool": name, "args": args})
            response_parts.append({"functionResponse": {"name": name, "response": result}})
        contents.append({"role": "user", "parts": response_parts})

    budget.log_agent_event(
        user_id,
        "ask_capped",
        {"model_calls": model_calls, "tool_calls": len(tool_calls_log)},
    )
    return {
        "answer": (
            "I gathered the data but ran out of reasoning steps before answering. "
            "Try a narrower question (one vendor, one month)."
        ),
        "tool_calls": tool_calls_log,
        "model_calls": model_calls,
    }
