"""Order lifecycle management."""

import logging
from datetime import datetime

from src.execution.broker import Broker, Order, OrderSide, OrderType, OrderStatus
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.robinhood_broker import RobinhoodBroker
from src.decision.portfolio import Portfolio, Position

logger = logging.getLogger(__name__)


class OrderManager:
    def __init__(self, config: dict, portfolio: Portfolio):
        self.config = config
        self.portfolio = portfolio
        self.broker: Broker | None = None
        self.active_orders: dict[str, Order] = {}
        self._pending_stops: dict[str, dict] = {}

    async def connect(self):
        broker_name = self.config["trading"]["broker"]
        if broker_name == "alpaca":
            self.broker = AlpacaBroker(self.config)
        elif broker_name == "robinhood":
            self.broker = RobinhoodBroker(self.config)
        else:
            raise ValueError(f"Unknown broker: {broker_name}")
        await self.broker.connect()

        await self._sync_portfolio()

    async def _sync_portfolio(self):
        try:
            account = await self.broker.get_account()
            self.portfolio.cash = account.cash

            positions = await self.broker.get_positions()
            for p in positions:
                if p["ticker"] not in self.portfolio.positions:
                    self.portfolio.positions[p["ticker"]] = Position(
                        ticker=p["ticker"],
                        shares=p["shares"],
                        entry_price=p["entry_price"],
                        current_price=p["current_price"],
                        stop_loss=p["entry_price"] * 0.95,
                        take_profit_targets=[],
                        sector="",
                        opened_at=datetime.now(),
                    )
                else:
                    self.portfolio.positions[p["ticker"]].current_price = p["current_price"]

            logger.info("Portfolio synced — Cash: $%.2f, Positions: %d, Total: $%.2f",
                        self.portfolio.cash, len(self.portfolio.positions), self.portfolio.total_value)
        except Exception as e:
            logger.warning("Portfolio sync failed: %s — using local state", e)

    async def disconnect(self):
        if self.broker:
            await self.broker.disconnect()

    async def execute(self, signal) -> Order | None:
        if signal.signal.value in ("SELL", "STRONG SELL"):
            return await self._execute_sell(signal)
        return await self._execute_buy(signal)

    async def _execute_buy(self, signal) -> Order | None:
        order = Order(
            ticker=signal.ticker,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            quantity=signal.shares,
            limit_price=round(signal.entry_price, 2),
        )

        result = await self.broker.submit_order(order)
        self.active_orders[result.broker_order_id] = result

        if result.status == OrderStatus.FILLED:
            self.portfolio.add_position(Position(
                ticker=signal.ticker,
                shares=signal.shares,
                entry_price=result.filled_price or signal.entry_price,
                current_price=result.filled_price or signal.entry_price,
                stop_loss=signal.stop_loss,
                take_profit_targets=signal.take_profit_targets,
                sector="",
                opened_at=datetime.now(),
            ))

            # Only place stop loss after buy is confirmed filled
            if signal.stop_loss and signal.stop_loss > 0:
                stop_order = Order(
                    ticker=signal.ticker,
                    side=OrderSide.SELL,
                    order_type=OrderType.STOP,
                    quantity=signal.shares,
                    stop_price=round(signal.stop_loss, 2),
                )
                stop_result = await self.broker.submit_order(stop_order)
                self.active_orders[stop_result.broker_order_id] = stop_result
        else:
            # Buy not yet filled — store stop loss info for later
            self._pending_stops[signal.ticker] = {
                "shares": signal.shares,
                "stop_price": round(signal.stop_loss, 2),
            }

        return result

    async def _execute_sell(self, signal) -> Order | None:
        position = self.portfolio.positions.get(signal.ticker)
        if not position:
            logger.warning("No position to sell for %s", signal.ticker)
            return None

        order = Order(
            ticker=signal.ticker,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            quantity=position.shares,
        )

        result = await self.broker.submit_order(order)
        self.active_orders[result.broker_order_id] = result

        if result.status == OrderStatus.FILLED:
            self.portfolio.close_position(signal.ticker)

        return result

    async def cancel(self, broker_order_id: str) -> bool:
        success = await self.broker.cancel_order(broker_order_id)
        if success:
            self.active_orders.pop(broker_order_id, None)
        return success

    async def update_positions(self):
        if not self.broker:
            return
        try:
            positions = await self.broker.get_positions()
            for p in positions:
                ticker = p["ticker"]
                if ticker in self.portfolio.positions:
                    self.portfolio.positions[ticker].current_price = p["current_price"]
                elif ticker in self._pending_stops:
                    self.portfolio.add_position(Position(
                        ticker=ticker,
                        shares=p["shares"],
                        entry_price=p["entry_price"],
                        current_price=p["current_price"],
                        stop_loss=self._pending_stops[ticker]["stop_price"],
                        take_profit_targets=[],
                        sector="",
                        opened_at=datetime.now(),
                    ))
                    stop_info = self._pending_stops.pop(ticker)
                    stop_order = Order(
                        ticker=ticker,
                        side=OrderSide.SELL,
                        order_type=OrderType.STOP,
                        quantity=stop_info["shares"],
                        stop_price=stop_info["stop_price"],
                    )
                    stop_result = await self.broker.submit_order(stop_order)
                    self.active_orders[stop_result.broker_order_id] = stop_result
                    logger.info("Buy filled for %s — stop loss placed at $%.2f",
                                ticker, stop_info["stop_price"])
            self.portfolio.update_peak()
        except Exception as e:
            logger.warning("Position update failed: %s", e)
