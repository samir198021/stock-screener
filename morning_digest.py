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

NSE = "India (Nifty 500 — top 50)"
IST = timezone(timedelta(hours=5, minutes=30))


def build_result():
    tickers, _ = get_universe(NSE)
    history = screener.fetch_price_history(tickers, period="1y")
    funds = screener.fetch_fundamentals(tickers)
    metrics = [screener.compute_metrics(t, history.get(t), funds.get(t)) for t in tickers]
    return screener.screen_and_rank(metrics)  # default filters: P/E<20, vol>1.5x, RSI>50


def _name(ticker):
    return ticker.replace(".NS", "").replace(".BO", "")


def _row(r):
    return (f"• {_name(r['ticker'])}  ₹{r['price']:.1f} | P/E {r['pe']:.1f} | "
            f"RSI {r['rsi']:.0f} | conv {int(r['conviction'])}/5")


def format_message(res):
    now = datetime.now(IST)
    header = (f"📈 Morning Watchlist — {now:%a %d %b %Y}\n"
              f"NSE • based on last close • NOT advice\n")

    if res is None or res.empty:
        return header + "\nNo stocks passed the filters. Quiet setup — sit tight."

    strong = res[res["signal"] == "🟢 Strong"]
    if not strong.empty:
        lines = [f"\n🟢 Strong setups ({len(strong)}):"]
        lines += [_row(r) for _, r in strong.iterrows()]
        lines.append("\nWatch these at the 9:15 open. Confirm the chart & set a stop-loss.")
        return header + "\n".join(lines)

    # No clean-strong names — show the top few candidates with their signal so it's never empty.
    lines = ["\nNo 🟢 Strong (non-extended) setups today. Top candidates:"]
    lines += [f"{r['signal']}  " + _row(r) for _, r in res.head(5).iterrows()]
    return header + "\n".join(lines)


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
    send_telegram(format_message(build_result()))
    print("Digest sent.")
