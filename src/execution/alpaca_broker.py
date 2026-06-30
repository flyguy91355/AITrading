"""Alpaca broker implementation for paper and live trading via alpaca-trade-api SDK."""

import asyncio
import logging
import os
from datetime import datetime

import alpaca_trade_api as tradeapi

from src.execution.broker import Broker, Order, OrderSide, OrderType, OrderStatus, AccountInfo

logger = logging.getLogger(__name__)

ALPACA_STATUS_MAP = {
    "new": OrderStatus.SUBMITTED,
    "accepted": OrderStatus.SUBMITTED,
    "partially_filled": OrderStatus.PARTIAL,
    "filled": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "cancelled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
    "pending_new": OrderStatus.PENDING,
    "pending_cancel": OrderStatus.SUBMITTED,
    "pending_replace": OrderStatus.SUBMITTED,
}


class AlpacaBroker(Broker):
    def __init__(self, config: dict):
        self.config = config
        self.paper = config["trading"]["paper_trading"]
        self.api: tradeapi.REST | None = None

    async def connect(self):
        api_key = os.getenv("ALPACA_API_KEY", "")
        secret_key = os.getenv("ALPACA_SECRET_KEY", "")
        base_url = os.getenv("ALPACA_BASE_URL", "")

        if not api_key or not secret_key:
            raise RuntimeError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set in credentials.env")

        if not base_url:
            base_url = "https://paper-api.alpaca.markets" if self.paper else "https://api.alpaca.markets"

        self.api = tradeapi.REST(api_key, secret_key, base_url, api_version="v2")

        account = await asyncio.to_thread(self.api.get_account)
        mode = "PAPER" if self.paper else "LIVE"
        logger.info("Connected to Alpaca (%s) — Account: %s, Equity: $%s",
                     mode, account.account_number, account.equity)

    async def disconnect(self):
        self.api = None
        logger.info("Disconnected from Alpaca")

    async def get_account(self) -> AccountInfo:
        account = await asyncio.to_thread(self.api.get_account)
        return AccountInfo(
            cash=float(account.cash),
            portfolio_value=float(account.portfolio_value),
            buying_power=float(account.buying_power),
            equity=float(account.equity),
            day_trade_count=int(account.daytrade_count),
            pattern_day_trader=account.pattern_day_trader,
        )

    async def submit_order(self, order: Order) -> Order:
        side = "buy" if order.side == OrderSide.BUY else "sell"

        # Use notional (dollar amount) for fractional market buys; qty for everything else
        if order.notional_value and order.side == OrderSide.BUY and order.order_type == OrderType.MARKET:
            kwargs = {
                "symbol": order.ticker,
                "notional": str(round(order.notional_value, 2)),
                "side": side,
                "type": "market",
                "time_in_force": "day",
            }
        else:
            kwargs = {
                "symbol": order.ticker,
                "qty": str(round(order.quantity, 9)).rstrip("0").rstrip(".") if order.quantity % 1 else str(int(order.quantity)),
                "side": side,
            }

        if order.order_type == OrderType.MARKET and not order.notional_value:
            kwargs["type"] = "market"
            kwargs["time_in_force"] = "day"

        elif order.order_type == OrderType.LIMIT:
            kwargs["type"] = "limit"
            kwargs["time_in_force"] = "gtc"
            kwargs["limit_price"] = str(round(order.limit_price, 2))

        elif order.order_type == OrderType.STOP:
            kwargs["type"] = "stop"
            kwargs["time_in_force"] = "gtc"
            kwargs["stop_price"] = str(round(order.stop_price, 2))

        elif order.order_type == OrderType.STOP_LIMIT:
            kwargs["type"] = "stop_limit"
            kwargs["time_in_force"] = "gtc"
            kwargs["stop_price"] = str(round(order.stop_price, 2))
            kwargs["limit_price"] = str(round(order.limit_price, 2))

        elif order.order_type == OrderType.TRAILING_STOP:
            kwargs["type"] = "trailing_stop"
            kwargs["time_in_force"] = "gtc"
            kwargs["trail_percent"] = str(order.trail_pct)

        else:
            raise ValueError(f"Unsupported order type: {order.order_type}")

        result = await asyncio.to_thread(lambda: self.api.submit_order(**kwargs))

        order.broker_order_id = result.id
        order.status = ALPACA_STATUS_MAP.get(result.status, OrderStatus.PENDING)
        order.submitted_at = datetime.now()

        if result.filled_avg_price:
            order.filled_price = float(result.filled_avg_price)
        if result.filled_qty:
            order.filled_quantity = float(result.filled_qty)
        if hasattr(result, "filled_at") and result.filled_at:
            try:
                order.filled_at = datetime.fromisoformat(str(result.filled_at).replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError):
                pass

        if order.notional_value:
            logger.info("Alpaca order submitted: %s %s $%.2f notional — ID: %s, Status: %s",
                        order.side.value, order.ticker, order.notional_value,
                        order.broker_order_id, order.status.value)
        else:
            logger.info("Alpaca order submitted: %s %s %.4g shares %s — ID: %s, Status: %s",
                        order.side.value, order.ticker, order.quantity, order.order_type.value,
                        order.broker_order_id, order.status.value)
        return order

    async def cancel_order(self, broker_order_id: str) -> bool:
        try:
            await asyncio.to_thread(self.api.cancel_order, broker_order_id)
            logger.info("Alpaca order cancelled: %s", broker_order_id)
            return True
        except Exception as e:
            logger.error("Failed to cancel Alpaca order %s: %s", broker_order_id, e)
            return False

    async def get_order_status(self, broker_order_id: str) -> Order:
        result = await asyncio.to_thread(self.api.get_order, broker_order_id)

        side = OrderSide.BUY if result.side == "buy" else OrderSide.SELL

        return Order(
            ticker=result.symbol,
            side=side,
            order_type=OrderType.MARKET,
            quantity=float(result.qty) if result.qty else 0.0,
            status=ALPACA_STATUS_MAP.get(result.status, OrderStatus.PENDING),
            filled_price=float(result.filled_avg_price) if result.filled_avg_price else None,
            filled_quantity=float(result.filled_qty) if result.filled_qty else 0.0,
            broker_order_id=result.id,
        )

    async def get_positions(self) -> list[dict]:
        positions = await asyncio.to_thread(self.api.list_positions)
        return [
            {
                "ticker": p.symbol,
                "shares": float(p.qty),
                "entry_price": float(p.avg_entry_price),
                "current_price": float(p.current_price),
                "market_value": float(p.market_value),
                "unrealized_pnl": float(p.unrealized_pl),
                "unrealized_pnl_pct": float(p.unrealized_plpc) * 100,
            }
            for p in positions
        ]

    async def get_quote(self, ticker: str) -> float:
        quote = await asyncio.to_thread(self.api.get_latest_quote, ticker)
        return float(quote.ap) if quote.ap else float(quote.bp)
