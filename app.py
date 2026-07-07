"""Near-real-time stock screener UI (Streamlit).

Run:  streamlit run app.py      ->  http://localhost:8501
"""

from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

import screener
from universe import MARKETS, get_universe

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


def run_screen(market_label, pe_max, vol_mult, rsi_min):
    tickers, currency = get_universe(market_label)
    history = cached_history(tuple(tickers))
    fundamentals = cached_fundamentals(tuple(tickers))
    metrics = [screener.compute_metrics(t, history.get(t), fundamentals.get(t)) for t in tickers]
    result = screener.screen_and_rank(metrics, pe_max, vol_mult, rsi_min)
    scanned = sum(1 for m in metrics if m)
    return result, currency, scanned, len(tickers)


# ---------------------------------------------------------------------------
# Sidebar controls
# ---------------------------------------------------------------------------
st.sidebar.header("⚙️ Settings")

market_label = st.sidebar.selectbox("Market", list(MARKETS.keys()))

st.sidebar.subheader("Filters")
pe_max = st.sidebar.number_input("Max trailing P/E", min_value=1.0, max_value=200.0, value=20.0, step=1.0)
vol_mult = st.sidebar.number_input("Min volume spike (× 20-day avg)", min_value=1.0, max_value=20.0, value=1.5, step=0.5)
rsi_min = st.sidebar.number_input("Min RSI (14)", min_value=1.0, max_value=99.0, value=50.0, step=1.0)

st.sidebar.subheader("Refresh")
auto = st.sidebar.toggle("Auto-refresh", value=True)
interval = st.sidebar.select_slider("Interval (seconds)", options=[30, 60, 120, 300], value=60)
if st.sidebar.button("🔄 Rescan now"):
    cached_history.clear()
    st.rerun()

st.sidebar.caption(
    "Data via Yahoo Finance (yfinance) — delayed ~15 min, not tick data. "
    "Prices are fetched in one batched request per refresh; EPS is cached hourly to respect rate limits."
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
    "ranked by composite score (RSI + volume ratio + inverse P/E).".format(pe_max, vol_mult, rsi_min)
)

with st.spinner("Fetching quotes…"):
    result, currency, scanned, total = run_screen(market_label, pe_max, vol_mult, rsi_min)

c1, c2, c3, c4 = st.columns(4)
c1.metric("Market", market_label.split(" (")[0])
c2.metric("Scanned", f"{scanned}/{total}")
c3.metric("Passed all filters", 0 if result is None or result.empty else len(result))
c4.metric("Last updated", datetime.now().strftime("%H:%M:%S"))

if result is None or result.empty:
    st.info("No stocks currently pass all three filters. Try loosening the thresholds in the sidebar.")
else:
    display = result[
        ["rank", "ticker", "sector", "price", "pe", "volume_ratio", "rsi",
         "range52", "vs_200dma", "score", "chart"]
    ].copy()
    display.columns = [
        "Rank", "Ticker", "Sector", f"Price ({currency})", "P/E", "Vol ×", "RSI",
        "52W Range", "vs 200DMA", "Score", "Chart",
    ]
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            f"Price ({currency})": st.column_config.NumberColumn(format="%.2f"),
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
            "Score": st.column_config.ProgressColumn(format="%.1f", min_value=0, max_value=100),
            "Chart": st.column_config.LinkColumn("Chart", display_text="📈 Open"),
        },
    )

    st.bar_chart(result.set_index("ticker")["score"])
