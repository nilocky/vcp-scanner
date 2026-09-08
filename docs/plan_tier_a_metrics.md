# Tier A — Screener Metrics & UI Enrichment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tweevest-style screener metrics (RS Score, Volume Buzz, % off 52W high) as first-class columns, saved scans, live result counts, chart MA overlays, and a market-regime gate — all from cached bars, no new data provider.

**Architecture:** A pure metrics layer (`app/screener/metrics.py`) computes all derived values from cached OHLCV bars. The VCP scan and watchlist endpoints enrich each `VCPResult` with these metrics. Saved scans persist the client `Filters` object as JSON in a new `saved_scans` sqlite table with CRUD endpoints. The frontend surfaces new columns, a save/load dropdown, live counts, MA overlays on the chart, and a SPY-vs-SMA200 regime badge. The regime endpoint backfills SPY through the existing yfinance path.

**Tech Stack:** Python 3.11/FastAPI (unchanged), sqlite3 stdlib (existing `cache.py` pattern), React 19/Vite/Tailwind/lightweight-charts (unchanged). No new dependencies.

**Spec:** `docs/plan_tweevest_blueprint.md` Tier A (A1–A7) + C-1.

## Global Constraints

- Pipeline stays `Universe → cache → metrics → VCP → AI`; metrics are a pure layer over cached bars.
- `VCPResult` (backend) gains only **optional** fields (defaults `None`) so existing tests/frontend keep working.
- RS Score is computed from cached bars: rank each symbol's 1-year return percentile 1–99 across all cached symbols (`metrics.rs_rank`). The scan-time `apply_rs_proxy` stays only as the universe filter.
- Frontend `Filters` interface lives in `src/hooks/useScanner.ts`; the backend gets a mirror Pydantic model for saved scans. Save = persist JSON; load = re-run with that filter set. Filters remain client-side for filtering logic.
- Test convention: `backend/tests/test_*.py` with `sys.path.insert(0, ...)` + plain asserts + `if __name__ == "__main__":` runner. Run `pytest tests/` in `backend/`.
- No new npm dependencies. Follow existing frontend patterns (`types.ts` interfaces, `api.ts` `get<T>` helper, sortable columns in `CandidateTable`).

---

### Task A-1: Metrics layer `backend/app/screener/metrics.py`

**Files:**
- Create: `backend/app/screener/__init__.py` (empty)
- Create: `backend/app/screener/metrics.py`
- Test: `backend/tests/test_metrics.py`

**Interfaces:**
- Consumes: bars as `list[tuple[int, float, float, float, float, float|None]]` → `(ts, open, high, low, close, volume)`.
- Produces:
  - `def sma(closes: list[float], n: int) -> float | None` — last SMA value (or `None` if fewer than `n` values).
  - `def relative_volume(bars, lookback: int = 50) -> float | None` — last bar volume ÷ mean of previous `lookback` volumes (`None` if insufficient data or last volume missing).
  - `def pct_off_52w_high(bars) -> float | None` — `(close/last 252-bar max high - 1) * 100`, negative below high.
  - `def pct_above_52w_low(bars) -> float | None` — `(close/last 252-bar min low - 1) * 100`.
  - `def one_year_return(bars) -> float | None` — `close[-1]/close[-253] - 1` (252 trading days), `None` if < 253 bars.
  - `def rs_rank(symbols_bars: dict[str, list[tuple]], *, min_bars: int = 253) -> dict[str, float]` — for each symbol with ≥ `min_bars` bars, `one_year_return`, then percentile rank 1–99 (`round(pos / max(n-1,1) * 99.0, 1)`, tied ranks averaged). Symbols with missing returns get `None`/are excluded.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_metrics.py`

```python
from __future__ import annotations
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.screener.metrics import (
    sma, relative_volume, pct_off_52w_high, pct_above_52w_low, one_year_return, rs_rank,
)


def _bars(closes: list[float], volumes: list[float] | None = None) -> list[tuple]:
    vols = volumes or [1000.0] * len(closes)
    return [(i, c, c, c, c, v) for i, (c, v) in enumerate(zip(closes, vols))]


def test_sma_basic() -> None:
    assert sma([1.0, 2.0, 3.0, 4.0], 3) == 3.0
    assert sma([1.0, 2.0], 3) is None


