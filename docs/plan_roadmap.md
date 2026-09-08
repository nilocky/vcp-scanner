# Implementation Roadmap: VCP Scanner WebApp

## Milestones & Development Timeline

### Phase 1: Environment Setup & Data Pipeline Foundation
- [ ] Initialize Python backend project structure with FastAPI and Poetry/UV.
- [ ] Implement TradingView America scanner client (`POST https://scanner.tradingview.com/america/scan`).
- [ ] Integrate Mark Minervini Trend Template query parameters.
- [ ] Build historical daily OHLCV fetcher with local SQLite caching.

### Phase 2: Quantitative VCP Algorithm & Contraction Engine
- [ ] Implement peak/trough detection using dynamic lookback windows.
- [ ] Build multi-stage contraction verification (\(T_1, T_2, T_3, \dots, T_n\)).
- [ ] Calculate volume dry-up ratio on final contractions.
- [ ] Determine automatic Pivot Buy Points and cheat entry levels.

### Phase 3: LLM Agent Integration (OpenAI-compatible endpoint)
- [ ] Configure OpenAI-compatible API adapter (`LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY`) — model-agnostic (DeepSeek, OpenAI, Ollama, LiteLLM).
- [ ] Formulate strict Pydantic structured output models for VCP pattern evaluation.
- [ ] Implement batch prompt runner with error handling and retry mechanism.
- [ ] Benchmark latency and quality against classical rule-based scanner outputs.

### Phase 4: WebApp GUI Frontend Development
- [ ] Scaffold React + Vite + Tailwind CSS frontend.
- [ ] Integrate TradingView Lightweight Charts library (`lightweight-charts`).
- [ ] Implement interactive scan control filters (Market Cap, Volume, VCP tightness).
- [ ] Add visual contraction annotations (drawn swings and pivot lines on chart).
- [ ] Build AI reasoning inspect panel (verdict, risk analysis, stop-loss).

### Phase 5: Containerization & DevOps Integration
- [ ] Write Multi-stage `Dockerfile` (Backend + Frontend static bundle).
- [ ] Prepare `docker-compose.yml` for single-command homelab deployment.
- [ ] Integrate optional Telegram webhook notification for high-conviction breakout setups.
