"""Nightly batch universe screener using Anthropic's Message Batches API.

Flow:
  1. Quick-screen the full universe with yfinance (free, ~2s/stock)
  2. Submit all passing stocks to Anthropic Batch API in one shot (50% cheaper)
  3. Poll until results arrive (typically 15-60 min)
  4. Store BUY/STRONG BUY stocks (conviction >= threshold) in the candidates table
  5. Next morning, slot filling pulls from candidates instead of scanning in real-time
"""

import asyncio
import json
import logging
import time
from datetime import datetime

import anthropic

from src.research.quick_screen import quick_screen
from src.utils.watchlist_manager import WatchlistManager

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECS = 60
_MAX_POLL_SECS = 7200  # 2 hours max wait


def _build_analysis_prompt(ticker: str, price: float, fundamental: str,
                            insider: str, news: str) -> str:
    return f"""You are a senior equity research analyst. Analyze this stock and produce a structured investment recommendation.

IMPORTANT RULES:
- Be conservative. The cardinal rule is NEVER LOSE MONEY.
- Only recommend BUY or STRONG BUY if conviction is 7/10 or higher.
- Every recommendation MUST include a stop loss (typically 5-8% below entry).
- Risk/reward ratio must be at least 3:1.
- If data is insufficient, recommend NO ACTION.

STOCK: {ticker}
CURRENT PRICE: ${price:.2f}

── FUNDAMENTAL DATA ──
{fundamental}

── INSIDER ACTIVITY ──
{insider}

── NEWS ──
{news}

Respond ONLY with this JSON:
{{
    "conviction_score": <1-10>,
    "signal": "<STRONG BUY|BUY|HOLD|SELL|STRONG SELL|NO ACTION>",
    "entry_price": <number>,
    "stop_loss": <number — 5-8% below entry>,
    "take_profit_targets": [<T1 4-6% above entry>, <T2 8-12% above entry>, <T3 15-20% above entry max>],
    "thesis": "<2-3 sentence thesis>"
}}"""