def test_relative_volume() -> None:
    vols = [1000.0] * 50 + [2500.0]
    bars = [(i, 10.0, 10.0, 10.0, 10.0, v) for i, v in enumerate(vols)]
    assert relative_volume(bars, lookback=50) == 2.5
    assert relative_volume(bars[:10], lookback=50) is None


def test_pct_off_high_and_above_low() -> None:
    # last close 95, 252-bar high 100, low 50
    bars = [(i, 100.0, 100.0, 50.0, 95.0, 1000.0) for i in range(252)]
    assert abs(pct_off_52w_high(bars) - (-5.0)) < 1e-9
    assert abs(pct_above_52w_low(bars) - 90.0) < 1e-9
    assert pct_off_52w_high(bars[:10]) is None


def test_one_year_return_and_rs_rank() -> None:
    up = _bars([100.0 + i for i in range(253)])
    flat = _bars([100.0] * 253)
    down = _bars([200.0 - i for i in range(253)])
    assert abs(one_year_return(up) - (352.0 / 100.0 - 1.0)) < 1e-9

    ranks = rs_rank({"UP": up, "FLAT": flat, "DOWN": down})
    assert ranks["UP"] == 99.0
    assert ranks["FLAT"] == 50.0
    assert ranks["DOWN"] == 1.0
    # short bars excluded
    assert "SHORT" not in rs_rank({"SHORT": _bars([1.0, 2.0])})


if __name__ == "__main__":
    test_sma_basic()
    print("sma passed")
    test_relative_volume()
    print("relative_volume passed")
    test_pct_off_high_and_above_low()
    print("off-high/above-low passed")
    test_one_year_return_and_rs_rank()
    print("return/rs_rank passed")
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_metrics.py -v`
  Expected: FAIL — `ModuleNotFoundError: No module named 'app.screener'`

- [ ] **Step 3: Write minimal implementation** — `backend/app/screener/metrics.py`

```python
"""Pure metrics computed from cached OHLCV bars. No I/O, no dependencies."""
from __future__ import annotations

TRADING_DAYS_YEAR = 252


def sma(closes: list[float], n: int) -> float | None:
    if len(closes) < n:
        return None
    return sum(closes[-n:]) / n


def relative_volume(bars: list[tuple], lookback: int = 50) -> float | None:
    if len(bars) < lookback + 1:
        return None
    last_vol = bars[-1][5]
    if last_vol is None:
        return None
    prev = [b[5] for b in bars[-(lookback + 1):-1]]
    if not prev or any(v is None for v in prev):
        return None
    avg = sum(v for v in prev) / len(prev)
    if avg == 0:
        return None
    return last_vol / avg


def pct_off_52w_high(bars: list[tuple]) -> float | None:
    window = bars[-TRADING_DAYS_YEAR:]
    if len(window) < TRADING_DAYS_YEAR:
        return None
    high = max(b[2] for b in window)
    return (window[-1][4] / high - 1.0) * 100.0 if high else None


def pct_above_52w_low(bars: list[tuple]) -> float | None:
    window = bars[-TRADING_DAYS_YEAR:]
    if len(window) < TRADING_DAYS_YEAR:
        return None
    low = min(b[3] for b in window)
    return (window[-1][4] / low - 1.0) * 100.0 if low else None


def one_year_return(bars: list[tuple]) -> float | None:
    if len(bars) < TRADING_DAYS_YEAR + 1:
        return None
    return bars[-1][4] / bars[-(TRADING_DAYS_YEAR + 1)][4] - 1.0


def rs_rank(symbols_bars: dict[str, list[tuple]], *, min_bars: int = TRADING_DAYS_YEAR + 1) -> dict[str, float]:
    """IBD-style RS proxy: percentile (1-99) of 1-year return across cached symbols."""
    returns = {sym: one_year_return(bars) for sym, bars in symbols_bars.items()}
    returns = {k: v for k, v in returns.items() if v is not None}
    if not returns:
        return {}
    ordered = sorted(returns.values())
    n = len(ordered)
    ranks: dict[str, float] = {}
    for sym, r in returns.items():
        # percentile with ties averaged
        lo = next(i for i, v in enumerate(ordered) if v >= r)
        hi = next(i for i in range(n - 1, -1, -1) if ordered[i] <= r)
        pos = (lo + hi) / 2.0
        ranks[sym] = round(pos / max(n - 1, 1) * 99.0, 1)
    return ranks
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_metrics.py -v`
  Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/screener/ backend/tests/test_metrics.py
git commit -m "feat: screener metrics layer (rs, vol buzz, off-high)"
```

