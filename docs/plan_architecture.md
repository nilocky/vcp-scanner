# System Architecture & Technical Specification
## Project: VCP Scanner WebApp (LLM-assisted, OpenAI-compatible endpoints)

### 1. Architecture Overview
```
+-------------------------------------------------------------+
|                      Frontend (SPA GUI)                     |
|           Tailwind CSS + TradingView Lightweight Charts      |
|           - Interactive Parameter Configuration             |
|           - Candidate Watchlist & Contraction Breakdown      |
|           - AI Analysis Inspector (Narrative & Risk)        |
+-------------------------------------------------------------+
                               |  HTTP / WebSocket
                               v
+-------------------------------------------------------------+
|                     Backend Server (FastAPI)                |
|  +------------------------+  +----------------------------+ |
|  | TradingView Scanner API|  | Quantitative Filter Engine | |
|  | (Universe & Baseline)  |  | (VCP Depth/Volume/MA Check)| |
|  +------------------------+  +----------------------------+ |
|                              |                              |
|  +--------------------------------------------------------+ |
|  |       LLM Agent (OpenAI-compatible endpoint)            | |
|  |       - Pattern Symmetry & Shakeout Verification       | |
|  |       - Entry Pivot, Stop-Loss, and R/R Synthesis      | |
|  +--------------------------------------------------------+ |
+-------------------------------------------------------------+
                               |
                               v
+-------------------------------------------------------------+
|                   Storage & Cache (SQLite/Redis)            |
|       - Cached daily OHLCV snapshots                        |
|       - Scan run history & AI reasoning logs                |
+-------------------------------------------------------------+
```

### 2. Core Modules & Specifications

#### 2.1 TradingView Scanner Ingestion Engine (`backend/scanner/tradingview.py`)
- **Endpoint**: `POST https://scanner.tradingview.com/america/scan` (supports US stocks, extendable to HK `hongkong/scan`).
- **Initial Technical Prescreen Payload**:
  - `close > 5` (Filter out illiquid penny stocks).
  - `volume * close > 10000000` (Liquidity threshold: > $10M turnover).
  - `close > SMA50` and `SMA50 > SMA150` and `SMA150 > SMA200` (Mark Minervini Trend Template base).
  - `close >= 0.75 * 52_week_high` (Within 25% of 52-week highs).
  - 10-day ATR / Close <= 0.05 (Preliminary volatility compression).

#### 2.2 Algorithmic VCP Recognition Engine (`backend/vcp/engine.py`)
- **Contraction Detection Algorithm**:
  - Peak/Trough segmentation using local extrema detection on 60–120 trading days.
  - Successive contraction verification: \( T_1 > T_2 > T_3 \) where depth shrinks progressively (e.g., \( T_1: 15-25\% \), \( T_2: 8-15\% \), \( T_3: 3-7\% \)).
  - Volume Dry-Up Ratio: \( \text{Volume}_{T_3} / \text{SMA50(Volume)} < 0.60 \).
  - Tightness Test: Daily spread over the last 3-5 days under average true range.

#### 2.3 LLM AI Synthesis Agent (`backend/agent/client.py`)
- Calls any OpenAI-compatible `/v1/chat/completions` endpoint (DeepSeek, OpenAI, Ollama, LiteLLM, ...) — model-agnostic.
- Endpoint/model/key configured via `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (empty key for local Ollama).
- Context payload provided to the LLM:
  - Ticker, Sector, Market Cap.
  - Exact wave coordinates (Dates, Highs, Lows, Volume profile of contractions).
  - Benchmark relative strength (RS rating vs. SPY / QQQ).
- Output Schema (Structured JSON):
  - `vcp_validity_score` (0-100)
  - `detected_contractions_count` (int)
  - `pivot_buy_point` (float)
  - `stop_loss_level` (float)
  - `structural_weaknesses` (list of strings: e.g. overhead supply, volume spike on down-day)
  - `summary_verdict` ("Strong Setup", "Premature", "Invalidated")

#### 2.4 Interactive GUI (`frontend/`)
- Built with a lightweight modern stack (Vite + React / Solid.js + TailwindCSS).
- **Controls Panel**: Adjust universe, minimum liquidity, contraction depth tolerance, and trigger instant scan.
- **Results Table**: Displays Ticker, Base Duration, Number of Contractions (e.g. 3T / 4T), Volume Dry-up %, Distance to Pivot, and AI Confidence Score.
- **Visual Chart Drawer**: TradingView Lightweight Charts with overlaid VCP contraction cones and pivot lines.
- **AI Modal**: LLM reasoning card with one-click export to Telegram or Watchlist.
