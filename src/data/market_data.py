"""Stock price and financial data fetching via yfinance with Finnhub fallback."""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime

import httpx
import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass
class StockQuote:
    ticker: str
    price: float
    open: float
    high: float
    low: float
    volume: int
    timestamp: datetime
    change_pct: float = 0.0


@dataclass
class Financials:
    ticker: str
    revenue: float = 0.0
    revenue_growth: float = 0.0
    eps: float = 0.0
    pe_ratio: float = 0.0
    pb_ratio: float = 0.0
    ps_ratio: float = 0.0
    peg_ratio: float = 0.0
    gross_margin: float = 0.0
    operating_margin: float = 0.0
    net_margin: float = 0.0
    free_cash_flow: float = 0.0
    debt_to_equity: float = 0.0
    current_ratio: float = 0.0
    quick_ratio: float = 0.0
    roe: float = 0.0
    roic: float = 0.0
    dividend_yield: float = 0.0
    market_cap: float = 0.0


@dataclass
class TechnicalIndicators:
    ticker: str
    sma_50: float = 0.0
    sma_200: float = 0.0
    rsi: float = 0.0
    avg_volume_30d: int = 0
    support_level: float = 0.0
    resistance_level: float = 0.0


class MarketDataFetcher:
    def __init__(self, config: dict):
        self.config = config
        self.finnhub_key = os.getenv("FINNHUB_API_KEY", "")

    async def get_quote(self, ticker: str) -> StockQuote:
        try:
            stock = yf.Ticker(ticker)
            info = stock.fast_info
            hist = stock.history(period="1d")

            if hist.empty:
                return await self._finnhub_quote(ticker)

            row = hist.iloc[-1]
            prev_close = info.previous_close if hasattr(info, "previous_close") else row["Close"]
            change_pct = ((row["Close"] - prev_close) / prev_close * 100) if prev_close else 0.0

            return StockQuote(
                ticker=ticker,
                price=float(row["Close"]),
                open=float(row["Open"]),
                high=float(row["High"]),
                low=float(row["Low"]),
                volume=int(row["Volume"]),
                timestamp=datetime.now(),
                change_pct=round(change_pct, 2),
            )
        except Exception as e:
            logger.warning("yfinance quote failed for %s: %s, trying Finnhub", ticker, e)
            return await self._finnhub_quote(ticker)

    async def _finnhub_quote(self, ticker: str) -> StockQuote:
        if not self.finnhub_key:
            raise RuntimeError(f"No quote data available for {ticker} — yfinance failed and no Finnhub key set")

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://finnhub.io/api/v1/quote",
                params={"symbol": ticker, "token": self.finnhub_key},
            )
            resp.raise_for_status()
            data = resp.json()

        prev = data.get("pc", 0)
        current = data.get("c", 0)
        change_pct = ((current - prev) / prev * 100) if prev else 0.0

        return StockQuote(
            ticker=ticker,
            price=float(current),
            open=float(data.get("o", 0)),
            high=float(data.get("h", 0)),
            low=float(data.get("l", 0)),
            volume=0,
            timestamp=datetime.now(),
            change_pct=round(change_pct, 2),
        )

    async def get_financials(self, ticker: str) -> Financials:
        stock = yf.Ticker(ticker)
        info = stock.info or {}

        def _g(key: str, default=0.0):
            v = info.get(key)
            return float(v) if v is not None else default

        return Financials(
            ticker=ticker,
            revenue=_g("totalRevenue"),
            revenue_growth=_g("revenueGrowth"),
            eps=_g("trailingEps"),
            pe_ratio=_g("trailingPE"),
            pb_ratio=_g("priceToBook"),
            ps_ratio=_g("priceToSalesTrailing12Months"),
            peg_ratio=_g("pegRatio"),
            gross_margin=_g("grossMargins"),
            operating_margin=_g("operatingMargins"),
            net_margin=_g("profitMargins"),
            free_cash_flow=_g("freeCashflow"),
            debt_to_equity=_g("debtToEquity"),
            current_ratio=_g("currentRatio"),
            quick_ratio=_g("quickRatio"),
            roe=_g("returnOnEquity"),
            roic=_g("returnOnAssets"),
            dividend_yield=_g("dividendYield"),
            market_cap=_g("marketCap"),
        )

    async def get_historical(self, ticker: str, period: str = "1y") -> list[dict]:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        results = []
        for date, row in hist.iterrows():
            results.append({
                "date": date.strftime("%Y-%m-%d"),
                "open": float(row["Open"]),
                "high": float(row["High"]),
                "low": float(row["Low"]),
                "close": float(row["Close"]),
                "volume": int(row["Volume"]),
            })
        return results

    async def get_technicals(self, ticker: str) -> TechnicalIndicators:
        stock = yf.Ticker(ticker)
        hist = stock.history(period="1y")

        if hist.empty:
            return TechnicalIndicators(ticker=ticker)

        closes = hist["Close"]
        volumes = hist["Volume"]

        sma_50 = float(closes.tail(50).mean()) if len(closes) >= 50 else float(closes.mean())
        sma_200 = float(closes.tail(200).mean()) if len(closes) >= 200 else float(closes.mean())

        rsi = self._compute_rsi(closes)

        avg_volume_30d = int(volumes.tail(30).mean()) if len(volumes) >= 30 else int(volumes.mean())

        recent = closes.tail(20)
        support_level = float(recent.min())
        resistance_level = float(recent.max())

        return TechnicalIndicators(
            ticker=ticker,
            sma_50=round(sma_50, 2),
            sma_200=round(sma_200, 2),
            rsi=round(rsi, 2),
            avg_volume_30d=avg_volume_30d,
            support_level=round(support_level, 2),
            resistance_level=round(resistance_level, 2),
        )

    @staticmethod
    def _compute_rsi(closes, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0

        deltas = closes.diff().dropna()
        gains = deltas.where(deltas > 0, 0.0)
        losses = (-deltas).where(deltas < 0, 0.0)

        avg_gain = gains.tail(period).mean()
        avg_loss = losses.tail(period).mean()

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return float(100 - (100 / (1 + rs)))
