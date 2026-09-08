from __future__ import annotations
import asyncio, os, sys
import httpx
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.agent.client import ContractionStage, VCPAssessment
from app.notify.telegram import send_vcp_alert


def _assessment() -> VCPAssessment:
    return VCPAssessment(
        ticker="NYSE:GKOS",
        vcp_confidence_score=88,
        base_type="Cup with Handle",
        contraction_stages=[
            ContractionStage(stage="T1", depth_pct=18.0, days=15),
            ContractionStage(stage="T2", depth_pct=9.0, days=8),
            ContractionStage(stage="T3", depth_pct=3.5, days=4),
        ],
        volume_dryup_confirmed=True,
        pivot_buy_price=142.50,
        suggested_stop_loss=137.20,
        risk_reward_ratio=3.4,
        verdict="STRONG_SETUP",
        ai_commentary="tight final contraction, volume drying up",
    )


def test_send_alert_posts_markdownv2() -> None:
    sent: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent["url"] = request.url
        sent["json"] = request.read()
        return httpx.Response(200, json={"ok": True})

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        ok = await send_vcp_alert(_assessment(), token="TOKEN", chat_id="123", transport=transport)
        assert ok is True

    asyncio.run(run())
    assert sent["url"].path == "/botTOKEN/sendMessage", sent["url"]
    assert sent["url"].host == "api.telegram.org", sent["url"]
    body = sent["json"]
    assert b'"chat_id": "123"' in body or b'"chat_id":"123"' in body
    assert b"MarkdownV2" in body
    assert b"NYSE:GKOS" in body
    assert b"3.5%" in body
    assert b"142.50" in body


def test_send_alert_false_without_credentials() -> None:
    async def run() -> None:
        ok = await send_vcp_alert(_assessment(), token="", chat_id="", transport=None)
        assert ok is False

    asyncio.run(run())


def test_send_alert_false_on_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    transport = httpx.MockTransport(handler)

    async def run() -> None:
        ok = await send_vcp_alert(_assessment(), token="T", chat_id="C", transport=transport)
        assert ok is False

    asyncio.run(run())


if __name__ == "__main__":
    test_send_alert_posts_markdownv2()
    print("posts passed")
    test_send_alert_false_without_credentials()
    print("no-creds passed")
    test_send_alert_false_on_http_error()
    print("http-error passed")