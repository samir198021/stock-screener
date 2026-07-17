"""Runs the condensed 18-point fundamentals scorecard against the Claude API with live
web research, for one ticker at a time. Used by the daily digest to add a fundamentals
read on top of the existing technical screen — see fundamentals_prompt.py for the prompt
and CLAUDE.md for how this fits into the pipeline.

Pure logic, no streamlit import, same convention as deep_dive.py.
"""

import json
import os

import anthropic

from fundamentals_prompt import POINT_KEYS, build_fundamentals_prompt

MODEL = "claude-opus-4-8"
MAX_TOKENS = 8000  # condensed scorecard — much smaller than the full deep-dive memo
MAX_CONTINUATIONS = 3

_SCHEMA = {
    "type": "object",
    "properties": {
        "fundamentals_score": {"type": "integer"},
        "score_rationale": {"type": "string"},
        "valuation_tag": {"type": "string"},
        "red_flag_count": {"type": "integer"},
        "points": {
            "type": "object",
            "properties": {k: {"type": "string"} for k in POINT_KEYS},
            "required": POINT_KEYS,
            "additionalProperties": False,
        },
    },
    "required": ["fundamentals_score", "score_rationale", "valuation_tag", "red_flag_count", "points"],
    "additionalProperties": False,
}


class MissingAPIKeyError(RuntimeError):
    """ANTHROPIC_API_KEY isn't set — caller should skip the fundamentals section, not crash."""


def _client() -> anthropic.Anthropic:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise MissingAPIKeyError("ANTHROPIC_API_KEY is not set — skipping fundamentals research.")
    return anthropic.Anthropic()


def research_fundamentals(ticker: str, sector: str = "") -> dict:
    """Returns the parsed scorecard dict (see _SCHEMA), or raises on failure.

    Raises MissingAPIKeyError, or an anthropic.APIError subclass — callers in an automated
    pipeline should catch broadly per-ticker so one bad name doesn't kill the whole run.
    """
    client = _client()
    prompt = build_fundamentals_prompt(ticker, sector)

    messages = [{"role": "user", "content": prompt}]
    tools = [
        {"type": "web_search_20260209", "name": "web_search"},
        {"type": "web_fetch_20260209", "name": "web_fetch"},
    ]
    output_config = {
        "effort": "medium",
        "format": {"type": "json_schema", "schema": _SCHEMA},
    }

    for _ in range(MAX_CONTINUATIONS):
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            thinking={"type": "adaptive"},
            output_config=output_config,
            tools=tools,
            messages=messages,
        )
        if response.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": response.content}]
    else:
        raise RuntimeError(f"{ticker}: gave up after {MAX_CONTINUATIONS} tool-use pauses")

    text = next((b.text for b in response.content if b.type == "text"), None)
    if not text:
        raise RuntimeError(f"{ticker}: no text block in response (stop_reason={response.stop_reason})")

    data = json.loads(text)
    data["ticker"] = ticker
    return data