---

### Task A-2: `VCPResult` enrichment fields

**Files:**
- Modify: `backend/app/vcp/engine.py`
- Test: `backend/tests/test_vcp.py` (extend)

**Interfaces:**
- Consumes: none new.
- Produces: `VCPResult` gains optional fields `relative_volume: float | None = None`, `pct_off_52w_high: float | None = None`, `rs: float | None = None`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_vcp.py`

```python
def test_vcp_result_optional_metrics_default_none() -> None:
    r = VCPResult(symbol="X", contractions=[], volume_dryup_ratio=None,
                  pivot_buy_price=None, stop_loss=None, verdict="FAILED_STRUCTURE")
    assert r.relative_volume is None
    assert r.pct_off_52w_high is None
    assert r.rs is None
    assert "relative_volume" in r.model_dump()
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_vcp.py::test_vcp_result_optional_metrics_default_none -v`
  Expected: FAIL — `AttributeError: 'VCPResult' object has no attribute 'relative_volume'`

- [ ] **Step 3: Add the fields** — in `backend/app/vcp/engine.py`

```python
class VCPResult(BaseModel):
    symbol: str
    contractions: list[Contraction]
    volume_dryup_ratio: float | None = None
    pivot_buy_price: float | None = None
    stop_loss: float | None = None
    verdict: str
    relative_volume: float | None = None
    pct_off_52w_high: float | None = None
    rs: float | None = None
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_vcp.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/vcp/engine.py backend/tests/test_vcp.py
git commit -m "feat: optional metrics fields on vcp result"
```

---

### Task A-3: Enrich `/vcp/scan` and `/watchlist` endpoints

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_routes.py` (extend)

**Interfaces:**
- Consumes: `metrics.relative_volume`, `metrics.pct_off_52w_high`, `metrics.rs_rank`; `_cache.get_bars`.
- Produces: `vcp_scan` and `watchlist` responses whose `results[]` each carry `relative_volume`, `pct_off_52w_high`, `rs`.

- [ ] **Step 1: Write the failing test** — append to `backend/tests/test_routes.py`

```python
def test_vcp_scan_enriches_metrics() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    symbol = "NYSE:GKOS"
    vols = [1000.0] * 50 + [2000.0]
    bars = [(i, 100.0, 105.0, 95.0, 100.0, v) for i, v in enumerate(vols)]
    # ensure >= 253 bars for rs_rank inclusion
    while len(bars) < 253:
        bars.append((len(bars), 100.0, 105.0, 95.0, 100.0, 1000.0))
    cache.upsert_bars(symbol, bars)

    def strong(sym, bars_):
        return VCPResult(symbol=sym, contractions=[Contraction(peak_ts=1, trough_ts=2, depth_pct=3.0, days=4)],
                         volume_dryup_ratio=0.3, pivot_buy_price=100.0, stop_loss=95.0, verdict="STRONG_SETUP")

    with mock.patch.object(main, "detect_vcp", strong), mock.patch.object(main, "_cache", cache):
        res = client.get("/api/v1/vcp/scan")
    assert res.status_code == 200, res.text
    row = res.json()["results"][0]
    assert row["relative_volume"] == 2.0
    assert row["pct_off_52w_high"] is not None
    assert row["rs"] == 99.0
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_routes.py::test_vcp_scan_enriches_metrics -v`
  Expected: FAIL — `KeyError: 'relative_volume'`

- [ ] **Step 3: Implement enrichment** — in `backend/app/main.py`

Add import:
```python
from .screener import metrics
```

Add a shared helper above the routes:
```python
def _attach_metrics(results: list[VCPResult]) -> None:
    """Fill relative_volume / pct_off_52w_high / rs from cached bars, in place."""
    symbols_bars = {r.symbol: _cache.get_bars(r.symbol) for r in results}
    ranks = metrics.rs_rank(symbols_bars)
    for r in results:
        bars = symbols_bars.get(r.symbol) or []
        r.relative_volume = metrics.relative_volume(bars)
        r.pct_off_52w_high = metrics.pct_off_52w_high(bars)
        r.rs = ranks.get(r.symbol)
```

