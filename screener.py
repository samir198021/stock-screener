"""Pure screening logic — no Streamlit here so it stays testable.

Pipeline:
    fetch_price_history()  ->  per-ticker OHLCV (1y, for 52-week range + 200-DMA)
    fetch_fundamentals()   ->  per-ticker {eps, sector} (cached hourly by the caller)
    compute_metrics()      ->  price, P/E, volume ratio, RSI + research columns
    screen_and_rank()      ->  filter by the three rules, rank by composite score
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd
import yfinance as yf

# Default thresholds (overridable from the UI).
PE_MAX = 20.0
VOLUME_MULTIPLE = 1.5
RSI_MIN = 50.0
RSI_PERIOD = 14

# "Conviction" = how many BONUS strength signals align, beyond the 3 mandatory filters.
# These are deliberately stricter than the filters, so a high count = an unusually strong setup.
STRONG_RSI = 60.0        # momentum clearly strong, not just > 50
STRONG_VOLUME = 2.0      # a real spike, not just above average
CHEAP_PE = 15.0          # cheaper than the 20 ceiling

# "Extended" = already run up hard, so higher pullback (mean-reversion) risk. These get flagged
# 🟠 so you DON'T chase them at the open — the edge is usually in strong-but-not-yet-overcooked names.
EXTENDED_RSI = 80.0            # overbought
EXTENDED_ABOVE_200DMA = 25.0  # price > 25% above its 200-day average = stretched
EXTENDED_DAY_MOVE = 8.0       # already up > 8% today (Chartink path) = chasing


def fetch_price_history(tickers, period="1y", interval="1d"):
    """Batch-download OHLCV for all tickers in ONE request.

    Returns {ticker: DataFrame}. 1 year of daily bars covers the 14-period RSI, 20-day
    volume average, the 52-week high/low range, and the 200-day moving average.
    """
    if not tickers:
        return {}

    data = yf.download(
        tickers,
        period=period,
        interval=interval,
        group_by="ticker",
        auto_adjust=False,
        threads=True,
        progress=False,
    )

    result = {}
    if len(tickers) == 1:
        result[tickers[0]] = data
    else:
        top = data.columns.get_level_values(0)
        for t in tickers:
            if t in top:
                result[t] = data[t].dropna(how="all")
    return result


def _one_fundamental(ticker):
    """Trailing EPS + sector for a single ticker (blank/None on any failure)."""
    try:
        info = yf.Ticker(ticker).get_info()
        return ticker, {"eps": info.get("trailingEps"), "sector": info.get("sector")}
    except Exception:
        return ticker, {"eps": None, "sector": None}


def fetch_fundamentals(tickers, max_workers=10):
    """Per-ticker {eps, sector}, fetched CONCURRENTLY so first load isn't 50 sequential
    round-trips. The caller caches this for ~1h (these barely move intraday), so P/E can be
    recomputed cheaply from the live price each cycle."""
    if not tickers:
        return {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tickers))) as pool:
        return dict(pool.map(_one_fundamental, tickers))


def compute_rsi(close: pd.Series, period: int = RSI_PERIOD) -> float:
    """Wilder's RSI. Returns the most recent value (NaN if not enough data)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - 100 / (1 + rs)
    return float(rsi.iloc[-1])


def compute_metrics(ticker: str, hist: pd.DataFrame, fundamentals):
    """Turn one ticker's history + fundamentals into the row dict used by the table,
    or None if there isn't enough data.

    Row keys: ticker, price, pe, volume_ratio, rsi, sector, range52 (0-100 position in the
    52-week range), vs_200dma (% above/below the 200-day MA), chart (Yahoo quote URL).
    """
    if hist is None or hist.empty or "Close" not in hist or "Volume" not in hist:
        return None

    close = hist["Close"].dropna()
    volume = hist["Volume"].dropna()
    # Need >20 prior days for the volume average plus the latest bar, and >=14 for RSI.
    if len(close) < RSI_PERIOD + 1 or len(volume) < 21:
        return None

    price = float(close.iloc[-1])
    latest_vol = float(volume.iloc[-1])
    avg20 = float(volume.iloc[-21:-1].mean())  # the 20 bars BEFORE the latest
    vol_ratio = latest_vol / avg20 if avg20 > 0 else np.nan

    rsi = compute_rsi(close)

    fundamentals = fundamentals or {}
    eps = fundamentals.get("eps")
    sector = fundamentals.get("sector") or "—"

    pe = None
    if eps is not None and eps > 0:
        pe = price / float(eps)

    # Where the price sits in its 52-week range: 0% = at the low, 100% = at the high.
    high52 = float(close.max())
    low52 = float(close.min())
    span = high52 - low52
    range52 = (price - low52) / span * 100.0 if span > 0 else np.nan

    # Distance from the 200-day moving average (needs ~200 bars).
    vs_200dma = np.nan
    if len(close) >= 200:
        ma200 = float(close.rolling(200).mean().iloc[-1])
        if ma200 > 0:
            vs_200dma = (price - ma200) / ma200 * 100.0

    # Trend direction from moving-average alignment (the classic "is it really trending up" read).
    ma20 = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else np.nan
    ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else np.nan
    trend = _trend(price, ma20, ma50)

    return {
        "ticker": ticker,
        "price": price,
        "pe": pe,
        "volume_ratio": vol_ratio,
        "rsi": rsi,
        "sector": sector,
        "range52": range52,
        "vs_200dma": vs_200dma,
        "trend": trend,
        "chart": "https://finance.yahoo.com/quote/" + ticker,
    }


