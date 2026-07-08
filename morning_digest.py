"""Morning watchlist digest — sends the NSE 🟢 Strong (non-Extended) names to Telegram.

Runs from a GitHub Action at ~09:10 IST (pre-open), so Yahoo's latest daily bar is YESTERDAY's
close — i.e. today's watchlist. Reads TELEGRAM_TOKEN / TELEGRAM_CHAT_ID from the environment
(GitHub secrets). Reuses the same screening logic as the app, so results match.
"""

import os
from datetime import datetime, timedelta, timezone

import requests

import screener
from universe import get_universe

NSE = "India (NSE Nifty 500)"
IST = timezone(timedelta(hours=5, minutes=30))


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
    active = screener.screen_and_rank(survivors)

    # Pre-breakout watch: tight-base coils in an uptrend (shared with the dashboard).
    watch = screener.prebreakout_watch(base, limit=10)
    return active, watch


def _name(ticker):
    return ticker.replace(".NS", "").replace(".BO", "")


def _active_row(r):
    return (f"• {_name(r['ticker'])}  ₹{r['price']:.1f} | RSI {r['rsi']:.0f} | "
            f"conv {int(r['conviction'])}/5 | {r['trend']} {r['breakout']}")


def _watch_row(m):
    return f"• {_name(m['ticker'])}  ₹{m['price']:.1f} | RSI {m['rsi']:.0f} | {m['trend']}"


def format_message(active, watch):
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
    send_telegram(format_message(active, watch))
    print("Digest sent.")
