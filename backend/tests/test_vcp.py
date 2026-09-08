"""Offline checks for the VCP contraction engine (synthetic series, no network).

Run directly:      python tests/test_vcp.py
Or as pytest:      pytest tests/test_vcp.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.vcp.engine import detect_vcp  # noqa: E402

START_TS = 1_700_000_000


def _series(closes: list[float], volumes: list[float]) -> list[tuple]:
    bars: list[tuple] = []
    for i, (c, v) in enumerate(zip(closes, volumes)):
        bars.append((START_TS + i, c, c * 1.02, c * 0.98, c, v))
    return bars


def _vcp_series() -> list[tuple]:
    """Rising trend, then 3 shrinking contractions (~18%, ~9%, ~4%) with volume dry-up."""
    closes = list(np.linspace(30.0, 60.0, 200))
    # Contraction 1: -18% over 15 bars
    closes += list(np.linspace(60.0, 49.2, 15))
    closes += list(np.linspace(49.2, 61.0, 10))  # recover to new high
    # Contraction 2: -9% over 8 bars
    closes += list(np.linspace(61.0, 55.5, 8))
    closes += list(np.linspace(55.5, 62.0, 7))
    # Contraction 3: -4% over 4 bars (tight), ends near the top
    closes += list(np.linspace(62.0, 59.5, 4))
    closes += list(np.linspace(59.5, 61.8, 3))
    # Volume: busy in the uptrend, drying toward the final contraction
    vols = [1_000_000.0] * 200
    vols += list(np.linspace(900_000, 600_000, 15)) + [700_000] * 10
    vols += list(np.linspace(650_000, 400_000, 8)) + [500_000] * 7
    vols += list(np.linspace(400_000, 150_000, 4)) + [100_000] * 3
    return _series(closes, vols)


def test_vcp_detected() -> None:
    result = detect_vcp("SYNTH", _vcp_series())
    assert result.verdict == "STRONG_SETUP", result.model_dump()
    assert len(result.contractions) == 3
    depths = [c.depth_pct for c in result.contractions]
    assert all(depths[i] > depths[i + 1] for i in range(len(depths) - 1))
    assert depths[-1] <= 8.0
    assert result.volume_dryup_ratio is not None and result.volume_dryup_ratio < 0.5
    assert result.pivot_buy_price and result.stop_loss
    assert result.pivot_buy_price > result.stop_loss


def test_random_walk_fails() -> None:
    rng = np.random.default_rng(7)
    closes = [50.0]
    for _ in range(299):
        closes.append(closes[-1] * (1 + rng.normal(0.0, 0.03)))
    vols = [1_000_000.0] * 300
    result = detect_vcp("RAND", _series(closes, vols))
    assert result.verdict != "STRONG_SETUP"


if __name__ == "__main__":
    test_vcp_detected()
    print("vcp detection passed")
    test_random_walk_fails()
    print("random walk rejection passed")