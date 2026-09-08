"""Minervini Trend Template query builder for the TradingView scanner API.

Only documented TradingView scanner columns and operations are used:
https://scanner.tradingview.com/america/scan
Filter grammar: {"left": <column>, "operation": <op>, "right": <value-or-column>}
"""
from __future__ import annotations

TRADINGVIEW_SCAN_URL = "https://scanner.tradingview.com/america/scan"

MIN_PRICE = 5.0
MIN_TURNOVER = 10_000_000.0  # Value.Traded = close * volume (daily dollar turnover)
RS_MIN = 70.0
HIGH_PROXIMITY_RATIO = 0.75  # close >= 0.75 * 52-week high
LOW_DISTANCE_RATIO = 1.30  # close >= 1.30 * 52-week low
SMA_SLOPE_LOOKBACK = 22  # ~1 trading month (intended rule; API caps shifts at [1])

# Positional order is contractually shared with scanner/client.py row parsing.
COLUMNS = [
    "name",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "Value.Traded",
    "SMA50",
    "SMA150",
    "SMA200",
    "price_52_week_high",
    "price_52_week_low",
    "Perf.Y",
]


def _gt(left: str, right: str | float) -> dict:
    return {"left": left, "operation": "greater", "right": right}


def _egt(left: str, right: str | float) -> dict:
    return {"left": left, "operation": "egreater", "right": right}


def _above_pct(left: str, column: str, pct: float) -> dict:
    return {"left": left, "operation": "above%", "right": [column, pct]}


def build_minervini_trend_template_payload(limit: int = 1000) -> dict:
    """Construct the POST body enforcing the classic Minervini Trend Template."""
    return {
        "markets": ["america"],
        "symbols": {"tickers": [], "query": {"types": []}},
        "options": {"lang": "en"},
        "columns": COLUMNS,
        "sort": {"sortBy": "RS", "sortOrder": "desc"},
        "range": [0, limit],
        "filter": [
            # Universe: common US-listed stocks only
            {"left": "type", "operation": "in_range", "right": ["stock"]},
            {"left": "exchange", "operation": "in_range", "right": ["AMEX", "NASDAQ", "NYSE"]},
            # Minimum price
            _gt("close", MIN_PRICE),
            # Minimum liquidity: daily turnover >= $10M
            _egt("Value.Traded", MIN_TURNOVER),
            # Moving-average alignment: close > SMA50 > SMA150 > SMA200
            _gt("close", "SMA50"),
            _gt("SMA50", "SMA150"),
            _gt("SMA150", "SMA200"),
            # 200-day SMA trending up (server proxy). The documented filter grammar
            # caps shifted-column comparisons at ~1-2 bars (SMA200[22] returns null),
            # so [1] is the strongest available server filter; the 22-day slope is
            # re-checked client-side once Phase 2 historical OHLCV exists.
            _gt("SMA200", "SMA200[1]"),
            # Within 25% of 52-week high
            _above_pct("close", "price_52_week_high", HIGH_PROXIMITY_RATIO),
            # At least 30% above 52-week low
            _above_pct("close", "price_52_week_low", LOW_DISTANCE_RATIO),
        ],
    }