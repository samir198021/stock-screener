# 📈 Near-Real-Time Stock Screener

Screens Indian (Nifty 500) or US (S&P 500) stocks with `yfinance` and shows ranked results in an
auto-refreshing Streamlit dashboard. Currently capped at the **top 50 names per market**.

## Filters (all must pass)
- Trailing **P/E < 20** (positive earnings only)
- **Volume > 1.5×** the 20-day average (default; adjustable in the UI)
- **RSI(14) > 50**

Survivors are ranked by a composite score (normalized RSI + volume ratio + inverse P/E).

## Setup & run
```bash
cd stock-screener
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py
```

Then open **http://localhost:8501** (Streamlit's default port).
If 8501 is taken: `streamlit run app.py --server.port 8600`.

## Using it
- Pick **Market**, tweak the **filters**, and toggle **Auto-refresh** (30/60/120/300s) in the sidebar.
- **Rescan now** forces an immediate refetch.

## Notes
- Data is Yahoo-delayed (~15 min) — "near real-time," not tick data.
- Rate limits: one batched price request per refresh + hourly-cached fundamentals. See `CLAUDE.md`.
- To expand beyond 50, extend the lists in `universe.py`.

## Deploy to Streamlit Community Cloud (always-on, no PC needed)
Runs 24/7 on Streamlit's servers with a public URL you can open on any device / network.

1. **Create a GitHub repo** (e.g. `stock-screener`) and push this folder:
   ```bash
   git remote add origin https://github.com/<your-username>/stock-screener.git
   git branch -M main
   git push -u origin main
   ```
   (This repo is already `git init`'d with a first commit — you just add your remote and push.)
2. Go to **https://share.streamlit.io** and sign in with GitHub.
3. **New app** → pick your repo, branch **main**, main file **app.py** → **Deploy**.
4. You'll get a permanent link like `https://<your-app>.streamlit.app`. Open it on your phone.

Notes:
- The app is **public** (no login). It contains no secrets — only public market data.
- Free tier **sleeps when idle** and wakes in ~30s on the next visit.
- On shared cloud IPs, Yahoo/`yfinance` may throttle more than from home; caching mitigates it.
  If scans come back thin, switch to a keyed market-data API.
- Python version: set it in the app's **Advanced settings** on Streamlit Cloud (3.11 recommended).
