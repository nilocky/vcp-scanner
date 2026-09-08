# Updated Project Directory Specification
## Project: VCP Scanner WebApp (LLM-assisted, OpenAI-compatible endpoints)

```text
vcp-scanner/
├── AGENTS.md                       # OpenCode Multi-Agent definitions & role guardrails
├── README.md                       # Getting started, local run commands & architecture summary
├── docker-compose.yml              # One-command orchestration for backend + frontend
├── .env.example                    # Template for API keys (LLM, Telegram Bot)
│
├── docs/                           # Documentation and planning artifacts
│   ├── plan_architecture.md        # Technical specifications & system architecture
│   ├── plan_roadmap.md             # 5-stage milestone checklist
│   ├── plan_quant_extension.md     # SciPy peak/trough math & VectorBT backtesting specs
│   └── plan_telegram_notification.md # Telegram bot formatting & APScheduler daily pipeline
│
├── backend/                        # Python FastAPI service
│   ├── pyproject.toml              # Dependencies (fastapi, scipy, vectorbt, httpx, apscheduler)
│   ├── Dockerfile
│   └── app/
│       ├── main.py                 # FastAPI entrypoint & router definitions
│       ├── config.py               # Pydantic environment configuration loader
│       ├── scheduler.py            # APScheduler cron job (runs daily post-close scan)
│       │
│       ├── scanner/                # TradingView Scanner API Integration
│       │   ├── __init__.py
│       │   ├── client.py           # HTTP client for POST scanner.tradingview.com/america/scan
│       │   └── filters.py          # Minervini Trend Template JSON query builder
│       │
│       ├── vcp/                    # Quantitative VCP Recognition Engine
│       │   ├── __init__.py
│       │   ├── extrema.py          # Peak/trough prominence detection using scipy.signal
│       │   ├── contraction.py      # T1 -> Tn contraction depth validator
│       │   └── volume.py           # Volume dry-up (VDU) ratio vs. 50-day SMA volume
│       │
│       ├── quant/                  # Extended Quant & Backtesting Module
│       │   ├── __init__.py
│       │   ├── backtest.py         # Breakout execution simulation & trailing stop logic
│       │   └── metrics.py          # Win rate, Profit Factor, Expectancy, Max Drawdown
│       │
│       ├── agent/                  # LLM AI Assessment (OpenAI-compatible endpoint)
│       │   ├── __init__.py
│       │   ├── client.py           # Model-agnostic adapter: assess_vcp / assess_batch
│       │   ├── prompts.py          # Structured system prompts & VCP evaluation rules
│       │   └── schemas.py          # Pydantic response models for pattern scoring
│       │
│       ├── notify/                 # Alerting & Webhooks
│       │   ├── __init__.py
│       │   └── telegram.py         # MarkdownV2 formatting, chart links & bot dispatcher
│       │
│       └── db/                     # Data Caching & Persistence
│           ├── __init__.py
│           └── cache.py            # SQLite / DuckDB cache for OHLCV bars & scan runs
│
└── frontend/                       # Interactive SPA WebApp
    ├── package.json                # Dependencies: vite, react, tailwindcss, lightweight-charts
    ├── Dockerfile
    ├── vite.config.ts
    ├── index.html
    └── src/
        ├── App.tsx                 # Main application layout (Split screen: Table + Chart)
        ├── components/
        │   ├── FilterBar.tsx       # Parameters: Liquidity, Min RS, Contractions count, Scan CTA
        │   ├── StockTable.tsx      # Candidate list with scores, stage depths, pivot distances
        │   ├── ChartViewer.tsx     # TradingView Lightweight Charts with VCP overlay (T1->Tn + Pivot)
│       └── AiAnalysis.tsx      # LLM thesis drawer with risk & R/R breakdown
        ├── hooks/
        │   └── useScanner.ts       # State hook managing scan lifecycle & WebSocket data
        └── types/
            └── scanner.d.ts        # TypeScript schemas matching Backend Pydantic types
```
