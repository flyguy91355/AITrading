"""Core research engine powered by Claude AI."""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path

import anthropic

from src.data.market_data import MarketDataFetcher
from src.data.insider_tracker import InsiderTracker
from src.data.news_feed import NewsFeed
from src.research.fundamental import FundamentalAnalyzer
from src.research.sentiment import SentimentAnalyzer
from src.research.insider_analysis import InsiderAnalyzer
from src.research.competitor import CompetitorAnalyzer
from src.utils.config import load_watchlist

logger = logging.getLogger(__name__)


class Signal(Enum):
    STRONG_BUY = "STRONG BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG SELL"
    NO_ACTION = "NO ACTION"


class RiskLevel(Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"


@dataclass
class ResearchReport:
    ticker: str
    company_name: str
    generated_at: datetime
    conviction_score: int
    signal: Signal
    risk_level: RiskLevel
    thesis: str
    fundamental_summary: str
    insider_summary: str
    news_summary: str
    competitive_summary: str
    risk_factors: str
    recommended_action: str
    entry_price: float
    position_size_pct: float
    stop_loss: float
    take_profit_targets: list[float] = field(default_factory=list)
    time_horizon: str = ""
    reasoning: str = ""


@dataclass
class DeepDiveReport:
    ticker: str
    company_name: str
    generated_at: datetime
    valuation_analysis: str
    fair_value_estimate: float
    margin_of_safety_pct: float
    catalysts: list[dict] = field(default_factory=list)
    risk_scenarios: list[dict] = field(default_factory=list)
    entry_zone_low: float = 0.0
    entry_zone_high: float = 0.0
    monitoring_checklist: list[str] = field(default_factory=list)
    enhanced_reasoning: str = ""


DEEP_DIVE_PROMPT = """\
You are a senior equity research analyst performing a DEEP DIVE analysis on a stock that has already passed initial screening as a buy candidate.

STOCK: {ticker} — {company_name}
CURRENT PRICE: ${current_price:.2f}
INITIAL SIGNAL: {signal} (Conviction: {conviction}/10)

── FUNDAMENTAL DATA ──
{fundamental_summary}

── INSIDER ACTIVITY ──
{insider_summary}

── NEWS & SENTIMENT ──
{news_summary}

── COMPETITIVE POSITION ──
{competitive_summary}

── TECHNICAL CONTEXT ──
{technical_summary}

Perform a thorough deep-dive analysis. Respond as JSON with these exact fields:
{{
    "valuation_analysis": "<detailed DCF-style valuation reasoning — is the stock cheap, fair, or expensive relative to intrinsic value?>",
    "fair_value_estimate": <your estimated fair value as a number>,
    "margin_of_safety_pct": <percentage below fair value the current price represents>,
    "catalysts": [
        {{"event": "<specific catalyst>", "timeframe": "<when>", "impact": "<expected price impact>"}}
    ],
    "risk_scenarios": [
        {{"scenario": "Bull", "probability_pct": <number>, "price_target": <number>, "description": "<what happens>"}},
        {{"scenario": "Base", "probability_pct": <number>, "price_target": <number>, "description": "<what happens>"}},
        {{"scenario": "Bear", "probability_pct": <number>, "price_target": <number>, "description": "<what happens>"}}
    ],
    "entry_zone_low": <optimal buy zone low price>,
    "entry_zone_high": <optimal buy zone high price>,
    "monitoring_checklist": ["<key metric or event to watch that would validate or invalidate the thesis>"],
    "enhanced_reasoning": "<comprehensive reasoning connecting valuation, catalysts, risks, and competitive position>"
}}

Respond with ONLY the JSON object, no other text.
"""


ANALYSIS_PROMPT = """\
You are a senior equity research analyst. Analyze the following stock data and produce a structured investment recommendation.

IMPORTANT RULES:
- Be conservative. The cardinal rule is NEVER LOSE MONEY.
- Only recommend BUY or STRONG BUY if conviction is 7/10 or higher.
- Every recommendation MUST include a stop loss.
- Risk/reward ratio must be at least 3:1 for any buy recommendation.
- If the data is insufficient or unclear, recommend NO ACTION.

STOCK: {ticker} — {company_name}
CURRENT PRICE: ${current_price:.2f}

── FUNDAMENTAL DATA ──
{fundamental_summary}

── INSIDER ACTIVITY ──
{insider_summary}

── NEWS & SENTIMENT ──
{news_summary}

── COMPETITIVE POSITION ──
{competitive_summary}

── TECHNICAL CONTEXT ──
{technical_summary}

Based on all of the above, provide your analysis as JSON with these exact fields:
{{
    "conviction_score": <1-10 integer>,
    "signal": "<STRONG BUY|BUY|HOLD|SELL|STRONG SELL|NO ACTION>",
    "risk_level": "<LOW|MODERATE|HIGH>",
    "thesis": "<2-3 sentence investment thesis>",
    "risk_factors": "<key risks that could invalidate the thesis>",
    "recommended_action": "<specific action to take>",
    "entry_price": <recommended entry price as number>,
    "stop_loss": <stop loss price as number>,
    "take_profit_targets": [<T1>, <T2>, <T3>],
    "position_size_pct": <recommended position size as % of portfolio, 1-10>,
    "time_horizon": "<days|weeks|months>",
    "reasoning": "<detailed reasoning connecting all research dimensions>"
}}

Respond with ONLY the JSON object, no other text.
"""


class ResearchEngine:
    def __init__(
        self,
        config: dict,
        market_data: MarketDataFetcher,
        insider_tracker: InsiderTracker,
        news_feed: NewsFeed,
    ):
        self.config = config
        self.market_data = market_data
        self.insider_tracker = insider_tracker
        self.news_feed = news_feed
        self.reports: dict[str, ResearchReport] = {}

        self.fundamental_analyzer = FundamentalAnalyzer(config)
        self.sentiment_analyzer = SentimentAnalyzer(config)
        self.insider_analyzer = InsiderAnalyzer(config)
        self.competitor_analyzer = CompetitorAnalyzer(config)

        api_key = os.getenv("ANTHROPIC_API_KEY", "")
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else None

        self.reports_dir = Path("data/research_reports")
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    async def analyze_stock(self, ticker: str) -> ResearchReport:
        logger.info("Starting research analysis for %s", ticker)

        quote = await self.market_data.get_quote(ticker)
        financials = await self.market_data.get_financials(ticker)
        technicals = await self.market_data.get_technicals(ticker)
        insider_summary = await self.insider_tracker.get_insider_summary(ticker)
        news_items = await self.news_feed.get_company_news(ticker, days=7)

        fundamental_score = await self.fundamental_analyzer.analyze(financials)
        sentiment_analysis = await self.sentiment_analyzer.analyze(news_items)
        insider_analysis = await self.insider_analyzer.analyze(insider_summary)
        competitive_analysis = await self.competitor_analyzer.analyze(ticker)

        company_name = ""
        try:
            import yfinance as yf
            company_name = yf.Ticker(ticker).info.get("shortName", ticker)
        except Exception:
            company_name = ticker

        technical_summary = (
            f"Price: ${quote.price:.2f} | SMA50: ${technicals.sma_50:.2f} | "
            f"SMA200: ${technicals.sma_200:.2f} | RSI: {technicals.rsi:.1f} | "
            f"Support: ${technicals.support_level:.2f} | "
            f"Resistance: ${technicals.resistance_level:.2f} | "
            f"Avg Volume 30d: {technicals.avg_volume_30d:,}"
        )

        if self.client:
            report = await self._claude_analysis(
                ticker, company_name, quote.price,
                fundamental_score.summary,
                insider_analysis.summary,
                sentiment_analysis.summary,
                competitive_analysis.summary,
                technical_summary,
            )
        else:
            logger.warning("No ANTHROPIC_API_KEY — generating rule-based report for %s", ticker)
            report = self._rule_based_analysis(
                ticker, company_name, quote.price,
                fundamental_score, insider_analysis, sentiment_analysis,
                competitive_analysis, technicals,
            )

        self.reports[ticker] = report
        self._save_report(report)
        logger.info("Research complete for %s — Signal: %s, Conviction: %d/10",
                     ticker, report.signal.value, report.conviction_score)
        return report

    async def _claude_analysis(
        self, ticker: str, company_name: str, current_price: float,
        fundamental_summary: str, insider_summary: str,
        news_summary: str, competitive_summary: str, technical_summary: str,
    ) -> ResearchReport:
        prompt = ANALYSIS_PROMPT.format(
            ticker=ticker,
            company_name=company_name,
            current_price=current_price,
            fundamental_summary=fundamental_summary,
            insider_summary=insider_summary,
            news_summary=news_summary,
            competitive_summary=competitive_summary,
            technical_summary=technical_summary,
        )

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

            data = json.loads(response_text)

            return ResearchReport(
                ticker=ticker,
                company_name=company_name,
                generated_at=datetime.now(),
                conviction_score=int(data.get("conviction_score", 0)),
                signal=Signal(data.get("signal", "NO ACTION")),
                risk_level=RiskLevel(data.get("risk_level", "HIGH")),
                thesis=data.get("thesis", ""),
                fundamental_summary=fundamental_summary,
                insider_summary=insider_summary,
                news_summary=news_summary,
                competitive_summary=competitive_summary,
                risk_factors=data.get("risk_factors", ""),
                recommended_action=data.get("recommended_action", ""),
                entry_price=float(data.get("entry_price") or current_price),
                position_size_pct=float(data.get("position_size_pct") or 3),
                stop_loss=float(data.get("stop_loss") or current_price * 0.95),
                take_profit_targets=[float(t) for t in (data.get("take_profit_targets") or []) if t is not None],
                time_horizon=data.get("time_horizon", ""),
                reasoning=data.get("reasoning", ""),
            )
        except Exception as e:
            logger.error("Claude analysis failed for %s: %s", ticker, e)
            return ResearchReport(
                ticker=ticker,
                company_name=company_name,
                generated_at=datetime.now(),
                conviction_score=0,
                signal=Signal.NO_ACTION,
                risk_level=RiskLevel.HIGH,
                thesis=f"Analysis failed: {e}",
                fundamental_summary=fundamental_summary,
                insider_summary=insider_summary,
                news_summary=news_summary,
                competitive_summary=competitive_summary,
                risk_factors="Analysis could not be completed",
                recommended_action="NO ACTION — analysis error",
                entry_price=current_price,
                position_size_pct=0,
                stop_loss=current_price * 0.95,
            )

    async def deep_dive_analysis(self, ticker: str) -> DeepDiveReport:
        report = self.reports.get(ticker)
        if not report:
            raise ValueError(f"No scan report for {ticker} — run analyze_stock first")

        logger.info("Starting deep-dive for %s", ticker)

        if not self.client:
            logger.warning("No ANTHROPIC_API_KEY — rule-based deep dive for %s", ticker)
            return self._rule_based_deep_dive(ticker, report)

        prompt = DEEP_DIVE_PROMPT.format(
            ticker=report.ticker,
            company_name=report.company_name,
            current_price=report.entry_price,
            signal=report.signal.value,
            conviction=report.conviction_score,
            fundamental_summary=report.fundamental_summary,
            insider_summary=report.insider_summary,
            news_summary=report.news_summary,
            competitive_summary=report.competitive_summary,
            technical_summary=f"Entry: ${report.entry_price:.2f} | Stop: ${report.stop_loss:.2f}",
        )

        try:
            message = self.client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=3000,
                messages=[{"role": "user", "content": prompt}],
            )

            response_text = message.content[0].text.strip()
            if response_text.startswith("```"):
                response_text = response_text.split("\n", 1)[1]
                if response_text.endswith("```"):
                    response_text = response_text[:-3]

            data = json.loads(response_text)

            dd = DeepDiveReport(
                ticker=ticker,
                company_name=report.company_name,
                generated_at=datetime.now(),
                valuation_analysis=data.get("valuation_analysis", ""),
                fair_value_estimate=float(data.get("fair_value_estimate", report.entry_price)),
                margin_of_safety_pct=float(data.get("margin_of_safety_pct", 0)),
                catalysts=data.get("catalysts", []),
                risk_scenarios=data.get("risk_scenarios", []),
                entry_zone_low=float(data.get("entry_zone_low", report.stop_loss)),
                entry_zone_high=float(data.get("entry_zone_high", report.entry_price)),
                monitoring_checklist=data.get("monitoring_checklist", []),
                enhanced_reasoning=data.get("enhanced_reasoning", ""),
            )

            self._save_deep_dive(dd)
            logger.info("Deep dive complete for %s — Fair value $%.2f, Margin %.0f%%",
                        ticker, dd.fair_value_estimate, dd.margin_of_safety_pct)
            return dd

        except Exception as e:
            logger.error("Deep dive failed for %s: %s", ticker, e)
            return self._rule_based_deep_dive(ticker, report)

    def _rule_based_deep_dive(self, ticker: str, report: ResearchReport) -> DeepDiveReport:
        price = report.entry_price
        return DeepDiveReport(
            ticker=ticker,
            company_name=report.company_name,
            generated_at=datetime.now(),
            valuation_analysis=f"Rule-based estimate for {ticker}.",
            fair_value_estimate=round(price * 1.15, 2),
            margin_of_safety_pct=13.0,
            catalysts=[{"event": "Earnings report", "timeframe": "Next quarter", "impact": "Moderate"}],
            risk_scenarios=[
                {"scenario": "Bull", "probability_pct": 25, "price_target": round(price * 1.35, 2),
                 "description": "Strong earnings beat and guidance raise"},
                {"scenario": "Base", "probability_pct": 50, "price_target": round(price * 1.10, 2),
                 "description": "In-line results, gradual appreciation"},
                {"scenario": "Bear", "probability_pct": 25, "price_target": round(price * 0.85, 2),
                 "description": "Earnings miss or macro headwinds"},
            ],
            entry_zone_low=round(price * 0.97, 2),
            entry_zone_high=round(price * 1.02, 2),
            monitoring_checklist=["Quarterly earnings", "Insider activity changes", "Sector rotation signals"],
            enhanced_reasoning=report.reasoning or report.thesis,
        )

    def _save_deep_dive(self, report: DeepDiveReport):
        filename = f"{report.ticker}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}_deepdive.json"
        filepath = self.reports_dir / filename
        data = {
            "ticker": report.ticker,
            "company_name": report.company_name,
            "generated_at": report.generated_at.isoformat(),
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
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)

    def _rule_based_analysis(
        self, ticker, company_name, price,
        fundamental, insider, sentiment, competitive, technicals,
    ) -> ResearchReport:
        score = 5

        if fundamental.overall_score >= 7:
            score += 1
        elif fundamental.overall_score <= 3:
            score -= 1

        if insider.signal_strength >= 0.5:
            score += 1
        elif insider.signal_strength <= -0.5:
            score -= 1

        if sentiment.overall_sentiment >= 0.3:
            score += 1
        elif sentiment.overall_sentiment <= -0.3:
            score -= 1

        if competitive.moat_score >= 7:
            score += 1
        elif competitive.moat_score <= 3:
            score -= 1

        if technicals.rsi < 30:
            score += 1
        elif technicals.rsi > 70:
            score -= 1

        score = max(1, min(10, score))

        if score >= 8:
            signal = Signal.STRONG_BUY
        elif score >= 7:
            signal = Signal.BUY
        elif score >= 5:
            signal = Signal.HOLD
        elif score >= 3:
            signal = Signal.SELL
        else:
            signal = Signal.STRONG_SELL

        stop_loss = round(price * 0.95, 2)
        t1 = round(price * 1.15, 2)
        t2 = round(price * 1.25, 2)
        t3 = round(price * 1.40, 2)

        return ResearchReport(
            ticker=ticker,
            company_name=company_name,
            generated_at=datetime.now(),
            conviction_score=score,
            signal=signal,
            risk_level=RiskLevel.MODERATE,
            thesis=f"Rule-based analysis for {ticker} yields a {score}/10 conviction score.",
            fundamental_summary=fundamental.summary,
            insider_summary=insider.summary,
            news_summary=sentiment.summary,
            competitive_summary=competitive.summary,
            risk_factors="Rule-based analysis — recommend manual review.",
            recommended_action=signal.value,
            entry_price=price,
            position_size_pct=3.0,
            stop_loss=stop_loss,
            take_profit_targets=[t1, t2, t3],
            time_horizon="weeks",
            reasoning=(
                f"Fundamental score: {fundamental.overall_score:.1f}/10. "
                f"Insider signal: {insider.signal_strength:.2f}. "
                f"Sentiment: {sentiment.overall_sentiment:.2f}. "
                f"Moat: {competitive.moat_score:.1f}/10. "
                f"RSI: {technicals.rsi:.1f}."
            ),
        )

    async def run_watchlist_scan(self) -> list[ResearchReport]:
        watchlist = load_watchlist()
        reports = []
        for stock in watchlist:
            try:
                report = await self.analyze_stock(stock["ticker"])
                reports.append(report)
            except Exception as e:
                logger.error("Failed to analyze %s: %s", stock["ticker"], e)
        return reports

    async def run_broad_scan(self) -> list[ResearchReport]:
        return await self.run_watchlist_scan()

    def get_latest_report(self, ticker: str) -> ResearchReport | None:
        return self.reports.get(ticker)

    def _save_report(self, report: ResearchReport):
        filename = f"{report.ticker}_{report.generated_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = self.reports_dir / filename
        data = {
            "ticker": report.ticker,
            "company_name": report.company_name,
            "generated_at": report.generated_at.isoformat(),
            "conviction_score": report.conviction_score,
            "signal": report.signal.value,
            "risk_level": report.risk_level.value,
            "thesis": report.thesis,
            "fundamental_summary": report.fundamental_summary,
            "insider_summary": report.insider_summary,
            "news_summary": report.news_summary,
            "competitive_summary": report.competitive_summary,
            "risk_factors": report.risk_factors,
            "recommended_action": report.recommended_action,
            "entry_price": report.entry_price,
            "position_size_pct": report.position_size_pct,
            "stop_loss": report.stop_loss,
            "take_profit_targets": report.take_profit_targets,
            "time_horizon": report.time_horizon,
            "reasoning": report.reasoning,
        }
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
