"""Async HTTP client for the TradingView America scanner endpoint."""
from __future__ import annotations

import httpx
from pydantic import BaseModel

from ..config import Settings, get_settings
from .filters import COLUMNS, RS_MIN, TRADINGVIEW_SCAN_URL, build_minervini_trend_template_payload

_DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Origin": "https://www.tradingview.com",
    "Referer": "https://www.tradingview.com/",
    "Accept": "text/plain, */*; q=0.01",
}


class ScanResult(BaseModel):
    exchange: str
    symbol: str
    name: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: float | None = None
    value_traded: float | None = None
    sma50: float | None = None
    sma150: float | None = None
    sma200: float | None = None
    high_52w: float | None = None
    low_52w: float | None = None
    perf_y: float | None = None
    rs: float | None = None  # IBD-style relative-strength proxy (1-99), computed client-side


class TradingViewScannerClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    async def scan(self, payload: dict) -> tuple[int, list[ScanResult]]:
        """POST the payload, return (total_count, parsed rows)."""
        timeout = self._settings.tv_scan_timeout_seconds
        async with httpx.AsyncClient(
            timeout=timeout, headers=_DEFAULT_HEADERS, follow_redirects=True
        ) as client:
            resp = await client.post(TRADINGVIEW_SCAN_URL, json=payload)
            resp.raise_for_status()
            try:
                body = resp.json()
            except ValueError as exc:
                raise ValueError(f"TradingView returned non-JSON body: {resp.text[:200]}") from exc

        columns = payload.get("columns") or COLUMNS
        return int(body.get("totalCount", 0)), parse_scan_response(body, columns)

    async def scan_minervini_trend_template(self, limit: int = 1000) -> tuple[int, list[ScanResult]]:
        payload = build_minervini_trend_template_payload(limit)
        total, results = await self.scan(payload)
        return total, apply_rs_proxy(results)


def parse_scan_response(body: dict, columns: list[str]) -> list[ScanResult]:
    """Parse the positional ``d`` rows of a scanner response into ScanResults."""
    results: list[ScanResult] = []
    for item in body.get("data", []):
        d = item.get("d")
        if not d or len(d) < len(columns):
            continue
        vals = dict(zip(columns, d))
        if vals.get("close") is None:
            continue
        exchange, _, symbol = (item.get("s") or ":").partition(":")
        results.append(
            ScanResult(
                exchange=exchange,
                symbol=symbol or vals.get("name", ""),
                name=vals.get("name") or symbol or "",
                open=_as_float(vals.get("open")),
                high=_as_float(vals.get("high")),
                low=_as_float(vals.get("low")),
                close=_as_float(vals.get("close")),
                volume=_as_float(vals.get("volume")),
                value_traded=_as_float(vals.get("Value.Traded")),
                sma50=_as_float(vals.get("SMA50")),
                sma150=_as_float(vals.get("SMA150")),
                sma200=_as_float(vals.get("SMA200")),
                high_52w=_as_float(vals.get("price_52_week_high")),
                low_52w=_as_float(vals.get("price_52_week_low")),
                perf_y=_as_float(vals.get("Perf.Y")),
            )
        )
    return results


def apply_rs_proxy(results: list[ScanResult], rs_min: float = RS_MIN) -> list[ScanResult]:
    """Rank candidates by 1-year return percentile (IBD-style RS rating, 1-99).

    TradingView's scanner exposes no native RS rating field (``RS`` is the
    Serbia country code), so relative strength is proxied from ``Perf.Y`` —
    the same percentile-of-12-month-performance methodology IBD uses.
    """
    n = len(results)
    if n == 0:
        return results

    def _key(i: int) -> float:
        p = results[i].perf_y
        return p if p is not None else float("-inf")

    order = sorted(range(n), key=_key)
    kept: list[ScanResult] = []
    for pos, idx in enumerate(order):
        pct = pos / max(n - 1, 1)
        rs = round(pct * 99.0, 1) if results[idx].perf_y is not None else 0.0
        results[idx].rs = rs
        if rs >= rs_min:
            kept.append(results[idx])
    return kept


def _as_float(value) -> float | None:
    if value is None:
        return None
    return float(value)