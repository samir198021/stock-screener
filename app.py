"""Near-real-time stock screener UI (Streamlit).

Run:  streamlit run app.py      ->  http://localhost:8501
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import chartink
import screener
from deep_dive_prompt import build_deep_dive_prompt
from universe import MARKETS, get_universe

INDIA_LABEL = "India (NSE Nifty 500)"

st.set_page_config(page_title="Stock Screener", page_icon="📈", layout="wide")


# ---------------------------------------------------------------------------
# Cached network wrappers (this is where rate-limit protection lives).
#   - prices: one batched request per market, cached for the refresh interval.
#   - EPS: per-ticker but cached for 1 hour, since EPS barely moves intraday.
# tickers are passed as a tuple so they're hashable for st.cache_data.
# ---------------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner=False)
def cached_history(tickers: tuple, period: str = "1y"):
    return screener.fetch_price_history(list(tickers), period=period)


@st.cache_data(ttl=3600, show_spinner=False)
def cached_fundamentals(tickers: tuple):
    return screener.fetch_fundamentals(list(tickers))


def run_screen(market_label, pe_max, vol_mult, rsi_min, min_traded_value=0.0):
    tickers, currency = get_universe(market_label)
    history = cached_history(tuple(tickers))
    # Two-stage: technicals for all, fundamentals only for survivors (cached, sorted for cache hits).
    fetch_funds = lambda ts: cached_fundamentals(tuple(sorted(ts)))
    result, scanned, watch = screener.scan_universe(
        tickers, history, fetch_funds, pe_max, vol_mult, rsi_min, min_traded_value)
    return result, currency, scanned, len(tickers), watch


@st.cache_data(ttl=60, show_spinner=False)
def cached_chartink(rsi_min: float, vol_mult: float):
    """Near-live NSE scan (RSI + volume) from Chartink, cached for the refresh interval."""
    return chartink.fetch_scan(rsi_min=rsi_min, vol_mult=vol_mult)


def run_screen_chartink(pe_max, vol_mult, rsi_min, min_traded_value=0.0, top_n=50):
    """India near-live path: Chartink finds today's RSI+volume movers across all NSE, then we
    enrich the top movers with Yahoo (P/E, sector, 200-DMA, conviction) and apply the P/E filter.
    Raises on Chartink failure so the caller can fall back to Yahoo."""
    rows = cached_chartink(rsi_min, vol_mult)
    if not rows:
        return pd.DataFrame(), "₹", 0, 0, None

    # Biggest movers first, capped so enrichment stays cheap.
    rows = sorted(rows, key=lambda r: r.get("per_chg") or 0, reverse=True)[:top_n]
    tickers = [r["nsecode"] + ".NS" for r in rows]
    history = cached_history(tuple(tickers))
    fundamentals = cached_fundamentals(tuple(tickers))

    metrics = []
    for r in rows:
        t = r["nsecode"] + ".NS"
        m = screener.compute_metrics(t, history.get(t), fundamentals.get(t))
        if not m:
            continue
        # Use Chartink's near-live price; scale P/E to it; keep today's % change.
        old_price = m["price"]
        live_price = float(r["close"])
        m["price"] = live_price
        if m.get("pe") and old_price:
            m["pe"] = m["pe"] * (live_price / old_price)
        m["pct_change"] = r.get("per_chg")
        m["ticker"] = r["nsecode"]
        metrics.append(m)

    # Trust Chartink's near-live RSI/volume; only apply the P/E + liquidity filters here.
    result = screener.screen_and_rank(metrics, pe_max, vol_mult, rsi_min,
                                      require_technicals=False, min_traded_value=min_traded_value)
    return result, "₹", len(metrics), len(tickers), None  # no full-universe base -> no coil watch


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ Settings")

market_label = st.sidebar.selectbox("Market", list(MARKETS.keys()))

# Data source — Chartink (near-live) is only offered for India; US is always Yahoo.
if market_label == INDIA_LABEL:
    source_choice = st.sidebar.radio(
        "Data source",
        ["Near-live (Chartink)", "Delayed (Yahoo)"],
        help="Chartink pulls near-live NSE data during market hours (scans all NSE, shows top "
             "movers). Yahoo is ~15 min delayed but always available. Falls back to Yahoo if "
             "Chartink is unreachable.",
    )
    use_chartink = source_choice.startswith("Near-live")
else:
    use_chartink = False

st.sidebar.subheader("Filters")
pe_max = st.sidebar.number_input("Max trailing P/E", min_value=1.0, max_value=200.0, value=20.0, step=1.0)
vol_mult = st.sidebar.number_input("Min volume spike (× 20-day avg)", min_value=1.0, max_value=20.0, value=1.5, step=0.5)
rsi_min = st.sidebar.number_input("Min RSI (14)", min_value=1.0, max_value=99.0, value=50.0, step=1.0)

# Liquidity floor — drops thinly-traded, untradeable names (avg daily turnover). Unit by market.
if market_label.startswith("US"):
    _min_liq_disp = st.sidebar.number_input("Min liquidity ($ million/day)", 0.0, 2000.0, 5.0, 1.0)
    min_traded_value = _min_liq_disp * 1e6
else:
    _min_liq_disp = st.sidebar.number_input("Min liquidity (₹ crore/day)", 0.0, 2000.0, 1.0, 0.5)
    min_traded_value = _min_liq_disp * 1e7

st.sidebar.subheader("Refresh")
auto = st.sidebar.toggle("Auto-refresh", value=True)
interval = st.sidebar.select_slider("Interval (seconds)", options=[30, 60, 120, 300], value=60)
if st.sidebar.button("🔄 Rescan now"):
    cached_history.clear()
    cached_chartink.clear()
    st.rerun()

st.sidebar.caption(
    "India can use **Chartink** (near-live NSE) or **Yahoo** (~15 min delayed); US uses Yahoo. "
    "Chartink finds today's RSI+volume movers across all NSE; P/E, sector, 200-DMA and conviction "
    "are enriched from Yahoo. Falls back to Yahoo automatically if Chartink is unreachable."
)

# Timed auto-refresh (triggers a rerun; the ttl caches decide when data is actually refetched).
if auto:
    st_autorefresh(interval=interval * 1000, key="autorefresh")


# ---------------------------------------------------------------------------
# Main panel
# ---------------------------------------------------------------------------
st.title("📈 Near-Real-Time Stock Screener")
st.caption(
    "Keeps stocks with **P/E < {:.0f}**, **volume > {:.1f}× 20-day avg**, and **RSI(14) > {:.0f}** — "
    "ranked by **Conviction** (how many bonus strength signals align), then composite score."
    .format(pe_max, vol_mult, rsi_min)
)

with st.spinner("Fetching quotes…"):
    if use_chartink:
        try:
            result, currency, scanned, total, watch = run_screen_chartink(pe_max, vol_mult, rsi_min, min_traded_value)
            source = "Chartink (near-live NSE)"
        except Exception as e:
            st.warning(f"Chartink is unreachable right now — falling back to Yahoo (delayed). [{e}]")
            result, currency, scanned, total, watch = run_screen(market_label, pe_max, vol_mult, rsi_min, min_traded_value)
            source = "Yahoo (delayed ~15 min)"
    else:
        result, currency, scanned, total, watch = run_screen(market_label, pe_max, vol_mult, rsi_min, min_traded_value)
        source = "Yahoo (delayed ~15 min)"

c1, c2, c3, c4 = st.columns(4)
c1.metric("Market", market_label.split(" (")[0])
c2.metric("Scanned", f"{scanned}/{total}")
c3.metric("Passed filters", 0 if result is None or result.empty else len(result))
c4.metric("Last updated", datetime.now().strftime("%H:%M:%S"))
st.caption(f"Source: **{source}**")

# Market-session awareness (NSE/BSE, IST) — only relevant for the India markets.
if market_label.startswith("India"):
    _IST = timezone(timedelta(hours=5, minutes=30))
    _now_ist = datetime.now(_IST)
    _mins = _now_ist.hour * 60 + _now_ist.minute
    st.caption(f"🕒 IST now: **{_now_ist:%a %d %b, %H:%M}**")
    if _now_ist.weekday() >= 5:
        st.info("🌙 **Market closed (weekend).** This reflects the **last close** — a watchlist to "
                "review before Monday's open.")
    elif _mins < 9 * 60 + 15:
        st.info("🌅 **Pre-open (before 9:15).** This scan reflects **yesterday's close** — treat it as "
                "**today's watchlist**, then watch these names at the 9:15 open before acting. "
                "Tip: use the **Yahoo** source now — Chartink's live volume only becomes meaningful "
                "~30 min after the open (before that, almost nothing has traded today).")
    elif _mins <= 15 * 60 + 30:
        st.info("🟢 **Market open** — data is intraday. For NSE, **Chartink** gives the freshest read; "
                "volume ratios firm up as the session builds. (BSE uses Yahoo, delayed.)")
    else:
        st.info("🔔 **Market closed for the day.** Showing **today's close** — a watchlist for tomorrow.")

if result is None or result.empty:
    st.info("No stocks currently pass all three filters. Try loosening the thresholds in the sidebar.")
else:
    # Liquidity in market units (₹ crore/day or $ million/day).
    liq_div = 1e6 if currency == "$" else 1e7
    liq_name = "Liq ($M)" if currency == "$" else "Liq (₹cr)"
    result = result.copy()
    result["liq"] = result["traded_value"] / liq_div

    cols = ["rank", "ticker", "signal", "trend", "breakout", "sector", "price"]
    names = ["Rank", "Ticker", "Signal", "Trend", "Breakout", "Sector", f"Price ({currency})"]
    if "pct_change" in result.columns:            # near-live today's move (Chartink path)
        cols.append("pct_change"); names.append("Chg %")
    cols += ["pe", "volume_ratio", "liq", "rsi", "range52", "vs_200dma", "conviction", "score", "chart"]
    names += ["P/E", "Vol ×", liq_name, "RSI", "52W Range", "vs 200DMA", "Conviction", "Score", "Chart"]
    display = result[cols].copy()
    display.columns = names
    colcfg = {
            liq_name: st.column_config.NumberColumn(
                format="%.2f",
                help="Avg daily turnover (price × 20-day avg volume). Higher = easier to buy/sell. "
                     "Low values = thinly traded (hard to exit, circuit-prone) — raise 'Min liquidity' "
                     "in the sidebar to hide these."),
            "Trend": st.column_config.TextColumn(
                help="Direction from moving averages — ⬆️ Uptrend (price > 20-DMA > 50-DMA, going "
                     "strong), ↗️ Turning up, ➡️ Pausing, ⬇️ Fading (rolling over). Not a guarantee."),
            "Breakout": st.column_config.TextColumn(
                help="🚀 55D high (broke ~3-month high, strongest) · 🔼 20D high (~1-month) · "
                     "🎯 Tight base (coiling, PRE-breakout — watch for the pop) · 🏔️ Near 52wk hi. "
                     "Breakouts are most reliable when Vol× is high (real, not a fake-out)."),
            f"Price ({currency})": st.column_config.NumberColumn(format="%.2f"),
            "Chg %": st.column_config.NumberColumn(format="%+.2f%%", help="Today's price change (near-live, Chartink)."),
            "P/E": st.column_config.NumberColumn(format="%.2f"),
            "Vol ×": st.column_config.NumberColumn(format="%.2fx"),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
            "52W Range": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=100,
                help="Where the price sits in its 52-week range: 0 = at the low, 100 = at the high.",
            ),
            "vs 200DMA": st.column_config.NumberColumn(
                format="%+.1f%%",
                help="Percent above (+) or below (-) the 200-day moving average. Above = longer-term uptrend.",
            ),
            "Conviction": st.column_config.ProgressColumn(
                format="%.0f", min_value=0, max_value=5,
                help="How many BONUS strength signals align (0-5): above 200-DMA, upper half of "
                     "52-week range, RSI>=60, volume>=2x, P/E<=15. Higher = stronger setup (not a guarantee).",
            ),
            "Score": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
            "Chart": st.column_config.LinkColumn("Chart", display_text="📈 Open"),
    }
    st.dataframe(display, hide_index=True, use_container_width=True, column_config=colcfg)

    st.caption(
        "⚠️ **Signal:** 🟢 Strong · 🟡 Watch · 🔴 Weak · 🟠 **Extended** = strong but already run up "
        "hard (overbought / far above average / big move today), so **higher pullback risk — don't "
        "chase**; wait for a pullback or a base. This is a mechanical read, **not financial advice "
        "or a buy/sell call**. Do your own research and set a stop-loss."
    )

    st.bar_chart(result.set_index("ticker")["score"])

    # --- Deep-dive research prompt: turn a screener hit into a ready-to-paste analyst-memo prompt. ---
    with st.expander("📋 Deep-dive research prompt", expanded=False):
        st.caption(
            "Picks up where the screener leaves off: fills the 18-section institutional-memo "
            "template (business model, peers, red flags, scenarios, valuation, etc.) for one "
            "ticker below. Copy it into a Claude chat to get the full report — this app only "
            "builds the prompt, it doesn't call an LLM itself."
        )
        dd_ticker = st.selectbox("Ticker", result["ticker"].tolist(), key="dd_ticker")
        dd_sector = result.loc[result["ticker"] == dd_ticker, "sector"].iloc[0] if "sector" in result.columns else ""
        dd_prompt = build_deep_dive_prompt(dd_ticker, dd_sector)
        st.text_area("Prompt", dd_prompt, height=300, key="dd_prompt_box")
        st.download_button(
            "⬇️ Download as .md", dd_prompt, file_name=f"{dd_ticker}_deep_dive_prompt.md", mime="text/markdown",
        )

# --- Pre-breakout watch (coiling tight bases) — shown when we have a full-universe base (Yahoo). ---
if watch:
    with st.expander(f"🎯 Pre-breakout watch — coiling ({len(watch)})", expanded=False):
        st.caption("Tight bases in an uptrend — **low volume, so they're NOT in the table above**. "
                   "These are coiling early setups; watch for a breakout (they'd flip to 🔼/🚀 on volume).")
        wdf = pd.DataFrame([
            {"Ticker": m["ticker"], "Trend": m["trend"], f"Price ({currency})": round(m["price"], 2),
             "RSI": round(m["rsi"], 1), "52W Range": m["range52"]}
            for m in watch
        ])
        st.dataframe(
            wdf, hide_index=True, use_container_width=True,
            column_config={
                "RSI": st.column_config.NumberColumn(format="%.1f"),
                "52W Range": st.column_config.ProgressColumn(format="%.0f", min_value=0, max_value=100),
            },
        )
elif use_chartink:
    st.caption("💡 Switch India **Data source** to *Delayed (Yahoo)* to also see the 🎯 pre-breakout "
               "(tight-base) watch — Chartink's near-live scan only covers volume-active names.")
