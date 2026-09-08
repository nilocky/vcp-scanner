"""Offline + live verification for the TradingView Minervini Trend Template scanner.

Run offline rule checks:           python tests/test_tv_scanner.py
Run checks + live scan:            python tests/test_tv_scanner.py --live
Or as pytest:                      pytest tests/test_tv_scanner.py
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.scanner.client import TradingViewScannerClient, apply_rs_proxy, parse_scan_response  # noqa: E402
from app.scanner.filters import (  # noqa: E402
    COLUMNS,
    HIGH_PROXIMITY_RATIO,
    LOW_DISTANCE_RATIO,
    MIN_PRICE,
    MIN_TURNOVER,
    RS_MIN,
    SMA_SLOPE_LOOKBACK,
    build_minervini_trend_template_payload,
)


def test_payload_rules() -> None:
    payload = build_minervini_trend_template_payload()
    filters = payload["filter"]

    def find(left: str, op: str, right=None) -> dict:
        matches = [f for f in filters if f["left"] == left and f["operation"] == op and (right is None or f["right"] == right)]
        assert len(matches) == 1, f"expected one {op} filter on {left} right={right}, got {len(matches)}"
        return matches[0]

    assert find("close", "greater", MIN_PRICE)["right"] == MIN_PRICE
    assert find("Value.Traded", "egreater")["right"] == MIN_TURNOVER
    assert find("close", "greater", "SMA50")["right"] == "SMA50"
    assert find("SMA50", "greater")["right"] == "SMA150"
    assert find("SMA150", "greater")["right"] == "SMA200"
    # API caps shifted-column filters at [1]; the 22-day slope is a client-side Phase 2 check
    assert find("SMA200", "greater")["right"] == "SMA200[1]"
    assert SMA_SLOPE_LOOKBACK == 22

    above = [x for x in filters if x["operation"] == "above%"]
    assert {"price_52_week_high": HIGH_PROXIMITY_RATIO, "price_52_week_low": LOW_DISTANCE_RATIO} == {
        x["right"][0]: x["right"][1] for x in above
    }

    assert payload["columns"] == COLUMNS
    assert payload["markets"] == ["america"]
    assert payload["range"] == [0, 1000]
    assert len(filters) == 10


def test_client_parsing() -> None:
    payload = build_minervini_trend_template_payload()
    columns = payload["columns"]
    body = {
        "totalCount": 2,
        "data": [
            {"s": "NASDAQ:AAPL", "d": ["AAPL", 200.0, 205.0, 198.0, 202.5, 40_000_000, 8_100_000_000, 190.0, 180.0, 170.0, 210.0, 100.0, 45.0]},
            {"s": "NYSE:BAD", "d": ["BAD", None, None, None, None, None, None, None, None, None, None, None, None]},
        ],
    }
    parsed = parse_scan_response(body, columns)

    assert len(parsed) == 1
    assert parsed[0].exchange == "NASDAQ"
    assert parsed[0].symbol == "AAPL"
    assert parsed[0].close == 202.5
    assert parsed[0].perf_y == 45.0
    assert parsed[0].value_traded == 8_100_000_000.0


def test_rs_proxy() -> None:
    payload = build_minervini_trend_template_payload()
    columns = payload["columns"]

    def row(sym: str, perf: float | None) -> dict:
        return {"s": f"NASDAQ:{sym}", "d": [sym, None, None, None, 10.0, 1, 1, None, None, None, None, None, perf]}

    body = {"totalCount": 4, "data": [row("A", 10.0), row("B", 20.0), row("C", 30.0), row("D", None)]}
    ranked = apply_rs_proxy(parse_scan_response(body, columns), rs_min=0.0)
    by_sym = {r.symbol: r for r in ranked}

    assert by_sym["C"].rs == 99.0  # top 1-year performer -> RS ~99
    assert by_sym["B"].rs == 66.0  # (2/3)*99
    assert by_sym["A"].rs == 33.0  # (1/3)*99
    assert by_sym["D"].rs == 0.0  # missing Perf.Y cannot be ranked
    assert RS_MIN == 70.0

    kept = apply_rs_proxy(parse_scan_response(body, columns))
    assert len(kept) == 1  # only C clears rs >= 70


async def _live_scan() -> None:
    total, results = await TradingViewScannerClient().scan_minervini_trend_template()
    print(f"totalCount={total}  candidates_after_rs={len(results)}")
    for r in results[:10]:
        print(f"  {r.exchange}:{r.symbol}  close={r.close}  rs={r.rs}  perf_y={r.perf_y}  sma50={r.sma50}  sma200={r.sma200}")
    assert len(results) <= total or total == 0
    assert all(r.rs is not None and r.rs >= 70 for r in results)


if __name__ == "__main__":
    test_payload_rules()
    print("offline rule checks passed")
    test_client_parsing()
    print("client parsing checks passed")
    test_rs_proxy()
    print("rs proxy checks passed")
    if "--live" in sys.argv:
        asyncio.run(_live_scan())
        print("live scan passed")