Call `_attach_metrics(rows)` just before each return in `vcp_scan` and in `watchlist`:
```python
    _attach_metrics(rows)
    return VCPScanResponse(scanned=len(results), qualified=len(qualified), results=rows)
```
```python
    _attach_metrics(results)
    return VCPScanResponse(...)
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_routes.py -v`
  Expected: PASS (all route tests incl. existing)

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/test_routes.py
git commit -m "feat: enrich vcp scan and watchlist with screener metrics"
```

---

### Task A-4: Frontend candidate table enrichment + live count

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/hooks/useScanner.ts`
- Modify: `frontend/src/components/CandidateTable.tsx`

**Interfaces:**
- Consumes: enriched `VCPResult` fields (`relative_volume`, `pct_off_52w_high`, `rs`).
- Produces: `Row` gains `rs`, `relativeVolume`, `pctOffHigh`; `CandidateTable` renders sortable **RS**, **Vol buzz**, **% off high** columns; live count "N candidates" in the toolbar.

- [ ] **Step 1: Update types** — `frontend/src/types.ts`

```ts
export interface VCPResult {
  symbol: string;
  contractions: Contraction[];
  volume_dryup_ratio: number | null;
  pivot_buy_price: number | null;
  stop_loss: number | null;
  verdict: string;
  relative_volume: number | null;
  pct_off_52w_high: number | null;
  rs: number | null;
}
```

- [ ] **Step 2: Update Row + mapping** — `frontend/src/hooks/useScanner.ts`

```ts
export interface Row {
  symbol: string;
  verdict: string;
  contractions: number;
  finalDepthPct: number;
  volumeDryup: number | null;
  pivot: number | null;
  stop: number | null;
  aiScore: number | null;
  riskReward: number | null;
  rs: number | null;
  relativeVolume: number | null;
  pctOffHigh: number | null;
}
```

In `toRow(r: VCPResult, a: VCPAssessment | null)` add:
```ts
  rs: r.rs,
  relativeVolume: r.relative_volume,
  pctOffHigh: r.pct_off_52w_high,
```

- [ ] **Step 3: Extend `CandidateTable`** — add columns (in the sortable `columns` array after `symbol`):

```ts
{ key: "rs", label: "RS" },
{ key: "relativeVolume", label: "Vol buzz" },
{ key: "pctOffHigh", label: "% off high" },
```

Add formatters (already have `pct()` and `num()`):
```ts
const volBuzz = (v: number | null) => (v == null ? "—" : `${v >= 0 ? "+" : ""}${Math.round((v - 1) * 100)}%`);
```

In the `<tr>` cells render: `rs` as `num()`-style badge (≥70 emerald, ≥50 amber, else red — mirror aiScore badges), `relativeVolume` via `volBuzz`, `pctOffHigh` via `pct()`. Update empty-state `colSpan` to `aiEnabled ? 12 : 11`.

- [ ] **Step 4: Add live count in toolbar** — `CandidateTable` header area above the table: `{rows.length} candidates`.

- [ ] **Step 5: Verify build**
  Run: `npm run build` (in `frontend/`)
  Expected: `tsc --noEmit` passes, build succeeds.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types.ts frontend/src/hooks/useScanner.ts frontend/src/components/CandidateTable.tsx
git commit -m "feat: candidate table rs/vol-buzz/off-high columns + live count"
```

---

### Task A-5: Saved scans — backend

**Files:**
- Modify: `backend/app/db/cache.py`
- Create: `backend/app/schemas.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_saved_scans.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `BarCache.list_scans() -> list[dict]`, `BarCache.save_scan(name: str, filters_json: str) -> int`, `BarCache.delete_scan(scan_id: int) -> bool`.
  - `Filters` Pydantic model: `min_contractions: int = 3`, `min_tightness: float = 8.0`, `min_ai_score: int = 0`, `include_premature: bool = False`.
  - Endpoints: `GET /api/v1/scans` → `list[SavedScan{id,name,filters,created_at}]`, `POST /api/v1/scans` body `{name, filters: Filters}` → `SavedScan`, `DELETE /api/v1/scans/{scan_id}` → `{ok: true}` (404 if missing).