async def _gather_light_data(ticker: str) -> dict | None:
    """Fetch minimal data needed for a batch analysis request."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.fast_info
        price = getattr(info, "last_price", None)
        if not price:
            return None

        hist = t.history(period="3mo", interval="1d")
        if hist.empty:
            return None

        # Basic fundamental summary (fast, no Alpha Vantage call)
        pe = getattr(info, "pe_ratio", "N/A")
        mktcap = getattr(info, "market_cap", 0)
        mktcap_str = f"${mktcap/1e9:.1f}B" if mktcap else "N/A"

        closes = hist["Close"].values
        import numpy as np
        ma50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else price
        rsi_val = _rsi(closes)

        fundamental = (f"Market cap: {mktcap_str} | P/E: {pe} | "
                       f"50-day MA: ${ma50:.2f} | RSI: {rsi_val:.0f}")
        insider = "No recent insider data available (light scan)."
        news = "No recent news available (light scan)."

        return {
            "ticker": ticker,
            "price": price,
            "fundamental": fundamental,
            "insider": insider,
            "news": news,
        }
    except Exception as e:
        logger.debug("Light data fetch failed for %s: %s", ticker, e)
        return None


def _rsi(closes, period=14) -> float:
    import numpy as np
    if len(closes) < period + 1:
        return 50.0
    deltas = np.diff(closes[-period - 1:])
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_loss = losses.mean()
    if avg_loss == 0:
        return 100.0
    return 100 - (100 / (1 + gains.mean() / avg_loss))


async def run_nightly_batch(
    universe: list[str],
    watchlist_manager: WatchlistManager,
    api_key: str,
    min_conviction: int = 7,
    model: str = "claude-haiku-4-5",
) -> str | None:
    """
    Run the full nightly batch screen. Returns the batch_id if submitted,
    None if nothing to screen. Results are processed and stored in candidates table.
    """
    held = set()  # portfolio positions not available here — filtered by watchlist manager
    active = watchlist_manager.get_active_tickers()
    exclude = active | held

    logger.info("Nightly batch screen starting — universe: %d stocks", len(universe))

    # ── Step 1: Quick screen ───────────────────────────────────────────────
    candidates_for_batch: list[str] = []
    screened_out = 0
    for ticker in universe:
        if ticker in exclude:
            continue
        passes, _ = await asyncio.get_event_loop().run_in_executor(
            None, quick_screen, ticker)
        if passes:
            candidates_for_batch.append(ticker)
        else:
            screened_out += 1
        await asyncio.sleep(0.1)  # avoid hammering yfinance

    logger.info("Quick screen done — %d passed, %d rejected",
                len(candidates_for_batch), screened_out)

    if not candidates_for_batch:
        logger.info("No candidates passed quick screen — batch not submitted")
        return None

    # ── Step 2: Gather light data for each candidate ───────────────────────
    batch_requests = []
    for ticker in candidates_for_batch:
        data = await _gather_light_data(ticker)
        if not data:
            continue
        prompt = _build_analysis_prompt(
            ticker, data["price"],
            data["fundamental"], data["insider"], data["news"])
        batch_requests.append({
            "custom_id": ticker,
            "params": {
                "model": model,
                "max_tokens": 512,
                "messages": [{"role": "user", "content": prompt}],
            },
        })
        await asyncio.sleep(0.05)

    if not batch_requests:
        logger.warning("No batch requests built — skipping submission")
        return None

    # ── Step 3: Submit to Anthropic Batch API ──────────────────────────────
    client = anthropic.Anthropic(api_key=api_key)
    logger.info("Submitting %d stocks to Anthropic Batch API...", len(batch_requests))
    try:
        batch = await asyncio.to_thread(
            client.beta.messages.batches.create,
            requests=batch_requests,
        )
        batch_id = batch.id
        logger.info("Batch submitted: %s (%d requests)", batch_id, len(batch_requests))
    except Exception as e:
        logger.error("Batch submission failed: %s", e)
        return None

    # ── Step 4: Poll for results ───────────────────────────────────────────
    start = time.time()
    while time.time() - start < _MAX_POLL_SECS:
        await asyncio.sleep(_POLL_INTERVAL_SECS)
        try:
            status = await asyncio.to_thread(
                client.beta.messages.batches.retrieve, batch_id)
            logger.info("Batch %s status: %s (%d/%d done)",
                        batch_id, status.processing_status,
                        status.request_counts.succeeded,
                        status.request_counts.processing)
            if status.processing_status == "ended":
                break
        except Exception as e:
            logger.warning("Batch poll error: %s", e)

    # ── Step 5: Process results and store candidates ───────────────────────
    watchlist_manager.clear_candidates()
    added = 0
    try:
        results = await asyncio.to_thread(
            client.beta.messages.batches.results, batch_id)
        for result in results:
            if result.result.type != "succeeded":
                continue
            ticker = result.custom_id
            try:
                raw = result.result.message.content[0].text
                data = json.loads(raw)
                signal = data.get("signal", "")
                conviction = int(data.get("conviction_score", 0))
                if signal in ("BUY", "STRONG BUY") and conviction >= min_conviction:
                    targets = [float(t) for t in (data.get("take_profit_targets") or [])
                               if t is not None]
                    watchlist_manager.add_candidate(
                        ticker=ticker,
                        company_name=ticker,
                        signal=signal,
                        conviction=conviction,
                        entry_price=float(data.get("entry_price") or 0),
                        stop_loss=float(data.get("stop_loss") or 0),
                        take_profit_targets=targets,
                        batch_id=batch_id,
                    )
                    added += 1
            except Exception as e:
                logger.debug("Result parse error for %s: %s", ticker, e)
    except Exception as e:
        logger.error("Batch result retrieval failed: %s", e)

    logger.info("Nightly batch complete — %d candidates stored from %d submitted",
                added, len(batch_requests))
    return batch_id
