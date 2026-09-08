"""VCP contraction engine: swing detection, contraction depth sequence, volume dry-up."""
from __future__ import annotations

import numpy as np
from pydantic import BaseModel
from scipy.signal import find_peaks

SWING_PROMINENCE = 0.03
MIN_CONTRACTIONS = 3
MAX_FINAL_DEPTH_PCT = 8.0
VOLUME_DRYUP_THRESHOLD = 0.5


class Contraction(BaseModel):
    peak_ts: int
    trough_ts: int
    depth_pct: float
    days: int


class VCPResult(BaseModel):
    symbol: str
    contractions: list[Contraction]
    volume_dryup_ratio: float | None
    pivot_buy_price: float | None
    stop_loss: float | None
    verdict: str
    relative_volume: float | None = None
    pct_off_52w_high: float | None = None
    rs: float | None = None


def detect_vcp(
    symbol: str,
    bars: list[tuple],
    min_contractions: int = MIN_CONTRACTIONS,
    max_final_depth_pct: float = MAX_FINAL_DEPTH_PCT,
    volume_dryup_threshold: float = VOLUME_DRYUP_THRESHOLD,
) -> VCPResult:
    """Detect a VCP from cached bars. Each bar: (ts, open, high, low, close, volume)."""
    if len(bars) < 200:
        return VCPResult(symbol=symbol, contractions=[], volume_dryup_ratio=None,
                         pivot_buy_price=None, stop_loss=None, verdict="FAILED_STRUCTURE")

    ts = np.asarray([b[0] for b in bars], dtype="int64")
    highs = np.asarray([b[2] for b in bars], dtype="float64")
    lows = np.asarray([b[3] for b in bars], dtype="float64")
    closes = np.asarray([b[4] for b in bars], dtype="float64")
    vols = np.asarray([float(b[5]) if b[5] is not None else 0.0 for b in bars], dtype="float64")

    peaks, _ = find_peaks(highs, prominence=SWING_PROMINENCE * highs)
    troughs, _ = find_peaks(-lows, prominence=SWING_PROMINENCE * lows)

    pairs: list[Contraction] = []
    for p in peaks:
        after = troughs[troughs > p]
        if after.size == 0:
            continue
        t = after[0]
        pairs.append(
            Contraction(
                peak_ts=int(ts[p]),
                trough_ts=int(ts[t]),
                depth_pct=float((highs[p] - lows[t]) / highs[p] * 100.0),
                days=int(t - p),
            )
        )

    recent = pairs[-6:]
    contractions = recent[-min_contractions:] if len(recent) >= min_contractions else recent

    # Volume dry-up: final contraction's last-5-bar avg volume vs 50-day SMA volume.
    dryup_ratio: float | None = None
    if contractions and vols[-1] > 0:
        peak_idx = int(np.argwhere(ts == contractions[-1].peak_ts)[0][0])
        idx = int(np.argwhere(ts == contractions[-1].trough_ts)[0][0])
        window = vols[max(0, idx - 4): idx + 1]
        final_vol = window.mean() if window.size else vols[idx]
        # Baseline = 50-day avg volume just before the final contraction begins.
        if peak_idx >= 50:
            sma50 = float(vols[peak_idx - 50:peak_idx].mean())
            if sma50 > 0:
                dryup_ratio = float(final_vol / sma50)

    verdict = _verdict(contractions, dryup_ratio, min_contractions, max_final_depth_pct, volume_dryup_threshold)

    pivot = stop = None
    if contractions:
        pivot = float(highs[int(np.argwhere(ts == contractions[-1].peak_ts)[0][0])])
        stop = float(lows[int(np.argwhere(ts == contractions[-1].trough_ts)[0][0])])

    return VCPResult(
        symbol=symbol,
        contractions=contractions,
        volume_dryup_ratio=dryup_ratio,
        pivot_buy_price=pivot,
        stop_loss=stop,
        verdict=verdict,
    )


def _verdict(contractions, dryup_ratio, min_contractions, max_final_depth_pct, volume_dryup_threshold) -> str:
    if len(contractions) < min_contractions:
        return "FAILED_STRUCTURE"
    depths = [c.depth_pct for c in contractions]
    if not all(depths[i] > depths[i + 1] for i in range(len(depths) - 1)):
        return "FAILED_STRUCTURE"
    if depths[-1] > max_final_depth_pct:
        return "PREMATURE"
    if dryup_ratio is None or dryup_ratio >= volume_dryup_threshold:
        return "PREMATURE"
    return "STRONG_SETUP"