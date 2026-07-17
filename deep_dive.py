"""Runs the deep-dive analyst-memo prompt against the Claude API with live web
research (web_search + web_fetch server tools) and returns the finished report
as markdown text.

Pure logic, no streamlit import (see CLAUDE.md convention) so it stays testable;
UI wiring (spinner, error display, API-key check messaging) lives in app.py.
"""

import os

import anthropic

from deep_dive_prompt import build_deep_dive_prompt

MODEL = "claude-opus-4-8"
MAX_TOKENS = 32000
MAX_CONTINUATIONS = 6  # server-tool turns can pause_turn after ~10 search/fetch calls


class MissingAPIKeyError(RuntimeError):
    """Raised when ANTHROPIC_API_KEY isn't set — caller should show setup instructions."""


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingAPIKeyError(
            "ANTHROPIC_API_KEY is not set. Get a key at console.anthropic.com/settings/keys "
            "and set it as an environment variable (or a Streamlit secret) before running a deep dive."
        )
    return anthropic.Anthropic()


def run_deep_dive_analysis(ticker: str, sector: str = "") -> str:
    """Fills the 18-section analyst-memo prompt for `ticker` and runs it live against
    Claude with web search + web fetch enabled. Returns the final report as markdown.

    Raises MissingAPIKeyError, or an anthropic.APIError subclass, on failure — the
    caller is expected to catch these and show a friendly message.
    """
    client = _client()
    prompt = build_deep_dive_prompt(ticker, sector)

    messages = [{"role": "user", "content": prompt}]
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]

    full_text_parts = []
    for _ in range(MAX_CONTINUATIONS):
        with client.messages.stream(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            tools=tools,
            messages=messages,
        ) as stream:
            response = stream.get_final_message()

        full_text_parts.extend(block.text for block in response.content if block.type == "text")

        if response.stop_reason != "pause_turn":
            break

        # Server-tool loop hit its iteration cap mid-report — resume where it left off.
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    else:
        full_text_parts.append(
            "\n\n---\n*Report generation stopped after repeated tool-use pauses — "
            "the analysis above may be incomplete.*"
        )

    return "\n\n".join(full_text_parts).strip()
