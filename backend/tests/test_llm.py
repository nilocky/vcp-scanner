"""Offline checks for the OpenAI-compatible LLM agent (mock transport, no network).

Run directly:      python tests/test_llm.py
Or as pytest:      pytest tests/test_llm.py
"""
from __future__ import annotations

import asyncio
import os
import sys

import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.client import VCPResult, assess_batch, assess_vcp, assess_vcp_cached  # noqa: E402
from app.db.cache import BarCache  # noqa: E402

FAKE_JSON = """{
    "ticker": "SYNTH",
    "vcp_confidence_score": 88,
    "base_type": "Cup with Handle",
    "contraction_stages": [
        {"stage": "T1", "depth_pct": 18.0, "days": 15},
        {"stage": "T2", "depth_pct": 9.0, "days": 8},
        {"stage": "T3", "depth_pct": 4.0, "days": 4}
    ],
    "volume_dryup_confirmed": true,
    "pivot_buy_price": 61.8,
    "suggested_stop_loss": 59.5,
    "risk_reward_ratio": 3.2,
    "verdict": "STRONG_SETUP",
    "ai_commentary": "tight final contraction, volume drying up."
}"""


def _handler(request: httpx.Request) -> httpx.Response:
    assert "/chat/completions" in request.url.path, request.url
    body = request.read().decode()
    assert "contraction_stages" in body, "prompt must carry the real numeric payload"
    return httpx.Response(200, json={"choices": [{"message": {"content": FAKE_JSON}}]})


def test_assess_single() -> None:
    result = VCPResult(
        symbol="SYNTH",
        contractions=[],
        volume_dryup_ratio=0.3,
        pivot_buy_price=61.8,
        stop_loss=59.5,
        verdict="STRONG_SETUP",
    )
    transport = httpx.MockTransport(_handler)
    async def run() -> None:
        a = await assess_vcp("SYNTH", result, base_url="http://x/v1", api_key="k",
                             model="m", timeout=5.0, transport=transport)
        assert a.vcp_confidence_score == 88
        assert a.verdict == "STRONG_SETUP"
        assert a.pivot_buy_price == 61.8
        assert len(a.contraction_stages) == 3
    asyncio.run(run())


def test_retries_on_5xx() -> None:
    calls = {"n": 0}
    def flaky(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"choices": [{"message": {"content": FAKE_JSON}}]})
    result = VCPResult(symbol="S", contractions=[], volume_dryup_ratio=None,
                       pivot_buy_price=None, stop_loss=None, verdict="PREMATURE")
    transport = httpx.MockTransport(flaky)
    async def run() -> None:
        a = await assess_vcp("S", result, base_url="http://x/v1", api_key="",
                             model="m", timeout=5.0, retries=2, transport=transport)
        assert a.ticker == "S"
        assert calls["n"] == 3
    asyncio.run(run())


def test_batch_drops_failures() -> None:
    result = VCPResult(symbol="S", contractions=[], volume_dryup_ratio=None,
                       pivot_buy_price=None, stop_loss=None, verdict="PREMATURE")
    def dead(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)
    transport = httpx.MockTransport(dead)
    async def run() -> None:
        out = await assess_batch([("A", result), ("B", result)], base_url="http://x/v1",
                                 api_key="", model="m", timeout=5.0, transport=transport)
        assert out == []
    asyncio.run(run())


def _tmp_cache() -> BarCache:
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return BarCache(path)


def test_assess_cached_reuses_until_bars_change() -> None:
    result = VCPResult(symbol="SYNTH", contractions=[], volume_dryup_ratio=0.3,
                       pivot_buy_price=61.8, stop_loss=59.5, verdict="STRONG_SETUP")
    bars = [(i, 10.0, 12.0, 9.0, 11.0, 1000.0) for i in range(250)]
    calls = {"n": 0}
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": FAKE_JSON}}]})
    transport = httpx.MockTransport(handler)
    cache = _tmp_cache()

    async def run() -> None:
        a1 = await assess_vcp_cached("SYNTH", result, bars, cache, base_url="http://x/v1",
                                     api_key="k", model="m", timeout=5.0, transport=transport)
        a2 = await assess_vcp_cached("SYNTH", result, bars, cache, base_url="http://x/v1",
                                     api_key="k", model="m", timeout=5.0, transport=transport)
        assert a1.vcp_confidence_score == 88
        assert a2.vcp_confidence_score == 88
        assert a1 == a2
        assert calls["n"] == 1, "identical bars must not re-invoke the LLM"

        changed = bars + [(300, 10.0, 12.0, 9.0, 11.5, 1100.0)]
        await assess_vcp_cached("SYNTH", result, changed, cache, base_url="http://x/v1",
                                api_key="k", model="m", timeout=5.0, transport=transport)
        assert calls["n"] == 2, "changed bars must invalidate the cache"
    asyncio.run(run())


if __name__ == "__main__":
    test_assess_single()
    print("assess_single passed")
    test_retries_on_5xx()
    print("retries passed")
    test_batch_drops_failures()
    print("batch drops passed")
    test_assess_cached_reuses_until_bars_change()
    print("cached reuse passed")