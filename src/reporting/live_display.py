"""Real-time terminal dashboard using Rich."""

import logging
from datetime import datetime

from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.live import Live

from src.decision.portfolio import Portfolio

logger = logging.getLogger(__name__)


class LiveDisplay:
    def __init__(self, config: dict, portfolio: Portfolio):
        self.config = config
        self.portfolio = portfolio
        self.console = Console()
        self.signals: list[dict] = []
        self.recent_trades: list[dict] = []
        self.last_scan_time: str = ""
        self.next_scan_time: str = ""
        self.stocks_analyzed: int = 0
        self._live: Live | None = None

    def start_live(self):
        self._live = Live(self._build_display(), console=self.console, refresh_per_second=1)
        self._live.start()

    def stop_live(self):
        if self._live:
            self._live.stop()

    def refresh(self):
        if self._live:
            self._live.update(self._build_display())
        else:
            self.console.clear()
            self.console.print(self._build_display())

    def _build_display(self) -> Panel:
        mode = "PAPER" if self.config["trading"]["paper_trading"] else "LIVE"
        broker = self.config["trading"]["broker"].upper()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=4),
        )
        layout["body"].split_column(
            Layout(name="portfolio", size=3),
            Layout(name="positions"),
            Layout(name="signals_trades"),
        )
        layout["signals_trades"].split_row(
            Layout(name="signals"),
            Layout(name="trades"),
        )

        header = Text(justify="center")
        header.append("AITrading Live Dashboard\n", style="bold white")
        header.append(f"Mode: {mode} ({broker}) | {now}", style="dim")
        layout["header"].update(Panel(header, style="bold blue"))

        portfolio_text = self._build_portfolio_summary()
        layout["portfolio"].update(Panel(portfolio_text, title="Portfolio", border_style="green"))

        positions_table = self._build_positions_table()
        layout["positions"].update(Panel(positions_table, title="Positions", border_style="cyan"))

        signals_text = self._build_signals()
        layout["signals"].update(Panel(signals_text, title="Active Signals", border_style="yellow"))

        trades_text = self._build_recent_trades()
        layout["trades"].update(Panel(trades_text, title="Recent Trades", border_style="magenta"))

        scan_info = Text()
        scan_info.append(f"Last scan: {self.last_scan_time or 'N/A'}", style="dim")
        scan_info.append(f" | Next scan: {self.next_scan_time or 'N/A'}", style="dim")
        scan_info.append(f" | Stocks analyzed: {self.stocks_analyzed}", style="dim")
        layout["footer"].update(Panel(scan_info, title="Research Cycle", border_style="dim"))

        return Panel(layout, border_style="bold blue")

    def _build_portfolio_summary(self) -> Text:
        p = self.portfolio
        text = Text()

        text.append(f"Total Value: ${p.total_value:,.2f}    ", style="bold")

        day_style = "green" if p.day_pnl >= 0 else "red"
        day_sign = "+" if p.day_pnl >= 0 else ""
        day_pct = (p.day_pnl / p.day_start_value * 100) if p.day_start_value else 0
        text.append(f"Day P/L: {day_sign}${p.day_pnl:,.2f} ({day_sign}{day_pct:.2f}%)    ", style=day_style)

        text.append(f"Cash: ${p.cash:,.2f} ({p.cash_pct:.1f}%)", style="dim")

        return text

    def _build_positions_table(self) -> Table:
        table = Table(show_header=True, header_style="bold", expand=True, show_lines=False)
        table.add_column("Ticker", style="bold", width=8)
        table.add_column("Shares", justify="right", width=8)
        table.add_column("Entry", justify="right", width=10)
        table.add_column("Current", justify="right", width=10)
        table.add_column("P/L", justify="right", width=12)
        table.add_column("P/L %", justify="right", width=8)
        table.add_column("Stop Loss", justify="right", width=10)

        if not self.portfolio.positions:
            table.add_row("—", "—", "—", "—", "—", "—", "—")
            return table

        for pos in self.portfolio.positions.values():
            pnl_style = "green" if pos.unrealized_pnl >= 0 else "red"
            pnl_sign = "+" if pos.unrealized_pnl >= 0 else ""

            table.add_row(
                pos.ticker,
                str(pos.shares),
                f"${pos.entry_price:.2f}",
                f"${pos.current_price:.2f}",
                Text(f"{pnl_sign}${pos.unrealized_pnl:,.2f}", style=pnl_style),
                Text(f"{pnl_sign}{pos.unrealized_pnl_pct:.1f}%", style=pnl_style),
                f"${pos.stop_loss:.2f}",
            )

        return table

    def _build_signals(self) -> Text:
        text = Text()
        if not self.signals:
            text.append("No active signals", style="dim")
            return text

        for sig in self.signals[-5:]:
            style = "green bold" if "BUY" in sig.get("signal", "") else "red bold" if "SELL" in sig.get("signal", "") else "yellow"
            text.append(f"● {sig.get('time', '')} — {sig.get('signal', '')} {sig.get('ticker', '')} ", style=style)
            text.append(f"(Conviction: {sig.get('conviction', '?')}/10)\n")
            if sig.get("reason"):
                text.append(f"  {sig['reason'][:80]}\n", style="dim")

        return text

    def _build_recent_trades(self) -> Text:
        text = Text()
        if not self.recent_trades:
            text.append("No recent trades", style="dim")
            return text

        for trade in self.recent_trades[-5:]:
            icon = "✓" if trade.get("status") == "FILLED" else "○"
            style = "green" if trade.get("side") == "BUY" else "red"
            text.append(f"{icon} {trade.get('time', '')} — ", style="dim")
            text.append(f"{trade.get('side', '')} {trade.get('shares', '')} {trade.get('ticker', '')} ", style=style)
            text.append(f"@ ${trade.get('price', 0):.2f}\n")
            if trade.get("reason"):
                text.append(f"  {trade['reason'][:80]}\n", style="dim")

        return text

    def show_signal(self, signal):
        self.signals.append({
            "time": datetime.now().strftime("%H:%M"),
            "ticker": signal.ticker,
            "signal": signal.signal.value,
            "conviction": signal.conviction,
            "reason": signal.reasoning[:100] if signal.reasoning else "",
        })
        if len(self.signals) > 20:
            self.signals = self.signals[-20:]

    def show_trade(self, trade):
        self.recent_trades.append({
            "time": datetime.now().strftime("%H:%M"),
            "ticker": trade.ticker,
            "side": trade.side.value.upper(),
            "shares": trade.quantity,
            "price": trade.filled_price or trade.limit_price or 0,
            "status": trade.status.value.upper(),
            "reason": "",
        })
        if len(self.recent_trades) > 20:
            self.recent_trades = self.recent_trades[-20:]

    def update_scan_info(self, last_scan: str, next_scan: str, count: int):
        self.last_scan_time = last_scan
        self.next_scan_time = next_scan
        self.stocks_analyzed = count
