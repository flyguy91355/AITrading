"""News aggregation and filtering via Finnhub and NewsAPI."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum

import httpx

logger = logging.getLogger(__name__)


class SentimentScore(Enum):
    VERY_NEGATIVE = -2
    NEGATIVE = -1
    NEUTRAL = 0
    POSITIVE = 1
    VERY_POSITIVE = 2


@dataclass
class NewsItem:
    ticker: str
    headline: str
    summary: str
    source: str
    url: str
    published: datetime
    sentiment: SentimentScore = SentimentScore.NEUTRAL
    relevance_score: float = 0.0
    category: str = ""


class NewsFeed:
    def __init__(self, config: dict):
        self.config = config
        self.finnhub_key = os.getenv("FINNHUB_API_KEY", "")
        self.newsapi_key = os.getenv("NEWSAPI_API_KEY", "")

    async def get_company_news(self, ticker: str, days: int = 7) -> list[NewsItem]:
        items = []

        if self.finnhub_key:
            items.extend(await self._finnhub_company_news(ticker, days))

        if self.newsapi_key and len(items) < 5:
            items.extend(await self._newsapi_search(ticker, days))

        items.sort(key=lambda n: n.published, reverse=True)
        return items

    async def get_market_news(self, limit: int = 50) -> list[NewsItem]:
        items = []

        if self.finnhub_key:
            items.extend(await self._finnhub_market_news(limit))

        if self.newsapi_key and len(items) < limit // 2:
            items.extend(await self._newsapi_search("stock market", days=3))

        items.sort(key=lambda n: n.published, reverse=True)
        return items[:limit]

    async def get_sector_news(self, sector: str, days: int = 7) -> list[NewsItem]:
        if self.newsapi_key:
            return await self._newsapi_search(f"{sector} stocks", days)
        if self.finnhub_key:
            return await self._finnhub_market_news(20)
        return []

    async def _finnhub_company_news(self, ticker: str, days: int) -> list[NewsItem]:
        to_date = datetime.now().strftime("%Y-%m-%d")
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://finnhub.io/api/v1/company-news",
                    params={
                        "symbol": ticker,
                        "from": from_date,
                        "to": to_date,
                        "token": self.finnhub_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Finnhub news failed for %s: %s", ticker, e)
            return []

        items = []
        for article in data[:30]:
            try:
                published = datetime.fromtimestamp(article.get("datetime", 0))
            except (ValueError, TypeError, OSError):
                published = datetime.now()

            items.append(NewsItem(
                ticker=ticker,
                headline=article.get("headline", ""),
                summary=article.get("summary", ""),
                source=article.get("source", ""),
                url=article.get("url", ""),
                published=published,
                category=article.get("category", ""),
            ))
        return items

    async def _finnhub_market_news(self, limit: int) -> list[NewsItem]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://finnhub.io/api/v1/news",
                    params={"category": "general", "token": self.finnhub_key},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("Finnhub market news failed: %s", e)
            return []

        items = []
        for article in data[:limit]:
            try:
                published = datetime.fromtimestamp(article.get("datetime", 0))
            except (ValueError, TypeError, OSError):
                published = datetime.now()

            items.append(NewsItem(
                ticker="MARKET",
                headline=article.get("headline", ""),
                summary=article.get("summary", ""),
                source=article.get("source", ""),
                url=article.get("url", ""),
                published=published,
                category=article.get("category", ""),
            ))
        return items

    async def _newsapi_search(self, query: str, days: int = 7) -> list[NewsItem]:
        from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": query,
                        "from": from_date,
                        "sortBy": "relevancy",
                        "language": "en",
                        "pageSize": 20,
                        "apiKey": self.newsapi_key,
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            logger.warning("NewsAPI search failed for '%s': %s", query, e)
            return []

        items = []
        for article in data.get("articles", []):
            try:
                published = datetime.fromisoformat(article["publishedAt"].replace("Z", "+00:00")).replace(tzinfo=None)
            except (ValueError, TypeError, KeyError):
                published = datetime.now()

            ticker = query.upper() if len(query) <= 5 and query.isalpha() else "MARKET"

            items.append(NewsItem(
                ticker=ticker,
                headline=article.get("title", ""),
                summary=article.get("description", "") or "",
                source=article.get("source", {}).get("name", ""),
                url=article.get("url", ""),
                published=published,
            ))
        return items
