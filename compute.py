#!/usr/bin/env python3
"""Weekly top-5 winners/losers for DAX, Euro Stoxx 50 and S&P 500."""

import io
import json
import sys
from datetime import datetime, timezone

import pandas as pd
import requests
import yfinance as yf

HEADERS = {"User-Agent": "Mozilla/5.0"}
OUT_PATH = "docs/data/movers.json"
TOP_N = 5


def _get_html(url: str) -> str:
    resp = requests.get(url, headers=HEADERS, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_dax():
    tables = pd.read_html(io.StringIO(_get_html("https://en.wikipedia.org/wiki/DAX")))
    t = tables[4][["Ticker", "Company"]].dropna()
    return dict(zip(t["Ticker"], t["Company"]))


def fetch_estoxx50():
    tables = pd.read_html(io.StringIO(_get_html("https://en.wikipedia.org/wiki/EURO_STOXX_50")))
    t = tables[3][["Ticker", "Name"]].dropna()
    return dict(zip(t["Ticker"], t["Name"]))


def fetch_sp500():
    tables = pd.read_html(io.StringIO(_get_html(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    )))
    t = tables[0][["Symbol", "Security"]].dropna()
    t["Symbol"] = t["Symbol"].str.replace(".", "-", regex=False)
    return dict(zip(t["Symbol"], t["Security"]))


def weekly_return(close: pd.Series) -> float | None:
    close = close.dropna()
    if len(close) < 6:
        return None
    return float((close.iloc[-1] / close.iloc[-6] - 1) * 100)


def compute_movers(names: dict, currency: str, label: str) -> dict:
    tickers = list(names.keys())
    print(f"[{label}] downloading {len(tickers)} tickers...", file=sys.stderr)
    data = yf.download(
        tickers, period="2mo", interval="1d", group_by="ticker",
        auto_adjust=True, threads=True, progress=False,
    )

    rows = []
    for ticker in tickers:
        try:
            close = data[ticker]["Close"]
        except (KeyError, TypeError):
            continue
        ret = weekly_return(close)
        if ret is None:
            continue
        last_price = float(close.dropna().iloc[-1])
        rows.append({
            "ticker": ticker,
            "name": names[ticker],
            "change_pct": round(ret, 2),
            "price": round(last_price, 2),
        })

    rows.sort(key=lambda r: r["change_pct"], reverse=True)
    winners = rows[:TOP_N]
    losers = sorted(rows, key=lambda r: r["change_pct"])[:TOP_N]

    return {
        "label": label,
        "currency": currency,
        "constituents_count": len(rows),
        "winners": winners,
        "losers": losers,
    }


def main():
    result = {
        "last_update": datetime.now(timezone.utc).isoformat(),
        "indices": {},
    }

    sources = [
        ("dax", "DAX", "EUR", fetch_dax),
        ("estoxx50", "Euro Stoxx 50", "EUR", fetch_estoxx50),
        ("sp500", "S&P 500", "USD", fetch_sp500),
    ]

    for key, label, currency, fetch_fn in sources:
        try:
            names = fetch_fn()
        except Exception as e:
            print(f"[{key}] constituent fetch failed: {e}", file=sys.stderr)
            continue
        try:
            result["indices"][key] = compute_movers(names, currency, label)
        except Exception as e:
            print(f"[{key}] compute failed: {e}", file=sys.stderr)
            continue

    if not result["indices"]:
        print("no index data computed, aborting without writing output", file=sys.stderr)
        sys.exit(1)

    with open(OUT_PATH, "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
