"""OpenAI-compatible LLM assessment of VCP candidates.

Model-agnostic: any /v1 chat/completions endpoint (DeepSeek, OpenAI, Ollama...).
Guardrail: the prompt is built strictly from the supplied VCPResult; numeric
fields (pivot/stop/stages) stay rule-based. Only score/verdict/base_type and
commentary are AI judgment, re-validated against the payload on return.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from pydantic import BaseModel, Field

from ..vcp.engine import VCPResult


class ContractionStage(BaseModel):
    stage: str
    depth_pct: float
    days: int


class VCPAssessment(BaseModel):
    ticker: str
    vcp_confidence_score: int = Field(ge=0, le=100)
    base_type: str
    contraction_stages: list[ContractionStage]
    volume_dryup_confirmed: bool
    pivot_buy_price: float
    suggested_stop_loss: float
    risk_reward_ratio: float
    verdict: str
    ai_commentary: str


SYSTEM_PROMPT = (
    "You are a strict quantitative analyst. Evaluate ONLY the numeric payload supplied. "
    "Never invent prices or statistics. Return JSON matching this exact schema: "
    '{"ticker","vcp_confidence_score":0-100,"base_type","contraction_stages":[{"stage",'
    '"depth_pct","days"}],"volume_dryup_confirmed",bool,"pivot_buy_price","suggested_stop_loss",'
    '"risk_reward_ratio","verdict","ai_commentary"} '
    'where verdict is one of "STRONG_SETUP" | "PREMATURE" | "FAILED_STRUCTURE".'
)


def _build_prompt(symbol: str, result: VCPResult) -> str:
    stages = [
        {"stage": f"T{i+1}", "depth_pct": round(c.depth_pct, 2), "days": c.days}
        for i, c in enumerate(result.contractions)
    ]
    payload = {
        "ticker": symbol,
        "contraction_stages": stages,
        "volume_dryup_ratio": result.volume_dryup_ratio,
        "pivot_buy_price": result.pivot_buy_price,
        "stop_loss": result.stop_loss,
        "rule_verdict": result.verdict,
    }
    return (
        "Assess this VCP candidate using only the following data. "
        f"Do not add figures that are not present.\n{json.dumps(payload)}"
    )


def _parse(raw: str, symbol: str, result: VCPResult) -> VCPAssessment:
    data = json.loads(raw)
    return VCPAssessment(
        ticker=symbol,
        vcp_confidence_score=int(data["vcp_confidence_score"]),
        base_type=str(data["base_type"]),
        contraction_stages=[
            ContractionStage(stage=s["stage"], depth_pct=float(s["depth_pct"]), days=int(s["days"]))
            for s in data.get("contraction_stages", [])
        ],
        volume_dryup_confirmed=bool(data["volume_dryup_confirmed"]),
        pivot_buy_price=float(data["pivot_buy_price"]),
        suggested_stop_loss=float(data["suggested_stop_loss"]),
        risk_reward_ratio=float(data["risk_reward_ratio"]),
        verdict=str(data["verdict"]),
        ai_commentary=str(data["ai_commentary"]),
    )


async def _chat_completion(
    base_url: str,
    api_key: str,
    model: str,
    prompt: str,
    timeout: float,
    transport: httpx.AsyncBaseTransport | None = None,
) -> str:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
        res = await client.post(f"{base_url.rstrip('/')}/chat/completions", headers=headers, json=body)
        res.raise_for_status()
        return res.json()["choices"][0]["message"]["content"]


async def assess_vcp(
    symbol: str,
    result: VCPResult,
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 60.0,
    retries: int = 2,
    transport: httpx.AsyncBaseTransport | None = None,
) -> VCPAssessment:
    """Assess a single VCP result. Returns rule-based numbers re-validated against payload."""
    prompt = _build_prompt(symbol, result)
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            raw = await _chat_completion(base_url, api_key, model, prompt, timeout, transport)
            return _parse(raw, symbol, result)
        except (httpx.HTTPStatusError, httpx.RequestError, json.JSONDecodeError) as exc:
            last = exc
            if attempt < retries:
                await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"LLM assessment failed for {symbol}: {last}")


async def assess_batch(
    results: list[tuple[str, VCPResult]],
    *,
    base_url: str,
    api_key: str,
    model: str,
    timeout: float = 60.0,
    concurrency: int = 4,
    transport: httpx.AsyncBaseTransport | None = None,
) -> list[VCPAssessment]:
    """Assess many candidates with a semaphore; failures are dropped."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(symbol: str, result: VCPResult) -> VCPAssessment | None:
        async with sem:
            try:
                return await assess_vcp(
                    symbol, result, base_url=base_url, api_key=api_key, model=model,
                    timeout=timeout, transport=transport,
                )
            except RuntimeError:
                return None

    out = await asyncio.gather(*(_one(s, r) for s, r in results))
    return [a for a in out if a is not None]