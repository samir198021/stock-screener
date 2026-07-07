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

# Top BSE large-caps (dual-listed with NSE — same companies, BSE prices). Yahoo uses ".BO".
# Verified to resolve on Yahoo; LTIM.BO and TATAMOTORS.BO are not on Yahoo's BSE feed, so omitted.
# Note: BSE has no near-live Chartink path here, so this market always uses Yahoo (delayed).
BSE_50 = [
    "RELIANCE.BO", "TCS.BO", "HDFCBANK.BO", "ICICIBANK.BO", "INFY.BO",
    "HINDUNILVR.BO", "ITC.BO", "SBIN.BO", "BHARTIARTL.BO", "BAJFINANCE.BO",
    "KOTAKBANK.BO", "LT.BO", "HCLTECH.BO", "AXISBANK.BO", "MARUTI.BO",
    "ASIANPAINT.BO", "SUNPHARMA.BO", "TITAN.BO", "ULTRACEMCO.BO", "WIPRO.BO",
    "ONGC.BO", "NTPC.BO", "POWERGRID.BO", "NESTLEIND.BO", "TATASTEEL.BO",
    "JSWSTEEL.BO", "ADANIENT.BO", "ADANIPORTS.BO", "COALINDIA.BO", "BAJAJFINSV.BO",
    "GRASIM.BO", "HDFCLIFE.BO", "SBILIFE.BO", "BRITANNIA.BO", "DIVISLAB.BO",
    "DRREDDY.BO", "CIPLA.BO", "EICHERMOT.BO", "HEROMOTOCO.BO", "HINDALCO.BO",
    "INDUSINDBK.BO", "TECHM.BO", "APOLLOHOSP.BO", "BPCL.BO", "TATACONSUM.BO",
    "BAJAJ-AUTO.BO", "M&M.BO", "SHRIRAMFIN.BO",
]

MARKETS = {
    "India (Nifty 500 — top 50)": {"tickers": NIFTY_50, "currency": "₹", "suffix": ".NS"},
    "India (BSE — top 50)":       {"tickers": BSE_50,   "currency": "₹", "suffix": ".BO"},
    "US (S&P 500 — top 50)":      {"tickers": SP_50,     "currency": "$", "suffix": ""},
}

# Hard cap applied everywhere, per the current requirement.
MAX_STOCKS = 50


def get_universe(market_label):
    """Return (tickers, currency_symbol) for a market label, capped at MAX_STOCKS."""
    m = MARKETS[market_label]
    return m["tickers"][:MAX_STOCKS], m["currency"]