- [ ] **Step 1: Write the failing test** — `backend/tests/test_saved_scans.py`

```python
from __future__ import annotations
import os, sys, tempfile, unittest.mock as mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app.main as main
from app.db.cache import BarCache

client = TestClient(main.app)


def test_saved_scans_crud() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    with mock.patch.object(main, "_cache", cache):
        res = client.get("/api/v1/scans")
        assert res.status_code == 200 and res.json() == []

        res = client.post("/api/v1/scans", json={
            "name": "Tight setups",
            "filters": {"min_contractions": 3, "min_tightness": 8.0, "min_ai_score": 80, "include_premature": True},
        })
        assert res.status_code == 200, res.text
        scan = res.json()
        assert scan["id"] == 1
        assert scan["filters"]["min_ai_score"] == 80
        assert scan["name"] == "Tight setups"

        res = client.get("/api/v1/scans")
        assert len(res.json()) == 1

        res = client.delete("/api/v1/scans/1")
        assert res.status_code == 200 and res.json() == {"ok": True}
        assert client.get("/api/v1/scans").json() == []

        res = client.delete("/api/v1/scans/99")
        assert res.status_code == 404


if __name__ == "__main__":
    test_saved_scans_crud()
    print("saved scans crud passed")
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_saved_scans.py -v`
  Expected: FAIL — 404/route missing

- [ ] **Step 3: Implement cache methods** — in `backend/app/db/cache.py`

Add to `_SCHEMA`:
```sql
CREATE TABLE IF NOT EXISTS saved_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filters TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
```

Add methods on `BarCache`:
```python
def list_scans(self) -> list[dict]:
    with self._connect() as conn:
        rows = conn.execute("SELECT id, name, filters, created_at FROM saved_scans ORDER BY created_at DESC").fetchall()
    return [{"id": r[0], "name": r[1], "filters": json.loads(r[2]), "created_at": r[3]} for r in rows]


def save_scan(self, name: str, filters_json: str) -> int:
    with self._connect() as conn:
        cur = conn.execute(
            "INSERT INTO saved_scans (name, filters, created_at) VALUES (?, ?, ?)",
            (name, filters_json, int(time.time())),
        )
        return int(cur.lastrowid)


def delete_scan(self, scan_id: int) -> bool:
    with self._connect() as conn:
        cur = conn.execute("DELETE FROM saved_scans WHERE id = ?", (scan_id,))
        return cur.rowcount > 0
```

Add `import json` and `import time` at the top of the module.

- [ ] **Step 4: Create `backend/app/schemas.py`**

```python
from pydantic import BaseModel, Field


class Filters(BaseModel):
    min_contractions: int = Field(default=3, ge=1)
    min_tightness: float = Field(default=8.0, gt=0)
    min_ai_score: int = Field(default=0, ge=0, le=100)
    include_premature: bool = False


class SavedScan(BaseModel):
    id: int
    name: str
    filters: Filters
    created_at: int
```

- [ ] **Step 5: Wire endpoints** — in `backend/app/main.py`

Imports:
```python
from .schemas import Filters, SavedScan
```

Routes:
```python
@app.get("/api/v1/scans", response_model=list[SavedScan], tags=["Scanner"], summary="List saved scans")
async def list_scans() -> list[SavedScan]:
    return [SavedScan(**s) for s in _cache.list_scans()]


@app.post("/api/v1/scans", response_model=SavedScan, tags=["Scanner"], summary="Save a scan filter set")
async def save_scan(name: str, filters: Filters) -> SavedScan:
    scan_id = _cache.save_scan(name, filters.model_dump_json())
    return SavedScan(id=scan_id, name=name, filters=filters, created_at=int(time.time()))


@app.delete("/api/v1/scans/{scan_id}", tags=["Scanner"], summary="Delete a saved scan")
async def delete_scan(scan_id: int) -> dict:
    if not _cache.delete_scan(scan_id):
        raise HTTPException(status_code=404, detail=f"No saved scan with id {scan_id}")
    return {"ok": True}
```

