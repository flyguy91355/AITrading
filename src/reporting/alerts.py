"""Notifications and alerts — console and optional file logging."""

import json
import logging
from datetime import datetime
from enum import Enum
from pathlib import Path

from rich.console import Console
from rich.panel import Panel

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


LEVEL_STYLES = {
    AlertLevel.INFO: "green",
    AlertLevel.WARNING: "yellow",
    AlertLevel.CRITICAL: "red bold",
}


class AlertManager:
    def __init__(self, config: dict):
        self.config = config
        self.console = Console(stderr=True)
        self.alert_log_dir = Path("data/alerts")
        self.alert_log_dir.mkdir(parents=True, exist_ok=True)

    def send_alert(self, level: AlertLevel, title: str, message: str):
        style = LEVEL_STYLES.get(level, "white")
        icon = {"info": "ℹ", "warning": "⚠", "critical": "🚨"}.get(level.value, "•")

        self.console.print(Panel(
            f"{icon} {message}",
            title=f"[{style}]{title}[/{style}]",
            border_style=style,
        ))

        self._log_alert(level, title, message)

    def _log_alert(self, level: AlertLevel, title: str, message: str):
        entry = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "title": title,
            "message": message,
        }
        log_file = self.alert_log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        try:
            with open(log_file, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.warning("Failed to write alert log: %s", e)

    def trade_executed(self, signal):
        self.send_alert(
            AlertLevel.INFO,
            f"Trade Executed: {signal.ticker}",
            f"{signal.signal.value} {signal.shares} shares @ ${signal.entry_price:.2f}",
        )

    def stop_loss_triggered(self, ticker: str, loss_amount: float):
        self.send_alert(
            AlertLevel.WARNING,
            f"Stop Loss: {ticker}",
            f"Position closed. Loss: ${loss_amount:.2f}",
        )

    def high_conviction_signal(self, signal):
        self.send_alert(
            AlertLevel.INFO,
            f"Signal: {signal.ticker} ({signal.conviction}/10)",
            f"{signal.signal.value} — {signal.reasoning[:200]}",
        )

    def risk_alert(self, message: str):
        self.send_alert(
            AlertLevel.CRITICAL,
            "Risk Management Alert",
            message,
        )

    def system_error(self, component: str, error: str):
        self.send_alert(
            AlertLevel.CRITICAL,
            f"System Error: {component}",
            error,
        )

    def daily_summary(self, portfolio):
        total_pnl = portfolio.total_pnl
        day_pnl = portfolio.day_pnl
        sign = "+" if total_pnl >= 0 else ""
        day_sign = "+" if day_pnl >= 0 else ""

        self.send_alert(
            AlertLevel.INFO,
            "Daily Portfolio Summary",
            (
                f"Total Value: ${portfolio.total_value:,.2f} | "
                f"Day P/L: {day_sign}${day_pnl:,.2f} | "
                f"Total P/L: {sign}${total_pnl:,.2f} ({sign}{portfolio.total_pnl_pct:.1f}%) | "
                f"Cash: ${portfolio.cash:,.2f} ({portfolio.cash_pct:.1f}%) | "
                f"Positions: {len(portfolio.positions)}"
            ),
        )
