"""Risk management and position sizing."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.research.engine import ResearchReport
    from src.decision.portfolio import Portfolio


class RiskManager:
    def __init__(self, config: dict):
        rm = config["risk_management"]
        self.max_position_pct = rm["max_position_pct"] / 100
        self.max_loss_per_trade_pct = rm["max_loss_per_trade_pct"] / 100
        self.min_cash_reserve_pct = rm["min_cash_reserve_pct"] / 100
        self.max_sector_positions = rm["max_sector_positions"]
        self.daily_loss_limit_pct = rm["daily_loss_limit_pct"] / 100
        self.drawdown_halt_pct = rm["drawdown_halt_pct"] / 100
        self.drawdown_defensive_pct = rm["drawdown_defensive_pct"] / 100
        self.drawdown_exit_review_pct = rm["drawdown_exit_review_pct"] / 100

    def calculate_position_size(self, entry_price: float, stop_loss: float, portfolio_value: float) -> float:
        risk_per_share = entry_price - stop_loss
        if risk_per_share <= 0:
            return 0.0

        max_risk_dollars = portfolio_value * self.max_loss_per_trade_pct
        shares_by_risk = max_risk_dollars / risk_per_share
        size_by_risk = shares_by_risk * entry_price

        max_position = portfolio_value * self.max_position_pct
        return min(size_by_risk, max_position)

    def check_cash_reserve(self, portfolio: Portfolio, order_cost: float) -> bool:
        remaining_cash = portfolio.cash - order_cost
        return remaining_cash >= portfolio.total_value * self.min_cash_reserve_pct

    def check_sector_concentration(self, portfolio: Portfolio, sector: str) -> bool:
        sector_count = sum(1 for p in portfolio.positions.values() if p.sector == sector)
        return sector_count < self.max_sector_positions

    def check_drawdown(self, portfolio: Portfolio) -> str:
        if portfolio.peak_value == 0:
            return "normal"
        drawdown = (portfolio.peak_value - portfolio.total_value) / portfolio.peak_value
        if drawdown >= self.drawdown_exit_review_pct:
            return "exit_review"
        if drawdown >= self.drawdown_defensive_pct:
            return "defensive"
        if drawdown >= self.drawdown_halt_pct:
            return "halt"
        return "normal"

    def check_daily_loss(self, portfolio: Portfolio) -> bool:
        if portfolio.total_value == 0:
            return False
        daily_loss = (portfolio.day_start_value - portfolio.total_value) / portfolio.day_start_value
        return daily_loss < self.daily_loss_limit_pct

    def check_all_rules(self, report: ResearchReport, portfolio: Portfolio) -> bool:
        order_cost = report.entry_price * (report.position_size_pct / 100 * portfolio.total_value / report.entry_price)

        if not self.check_cash_reserve(portfolio, order_cost):
            return False
        if not self.check_daily_loss(portfolio):
            return False
        if self.check_drawdown(portfolio) != "normal":
            return False
        return True
