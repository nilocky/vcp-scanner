from __future__ import annotations

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app.main as main
from app.db.cache import BarCache

client = TestClient(main.app)


def test_market_regime_above_sma200() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    # rising closes: close climbs above its own 200-sma
    bars = [(i, c, c + 1.0, c - 1.0, c, 1000.0) for i, c in enumerate([100.0 + i for i in range(300)])]

    async def fake_fetch(symbol, **kw):
        from app.scanner.history import Bar
        return [Bar(symbol=symbol, ts=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=b[5]) for b in bars]

    with mock.patch.object(main, "_cache", cache), mock.patch(
        "app.main.fetch_history_bars", side_effect=fake_fetch
    ):
        res = client.get("/api/v1/market/regime")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ticker"] == "SPY"
    assert body["above_sma200"] is True
    assert body["spy_close"] == bars[-1][4]
    assert body["spy_sma200"] > 0


if __name__ == "__main__":
    test_market_regime_above_sma200()
    print("market regime passed")
