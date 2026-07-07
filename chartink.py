"""Near-live NSE screening via Chartink's (unofficial) screener endpoint.

Chartink has no official API — this replicates exactly what the website does when you run a
scan (grab the CSRF token from the page, POST the scan clause). It is therefore best-effort:
every call can fail (site change, cloud-IP block, rate limit), so callers MUST fall back to
Yahoo. Keep this module dependency-light (requests only) and side-effect free.
"""

from __future__ import annotations

import re

import requests

BASE = "https://chartink.com"
SCREENER_URL = BASE + "/screener/"
PROCESS_URL = BASE + "/screener/process"

_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def build_scan_clause(rsi_min: float = 50, vol_mult: float = 1.5) -> str:
    """Chartink scan-language clause: cash stocks with RSI(14) above a floor and today's volume
    above a multiple of its 20-day SMA. (P/E is not reliably available here — applied via Yahoo.)"""
    return ("( {cash} ( latest rsi( 14 ) > %g and "
            "latest volume > %g * latest sma( volume , 20 ) ) )" % (rsi_min, vol_mult))


def fetch_scan(rsi_min: float = 50, vol_mult: float = 1.5, timeout: int = 15) -> list[dict]:
    """Run the near-live scan and return a list of rows:
    {'nsecode','name','close','per_chg','volume'}.  Raises on ANY failure."""
    scan_clause = build_scan_clause(rsi_min, vol_mult)

    session = requests.Session()
    session.headers.update({"User-Agent": _UA})

    home = session.get(SCREENER_URL, timeout=timeout)
    home.raise_for_status()

    match = re.search(r'name="csrf-token"\s+content="([^"]+)"', home.text)
    if not match:
        raise RuntimeError("Chartink CSRF token not found (site layout may have changed)")
    token = match.group(1)

    resp = session.post(
        PROCESS_URL,
        headers={"x-csrf-token": token, "x-requested-with": "XMLHttpRequest"},
        data={"scan_clause": scan_clause},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("data", [])
