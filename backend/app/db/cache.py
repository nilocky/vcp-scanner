"""SQLite cache for daily OHLCV bars (stdlib sqlite3, WAL mode)."""
from __future__ import annotations

import sqlite3
import threading
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
"""


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