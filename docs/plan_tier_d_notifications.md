# Tier D — Notifications & Containerization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Telegram breakout alerts on a scheduled daily scan and package the app for single-command Docker deployment (roadmap Phase 5).

**Architecture:** A `notify/telegram.py` module formats a `VCPAssessment` as a MarkdownV2 alert and posts it to the Telegram Bot API. An APScheduler job drives the existing `scan → backfill → detect_vcp → assess_vcp_cached` pipeline on weekdays at 16:30 NY, sending alerts only for scores ≥ threshold. FastAPI's lifespan starts the scheduler only when credentials exist. Multi-stage Dockerfiles build backend (uv → slim runtime) and frontend (vite → nginx), wired together by docker-compose.

**Tech Stack:** APScheduler (already a dependency), httpx, uvicorn, React/Vite (unchanged), nginx, Docker Compose.

**Spec:** `docs/plan_tweevest_blueprint.md` Tier D (D1–D8). Related prior spec: `docs/plan_telegram_notification.md` (message format; note it references functions that don't exist — we implement against the real codebase).

## Global Constraints

- Python 3.11, backend managed by `uv` (`uv.lock` frozen, `[tool.uv] package = false`).
- Settings via `app/config.py` `Settings(BaseSettings)`; `get_settings()` is `@lru_cache`.
- Test convention: `backend/tests/test_*.py` each do `sys.path.insert(0, dirname(dirname(abspath(__file__))))`, use plain `assert` + `if __name__ == "__main__":` runner. Run with `pytest tests/` in `backend/`.
- Scheduler MUST NOT auto-start during tests (existing `test_routes.py` imports `app.main` at module scope).
- No new dependencies. No secret values in code or committed files.
- Frontend API base is `/api/v1` (relative) — nginx proxy needs no frontend change.
- `.env.example` lives at repo root; `backend/app/config.py` reads `.env.local`, `.env`, `../.env.local`, `../.env`.

---

### Task D-1: Telegram notifier `send_vcp_alert`

**Files:**
- Create: `backend/app/notify/__init__.py` (empty)
- Create: `backend/app/notify/telegram.py`
- Test: `backend/tests/test_telegram.py`

**Interfaces:**
- Consumes: `VCPAssessment` from `app.agent.client` (fields: `ticker`, `vcp_confidence_score`, `contraction_stages[{stage,depth_pct,days}]`, `pivot_buy_price`, `suggested_stop_loss`, `risk_reward_ratio`, `ai_commentary`); `settings.telegram_bot_token`, `settings.telegram_chat_id`.
- Produces: `async def send_vcp_alert(assessment: VCPAssessment) -> bool` — `False` (no raise) when token/chat_id unset or on non-200.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_telegram.py`

```python
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
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_telegram.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'app.notify'`

- [ ] **Step 3: Write minimal implementation** — `backend/app/notify/telegram.py`

```python
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
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_telegram.py -v`
  Expected: PASS (3 tests)

- [ ] **Step 5: Wire credentials through config (needed by D-5)**

`backend/app/config.py` already has `telegram_bot_token` and `telegram_chat_id`. In `send_vcp_alert` the caller passes them explicitly; default them from `get_settings()` at call time in the scheduler (Task D-3). No config change needed here.

- [ ] **Step 6: Commit**

```bash
git add backend/app/notify/ backend/tests/test_telegram.py
git commit -m "feat: telegram VCP alert notifier"
```

---

### Task D-2: Config + `.env.example` additions

**Files:**
- Modify: `backend/app/config.py`
- Modify: `.env.example`

**Interfaces:**
- Produces: `Settings.min_telegram_alert_score: int = 85`, `Settings.db_path` already exists (`data/bars.db`), `Settings.cors_origins` already exists.
- Consumes: nothing.

- [ ] **Step 1: Add the score setting** — in `backend/app/config.py` `Settings` class, add:

```python
min_telegram_alert_score: int = 85
```

- [ ] **Step 2: Update `.env.example`** (repo root). Read current file, then append:

```bash
MIN_TELEGRAM_ALERT_SCORE=85
DB_PATH=data/bars.db
# Docker: nginx serves on :80, add its origin to CORS
CORS_ORIGINS=["http://localhost:5173","http://localhost:80"]
```

- [ ] **Step 3: Verify settings load**
  Run: `python -c "from app.config import get_settings; s=get_settings(); print(s.min_telegram_alert_score, s.db_path, s.cors_origins)"` (in `backend/`)
  Expected: prints `85 data/bars.db ['http://localhost:5173', 'http://localhost:80']`

- [ ] **Step 4: Commit**

```bash
git add backend/app/config.py .env.example
git commit -m "feat: min telegram alert score setting"
```

---

### Task D-3: Daily scheduler job

**Files:**
- Create: `backend/app/scheduler.py`
- Test: `backend/tests/test_scheduler.py`

**Interfaces:**
- Consumes: `TradingViewScannerClient` from `app.scanner.client`; `backfill_candidates`, `get_cache` from `app.scanner.history`; `detect_vcp` from `app.vcp.engine`; `assess_vcp_cached` from `app.agent.client`; `send_vcp_alert` from `app.notify.telegram`; `settings`.
- Produces: `async def run_daily_alert_job(settings, cache) -> list[VCPAssessment]` (returns alerts sent, for testability); `def start_scheduler(settings, cache) -> AsyncIOScheduler`; `def create_scheduler(settings, cache) -> AsyncIOScheduler`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_scheduler.py`

```python
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

    with mock.patch("app.scheduler.TradingViewScannerClient"), \
         mock.patch("app.scheduler.backfill_candidates", new=asyncio.coroutine(lambda *a, **k: None)), \
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
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_scheduler.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'app.scheduler'`

- [ ] **Step 3: Write minimal implementation** — `backend/app/scheduler.py`

```python
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
    sched.add_job(run_daily_alert_job, "cron", day_of_week="mon-fri", hour=16, minute=30, args=[settings, cache])
    return sched


def start_scheduler(settings: Settings, cache) -> AsyncIOScheduler:
    sched = create_scheduler(settings, cache)
    sched.start()
    return sched
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_scheduler.py -v`
  Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/scheduler.py backend/tests/test_scheduler.py
git commit -m "feat: daily VCP alert scheduler"
```

---

### Task D-4: FastAPI lifespan wiring

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routes.py` (extend)

**Interfaces:**
- Consumes: `start_scheduler` from `app.scheduler`.
- Produces: `lifespan(app)` context manager on `FastAPI`; scheduler starts only when `settings.telegram_bot_token` truthy.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_routes.py`

```python
def test_lifespan_does_not_start_scheduler_without_token() -> None:
    import app.scheduler as sched_mod

    s = main.get_settings()
    old = s.telegram_bot_token
    s.telegram_bot_token = ""
    started = []
    with mock.patch.object(sched_mod, "start_scheduler", side_effect=lambda *a, **k: started.append(1)):
        with TestClient(main.app) as c:
            assert c.get("/health").status_code == 200
    s.telegram_bot_token = old
    assert started == []
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_routes.py::test_lifespan_does_not_start_scheduler_without_token -v`
  Expected: FAIL — no lifespan on app / attribute error

- [ ] **Step 3: Implement lifespan** — in `backend/app/main.py`

At imports (keep the `settings`/`_cache` module-level lines):
```python
from contextlib import asynccontextmanager
from .scheduler import start_scheduler
```

Replace the current app construction with:
```python
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


app = FastAPI(title=settings.app_name, lifespan=lifespan)
```

Note: `_cache` is module-level via `get_cache(settings)`. If the current `app = FastAPI(...)` line already exists, replace it. Existing tests use `TestClient(main.app)` WITHOUT a context manager, so lifespan never runs there — no interference.

- [ ] **Step 4: Run full backend test suite**
  Run: `pytest tests/ -v`
  Expected: all PASS (including existing route tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_routes.py
git commit -m "feat: start scheduler via fastapi lifespan when telegram configured"
```

---

### Task D-5: Backend `Dockerfile`

**Files:**
- Create: `backend/Dockerfile`
- Create: `backend/.dockerignore`

**Interfaces:**
- Produces: image with `.venv` (deps installed frozen, no dev group), `app/` package, `EXPOSE 8000`, `CMD uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- Consumes: `pyproject.toml`, `uv.lock`, `app/`.

- [ ] **Step 1: Write `backend/Dockerfile`**

```dockerfile
FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim AS builder
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

FROM python:3.11-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY --from=builder /app/.venv /app/.venv
COPY app ./app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Write `backend/.dockerignore`**

```
.venv
__pycache__
*.pyc
tests
data
```

- [ ] **Step 3: Build to verify**
  Run: `docker build -t vcp-api .` (in `backend/`)
  Expected: image builds; deps installed from frozen lock.

- [ ] **Step 4: Commit**

```bash
git add backend/Dockerfile backend/.dockerignore
git commit -m "build: backend multi-stage dockerfile"
```

---

### Task D-6: Frontend `Dockerfile` + nginx config

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/.dockerignore`
- Create: `frontend/nginx.conf`

**Interfaces:**
- Produces: nginx image serving `dist/`, proxying `/api/` → `http://api:8000`.
- Consumes: `package.json`, `package-lock.json`, `src/`, `index.html`, `vite.config.ts`.

- [ ] **Step 1: Write `frontend/Dockerfile`**

```dockerfile
FROM node:20-alpine AS builder
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

- [ ] **Step 2: Write `frontend/.dockerignore`**

```
node_modules
dist
```

- [ ] **Step 3: Write `frontend/nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    location /api/ {
        proxy_pass http://api:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

- [ ] **Step 4: Verify a local production build works**
  Run: `npm run build` (in `frontend/`)
  Expected: `dist/` produced, no type errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/Dockerfile frontend/.dockerignore frontend/nginx.conf
git commit -m "build: frontend dockerfile + nginx reverse proxy"
```

---

### Task D-7: `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml` (repo root)

**Interfaces:**
- Produces: services `api` (backend, port 8000, named volume `vcp-data` for `data/bars.db`) and `web` (frontend, port 80, depends on api). Env from `.env`.
- Consumes: `backend/Dockerfile`, `frontend/Dockerfile`, `.env`.

- [ ] **Step 1: Write `docker-compose.yml`**

```yaml
services:
  api:
    build: ./backend
    container_name: vcp-api
    env_file: .env
    environment:
      - DB_PATH=/app/data/bars.db
    volumes:
      - vcp-data:/app/data
    ports:
      - "8000:8000"
    restart: unless-stopped

  web:
    build: ./frontend
    container_name: vcp-web
    depends_on:
      - api
    ports:
      - "80:80"
    restart: unless-stopped

volumes:
  vcp-data:
```

- [ ] **Step 2: Verify compose file parses**
  Run: `docker compose config`
  Expected: valid merged config, no errors.

- [ ] **Step 3: Commit**

```bash
git add docker-compose.yml
git commit -m "build: docker compose stack for api + web"
```

---

### Task D-8: End-to-end Docker smoke test (manual)

- [ ] **Step 1: Start the stack**
  Run: `docker compose up --build -d`
  Expected: both containers healthy.

- [ ] **Step 2: Check backend health through nginx**
  Run: `curl http://localhost/api/v1/health`
  Expected: `{"status":"ok"}` (proves nginx → api proxy + CORS origin working).

- [ ] **Step 3: Confirm data volume persistence**
  Run: `docker compose exec api ls /app/data`
  Expected: `bars.db` exists after a scan; survives `docker compose down && up` (named volume).

- [ ] **Step 4: Optional live alert test**
  With real `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID` in `.env`, run:
  Run: `docker compose exec api python -c "import asyncio; from app.scheduler import run_daily_alert_job; from app.config import get_settings; from app.scanner.history import get_cache; asyncio.run(run_daily_alert_job(get_settings(), get_cache(get_settings())))"`
  Expected: Telegram receives an alert for any qualified candidate; no crash otherwise.

---

## Self-Review

- **Spec coverage:** D1–D8 all mapped. D4 guarded by token so tests are safe. D5/D6/D7 produce buildable artifacts; D8 validates.
- **Type consistency:** `send_vcp_alert(assessment, *, token, chat_id, transport)` signature matches scheduler call `send_vcp_alert(assessment, token=..., chat_id=...)`; test uses `transport=` kwarg. `run_daily_alert_job(settings, cache)` matches scheduler `args=[settings, cache]`.
- **No placeholders:** every code block is concrete; tests are written out.
- **Test independence:** `test_routes.py` existing tests use `TestClient(main.app)` without context manager → lifespan (and scheduler) never starts; the new test uses `with TestClient(...)` and an empty token to assert no start.