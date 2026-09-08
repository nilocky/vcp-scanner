"""Historical daily OHLCV ingestion (yfinance) with SQLite caching and Minervini slope re-check."""
from __future__ import annotations

import asyncio

import numpy as np
import pandas as pd
import yfinance as yf
from pydantic import BaseModel

from ..config import Settings, get_settings
from ..db.cache import BarCache


class Bar(BaseModel):
    symbol: str
    ts: int  # UTC epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class BackfillStats(BaseModel):
    candidates: int
    fetched: int
    failed: int
    skipped_cached: int
    slope_failures: int
    survivors: list[str]


def _yf_fetch(tv_symbol: str, period: str) -> list[tuple]:
    """Fetch daily OHLCV rows for a TradingView symbol (runs in a worker thread)."""
    sym = tv_symbol.split(":")[-1].replace(".", "-")
    df = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=True)
    rows: list[tuple] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("Close")):
            continue
        volume = row.get("Volume")
        rows.append(
            (
                int(ts.value // 10**9),  # UTC epoch seconds
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(volume) if not pd.isna(volume) else None,
            )
        )
    return rows


async def fetch_history_bars(symbol: str, period: str = "1y", retries: int = 3) -> list[Bar]:
    for attempt in range(retries):
        try:
            rows = await asyncio.to_thread(_yf_fetch, symbol, period)
        except Exception:
            rows = []
        if rows:
            return [
                Bar(symbol=symbol, ts=ts, open=o, high=h, low=l, close=c, volume=v)
                for ts, o, h, l, c, v in rows
            ]
        if attempt < retries - 1:
            await asyncio.sleep(1.0 * (3**attempt))
    return []


async def backfill_candidates(
    symbols: list[str],
    cache: BarCache,
    period: str = "1y",
    concurrency: int = 5,
    min_bars: int = 200,
) -> BackfillStats:
    sem = asyncio.Semaphore(concurrency)

    async def work(symbol: str) -> str:
        async with sem:
            if cache.has_recent_bars(symbol, min_bars=min_bars):
                return "cached"
            bars = await fetch_history_bars(symbol, period)
            if not bars:
                return "failed"
            cache.upsert_bars(symbol, [(b.ts, b.open, b.high, b.low, b.close, b.volume) for b in bars])
            return "fetched"

    results = await asyncio.gather(*(work(s) for s in symbols))
    fetched = results.count("fetched")
    failed = results.count("failed")
    skipped = results.count("cached")

    survivors: list[str] = []
    slope_failures = 0
    for symbol in symbols:
        bars = cache.get_bars(symbol)
        if bars and sma_slope_ok([Bar(symbol=symbol, ts=t, open=o, high=h, low=l, close=c, volume=v) for t, o, h, l, c, v in bars]):
            survivors.append(symbol)
        else:
            slope_failures += 1

    return BackfillStats(
        candidates=len(symbols),
        fetched=fetched,
        failed=failed,
        skipped_cached=skipped,
        slope_failures=slope_failures,
        survivors=survivors,
    )


def sma_slope_ok(bars: list[Bar], lookback: int = 22) -> bool:
    """True iff SMA200 today > SMA200 `lookback` bars ago (rising ~1 month)."""
    if len(bars) < 200 + lookback + 1:
        return False
    closes = np.asarray([b.close for b in bars], dtype="float64")
    sma200 = np.asarray(pd.Series(closes).rolling(200).mean())
    today = sma200[-1]
    past = sma200[-1 - lookback]
    if np.isnan(today) or np.isnan(past):
        return False
    return today > past


def get_cache(settings: Settings | None = None) -> BarCache:
    settings = settings or get_settings()
    return BarCache(settings.db_path)