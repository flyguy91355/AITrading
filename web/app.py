"""Web dashboard server for AITrading system."""

import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.utils.config import load_config
from src.data.market_data import MarketDataFetcher
from src.data.insider_tracker import InsiderTracker
from src.data.news_feed import NewsFeed
from src.research.engine import ResearchEngine
from src.research.fundamental import FundamentalAnalyzer
from src.research.sentiment import SentimentAnalyzer
from src.research.insider_analysis import InsiderAnalyzer
from src.research.competitor import CompetitorAnalyzer
from src.decision.signal_generator import SignalGenerator
from src.decision.risk_manager import RiskManager
from src.decision.portfolio import Portfolio
from src.execution.order_manager import OrderManager
from src.execution.broker import OrderSide, OrderType, OrderStatus, Order
from src.reporting.trade_logger import TradeLogger
from src.utils.watchlist_manager import WatchlistManager
from src.data.stock_universe import STOCK_UNIVERSE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = FastAPI(title="AITrading Dashboard")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")

TOP_50_STOCKS = [
    {"ticker": "AAPL",  "name": "Apple Inc.",             "sector": "Technology"},
    {"ticker": "MSFT",  "name": "Microsoft Corp.",         "sector": "Technology"},
    {"ticker": "GOOGL", "name": "Alphabet Inc.",           "sector": "Technology"},
    {"ticker": "AMZN",  "name": "Amazon.com Inc.",         "sector": "Consumer Disc."},
    {"ticker": "NVDA",  "name": "NVIDIA Corp.",            "sector": "Technology"},
    {"ticker": "META",  "name": "Meta Platforms",          "sector": "Technology"},
    {"ticker": "TSLA",  "name": "Tesla Inc.",              "sector": "Consumer Disc."},
    {"ticker": "BRK.B", "name": "Berkshire Hathaway",      "sector": "Financials"},
    {"ticker": "LLY",   "name": "Eli Lilly & Co.",         "sector": "Healthcare"},
    {"ticker": "AVGO",  "name": "Broadcom Inc.",           "sector": "Technology"},
    {"ticker": "JPM",   "name": "JPMorgan Chase",          "sector": "Financials"},
    {"ticker": "V",     "name": "Visa Inc.",               "sector": "Financials"},
    {"ticker": "UNH",   "name": "UnitedHealth Group",      "sector": "Healthcare"},
    {"ticker": "MA",    "name": "Mastercard Inc.",         "sector": "Financials"},
    {"ticker": "XOM",   "name": "Exxon Mobil Corp.",       "sector": "Energy"},
    {"ticker": "COST",  "name": "Costco Wholesale",        "sector": "Cons. Staples"},
    {"ticker": "HD",    "name": "Home Depot Inc.",         "sector": "Consumer Disc."},
    {"ticker": "PG",    "name": "Procter & Gamble",        "sector": "Cons. Staples"},
    {"ticker": "JNJ",   "name": "Johnson & Johnson",       "sector": "Healthcare"},
    {"ticker": "ABBV",  "name": "AbbVie Inc.",             "sector": "Healthcare"},
    {"ticker": "CRM",   "name": "Salesforce Inc.",         "sector": "Technology"},
    {"ticker": "NFLX",  "name": "Netflix Inc.",            "sector": "Comm. Services"},
    {"ticker": "AMD",   "name": "Adv. Micro Devices",      "sector": "Technology"},
    {"ticker": "BAC",   "name": "Bank of America",         "sector": "Financials"},
    {"ticker": "KO",    "name": "Coca-Cola Co.",           "sector": "Cons. Staples"},
    {"ticker": "MRK",   "name": "Merck & Co.",             "sector": "Healthcare"},
    {"ticker": "PEP",   "name": "PepsiCo Inc.",            "sector": "Cons. Staples"},
    {"ticker": "TMO",   "name": "Thermo Fisher Sci.",      "sector": "Healthcare"},
    {"ticker": "ORCL",  "name": "Oracle Corp.",            "sector": "Technology"},
    {"ticker": "ACN",   "name": "Accenture plc",           "sector": "Technology"},
    {"ticker": "LIN",   "name": "Linde plc",               "sector": "Materials"},
    {"ticker": "WMT",   "name": "Walmart Inc.",            "sector": "Cons. Staples"},
    {"ticker": "CSCO",  "name": "Cisco Systems",           "sector": "Technology"},
    {"ticker": "MCD",   "name": "McDonald's Corp.",        "sector": "Consumer Disc."},
    {"ticker": "ABT",   "name": "Abbott Labs",             "sector": "Healthcare"},
    {"ticker": "DIS",   "name": "Walt Disney Co.",         "sector": "Comm. Services"},
    {"ticker": "ADBE",  "name": "Adobe Inc.",              "sector": "Technology"},
    {"ticker": "DHR",   "name": "Danaher Corp.",           "sector": "Healthcare"},
    {"ticker": "WFC",   "name": "Wells Fargo & Co.",       "sector": "Financials"},
    {"ticker": "INTC",  "name": "Intel Corp.",             "sector": "Technology"},
    {"ticker": "QCOM",  "name": "Qualcomm Inc.",           "sector": "Technology"},
    {"ticker": "INTU",  "name": "Intuit Inc.",             "sector": "Technology"},
    {"ticker": "TXN",   "name": "Texas Instruments",       "sector": "Technology"},
    {"ticker": "PM",    "name": "Philip Morris Intl.",     "sector": "Cons. Staples"},
    {"ticker": "NOW",   "name": "ServiceNow Inc.",         "sector": "Technology"},
    {"ticker": "IBM",   "name": "IBM Corp.",               "sector": "Technology"},
    {"ticker": "GE",    "name": "GE Aerospace",            "sector": "Industrials"},
    {"ticker": "CAT",   "name": "Caterpillar Inc.",        "sector": "Industrials"},
    {"ticker": "AMAT",  "name": "Applied Materials",       "sector": "Technology"},
    {"ticker": "GS",    "name": "Goldman Sachs",           "sector": "Financials"},
]

INTER_STOCK_DELAY = 3


