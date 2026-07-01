"""Order lifecycle management."""

import logging
from datetime import datetime

from src.execution.broker import Broker, Order, OrderSide, OrderType, OrderStatus
from src.execution.alpaca_broker import AlpacaBroker
from src.execution.robinhood_broker import RobinhoodBroker
from src.decision.portfolio import Portfolio, Position

logger = logging.getLogger(__name__)


def _split_thirds(shares: float) -> tuple[float, float, float]:
    """Split shares into three tranches that sum exactly to shares."""
    t1 = round(shares / 3, 9)
    t2 = round(shares / 3, 9)
    t3 = round(shares - t1 - t2, 9)
    return t1, t2, t3


class OrderManager:
    def __init__(self, config: dict, portfolio: Portfolio):
        self.config = config
        self.portfolio = portfolio
        self.broker: Broker | None = None
        self.active_orders: dict[str, Order] = {}

        # ticker → list of {order_id, shares, target, tranche}
        self._tp_orders: dict[str, list[dict]] = {}
        # ticker → current stop-loss order ID
        self._stop_order_ids: dict[str, str] = {}
        # pending info for orders not yet filled (after-hours market orders)
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
            if account.last_equity > 0:
                self.portfolio.day_start_value = account.last_equity

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
            order_type=OrderType.MARKET,
            notional_value=round(signal.position_size_dollars, 2),
        )

        result = await self.broker.submit_order(order)
        self.active_orders[result.broker_order_id] = result

        actual_shares = result.filled_quantity or signal.shares

        if result.status == OrderStatus.FILLED:
            filled_price = result.filled_price or signal.entry_price
            self.portfolio.add_position(Position(
                ticker=signal.ticker,
                shares=actual_shares,
                entry_price=filled_price,
                current_price=filled_price,
                stop_loss=signal.stop_loss,
                take_profit_targets=signal.take_profit_targets,
                sector="",
                opened_at=datetime.now(),
            ))
            await self._place_exit_orders(
                signal.ticker, actual_shares,
                signal.stop_loss, signal.take_profit_targets,
            )
        else:
            # Market order submitted but not yet filled (after hours) — store for later
            self._pending_stops[signal.ticker] = {
                "shares": actual_shares,
                "stop_price": round(signal.stop_loss, 2),
                "take_profit_targets": signal.take_profit_targets,
            }

        return result

    async def _place_exit_orders(
        self, ticker: str, shares: float,
        stop_price: float, targets: list[float],
    ):
        """Place 3 take-profit limit orders. Stop loss is enforced in software by
        the position monitor loop — placing a broker stop order alongside 3 TP orders
        would exceed the position size and get rejected by Alpaca."""
        # Stop price is stored on the Position object; position_monitor_loop handles it
        logger.info("Stop loss tracked in software for %s @ $%.2f", ticker, stop_price)

        # ── Take-profit limit orders (sell ⅓ at each target) ──
        if targets:
            t1, t2, t3 = _split_thirds(shares)
            tranches = [(t1, targets[0]), (t2, targets[1]), (t3, targets[2])] if len(targets) >= 3 \
                else [(shares, targets[0])]

            self._tp_orders[ticker] = []
            for i, (tranche_shares, target_price) in enumerate(tranches, 1):
                if tranche_shares <= 0:
                    continue
                tp_order = Order(
                    ticker=ticker, side=OrderSide.SELL,
                    order_type=OrderType.LIMIT,
                    quantity=round(tranche_shares, 9),
                    limit_price=round(target_price, 2),
                )
                try:
                    tp_result = await self.broker.submit_order(tp_order)
                    self.active_orders[tp_result.broker_order_id] = tp_result
                    self._tp_orders[ticker].append({
                        "order_id": tp_result.broker_order_id,
                        "shares": tranche_shares,
                        "target": target_price,
                        "tranche": i,
                    })
                    logger.info("Take-profit %d placed for %s: %.4g shares @ $%.2f",
                                i, ticker, tranche_shares, target_price)
                except Exception as e:
                    logger.warning("Take-profit %d order failed for %s: %s", i, ticker, e)

    async def _execute_sell(self, signal) -> Order | None:
        position = self.portfolio.positions.get(signal.ticker)
        if not position:
            logger.warning("No position to sell for %s", signal.ticker)
            return None

        # Cancel any open TP and stop orders for this position
        await self._cancel_exit_orders(signal.ticker)

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

    async def _cancel_exit_orders(self, ticker: str):
        """Cancel all open take-profit orders for a ticker."""
        for tp in self._tp_orders.pop(ticker, []):
            await self.cancel(tp["order_id"])

    async def cancel(self, broker_order_id: str) -> bool:
        success = await self.broker.cancel_order(broker_order_id)
        if success:
            self.active_orders.pop(broker_order_id, None)
        return success

    async def check_take_profits(self):
        """Check if any take-profit orders filled; adjust stop loss for remaining shares."""
        if not self.broker:
            return

        for ticker in list(self._tp_orders.keys()):
            remaining_tp = []
            shares_sold = 0.0

            for tp in self._tp_orders[ticker]:
                try:
                    status_order = await self.broker.get_order_status(tp["order_id"])
                except Exception:
                    remaining_tp.append(tp)
                    continue

                if status_order.status == OrderStatus.FILLED:
                    shares_sold += tp["shares"]
                    logger.info("Take-profit %d filled for %s: %.4g shares @ $%.2f",
                                tp["tranche"], ticker, tp["shares"], tp["target"])
                    # Update local portfolio position
                    pos = self.portfolio.positions.get(ticker)
                    if pos:
                        pos.shares = round(pos.shares - tp["shares"], 9)
                        if pos.take_profit_targets:
                            pos.take_profit_targets = pos.take_profit_targets[1:]
                else:
                    remaining_tp.append(tp)

            self._tp_orders[ticker] = remaining_tp

            if shares_sold > 0:
                pos = self.portfolio.positions.get(ticker)
                if pos and pos.shares <= 0.001:
                    # All shares sold via take-profits — position fully closed
                    self.portfolio.close_position(ticker)
                    logger.info("Position %s fully closed via take-profit orders", ticker)
                elif pos:
                    logger.info("TP filled for %s — %.4g shares remaining, stop still active at $%.2f",
                                ticker, pos.shares, pos.stop_loss)

    async def update_positions(self):
        if not self.broker:
            return
        try:
            positions = await self.broker.get_positions()
            alpaca_tickers = {p["ticker"] for p in positions}

            for p in positions:
                ticker = p["ticker"]
                if ticker in self.portfolio.positions:
                    self.portfolio.positions[ticker].current_price = p["current_price"]
                elif ticker in self._pending_stops:
                    # After-hours buy just filled — place exit orders now
                    pending = self._pending_stops.pop(ticker)
                    self.portfolio.add_position(Position(
                        ticker=ticker,
                        shares=p["shares"],
                        entry_price=p["entry_price"],
                        current_price=p["current_price"],
                        stop_loss=pending["stop_price"],
                        take_profit_targets=pending.get("take_profit_targets", []),
                        sector="",
                        opened_at=datetime.now(),
                    ))
                    await self._place_exit_orders(
                        ticker, p["shares"],
                        pending["stop_price"],
                        pending.get("take_profit_targets", []),
                    )

            # Detect positions closed by Alpaca (stop loss hit, etc.)
            for ticker in list(self.portfolio.positions.keys()):
                if ticker not in alpaca_tickers:
                    logger.info("%s position closed in Alpaca (stop/TP filled) — syncing local state", ticker)
                    # Cancel any still-open TP limit orders so they don't become orphan orders
                    for tp in self._tp_orders.pop(ticker, []):
                        await self.cancel(tp["order_id"])
                    self._stop_order_ids.pop(ticker, None)
                    self.portfolio.close_position(ticker)

            await self.check_take_profits()
            self.portfolio.update_peak()
        except Exception as e:
            logger.warning("Position update failed: %s", e)
