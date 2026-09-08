"""SQLite cache for daily OHLCV bars and AI assessments (stdlib sqlite3, WAL mode)."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol TEXT NOT NULL,
    ts INTEGER NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL,
    volume REAL,
    PRIMARY KEY (symbol, ts)
);
CREATE INDEX IF NOT EXISTS idx_bars_symbol_ts ON bars (symbol, ts);

CREATE TABLE IF NOT EXISTS assessments (
    symbol TEXT PRIMARY KEY,
    bar_hash TEXT NOT NULL,
    payload TEXT NOT NULL,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    symbol TEXT PRIMARY KEY,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_scans (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    filters TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
"""


def _bar_hash(bars: list[tuple], limit: int = 200) -> str:
    """Fingerprint of the bars the VCP engine consumes, so stale results invalidate."""
    h = hashlib.sha256()
    for b in bars[-limit:]:
        h.update(f"{b[0]}|{b[2]}|{b[3]}|{b[4]}|{b[5]}\n".encode())
    return h.hexdigest()


class BarCache:
    def __init__(self, db_path: str) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        return conn

    def has_recent_bars(self, symbol: str, min_bars: int = 200) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM bars WHERE symbol = ?", (symbol,)
            ).fetchone()
        return bool(row and row[0] >= min_bars)

    def upsert_bars(self, symbol: str, rows: list[tuple]) -> None:
        """Insert or replace bars. Each row is (ts, open, high, low, close, volume)."""
        if not rows:
            return
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO bars (symbol, ts, open, high, low, close, volume)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    [(symbol, *row) for row in rows],
                )

    def get_bars(self, symbol: str) -> list[tuple]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT ts, open, high, low, close, volume FROM bars"
                " WHERE symbol = ? ORDER BY ts",
                (symbol,),
            )
            return list(cur.fetchall())

    def symbols(self, min_bars: int = 200) -> list[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT symbol FROM bars GROUP BY symbol HAVING COUNT(*) >= ? ORDER BY symbol",
                (min_bars,),
            )
            return [row[0] for row in cur.fetchall()]

    def get_assessment(self, symbol: str, bar_hash: str) -> str | None:
        """Return cached assessment payload if the bar fingerprint matches, else None."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM assessments WHERE symbol = ? AND bar_hash = ?",
                (symbol, bar_hash),
            ).fetchone()
        return row[0] if row else None

    def put_assessment(self, symbol: str, bar_hash: str, payload: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO assessments (symbol, bar_hash, payload, updated_at)"
                    " VALUES (?, ?, ?, ?)",
                    (symbol, bar_hash, payload, int(time.time())),
                )

    def upsert_watchlist(self, symbols: list[str]) -> None:
        if not symbols:
            return
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT OR IGNORE INTO watchlist (symbol, added_at) VALUES (?, ?)",
                    [(s, now) for s in symbols],
                )

    def watchlist_symbols(self) -> list[str]:
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT symbol FROM watchlist ORDER BY added_at DESC, symbol"
            )
            return [row[0] for row in cur.fetchall()]

    def list_scans(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT id, name, filters, created_at FROM saved_scans ORDER BY created_at DESC"
            ).fetchall()
        return [
            {"id": r[0], "name": r[1], "filters": json.loads(r[2]), "created_at": r[3]}
            for r in rows
        ]

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