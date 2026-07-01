"""Stock universe for watchlist replacement scanning.

Dynamically fetches S&P 500 + S&P 400 MidCap (~900 stocks) from Wikipedia,
cached for 24 hours. Falls back to the hardcoded list if the fetch fails.
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_PATH = Path("data/universe_cache.json")
_CACHE_TTL_HOURS = 24


def get_universe() -> list[str]:
    """Return the full stock universe, refreshing from Wikipedia if cache is stale."""
    if _CACHE_PATH.exists():
        try:
            data = json.loads(_CACHE_PATH.read_text())
            cached_at = datetime.fromisoformat(data["cached_at"])
            if datetime.now() - cached_at < timedelta(hours=_CACHE_TTL_HOURS):
                return data["tickers"]
        except Exception:
            pass

    try:
        import pandas as pd
        tickers: set[str] = set()

        # S&P 500
        tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            attrs={"id": "constituents"},
        )
        col = "Symbol" if "Symbol" in tables[0].columns else tables[0].columns[0]
        tickers.update(tables[0][col].str.replace(".", "-", regex=False).tolist())
        logger.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))

        # S&P 400 MidCap
        sp400_tables = pd.read_html(
            "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies"
        )
        for t in sp400_tables:
            for candidate_col in ("Ticker symbol", "Symbol", "Ticker"):
                if candidate_col in t.columns:
                    sp400 = t[candidate_col].dropna().str.replace(".", "-", regex=False).tolist()
                    tickers.update(sp400)
                    logger.info("Fetched %d S&P 400 tickers from Wikipedia", len(sp400))
                    break

        result = sorted(tickers)
        _CACHE_PATH.parent.mkdir(exist_ok=True)
        _CACHE_PATH.write_text(json.dumps({
            "cached_at": datetime.now().isoformat(),
            "tickers": result,
        }))
        logger.info("Universe cached: %d stocks (S&P 500 + S&P 400)", len(result))
        return result

    except Exception as e:
        logger.warning("Universe fetch failed (%s) — using hardcoded fallback (%d stocks)",
                       e, len(STOCK_UNIVERSE))
        return STOCK_UNIVERSE


# ── Hardcoded fallback (~457 stocks) ──────────────────────────────────────────
# Used when Wikipedia fetch fails. Covers S&P 500 large-caps across all sectors.
STOCK_UNIVERSE = [
    # Mega-cap / current watchlist
    "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "BRK-B",
    "LLY", "AVGO", "JPM", "V", "UNH", "MA", "XOM", "COST", "HD",
    "PG", "JNJ", "ABBV", "CRM", "NFLX", "AMD", "BAC", "KO", "MRK",
    "PEP", "TMO", "ORCL", "ACN", "LIN", "WMT", "CSCO", "MCD", "ABT",
    "DIS", "ADBE", "DHR", "WFC", "INTC", "QCOM", "INTU", "TXN", "PM",
    "NOW", "IBM", "GE", "CAT", "AMAT", "GS",
    # Technology
    "LRCX", "MU", "KLAC", "SNPS", "CDNS", "ANSS", "FTNT", "PANW",
    "CRWD", "ZS", "OKTA", "DDOG", "SNOW", "PLTR", "UBER", "LYFT",
    "TTD", "SHOP", "SQ", "PYPL", "TWLO", "ZM", "DOCU", "WORK",
    "NET", "CFLT", "MDB", "ESTC", "GTLB", "HUBS", "BILL", "COUP",
    "MSCI", "SPGI", "ICE", "CME", "CBOE", "MCO", "FIS", "FISV",
    "GPN", "WEX", "JKHY", "BR", "SSNC",
    # Healthcare
    "BMY", "AMGN", "GILD", "BIIB", "REGN", "VRTX", "ILMN", "IQV",
    "ZBH", "SYK", "BSX", "MDT", "BDX", "EW", "ISRG", "ALGN",
    "DXCM", "IDXX", "PODD", "NVAX", "MRNA", "BNTX", "PFE", "CVS",
    "CI", "HUM", "ELV", "MOH", "CNC", "HCA", "THC", "UHS", "LPLA",
    "MCK", "CAH", "ABC", "PRGO", "ENDP", "PKI", "A", "RMD",
    # Financials
    "MS", "C", "USB", "PNC", "TFC", "COF", "AXP", "DFS", "SYF",
    "ALLY", "CMA", "FITB", "HBAN", "RF", "KEY", "CFG", "MTB",
    "ZION", "BOKF", "FHN", "SNV", "PBCT", "TCF", "WAL", "EWBC",
    "BK", "STT", "NTRS", "IVZ", "BEN", "AMG", "TROW", "VRTS",
    "PFG", "LNC", "AFL", "MET", "PRU", "AIG", "ALL", "TRV",
    "CB", "HIG", "WR", "MKL", "RLI", "CINF",
    # Consumer Discretionary
    "NKE", "SBUX", "LOW", "TJX", "ROST", "BURL", "GPS", "ANF",
    "AEO", "URBN", "LULU", "RH", "WSM", "BBY", "BBWI", "ETSY",
    "EBAY", "W", "CHWY", "CVNA", "KMX", "AZO", "ORLY",
    "AAP", "GPC", "GM", "F", "STLA", "TM", "HMC", "RIVN",
    "LCID", "NKLA", "BLNK", "MAR", "HLT", "H", "WH", "IHG",
    "CCL", "RCL", "NCLH", "LVS", "MGM", "WYNN", "CZR",
    # Consumer Staples
    "MO", "BTI", "MDLZ", "HSY", "GIS", "K", "CPB", "SJM",
    "CAG", "MKC", "HRL", "TSN", "KHC", "POST", "LANC", "BGS",
    "CLX", "CHD", "CL", "EL", "AVP", "COTY", "REV",
    "SFM", "KR", "ACI", "SYY", "PFGC", "USFD",
    # Energy
    "CVX", "COP", "EOG", "SLB", "HAL", "BKR", "OXY", "DVN",
    "FANG", "MPC", "VLO", "PSX", "PBF", "DK", "WMB",
    "KMI", "OKE", "EPD", "ET", "MPLX", "PAA", "TRGP", "AM",
    "AR", "EQT", "RRC", "CNX", "SWN",
    # Industrials
    "HON", "MMM", "RTX", "LMT", "NOC", "GD", "BA", "LHX",
    "TDG", "HEI", "TXT", "DRS", "KTOS", "AVAV",
    "UPS", "FDX", "CHRW", "EXPD", "XPO", "ODFL", "SAIA",
    "JBHT", "WERN", "KNX", "URI",
    "PWR", "PRIM", "MTZ", "EME", "MYR", "J", "EXPO",
    "PH", "EMR", "ITW", "DOV", "AME", "GWW", "MSM",
    "ROP", "XYL", "MIDD",
    # Materials
    "FCX", "NEM", "GOLD", "AEM", "KGC", "AG", "HL", "CDE",
    "AA", "CENX", "ATI", "MP",
    "DD", "DOW", "LYB", "WLK", "OLN", "RPM",
    "SHW", "PPG", "AXTA",
    "NUE", "STLD", "CLF", "X", "CMC", "RS",
    # Utilities
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "PCG",
    "PEG", "EIX", "XEL", "WEC", "DTE", "ETR", "FE", "CNP",
    "AES", "NI", "EVRG", "AWK",
    # Real Estate
    "AMT", "PLD", "CCI", "EQIX", "PSA", "EQR", "AVB", "ESS",
    "MAA", "UDR", "CPT", "NNN", "O", "WPC", "SPG",
    "SLG", "BXP", "KIM", "REG", "FRT",
    "DRE", "FR", "EGP", "REXR", "TRNO", "COLD",
    # Communication Services
    "T", "VZ", "TMUS", "CHTR", "CMCSA", "DISH", "LUMN",
    "OMC", "IPG",
    "EA", "TTWO", "ATVI", "RBLX", "U", "MTCH", "BMBL",
    "SNAP", "PINS", "SPOT", "YELP", "IAC",
]
