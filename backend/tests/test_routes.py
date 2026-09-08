"""Route-order regression: literal /vcp/scan must not be shadowed by /vcp/{symbol}."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest.mock as mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

import app.main as main  # noqa: E402
from app.db.cache import BarCache  # noqa: E402
from app.vcp.engine import Contraction, VCPResult  # noqa: E402

client = TestClient(main.app)


def test_scan_routes_not_shadowed_by_symbol_param() -> None:
    """Both /vcp/scan and /vcp/ai/scan must resolve to their handlers, not {symbol}."""
    for path in ("/api/v1/vcp/scan", "/api/v1/vcp/ai/scan"):
        res = client.get(path)
        assert res.status_code == 200, (path, res.status_code, res.text)


def test_single_ai_assessment_returns_502_not_500_on_llm_failure() -> None:
    """A failing LLM call must surface as 502, never an opaque 500."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    symbol = "NYSE:GKOS"
    bars = [(i, 100.0, 110.0, 95.0, 105.0, 1000.0) for i in range(250)]
    cache.upsert_bars(symbol, bars)

    async def boom(*args, **kwargs):
        raise RuntimeError("LLM assessment failed for NYSE:GKOS: 401 Unauthorized")

    with mock.patch.object(main, "assess_vcp_cached", boom), mock.patch.object(
        main, "_cache", cache
    ):
        res = client.get(f"/api/v1/vcp/ai/{symbol}")
    assert res.status_code == 502, res.text
    assert "401" in res.json()["detail"]


def test_watchlist_roundtrip() -> None:
    """include_premature scan persists symbols; /watchlist returns them."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    symbol = "NYSE:GKOS"

    def premature(sym, bars):
        return VCPResult(
            symbol=sym,
            contractions=[Contraction(peak_ts=1, trough_ts=2, depth_pct=10.0, days=3)],
            volume_dryup_ratio=0.7,
            pivot_buy_price=110.0,
            stop_loss=95.0,
            verdict="PREMATURE",
        )

    with mock.patch.object(main, "detect_vcp", premature), mock.patch.object(
        main, "_cache", cache
    ), mock.patch.object(cache, "symbols", return_value=[symbol]):
        res = client.get("/api/v1/vcp/scan?include_premature=true")
        assert res.status_code == 200, res.text
        assert cache.watchlist_symbols() == [symbol]

        res = client.get("/api/v1/watchlist")
    assert res.status_code == 200, res.text
    body = res.json()
    assert [r["symbol"] for r in body["results"]] == [symbol]
    assert body["results"][0]["verdict"] == "PREMATURE"


def test_lifespan_does_not_start_scheduler_without_token() -> None:
    import app.scheduler as sched_mod

    s = main.get_settings()
    old = s.telegram_bot_token
    s.telegram_bot_token = ""
    started = []
    with mock.patch.object(sched_mod, "start_scheduler", side_effect=lambda *a, **k: started.append(1)):
        with TestClient(main.app) as c:
            assert c.get("/health").status_code == 200
    s.telegram_bot_token = old
    assert started == []


if __name__ == "__main__":
    test_scan_routes_not_shadowed_by_symbol_param()
    print("route-order regression passed")
    test_single_ai_assessment_returns_502_not_500_on_llm_failure()
    print("single AI 502 regression passed")
    test_watchlist_roundtrip()
    print("watchlist round-trip passed")