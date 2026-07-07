# CLAUDE.md — Stock Screener

Momentum/value stock screener with a near-real-time Streamlit UI. Fetches quotes via
`yfinance` (Yahoo Finance), filters by three rules, ranks the survivors, and shows them
in an auto-refreshing table.

## What it does
For a chosen market (India / US) it screens a universe of stocks and keeps only those that pass
**all three** filters:
- **Trailing P/E < 20** (and > 0 — negative/missing earnings are excluded)
- **Volume spike > 1.5×** the 20-day average volume (default; adjustable in the UI)
- **RSI (14, Wilder's) > 50**

Survivors are ranked by a **composite score** = equal-weighted blend of normalized RSI,
volume ratio, and inverse P/E (so "cheap + strong momentum + volume spike" ranks highest).

Survivors are then ranked by **Conviction** first (0-5: how many bonus strength signals align —
above 200-DMA, upper half of 52-week range, RSI>=60, volume>=2x, P/E<=15), with the composite
score breaking ties. A stock can pass the 3 filters yet have low conviction (e.g. a bounce in a
downtrend), so this column separates strong setups from weak ones.

Output columns: rank, ticker, sector, current price, P/E, volume ratio, RSI,
52-week range position, % vs 200-day MA, conviction, score, and a chart link.
The extra columns are research aids (not part of the filter) to speed up due diligence.
History is fetched over 1 year so the 52-week range and 200-day MA can be computed.

## Universe (currently capped at 50 per market)
- **India** — top 50 of the Nifty 500 (i.e. the Nifty 50), Yahoo suffix `.NS`.
- **US** — top 50 of the S&P 500 by weight. NOTE: the S&P 500 spans NYSE **and** Nasdaq;
  it's the practical large-cap set. The full NYSE (~2,400 names) is not feasible in near real-time.
- Lists live in `universe.py`. To grow to the full 500/500 later, extend the lists there —
  nothing else needs to change.

## Files
```
stock-screener/
├── CLAUDE.md          this file
├── README.md          run instructions
├── requirements.txt   pinned-ish deps
├── universe.py        ticker lists + get_universe(market)
├── screener.py        pure logic: fetch, RSI, volume ratio, P/E, screen, rank (NO streamlit)
├── chartink.py        near-live NSE scan via Chartink's unofficial endpoint (best-effort)
└── app.py             Streamlit UI + cached network wrappers (port 8501)
```

## Data sources (India can pick; US is Yahoo-only)
- **Yahoo (default for US, optional for India):** ~15 min delayed, but always available.
- **Chartink (India near-live):** `chartink.py` POSTs a scan clause (RSI>min AND volume>mult×20-day
  SMA) to Chartink's screener endpoint and gets today's movers across ALL NSE with near-live price
  and % change. The app takes the top movers by % change, then **enriches them from Yahoo**
  (P/E, sector, 52-week range, 200-DMA, conviction) and applies the P/E filter. Chartink is
  unofficial and may be blocked from cloud IPs, so any failure **falls back to Yahoo automatically**.
  For the Chartink path, `screen_and_rank(..., require_technicals=False)` trusts Chartink's near-live
  RSI/volume and only re-applies the P/E filter.
`screener.py` is intentionally framework-agnostic (no `streamlit` import) so it stays testable;
Streamlit-specific caching lives in `app.py`.

## Run
```
pip install -r requirements.txt
streamlit run app.py
```
Opens on **http://localhost:8501**.

## Rate-limit strategy (Yahoo has no official API; it soft-bans heavy pollers)
- **Prices/volume:** ONE batched `yf.download(...)` call per refresh for all 50 tickers,
  cached for the refresh interval (`st.cache_data(ttl=refresh_seconds)`).
- **Fundamentals (trailing EPS):** fetched per ticker but cached for **1 hour** — EPS barely
  moves intraday. P/E is then recomputed each cycle as `current_price / trailing_eps`, so P/E
  tracks the live price without extra requests.
- Net: ~1 price request/cycle + ~50 EPS requests/hour — comfortably within Yahoo's tolerance.

## Conventions / gotchas
- Volume ratio uses the latest bar vs. the mean of the prior 20 daily bars. During market hours
  the latest daily bar's volume is still accumulating, so early-session ratios read low. Expected.
- "Current price" is the last close from the daily download (updates through the session).
- Data is delayed (Yahoo), typically ~15 min — "near real-time," not tick data.
- Keep all screening math in `screener.py`; keep all UI/caching in `app.py`.