class DashboardState:
    def __init__(self):
        self.config = load_config()
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
        self.fund_analyzer = FundamentalAnalyzer(self.config)
        self.sent_analyzer = SentimentAnalyzer(self.config)
        self.ins_analyzer = InsiderAnalyzer(self.config)
        self.comp_analyzer = CompetitorAnalyzer(self.config)

        self.ai_log: list[dict] = []
        self.trade_history: list[dict] = []
        self.active_signals: list[dict] = []
        self.ticker_signals: dict[str, dict] = {}
        self.buy_candidates: list[dict] = []
        self.deep_dive_reports: dict[str, dict] = {}
        self.connected_clients: list[WebSocket] = []

        self.current_ticker: str = ""
        self.cycle_count: int = 0
        self.scan_index: int = 0       # which stock in the 50 we're on
        self.next_cycle_at: str = ""
        self.paused: bool = False

        self.has_claude = bool(os.getenv("ANTHROPIC_API_KEY", ""))
        self.stock_delay = 15 if self.has_claude else INTER_STOCK_DELAY

        self.order_manager = OrderManager(self.config, self.portfolio)
        self.trade_logger = TradeLogger(self.config)
        self.broker_connected: bool = False
        self.pending_confirmations: dict[str, dict] = {}

        research_cfg = self.config.get("research", {})
        self.scans_per_day = research_cfg.get("scans_per_day", 3)
        h, m = research_cfg.get("market_open", "09:30").split(":")
        self.market_open = dtime(int(h), int(m))
        h, m = research_cfg.get("market_close", "16:00").split(":")
        self.market_close = dtime(int(h), int(m))
        self.market_tz = ZoneInfo(research_cfg.get("market_timezone", "America/New_York"))

        self.explicit_scan_times: list[dtime] = []
        for t_str in research_cfg.get("scan_times", []):
            sh, sm = t_str.split(":")
            self.explicit_scan_times.append(dtime(int(sh), int(sm)))

        self.position_monitor_interval = research_cfg.get("position_monitor_interval_minutes", 60)

        db_path = self.config.get("database", {}).get("path", "data/aitrading.db")
        self.watchlist_manager = WatchlistManager(
            db_path=db_path,
            target_size=research_cfg.get("watchlist_size", 50),
            weak_threshold=research_cfg.get("weak_signal_threshold", 3),
        )
        self.watchlist_manager.seed(TOP_50_STOCKS)


    # ── WebSocket helpers ──────────────────────────────────────────────────

    async def broadcast(self, msg: dict):
        dead = []
        for ws in self.connected_clients:
            try:
                await ws.send_json(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            if ws in self.connected_clients:
                self.connected_clients.remove(ws)

    def add_ai_log(self, ticker: str, phase: str, content: str, level: str = "info") -> dict:
        entry = {
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "ticker": ticker,
            "phase": phase,
            "content": content,
            "level": level,
        }
        self.ai_log.append(entry)
        if len(self.ai_log) > 500:
            self.ai_log = self.ai_log[-500:]
        return entry

    # ── Portfolio snapshot ─────────────────────────────────────────────────

    def get_portfolio_snapshot(self) -> dict:
        p = self.portfolio
        positions = [
            {
                "ticker": pos.ticker,
                "shares": pos.shares,
                "entry_price": round(pos.entry_price, 2),
                "current_price": round(pos.current_price, 2),
                "market_value": round(pos.market_value, 2),
                "pnl": round(pos.unrealized_pnl, 2),
                "pnl_pct": round(pos.unrealized_pnl_pct, 2),
                "stop_loss": round(pos.stop_loss, 2),
                "sector": pos.sector,
            }
            for pos in p.positions.values()
        ]
        return {
            "total_value": round(p.total_value, 2),
            "cash": round(p.cash, 2),
            "cash_pct": round(p.cash_pct, 1),
            "day_pnl": round(p.day_pnl, 2),
            "day_pnl_pct": round((p.day_pnl / p.day_start_value * 100) if p.day_start_value else 0, 2),
            "total_pnl": round(p.total_pnl, 2),
            "total_pnl_pct": round(p.total_pnl_pct, 2),
            "positions": positions,
            "position_count": len(positions),
        }

    def get_scan_status(self) -> dict:
        return {
            "current_ticker": self.current_ticker,
            "cycle": self.cycle_count,
            "index": self.scan_index,
            "total": self.watchlist_manager.size(),
            "next_cycle": self.next_cycle_at,
            "paused": self.paused,
        }

    # ── Buy candidate pipeline ──────────────────────────────────────────

    def _collect_buy_candidates(self) -> list[dict]:
        from src.research.engine import Signal
        candidates = []
        for ticker, report in self.research_engine.reports.items():
            if report.signal not in (Signal.STRONG_BUY, Signal.BUY):
                continue
            if report.conviction_score < self.config.get("research", {}).get("min_conviction_score", 7):
                continue
            candidates.append({
                "ticker": report.ticker,
                "company_name": report.company_name,
                "signal": report.signal.value,
                "conviction": report.conviction_score,
                "entry_price": round(report.entry_price, 2),
                "stop_loss": round(report.stop_loss, 2),
                "take_profit_targets": [round(t, 2) for t in report.take_profit_targets],
                "risk_level": report.risk_level.value,
                "thesis": report.thesis,
                "reasoning": report.reasoning,
                "time_horizon": report.time_horizon,
                "position_size_pct": report.position_size_pct,
                "generated_at": report.generated_at.isoformat(),
                "deep_dive": self.deep_dive_reports.get(report.ticker),
            })
        signal_priority = {"STRONG BUY": 0, "BUY": 1}
        candidates.sort(key=lambda c: (signal_priority.get(c["signal"], 9), -c["conviction"]))
        self.buy_candidates = candidates
        return candidates

    async def run_deep_dives(self, candidates: list[dict]):
        for candidate in candidates:
            ticker = candidate["ticker"]
            try:
                entry = self.add_ai_log(ticker, "DEEP_DIVE", "Starting deep-dive analysis...")
                await self.broadcast({"type": "ai_log", "entry": entry})
                report = await self.research_engine.deep_dive_analysis(ticker)
                dd = {
                    "ticker": report.ticker,
                    "valuation_analysis": report.valuation_analysis,
                    "fair_value_estimate": report.fair_value_estimate,
                    "margin_of_safety_pct": report.margin_of_safety_pct,
                    "catalysts": report.catalysts,
                    "risk_scenarios": report.risk_scenarios,
                    "entry_zone_low": report.entry_zone_low,
                    "entry_zone_high": report.entry_zone_high,
                    "monitoring_checklist": report.monitoring_checklist,
                    "enhanced_reasoning": report.enhanced_reasoning,
                }
                self.deep_dive_reports[ticker] = dd
                await self.broadcast({"type": "deep_dive_report", "ticker": ticker, "report": dd})
                entry = self.add_ai_log(ticker, "DEEP_DIVE",
                    f"Fair value ${report.fair_value_estimate:.2f} | "
                    f"Margin of safety {report.margin_of_safety_pct:.0f}%", "success")
                await self.broadcast({"type": "ai_log", "entry": entry})
            except Exception as e:
                logger.error("Deep dive failed for %s: %s", ticker, e)
                entry = self.add_ai_log(ticker, "ERROR", f"Deep dive failed: {e}", "error")
                await self.broadcast({"type": "ai_log", "entry": entry})
            await asyncio.sleep(2)

        self.buy_candidates = self._collect_buy_candidates()
        await self.broadcast({"type": "buy_candidates", "candidates": self.buy_candidates})

    async def _auto_buy_after_deep_dive(self, candidates: list[dict]):
        """Auto-buy candidates after deep-dive confirmation, with portfolio rotation."""
        max_positions = self.config.get("portfolio", {}).get("max_positions", 10)
        logger.info("Auto-buy evaluation starting — %d candidates, %d/%d positions held",
                     len(candidates), len(self.portfolio.positions), max_positions)

        confirmed = []
        for candidate in candidates:
            ticker = candidate["ticker"]
            if ticker in self.portfolio.positions:
                logger.info("  %s: already held — skipping", ticker)
                continue

            dd = self.deep_dive_reports.get(ticker)
            if not dd:
                entry = self.add_ai_log(ticker, "AUTO_TRADE",
                    "Skipping — no deep-dive report available", "warning")
                await self.broadcast({"type": "ai_log", "entry": entry})
                continue

            margin = dd.get("margin_of_safety_pct", 0)
            fair_value = dd.get("fair_value_estimate", 0)
            current_price = candidate.get("entry_price", 0)

            if margin < 10:
                entry = self.add_ai_log(ticker, "AUTO_TRADE",
                    f"Skipping — margin of safety too low ({margin:.0f}%). "
                    f"Fair value ${fair_value:.2f} vs price ${current_price:.2f}", "warning")
                await self.broadcast({"type": "ai_log", "entry": entry})
                continue

            report = self.research_engine.reports.get(ticker)
            if not report:
                logger.info("  %s: no research report found — skipping", ticker)
                continue

            # Upgrade T3 to deep-dive fair value so R/R uses the more accurate estimate
            if fair_value > 0 and fair_value > report.entry_price:
                targets = list(report.take_profit_targets) if report.take_profit_targets else []
                if len(targets) >= 3:
                    targets[2] = max(targets[2], fair_value)
                elif len(targets) == 2:
                    targets.append(fair_value)
                elif len(targets) == 1:
                    targets.extend([report.entry_price * 1.07, fair_value])
                else:
                    ep = report.entry_price
                    targets = [ep * 1.04, ep * 1.08, fair_value]
                report.take_profit_targets = targets

            signal = self.signal_generator._evaluate_report(report)
            if not signal:
                # Log specific reason for rejection
                risk = report.entry_price - report.stop_loss
                targets = report.take_profit_targets or []
                top = targets[2] if len(targets) >= 3 else (targets[-1] if targets else 0)
                rr = (top - report.entry_price) / risk if risk > 0 else 0
                reason = (
                    f"R/R {rr:.2f} < {self.config['research']['min_risk_reward_ratio']} "
                    f"(entry ${report.entry_price:.2f}, stop ${report.stop_loss:.2f}, T3 ${top:.2f})"
                    if risk > 0 else "invalid stop loss"
                )
                logger.info("  %s: rejected — %s", ticker, reason)
                entry = self.add_ai_log(ticker, "AUTO_TRADE",
                    f"Rejected — {reason}", "warning")
                await self.broadcast({"type": "ai_log", "entry": entry})
                continue

            confirmed.append({
                "ticker": ticker,
                "signal": signal,
                "conviction": candidate["conviction"],
                "margin": margin,
                "fair_value": fair_value,
                "score": candidate["conviction"] + (margin / 10),
            })

        confirmed.sort(key=lambda c: c["score"], reverse=True)

        # Track tickers ordered this scan so pending (unfilled) orders count against the limit
        pending_tickers: set[str] = set()
        pending_cash_reserved: float = 0.0

        for candidate in confirmed:
            ticker = candidate["ticker"]
            signal = candidate["signal"]
            margin = candidate["margin"]
            fair_value = candidate["fair_value"]

            if ticker in self.portfolio.positions or ticker in pending_tickers:
                continue

            current_count = len(self.portfolio.positions) + len(pending_tickers)
            if current_count >= max_positions:
                swapped = await self._try_rotation_swap(candidate)
                if not swapped:
                    entry = self.add_ai_log(ticker, "AUTO_TRADE",
                        f"Portfolio full ({max_positions} positions) — no weaker holding to swap", "warning")
                    await self.broadcast({"type": "ai_log", "entry": entry})
                    continue

            # Check cash reserve accounting for already-queued orders this scan
            order_cost = signal.shares * signal.entry_price
            effective_cash = self.portfolio.cash - pending_cash_reserved
            required_reserve = self.portfolio.total_value * (
                self.config["risk_management"]["min_cash_reserve_pct"] / 100)
            if effective_cash - order_cost < required_reserve:
                logger.info("  %s SKIPPED: insufficient cash after pending orders (need $%.0f, have $%.0f free)",
                            ticker, order_cost, effective_cash - required_reserve)
                continue

            try:
                order = await self.order_manager.execute(signal)
                if order:
                    pending_tickers.add(ticker)
                    pending_cash_reserved += order_cost
                    self.trade_logger.log_trade(signal)
                    result = {
                        "ticker": signal.ticker,
                        "status": order.status.value,
                        "filled_price": order.filled_price,
                        "shares": signal.shares,
                    }
                    await self.broadcast({"type": "trade_executed", "trade": result})
                    await self.broadcast({"type": "portfolio", "portfolio": self.get_portfolio_snapshot()})
                    entry = self.add_ai_log(ticker, "AUTO_TRADE",
                        f"AUTO BUY {signal.shares} shares @ ${order.filled_price or signal.entry_price:.2f} "
                        f"| Conviction {signal.conviction}/10 | Margin of safety {margin:.0f}% "
                        f"| Fair value ${fair_value:.2f}", "buy")
                    await self.broadcast({"type": "ai_log", "entry": entry})
                    logger.info("Auto-executed BUY %s — %d shares @ $%.2f (margin of safety %d%%)",
                                ticker, signal.shares, order.filled_price or signal.entry_price, margin)
                    # Free the watchlist slot — held stocks are monitored hourly, no need to scan daily
                    self.watchlist_manager.remove(ticker)
                    asyncio.create_task(self._replace_one_watchlist_slot())
            except Exception as e:
                entry = self.add_ai_log(ticker, "AUTO_TRADE", f"Auto-buy failed: {e}", "error")
                await self.broadcast({"type": "ai_log", "entry": entry})

    def _rank_position(self, ticker: str) -> float:
        """Score a held position — lower score = weaker holding, better swap candidate."""
        pos = self.portfolio.positions.get(ticker)
        if not pos:
            return float("inf")

        report = self.research_engine.reports.get(ticker)
        conviction = report.conviction_score if report else 5

        return conviction + (pos.unrealized_pnl_pct / 10)

    async def _try_rotation_swap(self, new_candidate: dict) -> bool:
        """Sell weakest holding if new candidate scores higher. Returns True if swap happened."""
        from src.decision.signal_generator import TradeSignal
        from src.research.engine import Signal as Sig

        ranked = sorted(
            self.portfolio.positions.keys(),
            key=lambda t: self._rank_position(t),
        )

        if not ranked:
            return False

        weakest_ticker = ranked[0]
        weakest_score = self._rank_position(weakest_ticker)
        new_score = new_candidate["score"]

        weakest_pos = self.portfolio.positions[weakest_ticker]
        weakest_report = self.research_engine.reports.get(weakest_ticker)
        weakest_conviction = weakest_report.conviction_score if weakest_report else 5

        if new_score <= weakest_score:
            entry = self.add_ai_log(new_candidate["ticker"], "ROTATION",
                f"New candidate (score {new_score:.1f}) does not beat weakest holding "
                f"{weakest_ticker} (score {weakest_score:.1f}) — keeping current portfolio", "info")
            await self.broadcast({"type": "ai_log", "entry": entry})
            return False

        entry = self.add_ai_log(weakest_ticker, "ROTATION",
            f"SWAPPING {weakest_ticker} (conviction {weakest_conviction}, P&L {weakest_pos.unrealized_pnl_pct:+.1f}%) "
            f"→ {new_candidate['ticker']} (conviction {new_candidate['conviction']}, "
            f"margin of safety {new_candidate['margin']:.0f}%)", "sell")
        await self.broadcast({"type": "ai_log", "entry": entry})

        sell_signal = TradeSignal(
            ticker=weakest_ticker, signal=Sig.SELL, conviction=10,
            entry_price=weakest_pos.current_price, stop_loss=0,
            take_profit_targets=[], position_size_pct=0,
            position_size_dollars=weakest_pos.market_value,
            shares=weakest_pos.shares,
            reasoning=f"Portfolio rotation: replacing with stronger candidate {new_candidate['ticker']}",
            research_report=weakest_report, generated_at=datetime.now(),
            should_execute=True,
        )

        try:
            order = await self.order_manager.execute(sell_signal)
            if order:
                self.trade_logger.log_trade(sell_signal)
                result = {
                    "ticker": weakest_ticker, "status": order.status.value,
                    "filled_price": order.filled_price,
                    "shares": weakest_pos.shares,
                    "pnl": round(weakest_pos.unrealized_pnl, 2),
                }
                await self.broadcast({"type": "trade_executed", "trade": result})
                entry = self.add_ai_log(weakest_ticker, "ROTATION",
                    f"SOLD {weakest_pos.shares} shares — P&L: ${weakest_pos.unrealized_pnl:+.2f} "
                    f"— making room for {new_candidate['ticker']}", "sell")
                await self.broadcast({"type": "ai_log", "entry": entry})
                logger.info("Rotation: sold %s (score %.1f) to make room for %s (score %.1f)",
                            weakest_ticker, weakest_score, new_candidate["ticker"], new_score)
                return True
        except Exception as e:
            entry = self.add_ai_log(weakest_ticker, "ERROR", f"Rotation sell failed: {e}", "error")
            await self.broadcast({"type": "ai_log", "entry": entry})

        return False

    # ── Core stock analysis ────────────────────────────────────────────────

    async def analyze_stock_with_logging(self, ticker: str) -> dict | None:
        self.current_ticker = ticker
        held = ticker in self.portfolio.positions

        async def log(phase, content, level="info"):
            entry = self.add_ai_log(ticker, phase, content, level)
            await self.broadcast({"type": "ai_log", "entry": entry})

        await log("START", f"Beginning research analysis for {ticker}")

        # ── Market data ──
        await log("DATA", "Fetching real-time quote...")
        try:
            quote = await self.market_data.get_quote(ticker)
            await log("DATA", f"${quote.price:.2f}  {quote.change_pct:+.2f}%  Vol: {quote.volume:,}")
        except Exception as e:
            await log("ERROR", f"Quote failed: {e}", "error")
            return None

        await log("DATA", "Pulling financials & ratios...")
        try:
            financials = await self.market_data.get_financials(ticker)
            await log("DATA",
                f"P/E {financials.pe_ratio:.1f} | Net margin {financials.net_margin:.0%} | "
                f"ROE {financials.roe:.0%} | D/E {financials.debt_to_equity:.1f}")
        except Exception as e:
            await log("WARN", f"Financials partial: {e}", "warning")
            financials = await self.market_data.get_financials(ticker)

        await log("DATA", "Computing technicals (SMA50/200, RSI, support/resistance)...")
        technicals = await self.market_data.get_technicals(ticker)
        rsi_note = "oversold" if technicals.rsi < 35 else "overbought" if technicals.rsi > 65 else "neutral"
        await log("DATA",
            f"SMA50 ${technicals.sma_50:.2f} | SMA200 ${technicals.sma_200:.2f} | "
            f"RSI {technicals.rsi:.1f} ({rsi_note})")

        # ── Insider data ──
        await log("INSIDER", "Scanning SEC Form 4 filings (90 days)...")
        insider_summary = await self.insider_tracker.get_insider_summary(ticker)
        await log("INSIDER",
            f"Buys: {insider_summary.buy_count_90d}  Sells: {insider_summary.sell_count_90d}  "
            f"Cluster buy: {'✓ YES' if insider_summary.cluster_buying else 'No'}")

        # ── News ──
        await log("NEWS", "Aggregating news and sentiment...")
        news_items = await self.news_feed.get_company_news(ticker, days=7)
        await log("NEWS", f"{len(news_items)} articles found in last 7 days")

        # ── Analysis modules ──
        await log("ANALYSIS", "Scoring fundamentals...")
        fund_score = await self.fund_analyzer.analyze(financials)
        await log("ANALYSIS",
            f"Fundamental {fund_score.overall_score:.1f}/10 — {fund_score.summary}")

        await log("ANALYSIS", "Scoring sentiment...")
        sentiment = await self.sent_analyzer.analyze(news_items)
        await log("ANALYSIS",
            f"Sentiment {sentiment.overall_sentiment:+.2f} "
            f"({sentiment.positive_count}+ / {sentiment.negative_count}-)")

        await log("ANALYSIS", "Scoring insider activity...")
        insider_analysis = await self.ins_analyzer.analyze(insider_summary)
        await log("ANALYSIS",
            f"Insider signal {insider_analysis.signal_strength:+.2f} — {insider_analysis.net_insider_sentiment}")

        await log("ANALYSIS", "Assessing competitive moat...")
        competitive = await self.comp_analyzer.analyze(ticker)
        await log("ANALYSIS",
            f"Moat {competitive.moat_score:.1f}/10 — {competitive.moat_assessment[:80]}")

        # ── Final synthesis ──
        await log("AI", "Synthesizing all dimensions into recommendation...")
        try:
            report = await self.research_engine.analyze_stock(ticker)
        except Exception as e:
            await log("ERROR", f"Synthesis failed: {e}", "error")
            return None

        sig = report.signal.value
        is_buy = "BUY" in sig
        is_sell = "SELL" in sig
        is_hold = sig == "HOLD"

        self.watchlist_manager.update_signal(ticker, sig)

        level = "buy" if is_buy else "sell" if is_sell else "neutral"
        await log("RESULT",
            f"▶ {sig}  |  Conviction {report.conviction_score}/10  |  Risk {report.risk_level.value}",
            level)

        if report.reasoning:
            await log("REASONING", report.reasoning)

        if report.stop_loss > 0:
            targets = ", ".join(f"${t:.2f}" for t in report.take_profit_targets) or "N/A"
            await log("TRADE",
                f"Entry ${report.entry_price:.2f}  Stop ${report.stop_loss:.2f}  "
                f"Targets: {targets}  Horizon: {report.time_horizon}")

        await log("DONE", f"✓ Done — {ticker}", "success")

        # ── Push ticker signal badge update ──
        badge = {
            "ticker": ticker,
            "signal": sig,
            "conviction": report.conviction_score,
            "price": round(report.entry_price, 2),
            "time": datetime.now().strftime("%H:%M"),
        }
        self.ticker_signals[ticker] = badge
        await self.broadcast({"type": "ticker_signal", "badge": badge})

        # ── Push full report ──
        report_data = {
            "ticker": report.ticker,
            "company_name": report.company_name,
            "signal": sig,
            "conviction": report.conviction_score,
            "risk_level": report.risk_level.value,
            "thesis": report.thesis,
            "entry_price": round(report.entry_price, 2),
            "stop_loss": round(report.stop_loss, 2),
            "take_profit_targets": [round(t, 2) for t in report.take_profit_targets],
            "position_size_pct": report.position_size_pct,
            "time_horizon": report.time_horizon,
            "reasoning": report.reasoning,
            "fundamental_summary": report.fundamental_summary,
            "insider_summary": report.insider_summary,
            "news_summary": report.news_summary,
            "competitive_summary": report.competitive_summary,
            "risk_factors": report.risk_factors,
            "generated_at": report.generated_at.isoformat(),
        }
        await self.broadcast({"type": "report", "report": report_data})

        # ── Surface actionable signals (not HOLD, unless we're holding it) ──
        if is_buy and report.conviction_score >= 7:
            sig_entry = {
                "ticker": ticker,
                "signal": sig,
                "conviction": report.conviction_score,
                "entry_price": round(report.entry_price, 2),
                "stop_loss": round(report.stop_loss, 2),
                "time": datetime.now().strftime("%H:%M:%S"),
                "reasoning": report.reasoning[:150] if report.reasoning else "",
            }
            # Replace existing entry for same ticker instead of accumulating
            self.active_signals = [s for s in self.active_signals if s["ticker"] != ticker]
            self.active_signals.append(sig_entry)
            await self.broadcast({"type": "signal", "signals": self.active_signals})

        elif is_sell:
            sig_entry = {
                "ticker": ticker,
                "signal": sig,
                "conviction": report.conviction_score,
                "entry_price": round(report.entry_price, 2),
                "stop_loss": 0,
                "time": datetime.now().strftime("%H:%M:%S"),
                "reasoning": report.reasoning[:150] if report.reasoning else "",
            }
            self.active_signals = [s for s in self.active_signals if s["ticker"] != ticker]
            self.active_signals.append(sig_entry)
            await self.broadcast({"type": "signal", "signals": self.active_signals})

        elif is_hold and held:
            sig_entry = {
                "ticker": ticker,
                "signal": "HOLD (owned)",
                "conviction": report.conviction_score,
                "entry_price": round(report.entry_price, 2),
                "stop_loss": round(report.stop_loss, 2),
                "time": datetime.now().strftime("%H:%M:%S"),
                "reasoning": report.reasoning[:150] if report.reasoning else "",
            }
            self.active_signals = [s for s in self.active_signals if s["ticker"] != ticker]
            self.active_signals.append(sig_entry)
            await self.broadcast({"type": "signal", "signals": self.active_signals})

        # ── Auto-execute trades when enabled ──
        if self.config["trading"].get("auto_execute", False) and self.broker_connected:
            await self._auto_execute_signal(report, ticker, is_buy, is_sell, held)

        return report_data

    async def _auto_execute_signal(self, report, ticker: str, is_buy: bool, is_sell: bool, held: bool):
        """Auto-sell during scan. Buys are deferred until after deep-dive confirmation."""
        from src.decision.signal_generator import TradeSignal
        from src.research.engine import Signal as Sig

        if is_sell and held:
            pos = self.portfolio.positions.get(ticker)
            if not pos:
                return
            sell_signal = TradeSignal(
                ticker=ticker, signal=Sig.SELL, conviction=report.conviction_score,
                entry_price=pos.current_price, stop_loss=0,
                take_profit_targets=[], position_size_pct=0,
                position_size_dollars=pos.market_value,
                shares=pos.shares, reasoning=f"Auto-sell: signal dropped to {report.signal.value}",
                research_report=report, generated_at=datetime.now(),
                should_execute=True,
            )
            try:
                order = await self.order_manager.execute(sell_signal)
                if order:
                    self.trade_logger.log_trade(sell_signal)
                    result = {
                        "ticker": ticker,
                        "status": order.status.value,
                        "filled_price": order.filled_price,
                        "shares": pos.shares,
                        "pnl": round(pos.unrealized_pnl, 2),
                    }
                    await self.broadcast({"type": "trade_executed", "trade": result})
                    await self.broadcast({"type": "portfolio", "portfolio": self.get_portfolio_snapshot()})
                    entry = self.add_ai_log(ticker, "AUTO_TRADE",
                        f"AUTO SELL {pos.shares} shares @ ${order.filled_price or pos.current_price:.2f} "
                        f"P&L: ${pos.unrealized_pnl:+.2f}", "sell")
                    await self.broadcast({"type": "ai_log", "entry": entry})
                    logger.info("Auto-executed SELL %s — %d shares, P&L $%.2f",
                                ticker, pos.shares, pos.unrealized_pnl)
            except Exception as e:
                entry = self.add_ai_log(ticker, "AUTO_TRADE", f"Auto-sell failed: {e}", "error")
                await self.broadcast({"type": "ai_log", "entry": entry})

    # ── Broker integration ─────────────────────────────────────────────

    async def connect_broker(self):
        try:
            await self.order_manager.connect()
            self.broker_connected = True
            broker = self.config["trading"]["broker"]
            mode = "PAPER" if self.config["trading"]["paper_trading"] else "LIVE"
            entry = self.add_ai_log("SYSTEM", "BROKER", f"Connected to {broker.upper()} ({mode})", "success")
            await self.broadcast({"type": "ai_log", "entry": entry})
            await self.broadcast({"type": "broker_status", "connected": True, "broker": broker, "mode": mode})
        except Exception as e:
            self.broker_connected = False
            logger.warning("Broker connection failed: %s — trading disabled", e)
            entry = self.add_ai_log("SYSTEM", "BROKER", f"Connection failed: {e}", "error")
            await self.broadcast({"type": "ai_log", "entry": entry})
            await self.broadcast({"type": "broker_status", "connected": False})

    async def position_update_loop(self):
        while True:
            await asyncio.sleep(30)
            if not self.broker_connected:
                continue
            try:
                await self.order_manager.update_positions()

                for ticker, pos in list(self.portfolio.positions.items()):
                    # ── Stop loss ──
                    if pos.stop_loss and pos.current_price <= pos.stop_loss:
                        entry = self.add_ai_log(ticker, "RISK",
                            f"STOP LOSS triggered at ${pos.current_price:.2f}", "sell")
                        await self.broadcast({"type": "ai_log", "entry": entry})
                        if self.config["trading"].get("auto_execute", False):
                            await self._auto_close_position(ticker, pos, "Stop loss hit")

                    # ── Trailing stop ──
                    if self.config["risk_management"].get("trailing_stop_enabled", True):
                        if pos.unrealized_pnl_pct > 5:
                            new_trailing = pos.current_price * 0.95
                            if pos.trailing_stop is None or new_trailing > pos.trailing_stop:
                                pos.trailing_stop = new_trailing
                        if pos.trailing_stop and pos.current_price <= pos.trailing_stop:
                            entry = self.add_ai_log(ticker, "RISK",
                                f"TRAILING STOP triggered at ${pos.current_price:.2f} "
                                f"(trail: ${pos.trailing_stop:.2f})", "sell")
                            await self.broadcast({"type": "ai_log", "entry": entry})
                            if self.config["trading"].get("auto_execute", False):
                                await self._auto_close_position(ticker, pos, "Trailing stop hit")

                    # ── Conviction-drop auto-sell ──
                    if (self.config["trading"].get("auto_execute", False)
                            and ticker in self.portfolio.positions):
                        report = self.research_engine.reports.get(ticker)
                        if report and report.conviction_score <= 4:
                            entry = self.add_ai_log(ticker, "RISK",
                                f"Conviction dropped to {report.conviction_score}/10 — auto-selling", "sell")
                            await self.broadcast({"type": "ai_log", "entry": entry})
                            await self._auto_close_position(ticker, pos,
                                f"Conviction dropped to {report.conviction_score}/10")

                await self.broadcast({"type": "portfolio", "portfolio": self.get_portfolio_snapshot()})
            except Exception as e:
                logger.warning("Position update failed: %s", e)

    async def position_monitor_loop(self):
        """Re-analyze held positions every hour during market hours."""
        interval = self.position_monitor_interval * 60
        while True:
            await asyncio.sleep(interval)
            if self.paused or not self._is_market_open():
                continue
            if not self.portfolio.positions:
                continue

            held_tickers = list(self.portfolio.positions.keys())
            entry = self.add_ai_log("SYSTEM", "MONITOR",
                f"Position monitor: re-analyzing {len(held_tickers)} held stocks", "info")
            await self.broadcast({"type": "ai_log", "entry": entry})

            for ticker in held_tickers:
                if ticker not in self.portfolio.positions:
                    continue
                try:
                    entry = self.add_ai_log(ticker, "MONITOR", "Hourly re-analysis starting...")
                    await self.broadcast({"type": "ai_log", "entry": entry})

                    report = await self.research_engine.analyze_stock(ticker)

                    pos = self.portfolio.positions.get(ticker)
                    if not pos:
                        continue

                    level = "buy" if "BUY" in report.signal.value else "sell" if "SELL" in report.signal.value else "neutral"
                    entry = self.add_ai_log(ticker, "MONITOR",
                        f"Updated: {report.signal.value} | Conviction {report.conviction_score}/10 | "
                        f"P&L {pos.unrealized_pnl_pct:+.1f}%", level)
                    await self.broadcast({"type": "ai_log", "entry": entry})

                    badge = {
                        "ticker": ticker, "signal": report.signal.value,
                        "conviction": report.conviction_score,
                        "price": round(report.entry_price, 2),
                        "time": datetime.now().strftime("%H:%M"),
                    }
                    self.ticker_signals[ticker] = badge
                    await self.broadcast({"type": "ticker_signal", "badge": badge})

                    if self.config["trading"].get("auto_execute", False) and self.broker_connected:
                        held = ticker in self.portfolio.positions
                        is_sell = "SELL" in report.signal.value
                        await self._auto_execute_signal(report, ticker, False, is_sell, held)

                except Exception as e:
                    entry = self.add_ai_log(ticker, "ERROR", f"Monitor re-analysis failed: {e}", "error")
                    await self.broadcast({"type": "ai_log", "entry": entry})

                await asyncio.sleep(self.stock_delay)

            entry = self.add_ai_log("SYSTEM", "MONITOR",
                f"Position monitor complete — {len(held_tickers)} stocks updated", "success")
            await self.broadcast({"type": "ai_log", "entry": entry})

    async def _auto_close_position(self, ticker: str, pos, reason: str):
        """Close entire position automatically."""
        from src.decision.signal_generator import TradeSignal
        from src.research.engine import Signal as Sig

        if ticker not in self.portfolio.positions:
            return

        sell_signal = TradeSignal(
            ticker=ticker, signal=Sig.SELL, conviction=10,
            entry_price=pos.current_price, stop_loss=0,
            take_profit_targets=[], position_size_pct=0,
            position_size_dollars=pos.market_value,
            shares=pos.shares, reasoning=reason,
            research_report=None, generated_at=datetime.now(),
            should_execute=True,
        )

        try:
            order = await self.order_manager.execute(sell_signal)
            if order:
                self.trade_logger.log_trade(sell_signal)
                result = {
                    "ticker": ticker, "status": order.status.value,
                    "filled_price": order.filled_price,
                    "shares": pos.shares, "pnl": round(pos.unrealized_pnl, 2),
                }
                await self.broadcast({"type": "trade_executed", "trade": result})
                entry = self.add_ai_log(ticker, "AUTO_TRADE",
                    f"AUTO SELL {pos.shares} shares — {reason} — "
                    f"P&L: ${pos.unrealized_pnl:+.2f}", "sell")
                await self.broadcast({"type": "ai_log", "entry": entry})
                logger.info("Auto-closed %s — %s — P&L $%.2f", ticker, reason, pos.unrealized_pnl)
        except Exception as e:
            entry = self.add_ai_log(ticker, "ERROR", f"Auto-close failed: {e}", "error")
            await self.broadcast({"type": "ai_log", "entry": entry})

    async def handle_trade_command(self, data: dict, websocket: WebSocket):
        import uuid as _uuid
        cmd = data.get("command")

        if cmd == "execute_buy":
            ticker = data.get("ticker", "").upper().strip()
            valid_tickers = state.watchlist_manager.get_active_tickers()
            if ticker not in valid_tickers:
                await websocket.send_json({"type": "trade_error", "error": f"Invalid ticker: {ticker}"})
                return
            if not self.broker_connected:
                await websocket.send_json({"type": "trade_error", "error": "Broker not connected"})
                return
            report = self.research_engine.reports.get(ticker)
            if not report:
                await websocket.send_json({"type": "trade_error", "error": f"No report for {ticker}"})
                return

            signal = self.signal_generator._evaluate_report(report)
            if not signal:
                await websocket.send_json({"type": "trade_error", "error": f"Signal rejected by risk checks for {ticker}"})
                return

            risk_ok = self.risk_manager.check_all_rules(report, self.portfolio)
            risk_msg = "" if risk_ok else "One or more risk rules failed"
            conf_id = str(_uuid.uuid4())
            preview = {
                "confirmation_id": conf_id,
                "ticker": ticker,
                "shares": signal.shares,
                "entry_price": round(signal.entry_price, 2),
                "stop_loss": round(signal.stop_loss, 2),
                "estimated_cost": round(signal.position_size_dollars, 2),
                "position_pct": round(signal.position_size_pct, 1),
                "risk_check_passed": risk_ok,
                "risk_message": risk_msg,
            }
            self.pending_confirmations[conf_id] = {
                "signal": signal,
                "created_at": datetime.now(),
            }
            await websocket.send_json({"type": "trade_preview", "preview": preview})

        elif cmd == "confirm_buy":
            conf_id = data.get("confirmation_id", "")
            pending = self.pending_confirmations.pop(conf_id, None)
            if not pending:
                await websocket.send_json({"type": "trade_error", "error": "Confirmation expired or invalid"})
                return
            elapsed = (datetime.now() - pending["created_at"]).total_seconds()
            if elapsed > 60:
                await websocket.send_json({"type": "trade_error", "error": "Confirmation expired (60s)"})
                return

            signal = pending["signal"]
            try:
                order = await self.order_manager.execute(signal)
                self.trade_logger.log_trade(signal)
                result = {
                    "ticker": signal.ticker,
                    "status": order.status.value if order else "FAILED",
                    "filled_price": order.filled_price if order else None,
                    "shares": signal.shares,
                }
                await self.broadcast({"type": "trade_executed", "trade": result})
                await self.broadcast({"type": "portfolio", "portfolio": self.get_portfolio_snapshot()})
                entry = self.add_ai_log(signal.ticker, "TRADE",
                    f"BUY {signal.shares} shares @ ${order.filled_price or signal.entry_price:.2f}", "buy")
                await self.broadcast({"type": "ai_log", "entry": entry})
            except Exception as e:
                await websocket.send_json({"type": "trade_error", "error": str(e)})

        elif cmd == "execute_sell":
            ticker = data.get("ticker", "")
            if not self.broker_connected:
                await websocket.send_json({"type": "trade_error", "error": "Broker not connected"})
                return
            pos = self.portfolio.positions.get(ticker)
            if not pos:
                await websocket.send_json({"type": "trade_error", "error": f"No position in {ticker}"})
                return

            from src.decision.signal_generator import TradeSignal
            from src.research.engine import Signal as Sig
            sell_signal = TradeSignal(
                ticker=ticker, signal=Sig.SELL, conviction=10,
                entry_price=pos.current_price, stop_loss=0,
                take_profit_targets=[], position_size_pct=0,
                position_size_dollars=pos.market_value,
                shares=pos.shares, reasoning="Manual sell",
                research_report=None, generated_at=datetime.now(),
                should_execute=True,
            )
            try:
                order = await self.order_manager.execute(sell_signal)
                result = {
                    "ticker": ticker,
                    "status": order.status.value if order else "FAILED",
                    "filled_price": order.filled_price if order else None,
                    "shares": pos.shares,
                    "pnl": round(pos.unrealized_pnl, 2),
                }
                await self.broadcast({"type": "trade_executed", "trade": result})
                await self.broadcast({"type": "portfolio", "portfolio": self.get_portfolio_snapshot()})
                entry = self.add_ai_log(ticker, "TRADE",
                    f"SELL {pos.shares} shares @ ${order.filled_price or pos.current_price:.2f} "
                    f"P&L: ${pos.unrealized_pnl:+.2f}", "sell")
                await self.broadcast({"type": "ai_log", "entry": entry})
            except Exception as e:
                await websocket.send_json({"type": "trade_error", "error": str(e)})

        elif cmd == "cancel_order":
            order_id = data.get("order_id", "")
            success = await self.order_manager.cancel(order_id)
            await websocket.send_json({"type": "order_cancelled", "order_id": order_id, "success": success})

    # ── Market hours helpers ─────────────────────────────────────────────

    def _now_et(self) -> datetime:
        return datetime.now(self.market_tz)

    def _is_market_open(self) -> bool:
        now = self._now_et()
        if now.weekday() >= 5:
            return False
        return self.market_open <= now.time() <= self.market_close

    def _scan_times_today(self) -> list[dtime]:
        """Build the scheduled scan times across market hours."""
        if self.explicit_scan_times:
            return sorted(self.explicit_scan_times)
        open_mins = self.market_open.hour * 60 + self.market_open.minute
        close_mins = self.market_close.hour * 60 + self.market_close.minute
        total = close_mins - open_mins
        count = max(self.scans_per_day, 2)
        times = []
        for i in range(count):
            offset = open_mins + (total * i) // (count - 1)
            times.append(dtime(offset // 60, offset % 60))
        return times

    def _seconds_until_next_scan(self) -> tuple[float, str]:
        """Return (seconds_to_wait, formatted_time) for the next scan."""
        now = self._now_et()
        today_times = self._scan_times_today()

        if now.weekday() < 5:
            for t in today_times:
                scan_dt = now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
                if scan_dt > now:
                    delta = (scan_dt - now).total_seconds()
                    return delta, scan_dt.strftime("%H:%M ET")

        days_ahead = 1
        while True:
            next_day = now + timedelta(days=days_ahead)
            if next_day.weekday() < 5:
                break
            days_ahead += 1

        next_open = now.replace(
            hour=self.market_open.hour, minute=self.market_open.minute,
            second=0, microsecond=0
        ) + timedelta(days=days_ahead)
        delta = (next_open - now).total_seconds()
        return delta, next_open.strftime("%a %H:%M ET")

    # ── Auto-scan loop (runs during market hours) ─────────────────────

    async def auto_scan_loop(self):
        scan_times = self._scan_times_today()
        scan_labels = [t.strftime("%H:%M") for t in scan_times]
        logger.info("Auto-scan loop started — %d scans/day at %s ET",
                    self.scans_per_day, ", ".join(scan_labels))

        while True:
            if self.paused:
                await asyncio.sleep(5)
                continue

            if not self._is_market_open():
                wait_secs, next_label = self._seconds_until_next_scan()
                self.next_cycle_at = next_label
                await self.broadcast({
                    "type": "market_closed",
                    "next_scan": next_label,
                })
                logger.info("Market closed — next scan at %s (%.0f min)",
                            next_label, wait_secs / 60)
                await asyncio.sleep(min(wait_secs, 60))
                continue

            wait_secs, next_label = self._seconds_until_next_scan()
            if wait_secs > 30:
                self.next_cycle_at = next_label
                await self.broadcast({
                    "type": "waiting",
                    "next_scan": next_label,
                    "seconds": int(wait_secs),
                })
                await asyncio.sleep(min(wait_secs, 30))
                continue

            self.cycle_count += 1
            now_et = self._now_et()
            tickers = [s["ticker"] for s in self.watchlist_manager.get_active()]
            logger.info("Starting scan cycle #%d at %s ET (%d stocks)", self.cycle_count,
                        now_et.strftime("%H:%M"), len(tickers))
            await self.broadcast({"type": "cycle_start", "cycle": self.cycle_count, "total": len(tickers)})

            for i, ticker in enumerate(tickers):
                if self.paused:
                    break

                self.scan_index = i + 1
                status = self.get_scan_status()
                await self.broadcast({"type": "scan_progress", "status": status})

                try:
                    await self.analyze_stock_with_logging(ticker)
                except Exception as e:
                    logger.error("Auto-scan error on %s: %s", ticker, e)

                await self.broadcast({
                    "type": "portfolio",
                    "portfolio": self.get_portfolio_snapshot(),
                })

                if i < len(tickers) - 1:
                    await asyncio.sleep(self.stock_delay)

            self.current_ticker = ""

            candidates = self._collect_buy_candidates()
            if candidates:
                await self.broadcast({"type": "buy_candidates", "candidates": candidates})
                logger.info("Buy candidates: %s",
                            ", ".join(f"{c['ticker']}({c['conviction']})" for c in candidates))
                await self.run_deep_dives(candidates)

                if self.config["trading"].get("auto_execute", False) and self.broker_connected:
                    await self._auto_buy_after_deep_dive(candidates)

            # If this was the last scan of the day, run end-of-day replacement scan
            if self.config.get("research", {}).get("replacement_scan_eod", True):
                now_et = self._now_et()
                last_scan_today = max(self.explicit_scan_times) if self.explicit_scan_times else dtime(15, 30)
                if now_et.time() >= last_scan_today:
                    await self.run_replacement_scan()

            wait_secs, next_label = self._seconds_until_next_scan()
            self.next_cycle_at = next_label
            await self.broadcast({
                "type": "cycle_end",
                "cycle": self.cycle_count,
                "next_at": next_label,
            })

            logger.info("Cycle #%d complete. Next scan at %s", self.cycle_count, next_label)

    async def _replace_one_watchlist_slot(self):
        """Find one BUY/STRONG BUY from the universe to fill a freed watchlist slot."""
        min_conviction = max(6, self.config.get("research", {}).get("min_conviction_score", 7) - 1)
        available = self.watchlist_manager.available_from_universe(STOCK_UNIVERSE)
        for ticker in available:
            try:
                report = await self.research_engine.analyze_stock(ticker)
            except Exception:
                await asyncio.sleep(self.stock_delay)
                continue
            if ticker in STOCK_UNIVERSE:
                next_cursor = (STOCK_UNIVERSE.index(ticker) + 1) % len(STOCK_UNIVERSE)
                self.watchlist_manager.set_scan_cursor(next_cursor)
            if report.signal.value in ("BUY", "STRONG BUY") and report.conviction_score >= min_conviction:
                self.watchlist_manager.add(ticker, report.company_name, "")
                entry = self.add_ai_log(ticker, "WATCHLIST",
                    f"Added to watchlist (replaced bought position) — "
                    f"{report.signal.value} conviction {report.conviction_score}/10", "buy")
                await self.broadcast({"type": "ai_log", "entry": entry})
                logger.info("Watchlist slot filled by %s after buy", ticker)
                return
            await asyncio.sleep(self.stock_delay)
        logger.warning("Could not find a replacement watchlist candidate from universe")

    async def run_replacement_scan(self):
        """Evict underperformers and any held positions, scan universe until all slots filled."""
        underperformers = self.watchlist_manager.get_underperformers()

        # Also remove any watchlist stocks that are now held — they're monitored hourly
        held_in_watchlist = [t for t in self.watchlist_manager.get_active_tickers()
                             if t in self.portfolio.positions]
        for ticker in held_in_watchlist:
            self.watchlist_manager.remove(ticker)

        if not underperformers and not held_in_watchlist:
            logger.info("End-of-day replacement scan: watchlist is clean — no changes needed")
            return

        for ticker in underperformers:
            self.watchlist_manager.remove(ticker)

        slots = self.watchlist_manager.slots_available()
        logger.info("Weekly replacement scan: evicted %s — scanning universe for %d replacement(s)",
                    ", ".join(underperformers), slots)
        entry = self.add_ai_log("SYSTEM", "WATCHLIST",
            f"Evicted {len(underperformers)} underperformer(s): {', '.join(underperformers)}. "
            f"Scanning for {slots} replacement(s).", "warning")
        await self.broadcast({"type": "ai_log", "entry": entry})

        filled = 0
        available = self.watchlist_manager.available_from_universe(STOCK_UNIVERSE)
        # Watchlist just means "scan this stock regularly" — lower bar than actual trading
        # Trading still requires min_conviction_score (7); watchlist only needs 6
        min_conviction = max(6, self.config.get("research", {}).get("min_conviction_score", 7) - 1)
        last_scanned = None

        total_available = len(available)
        scanned_count = 0
        for ticker in available:
            if filled >= slots:
                break
            last_scanned = ticker
            scanned_count += 1

            # Update the middle panel scan strip so universe scan is visible there too
            self.current_ticker = ticker
            await self.broadcast({"type": "scan_progress", "status": {
                "current_ticker": ticker,
                "index": scanned_count,
                "total": total_available,
                "cycle": self.cycle_count,
                "label": f"Universe scan — seeking {slots - filled} slot(s)",
            }})

            try:
                report = await self.research_engine.analyze_stock(ticker)
            except Exception as e:
                logger.warning("Replacement scan error on %s: %s", ticker, e)
                await asyncio.sleep(self.stock_delay)
                continue

            level = "buy" if report.signal.value in ("BUY", "STRONG BUY") else "neutral"
            entry = self.add_ai_log(ticker, "UNIVERSE SCAN",
                f"{report.signal.value} | Conviction {report.conviction_score}/10", level)
            await self.broadcast({"type": "ai_log", "entry": entry})

            if report.signal.value in ("BUY", "STRONG BUY") and report.conviction_score >= min_conviction:
                self.watchlist_manager.add(ticker, report.company_name, "")
                filled += 1
                entry = self.add_ai_log(ticker, "WATCHLIST",
                    f"Added to watchlist — {report.signal.value} conviction {report.conviction_score}/10",
                    "buy")
                await self.broadcast({"type": "ai_log", "entry": entry})
                logger.info("Replacement: added %s (%s, conviction %d)",
                            ticker, report.signal.value, report.conviction_score)

            await asyncio.sleep(self.stock_delay)

        if last_scanned and last_scanned in STOCK_UNIVERSE:
            next_cursor = (STOCK_UNIVERSE.index(last_scanned) + 1) % len(STOCK_UNIVERSE)
            self.watchlist_manager.set_scan_cursor(next_cursor)

        # Clear the scan strip
        self.current_ticker = ""
        await self.broadcast({"type": "scan_progress", "status": {
            "current_ticker": "",
            "index": scanned_count,
            "total": total_available,
            "cycle": self.cycle_count,
            "label": "Universe scan complete",
        }})

        logger.info("Replacement scan complete: %d/%d slots filled. Watchlist now %d stocks.",
                    filled, slots, self.watchlist_manager.size())
        entry = self.add_ai_log("SYSTEM", "WATCHLIST",
            f"Universe scan complete — {filled}/{slots} slots filled. "
            f"Watchlist: {self.watchlist_manager.size()} stocks.", "success")
        await self.broadcast({"type": "ai_log", "entry": entry})

    async def run_forced_scan(self):
        """Run a full scan cycle regardless of market hours."""
        tickers = [s["ticker"] for s in self.watchlist_manager.get_active()]
        self.cycle_count += 1
        logger.info("FORCED scan cycle #%d starting (%d stocks)", self.cycle_count, len(tickers))

        entry = self.add_ai_log("SYSTEM", "SCAN",
            f"Manual scan cycle #{self.cycle_count} started (after-hours)", "info")
        await self.broadcast({"type": "ai_log", "entry": entry})
        await self.broadcast({"type": "cycle_start", "cycle": self.cycle_count, "total": len(tickers)})

        for i, ticker in enumerate(tickers):
            if self.paused:
                break

            self.scan_index = i + 1
            status = self.get_scan_status()
            await self.broadcast({"type": "scan_progress", "status": status})

            try:
                await self.analyze_stock_with_logging(ticker)
            except Exception as e:
                logger.error("Forced scan error on %s: %s", ticker, e)

            await self.broadcast({
                "type": "portfolio",
                "portfolio": self.get_portfolio_snapshot(),
            })

            if i < len(tickers) - 1:
                await asyncio.sleep(self.stock_delay)

        self.current_ticker = ""

        candidates = self._collect_buy_candidates()
        if candidates:
            await self.broadcast({"type": "buy_candidates", "candidates": candidates})
            logger.info("Buy candidates: %s",
                        ", ".join(f"{c['ticker']}({c['conviction']})" for c in candidates))
            await self.run_deep_dives(candidates)

            if self.config["trading"].get("auto_execute", False) and self.broker_connected:
                await self._auto_buy_after_deep_dive(candidates)

        # Fill any open watchlist slots from the universe
        if self.watchlist_manager.slots_available() > 0:
            await self.run_replacement_scan()

        await self.broadcast({"type": "cycle_end", "cycle": self.cycle_count, "next_at": "Manual"})
        entry = self.add_ai_log("SYSTEM", "SCAN",
            f"Manual scan cycle #{self.cycle_count} complete — {len(candidates)} candidates found", "success")
        await self.broadcast({"type": "ai_log", "entry": entry})
        logger.info("Forced scan cycle #%d complete", self.cycle_count)


state = DashboardState()


# ── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html = (Path(__file__).parent / "templates" / "dashboard.html").read_text()
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@app.get("/api/stocks")
async def get_stocks():
    return state.watchlist_manager.get_active()


@app.get("/api/portfolio")
async def get_portfolio():
    return state.get_portfolio_snapshot()


@app.get("/api/signals")
async def get_signals():
    return state.active_signals


@app.get("/api/ticker-signals")
async def get_ticker_signals():
    return state.ticker_signals


@app.get("/api/reports")
async def get_reports():
    out = []
    for ticker, report in state.research_engine.reports.items():
        out.append({
            "ticker": report.ticker,
            "company_name": report.company_name,
            "signal": report.signal.value,
            "conviction": report.conviction_score,
            "risk_level": report.risk_level.value,
            "entry_price": round(report.entry_price, 2),
            "stop_loss": round(report.stop_loss, 2),
            "take_profit_targets": [round(t, 2) for t in report.take_profit_targets],
            "thesis": report.thesis,
            "reasoning": report.reasoning,
            "fundamental_summary": report.fundamental_summary,
            "insider_summary": report.insider_summary,
            "news_summary": report.news_summary,
            "competitive_summary": report.competitive_summary,
            "risk_factors": report.risk_factors,
            "generated_at": report.generated_at.isoformat(),
        })
    return out


@app.get("/api/buy-candidates")
async def get_buy_candidates():
    return state.buy_candidates


@app.get("/api/broker-status")
async def get_broker_status():
    return {
        "connected": state.broker_connected,
        "broker": state.config["trading"]["broker"],
        "paper_trading": state.config["trading"]["paper_trading"],
    }


@app.get("/api/trade-history")
async def get_trade_history():
    return state.trade_logger.get_trade_history(days=30)


@app.get("/api/orders")
async def get_orders():
    return [
        {
            "broker_order_id": o.broker_order_id,
            "ticker": o.ticker,
            "side": o.side.value,
            "order_type": o.order_type.value,
            "quantity": o.quantity,
            "limit_price": o.limit_price,
            "stop_price": o.stop_price,
            "status": o.status.value,
            "filled_price": o.filled_price,
            "filled_quantity": o.filled_quantity,
            "submitted_at": o.submitted_at.isoformat() if o.submitted_at else None,
        }
        for o in state.order_manager.active_orders.values()
    ]


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    state.connected_clients.append(websocket)

    await websocket.send_json({
        "type": "init",
        "portfolio": state.get_portfolio_snapshot(),
        "ai_log": state.ai_log[-150:],
        "signals": state.active_signals,
        "ticker_signals": state.ticker_signals,
        "buy_candidates": state.buy_candidates,
        "deep_dive_reports": state.deep_dive_reports,
        "broker_status": {
            "connected": state.broker_connected,
            "broker": state.config["trading"]["broker"],
            "paper_trading": state.config["trading"]["paper_trading"],
        },
        "stocks": state.watchlist_manager.get_active(),
        "scan_status": state.get_scan_status(),
        "max_positions": state.config.get("portfolio", {}).get("max_positions", 10),
    })

    try:
        while True:
            data = await websocket.receive_json()
            cmd = data.get("command")

            if cmd == "pause":
                state.paused = True
                await state.broadcast({"type": "paused", "paused": True})
            elif cmd == "resume":
                state.paused = False
                await state.broadcast({"type": "paused", "paused": False})
            elif cmd == "get_portfolio":
                await websocket.send_json({"type": "portfolio", "portfolio": state.get_portfolio_snapshot()})
            elif cmd == "set_max_positions":
                val = int(data.get("value", 10))
                val = max(1, min(50, val))
                state.config.setdefault("portfolio", {})["max_positions"] = val
                await state.broadcast({"type": "max_positions", "value": val})
                entry = state.add_ai_log("SYSTEM", "CONFIG",
                    f"Max stock positions changed to {val}", "info")
                await state.broadcast({"type": "ai_log", "entry": entry})
                logger.info("Max positions updated to %d", val)
            elif cmd == "force_scan":
                asyncio.create_task(state.run_forced_scan())
            elif cmd in ("execute_buy", "confirm_buy", "execute_sell", "cancel_order"):
                await state.handle_trade_command(data, websocket)

    except WebSocketDisconnect:
        if websocket in state.connected_clients:
            state.connected_clients.remove(websocket)


@app.on_event("startup")
async def startup():
    Path("data").mkdir(exist_ok=True)
    await state.portfolio.initialize()
    await state.connect_broker()
    asyncio.create_task(state.auto_scan_loop())
    asyncio.create_task(state.position_update_loop())
    asyncio.create_task(state.position_monitor_loop())
    logger.info("Dashboard started — auto-scan running, position monitor active")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
