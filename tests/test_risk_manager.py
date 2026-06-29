"""Tests for risk management."""

import pytest
from src.decision.risk_manager import RiskManager


def make_config():
    return {
        "risk_management": {
            "max_position_pct": 10.0,
            "starting_position_pct": 3.0,
            "max_loss_per_trade_pct": 2.0,
            "min_cash_reserve_pct": 30.0,
            "max_sector_positions": 3,
            "daily_loss_limit_pct": 2.0,
            "drawdown_halt_pct": 5.0,
            "drawdown_defensive_pct": 10.0,
            "drawdown_exit_review_pct": 15.0,
        }
    }


class TestRiskManager:
    def test_position_size_respects_max(self):
        rm = RiskManager(make_config())
        size = rm.calculate_position_size(
            entry_price=100.0, stop_loss=95.0, portfolio_value=100_000.0
        )
        assert size <= 100_000.0 * 0.10

    def test_position_size_respects_risk_limit(self):
        rm = RiskManager(make_config())
        size = rm.calculate_position_size(
            entry_price=100.0, stop_loss=75.0, portfolio_value=100_000.0
        )
        max_risk = 100_000.0 * 0.02
        shares = max_risk / 25.0
        expected = shares * 100.0
        assert size == pytest.approx(expected)

    def test_zero_risk_returns_zero(self):
        rm = RiskManager(make_config())
        size = rm.calculate_position_size(
            entry_price=100.0, stop_loss=100.0, portfolio_value=100_000.0
        )
        assert size == 0.0