def _trend(price, ma20, ma50):
    """Plain-English trend from price vs its 20- and 50-day averages.
    ⬆️ Uptrend = price above both, 20 above 50 (aligned up). ⬇️ Fading = below both."""
    if np.isnan(ma20) or np.isnan(ma50):
        return "—"
    if price > ma20 and ma20 > ma50:
        return "⬆️ Uptrend"
    if price > ma20:
        return "↗️ Turning up"
    if price < ma20 and price < ma50:
        return "⬇️ Fading"
    return "➡️ Pausing"


def scan_universe(tickers, history, fundamentals_fetcher,
                  pe_max=PE_MAX, vol_mult=VOLUME_MULTIPLE, rsi_min=RSI_MIN):
    """Efficient two-stage scan for large universes (e.g. Nifty 500).

    Stage 1: compute technicals (RSI, volume ratio, 52w, 200-DMA) for every ticker from the
             already-downloaded `history` — no network.
    Stage 2: keep only names passing the RSI + volume filters, then fetch fundamentals
             (P/E, sector) ONLY for those survivors via `fundamentals_fetcher(list_of_tickers)`.
             This turns ~500 slow per-stock fundamental calls into just a handful.
    Returns (ranked_dataframe, scanned_count).
    """
    base = []
    for t in tickers:
        m = compute_metrics(t, history.get(t), None)  # technicals only (pe=None)
        if m:
            base.append(m)

    survivors = [m for m in base if m["rsi"] > rsi_min and m["volume_ratio"] > vol_mult]
    if survivors:
        funds = fundamentals_fetcher([m["ticker"] for m in survivors]) or {}
        for m in survivors:
            f = funds.get(m["ticker"]) or {}
            eps = f.get("eps")
            m["sector"] = f.get("sector") or "—"
            if eps and eps > 0:
                m["pe"] = m["price"] / float(eps)

    result = screen_and_rank(survivors, pe_max, vol_mult, rsi_min)
    return result, len(base)


def _normalize(s: pd.Series) -> pd.Series:
    """Min-max normalize to [0,1]; if all values are equal, everyone scores 1.0."""
    rng = s.max() - s.min()
    if rng == 0 or np.isnan(rng):
        return pd.Series(1.0, index=s.index)
    return (s - s.min()) / rng


def screen_and_rank(metrics, pe_max=PE_MAX, vol_mult=VOLUME_MULTIPLE, rsi_min=RSI_MIN,
                    require_technicals=True):
    """Filter by the rules and rank survivors by conviction, then composite score.

    require_technicals=True  -> apply all three filters (P/E, volume, RSI) here (Yahoo path).
    require_technicals=False -> apply only the P/E filter; RSI + volume were already enforced
                                near-live upstream (Chartink path), so don't re-drop on the
                                slightly-delayed Yahoo recompute.
    Returns a DataFrame (possibly empty) sorted best-first, plus a 'rank' column.
    """
    rows = [m for m in metrics if m]
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.dropna(subset=["pe", "volume_ratio", "rsi"])
    cond = (df["pe"] > 0) & (df["pe"] < pe_max)
    if require_technicals:
        cond &= (df["volume_ratio"] > vol_mult) & (df["rsi"] > rsi_min)
    passed = df[cond].copy()

    if passed.empty:
        return passed

    score = (
        _normalize(passed["rsi"])
        + _normalize(passed["volume_ratio"])
        + _normalize(1.0 / passed["pe"])
    ) / 3.0 * 100.0
    passed["score"] = score

    # Conviction (0-5): count of bonus signals that agree. NaNs compare False -> not counted.
    passed["conviction"] = (
        (passed["vs_200dma"] > 0).astype(int)          # in a longer-term uptrend
        + (passed["range52"] >= 50).astype(int)        # in the upper half of its 52-week range
        + (passed["rsi"] >= STRONG_RSI).astype(int)    # strong momentum
        + (passed["volume_ratio"] >= STRONG_VOLUME).astype(int)  # genuine volume spike
        + (passed["pe"] <= CHEAP_PE).astype(int)       # cheaper than the ceiling
    )

    # Flag "extended" names (already run up hard) — higher next-day pullback risk, so don't chase.
    extended = (passed["rsi"] >= EXTENDED_RSI) | (passed["vs_200dma"].fillna(0) >= EXTENDED_ABOVE_200DMA)
    if "pct_change" in passed.columns:
        extended = extended | (passed["pct_change"].fillna(0) >= EXTENDED_DAY_MOVE)
    passed["extended"] = extended

    # Plain-English strength read (NOT advice). "Extended" overrides Strong so you don't chase it.
    def _signal(row):
        if row["extended"]:
            return "🟠 Extended"
        c = row["conviction"]
        return "🟢 Strong" if c >= 4 else ("🟡 Watch" if c == 3 else "🔴 Weak")
    passed["signal"] = passed.apply(_signal, axis=1)

    # Most-aligned setups first; composite score breaks ties.
    passed = passed.sort_values(["conviction", "score"], ascending=False).reset_index(drop=True)
    passed.insert(0, "rank", passed.index + 1)
    return passed
