# Tweevest Blueprint Audit & Enhancement Roadmap

**Source:** [tweevest.com](https://tweevest.com/) — CANSLIM-centric free stock screener.
**Purpose:** Blueprint audit to enhance the existing VCP Scanner WebApp. Nothing here is user-approved as an exact copy; features are adapted to our existing architecture (TradingView ingestion + rule-based VCP + DeepSeek AI).

---

## 1. What Tweevest Does Well

- **Growth Scan screener** with 80+ filters and **live result counts** while you edit.
- Every US stock **scored daily**: RS Score (1–99), EPS Score (1–99), EPS Acceleration, **Volume Buzz** (today's volume vs 50-day average, shown as e.g. `+160%`), **% off 52W high**, Institutional Buying QoQ.
- **Saved scans**: persist filter combos, rerun with one click (e.g. "RS 80+ on Volume Surge — 23 matches").
- **Earnings calendar** with watchlist alerts, sorted by market cap.
- **Signal-overlaid charts**: RS line vs S&P500, EPS markers, Pattern Detector, Growth Bars, moving averages, volume surges.
- **Snapshot panels**: 8-quarter EPS YoY history, institutional ownership QoQ, RS gauge.
- **Analyst grade**: peer valuation (P/E, P/S, P/B comparables), analyst consensus + price target, volume buzz.
- **Learn guides** and **market-regime filters** (the M of CANSLIM).

---

## 2. What We Already Have (baseline)

| Capability | Tweevest | VCP Scanner |
|---|---|---|
| Screener | Growth Scan (80+ filters) | Minervini Trend Template (fixed filter payload) |
| RS Score | 1–99 daily | `apply_rs_proxy` percentile at scan time (not persisted) |
| Volume Buzz | `+160%` style | Not surfaced (volume available in bars) |
| % off 52W high | Yes | Not surfaced (high_52w in scan) |
| Saved scans | Yes | No |
| Live result counts | Yes | No |
| Chart overlays | RS line, MAs, EPS markers, patterns | Candles + pivot/stop lines + contraction markers |
| AI thesis | No (analyst grade) | DeepSeek VCP assessment (our differentiator) |
| Notifications | Watchlist alerts | Roadmap Phase 5 (unimplemented) |

---

## 3. Audit Tiers

### Tier A — Zero new data provider (from cached bars + scan)
Fits our pipeline (`Universe → cache → metrics → VCP → AI`) with no new dependencies.

| # | Feature | Effort | Notes |
|---|---|---|---|
| A1 | **Relative volume / Volume Buzz** (today vol ÷ 50D avg) | S | Pure function over cached bars |
| A2 | **% off 52W high + % above 52W low** | S | Pure function over cached bars |
| A3 | **RS Score as first-class column** | S | Recomputed from cached bars (rank by 1-yr return) so it survives across endpoints |
| A4 | **Candidate table enrichment** | M | RS / Vol buzz / % off high columns in `CandidateTable` |
| A5 | **Saved scans** | M | New `saved_scans` sqlite table + `GET/POST/DELETE /api/v1/scans` + FilterBar dropdown |
| A6 | **Live result counts** | S | Client-side: "N candidates" while filtering |
| A7 | **MA overlays SMA20/50/200** | S | Line series on `ChartViewer` |
| A8 | **Volume sub-pane with surge markers** | M | Phase 2 (below) |
| A9 | **RS line vs S&P500 overlay** | M | Needs index bars cached; Phase 2 |

### Tier B — Needs a fundamentals/earnings/institutional provider (DEFERRED — separate spec)

| # | Feature | Notes |
|---|---|---|
| B1 | EPS Score / growth / acceleration / surprise | New data provider required |
| B2 | Sales growth | New data provider required |
| B3 | Earnings calendar + alerts | New data provider required |
| B4 | Institutional ownership QoQ | New data provider required |
| B5 | Analyst consensus + price target | New data provider required |
| B6 | Peer valuation (P/E, P/S, P/B) | New data provider required |
| B7 | Market cap / free-float filters | New data provider required |

### Tier C — Product & market context

| # | Feature | Status |
|---|---|---|
| C1 | **Market-regime gate** (M of CANSLIM: SPY vs SMA200) | IN SCOPE (C-1) |
| C2 | Learn guides | Deferred |
| C3 | Share / community features | Deferred |
| C4 | Generic pattern detector | Deferred |

### Tier D — Roadmap Phase 5 (Containerization + Notifications)

| # | Feature | Notes |
|---|---|---|
| D1 | Backend multi-stage `Dockerfile` | uv build stage → slim runtime; WAL sqlite in named volume |
| D2 | Frontend `Dockerfile` + `nginx.conf` | npm ci + vite build → nginx serving `dist/`, proxy `/api` → `backend:8000` |
| D3 | `docker-compose.yml` | `web` (nginx) + `api` services, env via `.env`, volume for `bars.db` |
| D4 | `app/notify/telegram.py` | `send_vcp_alert(assessment) -> bool` |
| D5 | `app/scheduler.py` | APScheduler cron Mon–Fri 16:30 NY, gated on `MIN_TELEGRAM_ALERT_SCORE` |
| D6 | `main.py` lifespan hook | Start scheduler only when `telegram_bot_token` set (must not run in tests) |
| D7 | `.env.example` additions | `MIN_TELEGRAM_ALERT_SCORE=85`, `DB_PATH`, nginx `CORS_ORIGINS` |
| D8 | Config fixes | `db_path` + `CORS_ORIGINS` must include nginx origin |

---

## 4. Phasing & Implementation Order

User-approved order: **Tier D first** (notifications wanted ASAP), then **Tier A + C-1**.

- **Phase 1a — Tier D (now):** Telegram alerts + scheduler + Docker. → `docs/plan_tier_d_notifications.md`
- **Phase 1b — Tier A (A1–A7) + C-1 (now):** metrics layer, table enrichment, saved scans, live counts, MAs, regime gate. → `docs/plan_tier_a_metrics.md`
- **Phase 2:** Tier A8–A9 (volume sub-pane, RS line vs S&P500 — needs index caching).
- **Phase 3 (separate spec):** Tier B1–B3 (EPS/sales/earnings calendar). Deferred: B4–B6, C2–C4.

---

## 5. Architecture Decisions

1. **Extract metrics layer** → `backend/app/screener/metrics.py`: pure functions over cached bars (`sma`, `relative_volume`, `pct_off_52w_high`, `pct_above_52w_low`, `rs_rank`). Testable in isolation; reused by scan, watchlist, and chart endpoints.
2. **RS from cached bars, not scan-time proxy** — `rs_rank(symbols_bars)` ranks by 1-year return percentile across all cached symbols. Self-contained, deterministic, survives across `/vcp/scan`, `/watchlist`, saved scans. The scan-time `apply_rs_proxy` stays as the universe filter threshold.
3. **Filters become server-visible** — a backend Pydantic `Filters` model mirrors `useScanner.Filters` so saved scans can round-trip as JSON.
4. **Pipeline unchanged:** `Universe → cache → metrics → VCP → AI`.
5. **Tier A adds no new dependencies.** Follow existing conventions: `cache.py` sqlite pattern, `client.py` httpx pattern, Pydantic response models, `docs/plan_*.md` naming.
6. **Scheduler reuses the real pipeline** — no new data paths; the daily job drives the same functions `main.py` already uses, so behavior matches the GUI scan.

---

## 6. Explicitly Out of Scope (this round)

- Any fundamental/earnings/institutional data (Tier B).
- Index caching + RS line overlay (Tier A8/A9, Phase 2).
- Learn guides, sharing, generic pattern detector (C2–C4).
- Backtest harness / vectorbt (existing `docs/plan_quant_extension.md` backlog).