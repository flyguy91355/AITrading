"""SEC EDGAR filing retrieval via the EDGAR full-text search API."""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = os.getenv("SEC_USER_AGENT", "AITrading ResearchBot admin@example.com")

TICKER_TO_CIK: dict[str, str] = {}


class FilingType(Enum):
    FORM_10K = "10-K"
    FORM_10Q = "10-Q"
    FORM_8K = "8-K"
    FORM_4 = "4"
    PROXY = "DEF 14A"


@dataclass
class SECFiling:
    ticker: str
    filing_type: FilingType
    filed_date: datetime
    period_of_report: datetime | None
    url: str
    description: str = ""


class SECFilingFetcher:
    def __init__(self, config: dict):
        self.config = config

    async def _get_cik(self, ticker: str) -> str | None:
        if ticker in TICKER_TO_CIK:
            return TICKER_TO_CIK[ticker]

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index?q=%22{}%22&dateRange=custom&startdt=2020-01-01&forms=10-K".format(ticker),
                    headers={"User-Agent": USER_AGENT},
                )
                resp.raise_for_status()

                resp2 = await client.get(
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company=&CIK={ticker}&type=&dateb=&owner=include&count=1&search_text=&action=getcompany&output=atom",
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                )
                text = resp2.text
                cik_start = text.find("<cik>")
                cik_end = text.find("</cik>")
                if cik_start != -1 and cik_end != -1:
                    cik = text[cik_start + 5:cik_end].strip().zfill(10)
                    TICKER_TO_CIK[ticker] = cik
                    return cik
        except Exception as e:
            logger.warning("CIK lookup failed for %s: %s", ticker, e)

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={"q": f'"{ticker}"', "forms": "10-K", "dateRange": "custom", "startdt": "2023-01-01"},
                    headers={"User-Agent": USER_AGENT},
                )
        except Exception:
            pass

        return None

    async def get_recent_filings(
        self, ticker: str, filing_type: FilingType | None = None, limit: int = 10
    ) -> list[SECFiling]:
        forms = filing_type.value if filing_type else "10-K,10-Q,8-K,4,DEF 14A"

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={
                        "q": f'"{ticker}"',
                        "forms": forms,
                        "dateRange": "custom",
                        "startdt": "2023-01-01",
                    },
                    headers={"User-Agent": USER_AGENT},
                    timeout=15,
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return await self._fallback_filings(ticker, forms, limit)

        filings = []
        for hit in data.get("hits", {}).get("hits", [])[:limit]:
            source = hit.get("_source", {})
            try:
                filed = datetime.strptime(source.get("file_date", ""), "%Y-%m-%d")
            except (ValueError, TypeError):
                filed = datetime.now()

            form = source.get("form_type", "")
            try:
                ft = FilingType(form)
            except ValueError:
                continue

            period = None
            if source.get("period_of_report"):
                try:
                    period = datetime.strptime(source["period_of_report"], "%Y-%m-%d")
                except (ValueError, TypeError):
                    pass

            url = f"https://www.sec.gov/Archives/edgar/data/{source.get('entity_id', '')}/{source.get('file_num', '')}"

            filings.append(SECFiling(
                ticker=ticker,
                filing_type=ft,
                filed_date=filed,
                period_of_report=period,
                url=url,
                description=source.get("display_names", [""])[0] if source.get("display_names") else "",
            ))

        return filings

    async def _fallback_filings(self, ticker: str, forms: str, limit: int) -> list[SECFiling]:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={"q": ticker, "forms": forms},
                    headers={"User-Agent": USER_AGENT},
                    timeout=15,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    filings = []
                    for hit in data.get("hits", {}).get("hits", [])[:limit]:
                        source = hit.get("_source", {})
                        try:
                            filed = datetime.strptime(source.get("file_date", ""), "%Y-%m-%d")
                        except (ValueError, TypeError):
                            filed = datetime.now()
                        form = source.get("form_type", "")
                        try:
                            ft = FilingType(form)
                        except ValueError:
                            continue
                        filings.append(SECFiling(
                            ticker=ticker,
                            filing_type=ft,
                            filed_date=filed,
                            period_of_report=None,
                            url=f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={ticker}&type={form}",
                            description=form,
                        ))
                    return filings
        except Exception as e:
            logger.warning("SEC EDGAR fallback also failed for %s: %s", ticker, e)
        return []

    async def get_filing_content(self, filing: SECFiling) -> str:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    filing.url,
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=True,
                    timeout=30,
                )
                resp.raise_for_status()
                text = resp.text
                if len(text) > 50000:
                    text = text[:50000] + "\n... [truncated]"
                return text
        except Exception as e:
            logger.warning("Failed to fetch filing content from %s: %s", filing.url, e)
            return ""
