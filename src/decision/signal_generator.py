"""Generates buy/sell/hold signals from research reports."""

import logging
from dataclasses import dataclass
from datetime import datetime

from src.research.engine import ResearchEngine, ResearchReport, Signal
from src.decision.risk_manager import RiskManager
from src.decision.portfolio import Portfolio

logger = logging.getLogger(__name__)


@dataclass
class TradeSignal:
    ticker: str
    signal: Signal
    conviction: int
    entry_price: float
    stop_loss: float
    take_profit_targets: list[float]
    position_size_pct: float
    position_size_dollars: float
    shares: int
    reasoning: str
    research_report: ResearchReport
    generated_at: datetime
    should_execute: bool = False


class SignalGenerator:
    def __init__(
        self,
        config: dict,
        research_engine: ResearchEngine,
        risk_manager: RiskManager,
        portfolio: Portfolio,
    ):
        self.config = config
        self.research_engine = research_engine
        self.risk_manager = risk_manager
        self.portfolio = portfolio
        self.min_conviction = config["research"]["min_conviction_score"]
        self.min_rr_ratio = config["research"]["min_risk_reward_ratio"]
        self.pending_signals: list[TradeSignal] = []

    async def check_signals(self) -> list[TradeSignal]:
        signals = []

        for ticker, report in self.research_engine.reports.items():
            if ticker in self.portfolio.positions and report.signal in (Signal.SELL, Signal.STRONG_SELL):
                signal = self._create_sell_signal(report)
                if signal:
                    signals.append(signal)
                continue

            if report.signal in (Signal.STRONG_BUY, Signal.BUY):
                if ticker in self.portfolio.positions:
                    continue
                signal = self._evaluate_report(report)
                if signal:
                    signals.append(signal)

        self.pending_signals = signals
        if signals:
            logger.info("Generated %d trade signal(s): %s",
                        len(signals), ", ".join(f"{s.ticker}({s.signal.value})" for s in signals))
        return signals

    def _evaluate_report(self, report: ResearchReport) -> TradeSignal | None:
        if report.conviction_score < self.min_conviction:
            return None

        risk = report.entry_price - report.stop_loss
        if risk <= 0:
            return None

        targets = report.take_profit_targets or []
        mid_target = targets[1] if len(targets) >= 2 else (targets[0] if targets else 0)
        reward = mid_target - report.entry_price
        if reward <= 0 or reward / risk < self.min_rr_ratio:
            return None

        position_size = self.risk_manager.calculate_position_size(
            report.entry_price, report.stop_loss, self.portfolio.total_value
        )

        if not self.risk_manager.check_all_rules(report, self.portfolio):
            return None

        shares = int(position_size / report.entry_price)
        if shares == 0:
            return None

        return TradeSignal(
            ticker=report.ticker,
            signal=report.signal,
            conviction=report.conviction_score,
            entry_price=report.entry_price,
            stop_loss=report.stop_loss,
            take_profit_targets=report.take_profit_targets,
            position_size_pct=report.position_size_pct,
            position_size_dollars=position_size,
            shares=shares,
            reasoning=report.reasoning,
            research_report=report,
            generated_at=datetime.now(),
            should_execute=report.signal in (Signal.STRONG_BUY, Signal.BUY),
        )

    def _create_sell_signal(self, report: ResearchReport) -> TradeSignal | None:
        position = self.portfolio.positions.get(report.ticker)
        if not position:
            return None

        return TradeSignal(
            ticker=report.ticker,
            signal=report.signal,
            conviction=report.conviction_score,
            entry_price=position.current_price,
            stop_loss=0,
            take_profit_targets=[],
            position_size_pct=0,
            position_size_dollars=position.market_value,
            shares=position.shares,
            reasoning=report.reasoning,
            research_report=report,
            generated_at=datetime.now(),
            should_execute=True,
        )
