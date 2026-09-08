import logging
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent.client import VCPAssessment, assess_vcp_cached
from .config import get_settings
from .scheduler import start_scheduler
from .schemas import SavedScan, SavedScanCreate
from .scanner.client import ScanResult, TradingViewScannerClient
from .scanner.history import BackfillStats, backfill_candidates, get_cache
from .screener import metrics
from .vcp.engine import VCPResult, detect_vcp

logger = logging.getLogger("vcp-scanner")
settings = get_settings()
_cache = get_cache(settings)

if not settings.llm_api_key:
    logger.warning(
        "LLM_API_KEY is empty: AI assessment endpoints will return 502. "
        "Set it in .env.local and restart the backend. Rule-based VCP scan still works."
    )

TAGS_METADATA = [
    {"name": "Health", "description": "Service liveness and metadata."},
    {"name": "Scanner", "description": "TradingView Minervini Trend Template scanning."},
    {"name": "History", "description": "Daily OHLCV backfill and cached bars."},
    {"name": "VCP Analysis", "description": "Volatility Contraction Pattern detection."},
]

@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.telegram_bot_token and settings.telegram_chat_id:
        scheduler = start_scheduler(settings, _cache)
        print("[INFO] Scheduled daily VCP alert job started.")
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)
    else:
        yield


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
    lifespan=lifespan,
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


def _attach_metrics(results: list[VCPResult]) -> None:
    """Fill relative_volume / pct_off_52w_high / rs from cached bars, in place."""
    symbols_bars = {r.symbol: _cache.get_bars(r.symbol) for r in results}
    ranks = metrics.rs_rank(symbols_bars)
    for r in results:
        bars = symbols_bars.get(r.symbol) or []
        r.relative_volume = metrics.relative_volume(bars)
        r.pct_off_52w_high = metrics.pct_off_52w_high(bars)
        r.rs = ranks.get(r.symbol)


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
        _cache.upsert_watchlist([r.symbol for r in premature])
    _attach_metrics(rows)
    return VCPScanResponse(scanned=len(results), qualified=len(qualified), results=rows)


@app.get(
    "/api/v1/watchlist",
    response_model=VCPScanResponse,
    tags=["VCP Analysis"],
    summary="Get persisted watchlist candidates",
    description="Recompute VCP metrics from cached bars for every symbol on the persisted watchlist.",
)
async def watchlist() -> VCPScanResponse:
    results = [
        r
        for symbol in _cache.watchlist_symbols()
        if (r := detect_vcp(symbol, _cache.get_bars(symbol))).verdict != "FAILED_STRUCTURE"
    ]
    results.sort(key=lambda r: r.contractions[-1].depth_pct)
    _attach_metrics(results)
    return VCPScanResponse(
        scanned=len(results),
        qualified=sum(1 for r in results if r.verdict == "STRONG_SETUP"),
        results=results,
    )


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
    assessments: list[VCPAssessment] = []
    candidates = 0
    for symbol in _cache.symbols():
        bars = _cache.get_bars(symbol)
        result = detect_vcp(symbol, bars)
        if result.verdict != "STRONG_SETUP":
            continue
        candidates += 1
        try:
            assessments.append(await assess_vcp_cached(
                symbol, result, bars, _cache,
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                timeout=settings.llm_timeout_seconds,
            ))
        except RuntimeError:
            continue
    assessments.sort(key=lambda a: a.vcp_confidence_score, reverse=True)
    return VLIAssessmentResponse(scanned=candidates, results=assessments)


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
    try:
        return await assess_vcp_cached(
            symbol,
            result,
            bars,
            _cache,
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            timeout=settings.llm_timeout_seconds,
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"LLM assessment failed for {symbol}: {exc}",
        ) from exc


@app.get("/api/v1/scans", response_model=list[SavedScan], tags=["Scanner"], summary="List saved scans")
async def list_scans() -> list[SavedScan]:
    return [SavedScan(**s) for s in _cache.list_scans()]


@app.post("/api/v1/scans", response_model=SavedScan, tags=["Scanner"], summary="Save a scan filter set")
async def save_scan(payload: SavedScanCreate) -> SavedScan:
    scan_id = _cache.save_scan(payload.name, payload.filters.model_dump_json())
    return SavedScan(id=scan_id, name=payload.name, filters=payload.filters, created_at=int(time.time()))


@app.delete("/api/v1/scans/{scan_id}", tags=["Scanner"], summary="Delete a saved scan")
async def delete_scan(scan_id: int) -> dict:
    if not _cache.delete_scan(scan_id):
        raise HTTPException(status_code=404, detail=f"No saved scan with id {scan_id}")
    return {"ok": True}