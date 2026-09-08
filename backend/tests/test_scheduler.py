from __future__ import annotations
import asyncio, os, sys
import unittest.mock as mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import Settings
from app.scheduler import run_daily_alert_job, start_scheduler


def _settings() -> Settings:
    s = Settings(_env_file=None)
    s.telegram_bot_token = "TOKEN"
    s.telegram_chat_id = "123"
    s.min_telegram_alert_score = 85
    s.llm_base_url = "http://x/v1"
    s.llm_api_key = "k"
    s.llm_model = "m"
    return s


def test_run_daily_alert_job_sends_qualified_only() -> None:
    from app.agent.client import ContractionStage, VCPAssessment
    from app.vcp.engine import VCPResult

    sent: list[str] = []
    async def fake_send(a, **kw):
        sent.append(a.ticker)
        return True

    qualified = VCPAssessment(
        ticker="NYSE:GKOS", vcp_confidence_score=88, base_type="Cup with Handle",
        contraction_stages=[ContractionStage(stage="T1", depth_pct=10.0, days=5)],
        volume_dryup_confirmed=True, pivot_buy_price=142.5, suggested_stop_loss=137.2,
        risk_reward_ratio=3.4, verdict="STRONG_SETUP", ai_commentary="ok",
    )
    weak = qualified.model_copy(update={"ticker": "NYSE:ABC", "vcp_confidence_score": 60})

    class FakeCache:
        def symbols(self):
            return ["NYSE:GKOS", "NYSE:ABC"]

        def get_bars(self, symbol):
            return [(i, 100.0, 110.0, 95.0, 105.0, 1000.0) for i in range(250)]

    async def fake_assess(symbol, result, bars, cache, **kw):
        return qualified if symbol == "NYSE:GKOS" else weak

    async def noop(*a, **k):
        return None

    class FakeClient:
        def __init__(self, settings=None):
            pass

        async def scan_minervini_trend_template(self):
            return (0, [])

    with mock.patch("app.scheduler.TradingViewScannerClient", FakeClient), \
         mock.patch("app.scheduler.backfill_candidates", new=noop), \
         mock.patch("app.scheduler.detect_vcp", return_value=VCPResult(symbol="x", contractions=[], volume_dryup_ratio=0.3, pivot_buy_price=142.5, stop_loss=137.2, verdict="STRONG_SETUP")), \
         mock.patch("app.scheduler.assess_vcp_cached", side_effect=fake_assess), \
         mock.patch("app.scheduler.send_vcp_alert", side_effect=fake_send):
        asyncio.run(run_daily_alert_job(_settings(), FakeCache()))

    assert sent == ["NYSE:GKOS"], sent


def test_start_scheduler_uses_ny_cron() -> None:
    with mock.patch("app.scheduler.AsyncIOScheduler") as mock_sched:
        sched = start_scheduler(_settings(), object())
        assert sched is not None
        added = mock_sched.return_value.add_job
        assert added.called
        _, kwargs = added.call_args
        assert kwargs["trigger"] == "cron"
        assert kwargs["hour"] == 16
        assert kwargs["minute"] == 30
        assert kwargs["day_of_week"] == "mon-fri"


if __name__ == "__main__":
    test_run_daily_alert_job_sends_qualified_only()
    print("daily job passed")
    test_start_scheduler_uses_ny_cron()
    print("cron passed")