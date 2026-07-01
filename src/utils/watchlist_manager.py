"""Dynamic watchlist — tracks 50 active stocks, evicts weak performers, pulls replacements from universe."""

import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

WEAK_SIGNALS = {"HOLD", "SELL", "STRONG SELL", "NO ACTION"}


class WatchlistManager:
    def __init__(self, db_path: str, target_size: int = 50, weak_threshold: int = 3):
        self.db_path = db_path
        self.target_size = target_size
        self.weak_threshold = weak_threshold
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS watchlist (
                    ticker TEXT PRIMARY KEY,
                    name TEXT,
                    sector TEXT,
                    added_date TEXT,
                    consecutive_weak_signals INTEGER DEFAULT 0,
                    last_signal TEXT,
                    last_scanned TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scan_state (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidates (
                    ticker TEXT PRIMARY KEY,
                    company_name TEXT,
                    signal TEXT,
                    conviction_score INTEGER,
                    entry_price REAL,
                    stop_loss REAL,
                    take_profit_targets TEXT,
                    screened_at TEXT,
                    batch_id TEXT
                )
            """)
            conn.commit()

    # ── Candidates (batch pre-screened stocks) ─────────────────────────────

    def add_candidate(self, ticker: str, company_name: str, signal: str,
                      conviction: int, entry_price: float, stop_loss: float,
                      take_profit_targets: list, batch_id: str = ""):
        import json as _json
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO candidates
                (ticker, company_name, signal, conviction_score, entry_price,
                 stop_loss, take_profit_targets, screened_at, batch_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (ticker, company_name, signal, conviction, entry_price,
                  stop_loss, _json.dumps(take_profit_targets), now, batch_id))
            conn.commit()

    def get_candidates(self, limit: int = 20, exclude: set | None = None) -> list[dict]:
        """Return top candidates sorted by conviction then risk/reward ratio."""
        import json as _json
        exclude = exclude or set()
        exclude |= self.get_active_tickers()
        placeholders = ",".join("?" * len(exclude)) if exclude else "NULL"
        with self._connect() as conn:
            rows = conn.execute(f"""
                SELECT ticker, company_name, signal, conviction_score,
                       entry_price, stop_loss, take_profit_targets, screened_at
                FROM candidates
                WHERE ticker NOT IN ({placeholders})
            """, tuple(exclude) if exclude else ()).fetchall()

        results = []
        for r in rows:
            targets = _json.loads(r[6]) if r[6] else []
            entry, stop = r[4], r[5]
            t3 = targets[2] if len(targets) >= 3 else (targets[-1] if targets else 0)
            risk = entry - stop
            rr = (t3 - entry) / risk if risk > 0 else 0.0
            results.append({
                "ticker": r[0], "company_name": r[1], "signal": r[2],
                "conviction_score": r[3], "entry_price": entry,
                "stop_loss": stop, "take_profit_targets": targets,
                "screened_at": r[7], "rr_ratio": round(rr, 2),
            })

        results.sort(key=lambda x: (-x["conviction_score"], -x["rr_ratio"]))
        return results[:limit]

    def remove_candidate(self, ticker: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM candidates WHERE ticker = ?", (ticker,))
            conn.commit()

    def clear_candidates(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM candidates")
            conn.commit()

    def candidate_count(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]

    def get_scan_cursor(self) -> int:
        """Position in the universe list where the next replacement scan should resume."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM scan_state WHERE key = 'universe_cursor'"
            ).fetchone()
        return int(row[0]) if row else 0

    def set_scan_cursor(self, index: int):
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO scan_state (key, value) VALUES ('universe_cursor', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(index),),
            )
            conn.commit()

    def size(self) -> int:
        with self._connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0]

    def get_active(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker, name, sector FROM watchlist ORDER BY ticker"
            ).fetchall()
        return [{"ticker": r[0], "name": r[1], "sector": r[2]} for r in rows]

    def get_active_tickers(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT ticker FROM watchlist").fetchall()
        return {r[0] for r in rows}

    def seed(self, stocks: list[dict]):
        """Populate watchlist with initial stocks if it is currently empty."""
        if self.size() > 0:
            return
        now = datetime.now().isoformat()
        with self._connect() as conn:
            for s in stocks:
                conn.execute(
                    "INSERT OR IGNORE INTO watchlist (ticker, name, sector, added_date) VALUES (?, ?, ?, ?)",
                    (s["ticker"], s.get("name", s["ticker"]), s.get("sector", ""), now),
                )
            conn.commit()
        logger.info("Watchlist seeded with %d stocks", self.size())

    def update_signal(self, ticker: str, signal: str):
        """Increment or reset the consecutive-weak-signal counter after each scan."""
        now = datetime.now().isoformat()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT consecutive_weak_signals FROM watchlist WHERE ticker = ?", (ticker,)
            ).fetchone()
            if not row:
                return
            count = (row[0] + 1) if signal in WEAK_SIGNALS else 0
            conn.execute(
                "UPDATE watchlist SET consecutive_weak_signals=?, last_signal=?, last_scanned=? WHERE ticker=?",
                (count, signal, now, ticker),
            )
            conn.commit()
        if count >= self.weak_threshold:
            logger.info("%s flagged as underperformer (%d consecutive weak signals)", ticker, count)

    def get_underperformers(self) -> list[str]:
        """Tickers that have hit the weak-signal eviction threshold."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ticker FROM watchlist WHERE consecutive_weak_signals >= ?",
                (self.weak_threshold,),
            ).fetchall()
        return [r[0] for r in rows]

    def remove(self, ticker: str):
        with self._connect() as conn:
            conn.execute("DELETE FROM watchlist WHERE ticker = ?", (ticker,))
            conn.commit()
        logger.info("Evicted %s from watchlist", ticker)

    def add(self, ticker: str, name: str, sector: str):
        now = datetime.now().isoformat()
        with self._connect() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO watchlist
                   (ticker, name, sector, added_date, consecutive_weak_signals)
                   VALUES (?, ?, ?, ?, 0)""",
                (ticker, name, sector, now),
            )
            conn.commit()
        logger.info("Added %s (%s) to watchlist", ticker, name)

    def slots_available(self) -> int:
        return max(0, self.target_size - self.size())

    def available_from_universe(self, universe: list[str]) -> list[str]:
        """Universe tickers not currently in the watchlist, starting from the saved
        scan cursor and wrapping around — so repeated scans cycle through the full
        universe before repeating, instead of always restarting at index 0."""
        if not universe:
            return []
        current = self.get_active_tickers()
        cursor = self.get_scan_cursor() % len(universe)
        rotated = universe[cursor:] + universe[:cursor]
        return [t for t in rotated if t not in current]
