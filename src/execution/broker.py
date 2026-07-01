"""Broker abstraction layer — common interface for all brokers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"
    TRAILING_STOP = "trailing_stop"


class OrderStatus(Enum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIAL = "partial"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass
class Order:
    ticker: str
    side: OrderSide
    order_type: OrderType
    quantity: float = 0           # shares (int for whole, float for fractional)
    notional_value: float | None = None  # dollar amount — used instead of qty for fractional buys
    limit_price: float | None = None
    stop_price: float | None = None
    trail_pct: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    filled_price: float | None = None
    filled_quantity: float = 0
    broker_order_id: str = ""
    submitted_at: datetime | None = None
    filled_at: datetime | None = None


@dataclass
class AccountInfo:
    cash: float
    portfolio_value: float
    buying_power: float
    equity: float
    last_equity: float = 0.0  # equity at previous day's close — used for daily P/L
    day_trade_count: int = 0
    pattern_day_trader: bool = False


class Broker(ABC):
    @abstractmethod
    async def connect(self):
        pass

    @abstractmethod
    async def disconnect(self):
        pass

    @abstractmethod
    async def get_account(self) -> AccountInfo:
        pass

    @abstractmethod
    async def submit_order(self, order: Order) -> Order:
        pass

    @abstractmethod
    async def cancel_order(self, broker_order_id: str) -> bool:
        pass

    @abstractmethod
    async def get_order_status(self, broker_order_id: str) -> Order:
        pass

    @abstractmethod
    async def get_positions(self) -> list[dict]:
        pass

    @abstractmethod
    async def get_quote(self, ticker: str) -> float:
        pass
