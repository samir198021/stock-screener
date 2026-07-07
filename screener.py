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

    return {
        "ticker": ticker,
        "price": price,
        "pe": pe,
        "volume_ratio": vol_ratio,
        "rsi": rsi,
        "sector": sector,
        "range52": range52,
        "vs_200dma": vs_200dma,
        "chart": "https://finance.yahoo.com/quote/" + ticker,
    }


def _normalize(s: pd.Series) -> pd.Series:
    """Min-max normalize to [0,1]; if all values are equal, everyone scores 1.0."""
    rng = s.max() - s.min()
    if rng == 0 or np.isnan(rng):
        return pd.Series(1.0, index=s.index)
    return (s - s.min()) / rng


def screen_and_rank(metrics, pe_max=PE_MAX, vol_mult=VOLUME_MULTIPLE, rsi_min=RSI_MIN):
    """Filter by all three rules (AND) and rank survivors by composite score.

    Composite = mean of normalized(RSI), normalized(volume_ratio), normalized(1/PE), ×100.
    Returns a DataFrame (possibly empty) sorted best-first, plus a 'rank' column.
    """
    rows = [m for m in metrics if m]
    df = pd.DataFrame(rows)
    if df.empty:
        return df

    df = df.dropna(subset=["pe", "volume_ratio", "rsi"])
    passed = df[
        (df["pe"] > 0)
        & (df["pe"] < pe_max)
        & (df["volume_ratio"] > vol_mult)
        & (df["rsi"] > rsi_min)
    ].copy()

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

    # Most-aligned setups first; composite score breaks ties.
    passed = passed.sort_values(["conviction", "score"], ascending=False).reset_index(drop=True)
    passed.insert(0, "rank", passed.index + 1)
    return passed
