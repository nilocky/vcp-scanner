import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent.client import VCPAssessment, assess_batch, assess_vcp
from .config import get_settings
from .scanner.client import ScanResult, TradingViewScannerClient
from .scanner.history import BackfillStats, backfill_candidates, get_cache
from .vcp.engine import VCPResult, detect_vcp

settings = get_settings()
_cache = get_cache(settings)

TAGS_METADATA = [
    {"name": "Health", "description": "Service liveness and metadata."},
    {"name": "Scanner", "description": "TradingView Minervini Trend Template scanning."},
    {"name": "History", "description": "Daily OHLCV backfill and cached bars."},
    {"name": "VCP Analysis", "description": "Volatility Contraction Pattern detection."},
]

app = FastAPI(
    title=settings.app_name,
    description=(
        "FastAPI backend for the VCP Scanner: TradingView Trend Template ingestion, "
        "daily OHLCV history caching, and volatility contraction pattern detection."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class HealthResponse(BaseModel):
    status: str
    app: str


class HistoryBar(BaseModel):
    ts: int  # UTC epoch seconds
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None


class HistoryResponse(BaseModel):
    symbol: str
    count: int
    bars: list[HistoryBar]


class ScanResponse(BaseModel):
    total_count: int
    top_10: list[ScanResult]


class VCPScanResponse(BaseModel):
    scanned: int
    qualified: int
    results: list[VCPResult]


class VLIAssessmentResponse(BaseModel):
    scanned: int
    results: list[VCPAssessment]


@app.get("/health", response_model=HealthResponse, tags=["Health"], summary="Service liveness check")
async def health() -> HealthResponse:
    return HealthResponse(status="ok", app=settings.app_name)


@app.get(
    "/api/v1/scan/tradingview-test",
    response_model=ScanResponse,
    tags=["Scanner"],
    summary="Scan the Minervini Trend Template",
    description="Query TradingView's scanner for Trend Template candidates and return the top 10 by RS proxy.",
)
async def tradingview_test() -> ScanResponse:
    client = TradingViewScannerClient()
    try:
        total, results = await client.scan_minervini_trend_template()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"TradingView scanner returned HTTP {exc.response.status_code}",
        ) from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"TradingView scanner unreachable: {exc}") from exc
    return ScanResponse(total_count=total, top_10=results[:10])


@app.get(
    "/api/v1/history/backfill",
    response_model=BackfillStats,
    tags=["History"],
    summary="Backfill daily OHLCV for all candidates",
    description="Scan the Trend Template, backfill daily OHLCV into SQLite, apply the SMA200 slope re-check.",
)
async def history_backfill(limit: int = 1000) -> BackfillStats:
    client = TradingViewScannerClient()
    try:
        _, results = await client.scan_minervini_trend_template(limit)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"TradingView scanner returned HTTP {exc.response.status_code}") from exc
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail=f"TradingView scanner unreachable: {exc}") from exc

    symbols = [f"{r.exchange}:{r.symbol}" for r in results]
    stats = await backfill_candidates(
        symbols,
        _cache,
        period=settings.history_period,
        concurrency=settings.backfill_concurrency,
    )
    return stats


@app.get(
    "/api/v1/history/{symbol}",
    response_model=HistoryResponse,
    tags=["History"],
    summary="Get cached OHLCV bars for a symbol",
)
async def history_bars(symbol: str) -> HistoryResponse:
    bars = _cache.get_bars(symbol)
    return HistoryResponse(
        symbol=symbol,
        count=len(bars),
        bars=[
            HistoryBar(ts=ts, open=o, high=h, low=l, close=c, volume=v)
            for ts, o, h, l, c, v in bars
        ],
    )


@app.get(
    "/api/v1/vcp/scan",
    response_model=VCPScanResponse,
    tags=["VCP Analysis"],
    summary="Scan all cached symbols for VCP setups",
    description="Run the VCP engine over every cached symbol and rank by final contraction tightness.",
)
async def vcp_scan(include_premature: bool = False) -> VCPScanResponse:
    results = [detect_vcp(symbol, _cache.get_bars(symbol)) for symbol in _cache.symbols()]
    qualified = [r for r in results if r.verdict == "STRONG_SETUP"]
    qualified.sort(key=lambda r: r.contractions[-1].depth_pct)
    rows = list(qualified)
    if include_premature:
        premature = [r for r in results if r.verdict == "PREMATURE"]
        premature.sort(key=lambda r: r.contractions[-1].depth_pct)
        rows.extend(premature)
    return VCPScanResponse(scanned=len(results), qualified=len(qualified), results=rows)


@app.get(
    "/api/v1/vcp/{symbol}",
    response_model=VCPResult,
    tags=["VCP Analysis"],
    summary="Detect VCP for a symbol from cached bars",
)
async def vcp_analysis(symbol: str) -> VCPResult:
    bars = _cache.get_bars(symbol)
    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"No cached bars for {symbol}. Run /api/v1/history/backfill first.",
        )
    return detect_vcp(symbol, bars)


@app.get(
    "/api/v1/vcp/ai/scan",
    response_model=VLIAssessmentResponse,
    tags=["VCP Analysis"],
    summary="LLM-assess all STRONG_SETUP candidates, ranked by confidence",
    description="Run the VCP engine over cached symbols, keep STRONG_SETUP, assess each via the "
    "OpenAI-compatible LLM, and rank by vcp_confidence_score.",
)
async def vcp_ai_scan() -> VLIAssessmentResponse:
    results = [detect_vcp(symbol, _cache.get_bars(symbol)) for symbol in _cache.symbols()]
    candidates = [(r.symbol, r) for r in results if r.verdict == "STRONG_SETUP"]
    assessments = await assess_batch(
        candidates,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )
    assessments.sort(key=lambda a: a.vcp_confidence_score, reverse=True)
    return VLIAssessmentResponse(scanned=len(candidates), results=assessments)


@app.get(
    "/api/v1/vcp/ai/{symbol}",
    response_model=VCPAssessment,
    tags=["VCP Analysis"],
    summary="LLM-assess a single symbol from cached bars",
)
async def vcp_ai_analysis(symbol: str) -> VCPAssessment:
    bars = _cache.get_bars(symbol)
    if not bars:
        raise HTTPException(
            status_code=404,
            detail=f"No cached bars for {symbol}. Run /api/v1/history/backfill first.",
        )
    result = detect_vcp(symbol, bars)
    return await assess_vcp(
        symbol,
        result,
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.llm_timeout_seconds,
    )