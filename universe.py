"""Stock universes for the screener.

Currently capped at the top 50 names per market. To scale up to the full Nifty 500 /
S&P 500 later, just extend these lists — the rest of the app slices whatever is here.
"""

# Top 50 of the Nifty 500 (= Nifty 50). Yahoo Finance uses the ".NS" suffix for NSE.
NIFTY_50 = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
    "HINDUNILVR.NS", "ITC.NS", "SBIN.NS", "BHARTIARTL.NS", "BAJFINANCE.NS",
    "KOTAKBANK.NS", "LT.NS", "HCLTECH.NS", "AXISBANK.NS", "MARUTI.NS",
    "ASIANPAINT.NS", "SUNPHARMA.NS", "TITAN.NS", "ULTRACEMCO.NS", "WIPRO.NS",
    "ONGC.NS", "NTPC.NS", "POWERGRID.NS", "NESTLEIND.NS", "TATAMOTORS.NS",
    "TATASTEEL.NS", "JSWSTEEL.NS", "ADANIENT.NS", "ADANIPORTS.NS", "COALINDIA.NS",
    "BAJAJFINSV.NS", "GRASIM.NS", "HDFCLIFE.NS", "SBILIFE.NS", "BRITANNIA.NS",
    "DIVISLAB.NS", "DRREDDY.NS", "CIPLA.NS", "EICHERMOT.NS", "HEROMOTOCO.NS",
    "HINDALCO.NS", "INDUSINDBK.NS", "TECHM.NS", "APOLLOHOSP.NS", "BPCL.NS",
    "TATACONSUM.NS", "BAJAJ-AUTO.NS", "M&M.NS", "LTIM.NS", "SHRIRAMFIN.NS",
]

# Top 50 of the S&P 500 by index weight. Spans NYSE and Nasdaq listings.
SP_50 = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "GOOG", "BRK-B", "LLY", "AVGO",
    "JPM", "TSLA", "UNH", "XOM", "V", "PG", "MA", "JNJ", "HD", "COST",
    "MRK", "ABBV", "CVX", "CRM", "PEP", "KO", "WMT", "BAC", "ADBE", "MCD",
    "NFLX", "TMO", "CSCO", "ACN", "LIN", "ABT", "DHR", "WFC", "DIS", "INTC",
    "VZ", "TXN", "PM", "INTU", "AMGN", "COP", "CAT", "NEE", "UNP", "LOW",
]

MARKETS = {
    "India (Nifty 500 — top 50)": {"tickers": NIFTY_50, "currency": "₹", "suffix": ".NS"},
    "US (S&P 500 — top 50)":      {"tickers": SP_50,     "currency": "$", "suffix": ""},
}

# Hard cap applied everywhere, per the current requirement.
MAX_STOCKS = 50


def get_universe(market_label):
    """Return (tickers, currency_symbol) for a market label, capped at MAX_STOCKS."""
    m = MARKETS[market_label]
    return m["tickers"][:MAX_STOCKS], m["currency"]
