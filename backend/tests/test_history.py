"""Offline + live verification for the historical OHLCV cache and SMA200 slope re-check.

Run offline checks:     python tests/test_history.py
Run checks + live:      python tests/test_history.py --live
Or as pytest:           pytest tests/test_history.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.cache import BarCache  # noqa: E402
from app.scanner.history import Bar, BackfillStats, backfill_candidates, sma_slope_ok  # noqa: E402


def _bars(closes: list[float], start_ts: int = 1_700_000_000) -> list[Bar]:
    return [Bar(symbol="X", ts=start_ts + i, open=c, high=c, low=c, close=c, volume=1.0) for i, c in enumerate(closes)]


def test_cache_roundtrip() -> None:
    db_path = os.path.join(tempfile.mkdtemp(), "t.db")
    cache = BarCache(db_path)
    assert not cache.has_recent_bars("X", min_bars=2)
    cache.upsert_bars("X", [(1, 10.0, 11.0, 9.5, 10.5, 100), (2, 10.5, 11.5, 10.0, 11.0, 200)])
    cache.upsert_bars("X", [(2, 10.6, 11.6, 10.1, 11.1, 300)])  # replace duplicate ts
    assert cache.has_recent_bars("X", min_bars=2)
    rows = cache.get_bars("X")
    assert [(r[0], r[4]) for r in rows] == [(1, 10.5), (2, 11.1)]


def test_sma_slope_ok() -> None:
    rising = [100.0 + i * 0.5 for i in range(300)]
    assert sma_slope_ok(_bars(rising))

    falling = [100.0 - i * 0.5 for i in range(300)]
    assert not sma_slope_ok(_bars(falling))

    too_short = [100.0] * 150
    assert not sma_slope_ok(_bars(too_short))


def test_backfill_stats() -> None:
    import asyncio

    import app.scanner.history as history_mod

    db_path = os.path.join(tempfile.mkdtemp(), "t.db")
    cache = BarCache(db_path)

    async def fake_fetch(symbol: str, period: str = "1y") -> list[Bar]:
        if symbol.endswith("GOOD"):
            return _bars([100.0 + i * 0.5 for i in range(300)])
        return []

    async def run() -> BackfillStats:
        return await backfill_candidates(
            ["x:GOOD", "x:BAD"], cache, period="1y", concurrency=2
        )

    orig = history_mod.fetch_history_bars
    history_mod.fetch_history_bars = fake_fetch
    try:
        stats = asyncio.run(run())
    finally:
        history_mod.fetch_history_bars = orig

    assert stats.candidates == 2
    assert stats.fetched == 1
    assert stats.failed == 1
    assert stats.skipped_cached == 0
    assert stats.survivors == ["x:GOOD"]  # rising SMA200 passes the slope re-check


if __name__ == "__main__":
    test_cache_roundtrip()
    print("cache roundtrip passed")
    test_sma_slope_ok()
    print("slope checks passed")
    test_backfill_stats()
    print("backfill stats passed")
    if "--live" in sys.argv:
        import asyncio

        from app.scanner.client import TradingViewScannerClient

        async def live() -> None:
            _, results = await TradingViewScannerClient().scan_minervini_trend_template(10)
            symbols = [f"{r.exchange}:{r.symbol}" for r in results[:3]]
            db_path = os.path.join(tempfile.mkdtemp(), "live.db")
            cache = BarCache(db_path)
            stats = await backfill_candidates(symbols, cache, period="1y", concurrency=3)
            print(stats.model_dump())
            for symbol in symbols:
                bars = cache.get_bars(symbol)
                assert len(bars) >= 200, f"{symbol} only {len(bars)} bars"

        asyncio.run(live())
        print("live backfill passed")