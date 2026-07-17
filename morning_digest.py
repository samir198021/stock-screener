"""Morning watchlist digest — sends the NSE 🟢 Strong (non-Extended) names to Telegram.

Runs from a GitHub Action at ~09:10 IST (pre-open), so Yahoo's latest daily bar is YESTERDAY's
close — i.e. today's watchlist. Reads TELEGRAM_TOKEN / TELEGRAM_CHAT_ID from the environment
(GitHub secrets). Reuses the same screening logic as the app, so results match.
"""

import os
from datetime import datetime, timedelta, timezone

import requests

import screener
from fundamentals_research import MissingAPIKeyError, research_fundamentals
from universe import get_universe

NSE = "India (NSE Nifty 500)"
IST = timezone(timedelta(hours=5, minutes=30))

# Fundamentals research costs one Claude API call (with live web search) per ticker —
# cap it so an unusually large Strong-list day doesn't quietly run up a large bill.
MAX_FUNDAMENTALS_PER_DAY = 10


def build_lists():
    """Returns (active_df, watch_metrics):
      active_df     — stocks passing the full screen (breaking out now, volume up)
      watch_metrics — 🎯 tight-base coils in an uptrend (pre-breakout; low volume, so they'd
                      never survive the volume filter — hence a separate list from the base).
    """
    tickers, _ = get_universe(NSE)
    history = screener.fetch_price_history(tickers, period="1y")
    base = screener.compute_base(tickers, history)

    # Active setups: apply the volume/RSI filter, fetch fundamentals only for survivors.
    survivors = [m for m in base if m["rsi"] > screener.RSI_MIN and m["volume_ratio"] > screener.VOLUME_MULTIPLE]
    if survivors:
        funds = screener.fetch_fundamentals([m["ticker"] for m in survivors])
        for m in survivors:
            f = funds.get(m["ticker"]) or {}
            eps = f.get("eps")
            m["sector"] = f.get("sector") or "—"
            if eps and eps > 0:
                m["pe"] = m["price"] / float(eps)
    min_liq = 1e7  # ₹1 crore/day turnover — skip thinly-traded, untradeable names
    active = screener.screen_and_rank(survivors, min_traded_value=min_liq)

    # Pre-breakout watch: tight-base coils in an uptrend (shared with the dashboard).
    watch = screener.prebreakout_watch(base, limit=10, min_traded_value=min_liq)
    return active, watch


def _name(ticker):
    return ticker.replace(".NS", "").replace(".BO", "")


def _active_row(r):
    return (f"• {_name(r['ticker'])}  ₹{r['price']:.1f} | RSI {r['rsi']:.0f} | "
            f"conv {int(r['conviction'])}/5 | {r['trend']} {r['breakout']}")


def _watch_row(m):
    return f"• {_name(m['ticker'])}  ₹{m['price']:.1f} | RSI {m['rsi']:.0f} | {m['trend']}"


def _fundamentals_row(data):
    return (f"• {_name(data['ticker'])}  {data.get('fundamentals_score', '—')}/100 | "
            f"{data.get('valuation_tag', '—')} | {data.get('red_flag_count', 0)} red flag(s)")


def build_fundamentals_section(active):
    """Runs the condensed fundamentals scorecard on today's top Strong candidates (capped at
    MAX_FUNDAMENTALS_PER_DAY to bound API spend). Returns None if the feature isn't configured
    (no ANTHROPIC_API_KEY) or there's nothing to research — the technical digest still sends
    either way, this section is additive.
    """
    if active is None or active.empty or not os.environ.get("ANTHROPIC_API_KEY"):
        return None

    strong = active[active["signal"] == "🟢 Strong"] if "signal" in active.columns else active
    candidates = (strong if not strong.empty else active).head(MAX_FUNDAMENTALS_PER_DAY)

    rows = []
    for _, r in candidates.iterrows():
        try:
            data = research_fundamentals(r["ticker"], r.get("sector", ""))
            rows.append(_fundamentals_row(data))
        except MissingAPIKeyError:
            return None
        except Exception as e:
            rows.append(f"• {_name(r['ticker'])}  fundamentals research failed ({type(e).__name__})")

    if not rows:
        return None
    return [f"\n🔎 Fundamentals read (top {len(rows)}, 18-point live research):"] + rows


def format_message(active, watch, fundamentals_section=None):
    now = datetime.now(IST)
    out = [f"📈 Morning Watchlist — {now:%a %d %b %Y}", "NSE • last close • NOT advice"]

    strong = active[active["signal"] == "🟢 Strong"] if active is not None and not active.empty else active
    if strong is not None and not strong.empty:
        out += [f"\n🟢 Strong now ({len(strong)}):"] + [_active_row(r) for _, r in strong.iterrows()]
    elif active is not None and not active.empty:
        out += ["\nNo 🟢 Strong today. Top active candidates:"]
        out += [f"{r['signal']} " + _active_row(r) for _, r in active.head(5).iterrows()]
    else:
        out += ["\nNo active breakout setups today."]

    if watch:
        out += [f"\n🎯 Pre-breakout watch — coiling ({len(watch)}):"] + [_watch_row(m) for m in watch]

    if fundamentals_section:
        out += fundamentals_section

    out.append("\nWatch at the 9:15 open. Confirm the chart & set a stop-loss.")
    return "\n".join(out)


def send_telegram(text):
    token = os.environ["TELEGRAM_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True},
        timeout=20,
    )
    resp.raise_for_status()


if __name__ == "__main__":
    active, watch = build_lists()
    fundamentals_section = build_fundamentals_section(active)
    send_telegram(format_message(active, watch, fundamentals_section))
    print("Digest sent.")
