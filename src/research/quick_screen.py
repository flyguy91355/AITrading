"""Fast pre-screen for universe candidates — yfinance only, no Claude API call.

Returns in ~2s per stock. Only passes stocks worth a full 25s Claude analysis.
Filters: uptrend (price > 50-day MA), RSI not extreme, positive 1-month momentum,
sufficient liquidity.
"""

import logging
import numpy as np
import yfinance as yf

logger = logging.getLogger(__name__)

_MIN_AVG_VOLUME = 200_000
_RSI_HIGH = 72       # overbought — likely to pull back soon
_RSI_LOW = 28        # oversold/falling hard
_MA50_BUFFER = 0.97  # allow 3% below 50-day MA (near support is fine)
_MOMENTUM_BUFFER = 0.95  # allow 5% below 20-day-ago price


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-period - 1:])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains.mean()
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + avg_gain / avg_loss))


def quick_screen(ticker: str) -> tuple[bool, str]:
    """Return (passes, reason). Synchronous — run in executor from async code."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info

        avg_vol = getattr(info, "three_month_average_volume", 0) or 0
        if avg_vol < _MIN_AVG_VOLUME:
            return False, f"low volume ({avg_vol:,.0f} avg)"

        price = getattr(info, "last_price", None)
        if not price or price <= 0:
            return False, "no price data"

        ma50 = getattr(info, "fifty_day_average", None)
        if ma50 and price < ma50 * _MA50_BUFFER:
            return False, f"downtrend (${price:.2f} < 50-MA ${ma50:.2f})"

        hist = t.history(period="2mo", interval="1d")
        if hist.empty or len(hist) < 15:
            return False, "insufficient history"

        closes = hist["Close"].values
        rsi = _rsi(closes)

        if rsi > _RSI_HIGH:
            return False, f"overbought (RSI {rsi:.0f})"
        if rsi < _RSI_LOW:
            return False, f"oversold (RSI {rsi:.0f})"

        if len(closes) >= 20 and closes[-1] < closes[-20] * _MOMENTUM_BUFFER:
            chg = (closes[-1] / closes[-20] - 1) * 100
            return False, f"weak momentum ({chg:+.1f}% vs 20d ago)"

        return True, f"RSI {rsi:.0f} | vol {avg_vol / 1e6:.1f}M | momentum OK"

    except Exception as e:
        logger.debug("Quick screen error for %s: %s", ticker, e)
        return False, f"data error"
