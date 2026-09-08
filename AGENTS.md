# AGENTS.md

This document defines the agent personas, coordination protocols, and role-specific operational constraints for building and maintaining the Volatility Contraction Pattern (VCP) Scanner WebApp using OpenCode with DeepSeek V4 Flash.

---

## Agent Directory & Roles

### 1. Lead Architect Agent (`@architect`)
- **Mission**: Maintains end-to-end architecture integrity, cross-module contracts, performance constraints, and containerization standards.
- **Responsibilities**:
  - Enforce clean separation between TradingView data ingestion, algorithmic contraction math, AI evaluation, and frontend presentation.
  - Review schemas, database migration, and Docker configurations.
  - Ensure zero leak of proprietary tokens and API keys.

---

### 2. Market Data & Screener Agent (`@data-screener`)
- **Mission**: Integrates with TradingView scanner APIs and manages OHLCV ingestion pipelines.
- **Responsibilities**:
  - Target endpoint: `https://scanner.tradingview.com/america/scan`.
  - Maintain the Minervini Trend Template filter payload:
    - `close > SMA(50)`
    - `SMA(50) > SMA(150) > SMA(200)`
    - `SMA(200)` trending up for at least 1 month
    - `close >= 0.75 * 52_week_high`
    - Turnover `volume * close >= 10,000,000`
  - Ensure polite rate-limiting, back-off mechanisms, and local caching in SQLite/DuckDB.

---

### 3. Quantitative Pattern Agent (`@quant-vcp`)
- **Mission**: Mathematical detection and parameterization of Volatility Contraction Patterns.
- **Responsibilities**:
  - Implement dynamic zig-zag / peak-valley detection algorithms.
  - Verify contraction sequence: \( \text{Depth}(T_n) < \text{Depth}(T_{n-1}) \).
  - Quantify volume dry-up: final contraction volume must be at least 40–50% lower than the 50-day moving average volume.
  - Calculate precise pivot entry points (highest point of the final contraction) and tight stop-loss boundaries (low of the final contraction).

---

### 4. DeepSeek Intelligence Agent (`@deepseek-agent`)
- **Mission**: Leverages DeepSeek V4 Flash through OpenCode to perform pattern qualification, false-breakout filtering, and natural language synthesis.
- **Prompting & Output Guardrails**:
  - Model: `deepseek-chat` / `deepseek-v4-flash` via OpenCode interface.
  - Input: Raw wave coordinates, volume dry-up statistics, relative strength versus index, and market trend status.
  - Required Output Schema:
    ```json
    {
      "ticker": "STRING",
      "vcp_confidence_score": 0-100,
      "base_type": "Cup with Handle / Flat Base / High Tight Flag / Standard VCP",
      "contraction_stages": [
        {"stage": "T1", "depth_pct": 18.5, "days": 15},
        {"stage": "T2", "depth_pct": 9.2, "days": 8},
        {"stage": "T3", "depth_pct": 3.8, "days": 4}
      ],
      "volume_dryup_confirmed": true,
      "pivot_buy_price": 142.50,
      "suggested_stop_loss": 137.20,
      "risk_reward_ratio": 3.4,
      "verdict": "STRONG_SETUP | PREMATURE | FAILED_STRUCTURE",
      "ai_commentary": "STRING"
    }
    ```
  - Prohibit hallucinated ticker statistics; strictly enforce evaluation against the supplied numerical payload.

---

### 5. Frontend & UI/UX Agent (`@ui-frontend`)
- **Mission**: Delivers an intuitive, high-performance web GUI for trader operation.
- **Tech Stack**: React 19 / Vite + Tailwind CSS + TradingView Lightweight Charts (`lightweight-charts`).
- **Core Views**:
  - **Filter Bar**: Dynamic controls for liquidity, minimum RS rating, contraction count, and trigger button.
  - **Candidate Grid**: Instant sorting by tightness score, distance to pivot, and AI score.
  - **Interactive Chart View**: Real-time candlestick chart overlaying contraction brackets and the pivot line.
  - **AI Thesis Drawer**: Side-sheet rendering DeepSeek's technical analysis and risk parameters.

---

### 6. DevOps & Automation Agent (`@devops-ops`)
- **Mission**: Packages the application into reproducible Docker and deployment artifacts.
- **Deliverables**:
  - Multi-stage Dockerfile bundling Vite frontend and FastAPI backend into a single lean container or Docker Compose stack.
  - Environment configuration (`.env.example`) managing OpenCode/DeepSeek API endpoints and keys.
  - Optional n8n / Telegram webhook dispatcher for instant notification when a candidate triggers a breakout scan.
