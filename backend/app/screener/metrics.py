"""Pure metrics computed from cached OHLCV bars. No I/O, no dependencies."""
from __future__ import annotations

TRADING_DAYS_YEAR = 252


def sma(closes: list[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def relative_volume(bars: list[tuple], lookback: int = 50) -> float | None:
    if len(bars) < lookback + 1:
        return None
    last_vol = bars[-1][5]
    if last_vol is None:
        return None
    prev = [b[5] for b in bars[-(lookback + 1):-1]]
    if not prev or any(v is None for v in prev):
        return None
    avg = sum(v for v in prev) / len(prev)
    if avg == 0:
        return None
    return last_vol / avg


def pct_off_52w_high(bars: list[tuple]) -> float | None:
    window = bars[-TRADING_DAYS_YEAR:]
    if len(window) < TRADING_DAYS_YEAR:
        return None
    high = max(b[2] for b in window)
    return (window[-1][4] / high - 1.0) * 100.0 if high else None


def pct_above_52w_low(bars: list[tuple]) -> float | None:
    window = bars[-TRADING_DAYS_YEAR:]
    if len(window) < TRADING_DAYS_YEAR:
        return None
    low = min(b[3] for b in window)
    return (window[-1][4] / low - 1.0) * 100.0 if low else None


def one_year_return(bars: list[tuple]) -> float | None:
    if len(bars) < TRADING_DAYS_YEAR + 1:
        return None
    return bars[-1][4] / bars[-(TRADING_DAYS_YEAR + 1)][4] - 1.0


def rs_rank(symbols_bars: dict[str, list[tuple]], *, min_bars: int = TRADING_DAYS_YEAR + 1) -> dict[str, float]:
    """IBD-style RS proxy: percentile (1-99) of 1-year return across cached symbols."""
    returns = {sym: one_year_return(bars) for sym, bars in symbols_bars.items()}
    returns = {k: v for k, v in returns.items() if v is not None}
    if not returns:
        return {}
    ordered = sorted(returns.values())
    n = len(ordered)
    ranks: dict[str, float] = {}
    for sym, r in returns.items():
        # percentile with ties averaged; 1 + (pos/(n-1))*98 maps 0..1 -> 1..99
        lo = next(i for i, v in enumerate(ordered) if v >= r)
        hi = next(i for i in range(n - 1, -1, -1) if ordered[i] <= r)
        pos = (lo + hi) / 2.0
        ranks[sym] = round(1.0 + pos / max(n - 1, 1) * 98.0, 1)
    return ranks
