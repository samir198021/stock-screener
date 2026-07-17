"""Builds the condensed 18-point fundamentals-scorecard prompt used by the daily digest.

Pure string templating (no streamlit, no API calls) — mirrors deep_dive_prompt.py's
convention, but produces a compact scorecard instead of the full 18-section memo,
since this one runs automatically every trading day and needs to stay cheap and fast.
"""

POINT_LABELS = {
    "business_model": "Business model",
    "industry_position": "Industry position",
    "peer_standing": "Peer standing",
    "product_concentration": "Product concentration",
    "pipeline_growth_visibility": "Pipeline / growth visibility",
    "business_performance": "Business performance",
    "analyst_sentiment": "Analyst sentiment",
    "management_tone": "Management tone",
    "promoter_trend": "Promoter trend",
    "capital_allocation": "Capital allocation",
    "financial_quality": "Financial quality",
    "shareholding_trend": "Shareholding trend",
    "guidance_read": "Guidance read",
    "variant_perception": "Variant perception",
    "scenario_skew": "Scenario skew",
    "valuation": "Valuation",
    "key_quote": "Key quote",
    "walk_the_talk": "Walk-the-talk",
}

POINT_KEYS = list(POINT_LABELS.keys())

_TEMPLATE = """Research {company} (NSE-listed) using live web sources (Screener.in, Tickertape, company filings, recent financial press). Return a compact fundamentals scorecard, not a narrative report.

Cover exactly these 18 points, one sourced sentence each:
{point_list}

Rules:
- No buy/sell/hold, no target price — ever.
- If a point can't be verified live, say so plainly rather than guessing or estimating.
- Attribute every claim to its source (company filing, brokerage name, exchange notice) — never present analyst commentary as if it were management's own words.
- Flag any data conflicts across sources explicitly instead of silently picking one number.

Then give a fundamentals_score from 0-100 — your own qualitative synthesis of the 18 points, not a market-sourced statistic — with a one-line rationale, a one-word valuation_tag (e.g. cheap / fair / rich), and a red_flag_count (integer, only real flags found above)."""


def build_fundamentals_prompt(ticker: str, sector: str = "") -> str:
    company = f"{ticker} ({sector})" if sector else ticker
    point_list = "\n".join(f"- {label}" for label in POINT_LABELS.values())
    return _TEMPLATE.format(company=company, point_list=point_list)
