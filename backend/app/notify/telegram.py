"""Telegram dispatch for high-conviction VCP alerts (MarkdownV2)."""
from __future__ import annotations

import httpx

from ..agent.client import VCPAssessment


def _escape_md2(text: str) -> str:
    for ch in "._-()[]{}>#+-=|!`":
        text = text.replace(ch, f"\\{ch}")
    return text


async def send_vcp_alert(
    assessment: VCPAssessment,
    *,
    token: str = "",
    chat_id: str = "",
    transport: httpx.AsyncBaseTransport | None = None,
) -> bool:
    """Dispatch a VCP alert to Telegram. Returns False (no raise) when creds are missing or the API errors."""
    if not token or not chat_id:
        print("[WARN] Telegram bot credentials missing. Skipping notification.")
        return False

    waves = " ➔ ".join(f"{s.depth_pct}%" for s in assessment.contraction_stages)
    risk_pct = ((assessment.pivot_buy_price - assessment.suggested_stop_loss) / assessment.pivot_buy_price) * 100
    text = (
        "🚨 *VCP BREAKOUT ALERT* 🚨\n\n"
        f"🎯 *Ticker*: `{assessment.ticker}`\n"
        f"⭐ *AI Score*: `{assessment.vcp_confidence_score}/100`\n"
        f"🌊 *Contractions*: `{waves}`\n"
        f"⚡ *Pivot Buy*: `${assessment.pivot_buy_price:.2f}`\n"
        f"🛡️ *Stop Loss*: `${assessment.suggested_stop_loss:.2f}` \\(Risk: {risk_pct:.1f}%\\)\n"
        f"⚖️ *R/R Ratio*: `{assessment.risk_reward_ratio:.1f}R`\n\n"
        f"💡 *AI Thesis*:\n_{assessment.ai_commentary}_\n\n"
        f"📈 [View on TradingView](https://www.tradingview.com/chart/?symbol={assessment.ticker})"
    )

    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False,
    }
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10.0, transport=transport) as client:
        try:
            res = await client.post(url, json=payload)
        except httpx.RequestError:
            return False
        return res.status_code == 200