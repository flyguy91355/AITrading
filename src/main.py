"""System entry point and orchestrator for AITrading."""

import asyncio
import logging
import signal
import sys
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path

from src.utils.config import load_config
from src.research.engine import ResearchEngine
from src.decision.signal_generator import SignalGenerator
from src.decision.risk_manager import RiskManager
from src.decision.portfolio import Portfolio
from src.execution.order_manager import OrderManager
from src.reporting.live_display import LiveDisplay
from src.reporting.trade_logger import TradeLogger
from src.reporting.alerts import AlertManager
from src.data.market_data import MarketDataFetcher
from src.data.insider_tracker import InsiderTracker
from src.data.news_feed import NewsFeed

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("data/aitrading.log", mode="a"),
    ],
)
logger = logging.getLogger(__name__)


class AITradingSystem:
    def __init__(self, config_path: str = "config/settings.yaml"):
        Path("data").mkdir(exist_ok=True)

        self.config = load_config(config_path)
        self.running = False

        self.market_data = MarketDataFetcher(self.config)
        self.insider_tracker = InsiderTracker(self.config)
        self.news_feed = NewsFeed(self.config)

        self.research_engine = ResearchEngine(
            self.config, self.market_data, self.insider_tracker, self.news_feed
        )
        self.risk_manager = RiskManager(self.config)
        self.portfolio = Portfolio(self.config)
        self.signal_generator = SignalGenerator(
            self.config, self.research_engine, self.risk_manager, self.portfolio
        )
        self.order_manager = OrderManager(self.config, self.portfolio)
        self.trade_logger = TradeLogger(self.config)
        self.display = LiveDisplay(self.config, self.portfolio)
        self.alerts = AlertManager(self.config)

    async def start(self):
        self.running = True
        mode = "PAPER" if self.config["trading"]["paper_trading"] else "LIVE"
        broker = self.config["trading"]["broker"].upper()

        print(f"\n{'='*60}")
        print(f"  AITrading System Starting — {mode} MODE ({broker})")
        print(f"{'='*60}\n")

        if not self.config["trading"]["paper_trading"]:
            confirm = input("LIVE TRADING ENABLED — real money at risk. Type CONFIRM to proceed: ")
            if confirm != "CONFIRM":
                print("Live trading not confirmed. Exiting.")
                return

        await self.portfolio.initialize()

        try:
            await self.order_manager.connect()
        except Exception as e:
            logger.warning("Broker connection failed: %s — running in research-only mode", e)
            self.alerts.system_error("Broker", str(e))

        try:
            await asyncio.gather(
                self._research_loop(),
                self._signal_loop(),
                self._display_loop(),
                self._position_update_loop(),
                self._position_monitor_loop(),
            )
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    def _get_market_tz(self):
        return ZoneInfo(self.config["research"].get("market_timezone", "America/New_York"))

    def _now_et(self):
        return datetime.now(self._get_market_tz())

    def _is_market_open(self) -> bool:
        now = self._now_et()
        if now.weekday() >= 5:
            return False
        research = self.config["research"]
        h, m = research.get("market_open", "09:30").split(":")
        market_open = dtime(int(h), int(m))
        h, m = research.get("market_close", "16:00").split(":")
        market_close = dtime(int(h), int(m))
        return market_open <= now.time() <= market_close

    def _scan_times(self) -> list[dtime]:
        explicit = self.config["research"].get("scan_times", [])
        if explicit:
            times = []
            for t_str in explicit:
                sh, sm = t_str.split(":")
                times.append(dtime(int(sh), int(sm)))
            return sorted(times)
        scans_per_day = self.config["research"].get("scans_per_day", 3)
        count = max(scans_per_day, 2)
        open_mins = 9 * 60 + 30
        close_mins = 16 * 60
        total = close_mins - open_mins
        times = []
        for i in range(count):
            offset = open_mins + (total * i) // (count - 1)
            times.append(dtime(offset // 60, offset % 60))
        return times

    def _seconds_until_next_scan(self) -> tuple[float, str]:
        now = self._now_et()
        scan_times = self._scan_times()
        if now.weekday() < 5:
            for t in scan_times:
                scan_dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                if scan_dt > now:
                    return (scan_dt - now).total_seconds(), scan_dt.strftime("%H:%M ET")
        days_ahead = 1
        while True:
            next_day = now + timedelta(days=days_ahead)
            if next_day.weekday() < 5:
                break
            days_ahead += 1
        research = self.config["research"]
        h, m = research.get("market_open", "09:30").split(":")
        first_scan = scan_times[0] if scan_times else dtime(int(h), int(m))
        next_open = now.replace(
            hour=first_scan.hour, minute=first_scan.minute, second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        return (next_open - now).total_seconds(), next_open.strftime("%a %H:%M ET")

    async def _research_loop(self):
        scan_labels = [t.strftime("%H:%M") for t in self._scan_times()]
        logger.info("Research loop started — scan times: %s ET", ", ".join(scan_labels))

        while self.running:
            if not self._is_market_open():
                wait_secs, next_label = self._seconds_until_next_scan()
                self.display.next_scan_time = next_label
                logger.info("Market closed — next scan at %s", next_label)
                await asyncio.sleep(min(wait_secs, 60))
                continue

            wait_secs, next_label = self._seconds_until_next_scan()
            if wait_secs > 30:
                self.display.next_scan_time = next_label
                await asyncio.sleep(min(wait_secs, 30))
                continue

            try:
                scan_start = datetime.now()
                self.display.last_scan_time = scan_start.strftime("%H:%M")

                logger.info("Starting watchlist research scan...")
                reports = await self.research_engine.run_watchlist_scan()
                self.display.stocks_analyzed = len(reports)

                _, next_label = self._seconds_until_next_scan()
                self.display.next_scan_time = next_label

                for report in reports:
                    logger.info("  %s: %s (Conviction: %d/10)",
                                report.ticker, report.signal.value, report.conviction_score)

            except Exception as e:
                logger.error("Research scan failed: %s", e)
                self.alerts.system_error("Research", str(e))

            wait_secs, _ = self._seconds_until_next_scan()
            await asyncio.sleep(min(wait_secs, 60))

    async def _signal_loop(self):
        while self.running:
            try:
                signals = await self.signal_generator.check_signals()

                for sig in signals:
                    self.display.show_signal(sig)
                    self.alerts.high_conviction_signal(sig)

                    if sig.should_execute and self.order_manager.broker:
                        result = await self.order_manager.execute(sig)
                        if result:
                            self.trade_logger.log_trade(sig)
                            self.display.show_trade(result)
                            self.alerts.trade_executed(sig)

            except Exception as e:
                logger.error("Signal loop error: %s", e)

            await asyncio.sleep(10)

    async def _display_loop(self):
        while self.running:
            try:
                self.display.refresh()
            except Exception as e:
                logger.debug("Display refresh error: %s", e)
            await asyncio.sleep(2)

    async def _position_update_loop(self):
        while self.running:
            try:
                await self.order_manager.update_positions()

                for ticker, pos in list(self.portfolio.positions.items()):
                    if pos.current_price <= pos.stop_loss:
                        logger.warning("Stop loss triggered for %s at $%.2f", ticker, pos.current_price)
                        pnl = self.portfolio.close_position(ticker)
                        self.alerts.stop_loss_triggered(ticker, abs(pnl))

                    if pos.trailing_stop and pos.current_price <= pos.trailing_stop:
                        logger.info("Trailing stop triggered for %s at $%.2f", ticker, pos.current_price)
                        pnl = self.portfolio.close_position(ticker)
                        if pnl < 0:
                            self.alerts.stop_loss_triggered(ticker, abs(pnl))

                    if self.config["risk_management"].get("trailing_stop_enabled", True):
                        if pos.unrealized_pnl_pct > 5:
                            new_trailing = pos.current_price * 0.95
                            if pos.trailing_stop is None or new_trailing > pos.trailing_stop:
                                pos.trailing_stop = new_trailing

                drawdown_status = self.risk_manager.check_drawdown(self.portfolio)
                if drawdown_status != "normal":
                    self.alerts.risk_alert(f"Drawdown alert: {drawdown_status}")

            except Exception as e:
                logger.debug("Position update error: %s", e)

            await asyncio.sleep(30)

    async def _position_monitor_loop(self):
        interval = self.config["research"].get("position_monitor_interval_minutes", 60) * 60
        while self.running:
            await asyncio.sleep(interval)
            if not self._is_market_open() or not self.portfolio.positions:
                continue

            held = list(self.portfolio.positions.keys())
            logger.info("Position monitor: re-analyzing %d held stocks", len(held))

            for ticker in held:
                if ticker not in self.portfolio.positions:
                    continue
                try:
                    report = await self.research_engine.analyze_stock(ticker)
                    pos = self.portfolio.positions.get(ticker)
                    if pos:
                        logger.info("  %s: %s (Conviction: %d/10, P&L: %+.1f%%)",
                                    ticker, report.signal.value, report.conviction_score,
                                    pos.unrealized_pnl_pct)
                except Exception as e:
                    logger.error("Position monitor failed for %s: %s", ticker, e)

            logger.info("Position monitor cycle complete")

    async def shutdown(self):
        self.running = False
        self.alerts.daily_summary(self.portfolio)
        await self.order_manager.disconnect()
        print("\nAITrading System shut down.")


def main():
    system = AITradingSystem()

    def handle_signal(sig, frame):
        system.running = False

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    asyncio.run(system.start())


if __name__ == "__main__":
    main()
