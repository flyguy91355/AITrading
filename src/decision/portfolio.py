"""Portfolio state and tracking with SQLite persistence."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


@dataclass
class Position:
    ticker: str
    shares: int
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit_targets: list[float]
    sector: str
    opened_at: datetime
    trailing_stop: float | None = None

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def cost_basis(self) -> float:
        return self.shares * self.entry_price

    @property
    def unrealized_pnl(self) -> float:
        return self.market_value - self.cost_basis

    @property
    def unrealized_pnl_pct(self) -> float:
        if self.cost_basis == 0:
            return 0.0
        return (self.unrealized_pnl / self.cost_basis) * 100


class Portfolio:
    def __init__(self, config: dict):
        self.config = config
        self.initial_capital = config["portfolio"]["initial_capital"]
        self.cash = self.initial_capital
        self.positions: dict[str, Position] = {}
        self.peak_value = self.initial_capital
        self.day_start_value = self.initial_capital
        self.db_path = config.get("database", {}).get("path", "data/aitrading.db")
        self._db: aiosqlite.Connection | None = None

    @property
    def total_value(self) -> float:
        positions_value = sum(p.market_value for p in self.positions.values())
        return self.cash + positions_value

    @property
    def total_pnl(self) -> float:
        return self.total_value - self.initial_capital

    @property
    def total_pnl_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return (self.total_pnl / self.initial_capital) * 100

    @property
    def cash_pct(self) -> float:
        if self.total_value == 0:
            return 0.0
        return (self.cash / self.total_value) * 100

    @property
    def day_pnl(self) -> float:
        return self.total_value - self.day_start_value

    async def initialize(self):
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.db_path)

        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS positions (
                ticker TEXT PRIMARY KEY,
                shares INTEGER,
                entry_price REAL,
                current_price REAL,
                stop_loss REAL,
                take_profit_targets TEXT,
                sector TEXT,
                opened_at TEXT,
                trailing_stop REAL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS portfolio_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                cash REAL,
                peak_value REAL,
                day_start_value REAL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT,
                action TEXT,
                shares INTEGER,
                price REAL,
                pnl REAL,
                timestamp TEXT
            )
        """)
        await self._db.commit()

        await self._load_state()

    async def _load_state(self):
        async with self._db.execute("SELECT cash, peak_value, day_start_value FROM portfolio_state WHERE id = 1") as cur:
            row = await cur.fetchone()
            if row:
                self.cash = row[0]
                self.peak_value = row[1]
                self.day_start_value = row[2]

        async with self._db.execute("SELECT * FROM positions") as cur:
            async for row in cur:
                targets = json.loads(row[5]) if row[5] else []
                self.positions[row[0]] = Position(
                    ticker=row[0],
                    shares=row[1],
                    entry_price=row[2],
                    current_price=row[3],
                    stop_loss=row[4],
                    take_profit_targets=targets,
                    sector=row[6],
                    opened_at=datetime.fromisoformat(row[7]),
                    trailing_stop=row[8],
                )

    async def _save_state(self):
        if not self._db:
            return
        await self._db.execute(
            "INSERT OR REPLACE INTO portfolio_state (id, cash, peak_value, day_start_value) VALUES (1, ?, ?, ?)",
            (self.cash, self.peak_value, self.day_start_value),
        )
        await self._db.commit()

    async def _save_position(self, position: Position):
        if not self._db:
            return
        await self._db.execute(
            "INSERT OR REPLACE INTO positions (ticker, shares, entry_price, current_price, stop_loss, take_profit_targets, sector, opened_at, trailing_stop) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                position.ticker, position.shares, position.entry_price,
                position.current_price, position.stop_loss,
                json.dumps(position.take_profit_targets), position.sector,
                position.opened_at.isoformat(), position.trailing_stop,
            ),
        )
        await self._db.commit()

    async def _remove_position_db(self, ticker: str):
        if not self._db:
            return
        await self._db.execute("DELETE FROM positions WHERE ticker = ?", (ticker,))
        await self._db.commit()

    def update_peak(self):
        if self.total_value > self.peak_value:
            self.peak_value = self.total_value

    def new_trading_day(self):
        self.day_start_value = self.total_value

    def add_position(self, position: Position):
        self.positions[position.ticker] = position
        self.cash -= position.cost_basis

    def close_position(self, ticker: str) -> float:
        position = self.positions.pop(ticker, None)
        if position is None:
            return 0.0
        self.cash += position.market_value
        self.update_peak()
        return position.unrealized_pnl

    async def add_position_async(self, position: Position):
        self.add_position(position)
        await self._save_position(position)
        await self._save_state()

    async def close_position_async(self, ticker: str) -> float:
        pnl = self.close_position(ticker)
        await self._remove_position_db(ticker)
        await self._save_state()
        if self._db:
            await self._db.execute(
                "INSERT INTO trade_history (ticker, action, shares, price, pnl, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (ticker, "SELL", 0, 0, pnl, datetime.now().isoformat()),
            )
            await self._db.commit()
        return pnl
