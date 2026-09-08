from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.screener.metrics import (
    sma, relative_volume, pct_off_52w_high, pct_above_52w_low, one_year_return, rs_rank,
)


def _bars(closes: list[float], volumes: list[float] | None = None) -> list[tuple]:
    vols = volumes or [1000.0] * len(closes)
    return [(i, c, c, c, c, v) for i, (c, v) in enumerate(zip(closes, vols))]


def test_sma_basic() -> None:
    assert sma([1.0, 2.0, 3.0, 4.0], 3) == 3.0
    assert sma([1.0, 2.0], 3) is None


def test_relative_volume() -> None:
    vols = [1000.0] * 50 + [2500.0]
    bars = [(i, 10.0, 10.0, 10.0, 10.0, v) for i, v in enumerate(vols)]
    assert relative_volume(bars, lookback=50) == 2.5
    assert relative_volume(bars[:10], lookback=50) is None


def test_pct_off_high_and_above_low() -> None:
    bars = [(i, 100.0, 100.0, 50.0, 95.0, 1000.0) for i in range(252)]
    assert abs(pct_off_52w_high(bars) - (-5.0)) < 1e-9
    assert abs(pct_above_52w_low(bars) - 90.0) < 1e-9
    assert pct_off_52w_high(bars[:10]) is None


def test_one_year_return_and_rs_rank() -> None:
    up = _bars([100.0 + i for i in range(253)])
    flat = _bars([100.0] * 253)
    down = _bars([200.0 - i for i in range(253)])
    assert abs(one_year_return(up) - (352.0 / 100.0 - 1.0)) < 1e-9

    ranks = rs_rank({"UP": up, "FLAT": flat, "DOWN": down})
    assert ranks["UP"] == 99.0
    assert ranks["FLAT"] == 50.0
    assert ranks["DOWN"] == 1.0
    assert "SHORT" not in rs_rank({"SHORT": _bars([1.0, 2.0])})


if __name__ == "__main__":
    test_sma_basic()
    print("sma passed")
    test_relative_volume()
    print("relative_volume passed")
    test_pct_off_high_and_above_low()
    print("off-high/above-low passed")
    test_one_year_return_and_rs_rank()
    print("return/rs_rank passed")