Add `import time` to `main.py`.

- [ ] **Step 6: Run test to verify it passes**
  Run: `pytest tests/test_saved_scans.py -v`
  Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/db/cache.py backend/app/schemas.py backend/app/main.py backend/tests/test_saved_scans.py
git commit -m "feat: saved scans crud endpoints"
```

---

### Task A-6: Saved scans — frontend

**Files:**
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/components/FilterBar.tsx`
- Modify: `frontend/src/hooks/useScanner.ts`

**Interfaces:**
- Consumes: `GET/POST/DELETE /api/v1/scans`.
- Produces: `api.listScans/saveScan/deleteScan`; `FilterBar` save/load dropdown; `useScanner.applySaved(filters)` runs a scan with saved filters.

- [ ] **Step 1: Extend `api.ts`**

```ts
export interface SavedScan { id: number; name: string; filters: Filters; created_at: number; }

export const api = {
  // ... existing ...
  listScans: () => get<SavedScan[]>('/scans'),
  saveScan: (name: string, filters: Filters) => post<SavedScan>('/scans', { name, filters }),
  deleteScan: (id: number) => del<{ ok: boolean }>(`/scans/${id}`),
};
```

Add small `post`/`del` helpers beside the existing `get<T>` helper (mirror its error handling: throw on `!res.ok` after parsing `detail`).

- [ ] **Step 2: Extend `useScanner`** — expose `run` (existing) plus `applySaved(filters: Filters)` that calls the same `run` path, and a `savedScans` list loaded via `api.listScans()` on mount.

- [ ] **Step 3: FilterBar save/load** — add props `onSave(filters: Filters)` and `onLoad(filters: Filters)` (or reuse `onScan`). UI: a small `Save` button prompting for a name (reuse `window.prompt`) and a `<select>` dropdown of saved scans whose `onChange` calls `onLoad(scan.filters)`.

- [ ] **Step 4: Wire in `App.tsx`** — pass `onSave` (calls `api.saveScan`) and `onLoad` (calls `applySaved`) into `FilterBar`.

- [ ] **Step 5: Verify build**
  Run: `npm run build` (in `frontend/`)
  Expected: build passes.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api.ts frontend/src/components/FilterBar.tsx frontend/src/hooks/useScanner.ts frontend/src/App.tsx
git commit -m "feat: saved scans save/load in filter bar"
```

---

### Task A-7: Chart MA overlays + market-regime gate (C-1)

**Files:**
- Modify: `frontend/src/components/ChartViewer.tsx`
- Modify: `backend/app/main.py`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/types.ts`, `frontend/src/api.ts`
- Test: `backend/tests/test_regime.py`

**Interfaces:**
- Consumes: `metrics.sma`; existing `fetch_history_bars`/`get_cache`.
- Produces:
  - Backend `GET /api/v1/market/regime` → `MarketRegime{ticker:"SPY", above_sma200: bool, spy_close: float, spy_sma200: float}`. Backfills SPY via `fetch_history_bars("SPY")`, `_cache.upsert_bars`, computes `sma(closes, 200)`, returns `above = spy_close > spy_sma200`.
  - Chart: SMA20/50/200 line overlays from `bars`.

- [ ] **Step 1: Write the failing test** — `backend/tests/test_regime.py`

```python
from __future__ import annotations
import os, sys, unittest.mock as mock
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app.main as main
from app.db.cache import BarCache

client = TestClient(main.app)


def test_market_regime_above_sma200() -> None:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    cache = BarCache(path)
    # rising closes: close climbs above its own 200-sma
    bars = [(i, c, c + 1.0, c - 1.0, c, 1000.0) for i, c in enumerate([100.0 + i for i in range(300)])]

    async def fake_fetch(symbol, **kw):
        from app.scanner.history import Bar
        return [Bar(symbol=symbol, ts=b[0], open=b[1], high=b[2], low=b[3], close=b[4], volume=b[5]) for b in bars]

    with mock.patch.object(main, "_cache", cache), mock.patch(
        "app.main.fetch_history_bars", side_effect=fake_fetch
    ):
        res = client.get("/api/v1/market/regime")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ticker"] == "SPY"
    assert body["above_sma200"] is True
    assert body["spy_close"] == bars[-1][4]
    assert body["spy_sma200"] > 0


if __name__ == "__main__":
    test_market_regime_above_sma200()
    print("market regime passed")
```

