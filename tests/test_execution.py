"""Tests for order execution."""

import pytest
from src.execution.broker import Order, OrderSide, OrderType, OrderStatus


class TestOrder:
    def test_order_defaults(self):
        order = Order(
            ticker="AAPL",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=10,
        )
        assert order.status == OrderStatus.PENDING
        assert order.filled_quantity == 0
        assert order.filled_price is None
