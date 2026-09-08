"""Daily scheduled VCP scan that dispatches Telegram alerts for high-conviction setups."""
from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .agent.client import VCPAssessment, assess_vcp_cached
from .config import Settings
from .notify.telegram import send_vcp_alert
from .scanner.client import TradingViewScannerClient
from .scanner.history import backfill_candidates
from .vcp.engine import VCPResult, detect_vcp


async def run_daily_alert_job(settings: Settings, cache) -> list[VCPAssessment]:
    """Run the full scan pipeline and send alerts for assessments scoring >= min_telegram_alert_score."""
    client = TradingViewScannerClient(settings)
    _, results = await client.scan_minervini_trend_template()
    symbols = [f"{r.exchange}:{r.symbol}" for r in results]
    await backfill_candidates(symbols, cache, period=settings.history_period, concurrency=settings.backfill_concurrency)

    alerts: list[VCPAssessment] = []
    for symbol in cache.symbols():
        bars = cache.get_bars(symbol)
        result: VCPResult = detect_vcp(symbol, bars)
        if result.verdict != "STRONG_SETUP":
            continue
        try:
            assessment = await assess_vcp_cached(
                symbol, result, bars, cache,
                base_url=settings.llm_base_url, api_key=settings.llm_api_key,
                model=settings.llm_model, timeout=settings.llm_timeout_seconds,
            )
        except RuntimeError:
            continue
        if assessment.vcp_confidence_score >= settings.min_telegram_alert_score:
            await send_vcp_alert(assessment, token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)
            alerts.append(assessment)
    return alerts


def create_scheduler(settings: Settings, cache) -> AsyncIOScheduler:
    sched = AsyncIOScheduler(timezone="America/New_York")
    sched.add_job(run_daily_alert_job, trigger="cron", day_of_week="mon-fri", hour=16, minute=30, args=[settings, cache])
    return sched


def start_scheduler(settings: Settings, cache) -> AsyncIOScheduler:
    sched = create_scheduler(settings, cache)
    sched.start()
    return sched