- [ ] **Step 2: Run test to verify it fails**
  Run: `pytest tests/test_regime.py -v`
  Expected: FAIL — 404 route missing

- [ ] **Step 3: Implement regime endpoint** — in `backend/app/main.py`

Imports:
```python
from .scanner.history import fetch_history_bars
from .screener import metrics
```

Schema (add near other response models):
```python
class MarketRegime(BaseModel):
    ticker: str
    above_sma200: bool
    spy_close: float
    spy_sma200: float
```

Route:
```python
@app.get("/api/v1/market/regime", response_model=MarketRegime, tags=["Scanner"], summary="Market regime: SPY vs SMA200 (M of CANSLIM)")
async def market_regime() -> MarketRegime:
    bars = _cache.get_bars("SPY")
    if not bars:
        fetched = await fetch_history_bars("SPY", period=settings.history_period)
        _cache.upsert_bars("SPY", [(b.ts, b.open, b.high, b.low, b.close, b.volume) for b in fetched])
        bars = _cache.get_bars("SPY")
    closes = [b[4] for b in bars]
    spy_sma200 = metrics.sma(closes, 200)
    if spy_sma200 is None:
        raise HTTPException(status_code=422, detail="Not enough SPY bars for a 200-day SMA")
    spy_close = closes[-1]
    return MarketRegime(ticker="SPY", above_sma200=spy_close > spy_sma200, spy_close=spy_close, spy_sma200=round(spy_sma200, 2))
```

- [ ] **Step 4: Run test to verify it passes**
  Run: `pytest tests/test_regime.py -v`
  Expected: PASS

- [ ] **Step 5: Chart MA overlays** — `frontend/src/components/ChartViewer.tsx`

Add a local SMA helper and line series after the candlestick series:
```ts
function sma(values: number[], n: number): (number | null)[] {
  return values.map((_, i) => (i < n - 1 ? null : values.slice(i - n + 1, i + 1).reduce((a, b) => a + b, 0) / n));
}
```
Then for each of `[20, 50, 200]` add a `LineSeries` (`color` slate/blue/amber) fed with `{ time, value }` (skip nulls) from `bars.map(b => b.close)`.

- [ ] **Step 6: Regime badge in frontend** — `types.ts` adds `MarketRegime{ticker, above_sma200, spy_close, spy_sma200}`; `api.ts` adds `regime: () => get<MarketRegime>('/market/regime')`. In `App.tsx`, on mount call `api.regime().then(setRegime)`; render a header badge: green "Market: Uptrend (SPY > SMA200)" when `above_sma200`, else red "Market: Downtrend". On fetch error, show nothing.

- [ ] **Step 7: Verify build**
  Run: `npm run build` (in `frontend/`)
  Expected: build passes.

- [ ] **Step 8: Commit**

```bash
git add backend/app/main.py backend/tests/test_regime.py frontend/src/components/ChartViewer.tsx frontend/src/App.tsx frontend/src/types.ts frontend/src/api.ts
git commit -m "feat: chart ma overlays + spy market regime gate"
```

---

## Self-Review

- **Spec coverage:** A1–A7 and C-1 all mapped to tasks. A8/A9 and Tier B intentionally deferred (see `docs/plan_tweevest_blueprint.md`). A6 live counts folded into A-4 (toolbar count).
- **Type consistency:** `metrics.relative_volume(bars, lookback=50)`, `pct_off_52w_high(bars)`, `rs_rank(symbols_bars)` names match across A-1 tests, A-3 `_attach_metrics`, and A-7 regime. `Row` fields (`rs`, `relativeVolume`, `pctOffHigh`) match `types.ts` → `useScanner.toRow` → `CandidateTable` usage.
- **No placeholders:** every code block is concrete; tests written out.
- **Test independence:** enriched-field tests use a fresh temp DB per test; regime test mocks `main.fetch_history_bars` so no network; saved-scans test mocks `main._cache`.
- **Backward compat:** all new `VCPResult` fields are optional with `None` defaults; frontend `Row` additions render "—" for null, so pre-backfill states degrade gracefully.