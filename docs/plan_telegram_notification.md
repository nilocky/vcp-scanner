# Telegram Notification Module Specification
## Module: `backend/app/notify/telegram.py`

### 1. Architectural Role
The Telegram notifier runs autonomously after the daily scheduled scan (or via manual trigger from the GUI). It takes the high-conviction candidate list produced by the quantitative VCP engine and approved by the LLM agent, formatting it into an actionable trading alert with direct chart links.

---

### 2. Implementation (`backend/app/notify/telegram.py`)

```python
import os
import httpx
from typing import Dict, Any, List

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

async def send_vcp_alert(candidate: Dict[str, Any]) -> bool:
    """
    Dispatches a structured MarkdownV2 alert to Telegram.
    Includes ticker, base shape, pivot price, stop loss, and AI thesis.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Telegram bot credentials missing. Skipping notification.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # Extract candidate data
    ticker = candidate.get("ticker", "UNKNOWN")
    score = candidate.get("vcp_confidence_score", 0)
    stages = candidate.get("contraction_stages", [])
    pivot = candidate.get("pivot_buy_price", 0.0)
    stop = candidate.get("suggested_stop_loss", 0.0)
    rr = candidate.get("risk_reward_ratio", 0.0)
    commentary = candidate.get("ai_commentary", "N/A")
    
    # Format wave contractions string e.g. "21% -> 9% -> 3.5%"
    waves_str = " ➔ ".join([f"{s.get('depth_pct', 0)}%" for s in stages])
    tv_chart_url = f"https://www.tradingview.com/chart/?symbol={ticker}"

    text = (
        f"🚨 *VCP BREAKOUT ALERT* 🚨\n\n"
        f"🎯 *Ticker*: `{ticker}`\n"
        f"⭐ *AI Score*: `{score}/100`\n"
        f"🌊 *Contractions*: `{waves_str}`\n"
        f"⚡ *Pivot Buy*: `${pivot:.2f}`\n"
        f"🛡️ *Stop Loss*: `${stop:.2f}` \\(Risk: {((pivot - stop)/pivot)*100:.1f}%\\)\n"
        f"⚖️ *R/R Ratio*: `{rr:.1f}R`\n\n"
        f"💡 *AI Thesis*:\n_{commentary}_\n\n"
        f"📈 [View on TradingView]({tv_chart_url})"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "MarkdownV2",
        "disable_web_page_preview": False
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        res = await client.post(url, json=payload)
        return res.status_code == 200
```

---

### 3. Automated Daily Scheduler (`backend/app/scheduler.py`)

Using `APScheduler` inside FastAPI:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.scanner.client import scan_tradingview_universe
from app.vcp.contraction import filter_vcp_candidates
from app.agent.client import assess_vcp
from app.notify.telegram import send_vcp_alert

scheduler = AsyncIOScheduler(timezone="America/New_York")

async def scheduled_daily_scan_job():
    """Runs automatically after US market close (16:30 EST)"""
    print("[INFO] Starting scheduled daily VCP scan...")
    raw_tickers = await scan_tradingview_universe()
    quant_vcp_list = await filter_vcp_candidates(raw_tickers)
    
    for candidate in quant_vcp_list:
        ai_assessment = await assess_vcp(candidate)
        # Dispatch notification if score is >= 85 and verdict is STRONG_SETUP
        if ai_assessment.get("vcp_confidence_score", 0) >= 85:
            await send_vcp_alert(ai_assessment)

def start_scheduler():
    # Run Monday through Friday at 16:30 NY time
    scheduler.add_job(scheduled_daily_scan_job, 'cron', day_of_week='mon-fri', hour=16, minute=30)
    scheduler.start()
```

---

### 4. Configuration Requirements (`.env`)
```bash
TELEGRAM_BOT_TOKEN="123456789:ABCdefGHIjklMNOpqrsTUVwxyz"
TELEGRAM_CHAT_ID="987654321"
MIN_TELEGRAM_ALERT_SCORE=85
```
