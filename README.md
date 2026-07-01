# AITrading

AI-Powered Stock Research & Autonomous Trading System that uses Claude AI to analyze stocks, generate trade signals, and execute trades automatically through Alpaca's brokerage API.

## What It Does

AITrading maintains a **dynamic watchlist of 50 stocks**, scans them at strategic times during market hours, runs each through a multi-dimensional research pipeline, and autonomously buys/sells based on high-conviction signals. The watchlist is self-managing — it starts empty, begins filling at market open, and continuously replaces underperformers with better candidates from the S&P 500 universe throughout the day.

It's designed around one principle: **never lose money** — every trade requires strong conviction, favorable risk/reward, and mandatory stop losses.

---

## The Research Pipeline

For each stock, the system gathers and analyzes:

1. **Fundamentals** — P/E ratio, net margin, ROE, debt-to-equity via Yahoo Finance and Alpha Vantage
2. **Technicals** — SMA50/200, RSI, support/resistance levels, volume analysis
3. **Insider Activity** — SEC Form 4 filings over 90 days, cluster buying detection
4. **News & Sentiment** — 7-day news aggregation with positive/negative sentiment scoring
5. **Competitive Moat** — Industry position and competitive advantage assessment

All five dimensions feed into **Claude AI** (Haiku 4.5), which synthesizes them into a structured recommendation: conviction score (1–10), signal (STRONG BUY through STRONG SELL), entry price, stop loss, and three take-profit targets.

---

## Trade Execution Rules

- Minimum conviction score: **7/10** to trigger a buy
- Minimum risk/reward ratio: **2.1:1** (measured against T3, the full upside target)
- Maximum **2%** portfolio risk per trade
- Maximum **7%** of portfolio in any single position
- **10%** minimum cash reserve (raised to 30% once positions rebalance to 7% sizing)
- Maximum **10 positions** open simultaneously
- Maximum **3 positions** per sector
- **Stop losses are mandatory** on every position
- Trailing stops activate automatically at +5% P&L
- **Notional (dollar-based) orders** used for all buys — ensures fractional shares and exact position sizing

### Take-Profit Strategy (Staged Exits)

Each position has three GTC limit orders placed in the broker at buy time. The system sells in thirds as each target is hit:

| Stage | Target | Action |
|-------|--------|--------|
| T1 | ~+4–6% | Sell ⅓ of position |
| T2 | ~+8–12% | Sell ⅓ of position |
| T3 | ~+15–20% | Sell final ⅓ |

Orders are placed **sequentially** to comply with Alpaca's position-size constraint:
- At buy: stop covers ⅔ of shares + TP1 covers ⅓ = 100%
- After TP1 fills: stop updated to cover ⅓ + TP2 placed for ⅓
- After TP2 fills: stop cancelled + TP3 placed for final ⅓

---

## Scan Schedule

The system runs **3 full scans per day** at strategic times (all Eastern):

| Scan | Time | Purpose |
|------|------|---------|
| Morning | 9:45 AM | Post-open — opening volatility settles, first signals |
| Midday | 12:30 PM | Catch morning reactions and lunch-break reversals |
| Pre-close | 3:30 PM | End-of-day signals, set up overnight thesis |

---

## Dynamic Watchlist

The 50-stock watchlist is **self-managing** — it starts empty and stays populated with high-quality BUY candidates organically through scanning.

### How It Works

- The watchlist is stored in a SQLite database and tracks each stock's recent signal history
- After every scan, each stock's signal (BUY, HOLD, SELL, etc.) is recorded
- **2 consecutive HOLD or SELL signals** marks a stock as an underperformer

### Filling Open Slots

- At market open, a fill scan immediately begins scanning the S&P 500 universe for BUY/STRONG BUY stocks (conviction ≥ 7) to populate any open slots
- The same fill scan runs after each of the 3 daily scans as well
- A **two-pass quick screen** filters stocks in ~2 seconds before committing to a full 25-second Claude analysis:
  - Rejects downtrends (price below 50-day MA), extreme RSI, weak momentum, and low volume
  - Only candidates that pass go to full Claude analysis — roughly 4–5x faster than scanning every stock

### When a Stock Gets Bought

- It's **immediately removed from the watchlist** — held positions are already monitored hourly, so the slot is freed for a new candidate
- The system scans for one replacement from the universe right away
- Held positions are also excluded from universe scan candidates — the system never re-adds a stock you already own

### Universe Scan Cursor

The scan cycles through the full S&P 500 before repeating — a persistent cursor in the database ensures every stock gets evaluated before the list wraps around. The cursor is saved after each stock so market-close interruptions resume exactly where they left off.

---

## Position Monitoring

Held stocks get continuous attention separate from the watchlist:

- **Every 60 minutes** — Full re-analysis of all held positions with fresh data
- **Every 30 seconds** — Price updates, stop-loss checks, trailing stop adjustments
- **Automatic sells** when conviction drops to 4/10 or below
- **Portfolio rotation** — weakest holdings are swapped for stronger candidates when portfolio is full
- **Same-day protection** — positions bought today are never rotated out; must hold at least one full day

---

## Risk Management

- **Daily loss limit**: Trading halts if portfolio drops 2% in a day
- **Drawdown protection**: Defensive mode at 5%, halt at 10%, full exit review at 15%
- **Max positions enforced in real time**: Pending (unfilled) orders count against the limit immediately, preventing over-allocation during after-hours order queuing
- **Cash reserve check**: Accounts for all pending orders in the same scan cycle before placing the next one
- **Staged take-profits**: Sells ⅓ of position at each of three profit targets via real Alpaca GTC limit orders
- **Hardware stop losses**: Alpaca stop orders protect the broker side — if the server goes down, stops still fire
- **Trailing stops**: Automatically ratchet upward as positions gain

---

## Architecture

```
src/
  data/
    market_data.py       Real-time quotes, financials, technicals (Yahoo Finance, Alpha Vantage)
    insider_tracker.py   SEC Form 4 insider transaction tracking (Finnhub)
    news_feed.py         News aggregation (NewsAPI, Finnhub)
    stock_universe.py    S&P 500 universe used for watchlist replacement scanning

  research/
    engine.py            Claude AI synthesis — produces conviction scores and trade signals
    fundamental.py       Fundamental scoring
    sentiment.py         News sentiment analysis
    insider_analysis.py  Insider activity scoring
    competitor.py        Competitive moat assessment
    quick_screen.py      Fast yfinance-only pre-filter — rejects non-candidates in ~2s

  decision/
    signal_generator.py  Converts research reports into actionable trade signals
    risk_manager.py      Enforces all risk rules before any order is placed
    portfolio.py         Tracks positions, cash, P&L, drawdown

  execution/
    alpaca_broker.py     Alpaca API integration (paper + live)
    order_manager.py     Order lifecycle, sequential TP/stop placement, position sync
    robinhood_broker.py  Robinhood (planned)

  reporting/
    trade_logger.py      Trade history to SQLite

  utils/
    config.py            Settings and credential loader
    watchlist_manager.py Dynamic watchlist — DB-backed, tracks signal history, manages evictions and scan cursor

web/
  app.py          FastAPI server — WebSocket real-time dashboard, scan loops, auto-buy logic
  templates/      Dashboard HTML (live activity feed, scan progress, portfolio panel)
  static/         CSS/JS assets

config/
  settings.yaml   All system parameters (scan times, risk limits, thresholds)
  .env            API keys (never committed — copy from credentials.env template)

data/
  aitrading.db    SQLite database (positions, trade history, watchlist, portfolio state, scan cursor)
```

---

## Setup

### Prerequisites

- Python 3.12+
- Alpaca brokerage account (paper or live)
- Anthropic API key (Claude AI)
- API keys: Alpha Vantage, Finnhub, NewsAPI

### Installation

```bash
git clone https://github.com/flyguy91355/AITrading.git
cd AITrading
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Configuration

1. Copy the credentials template:
```bash
cp config/credentials.env .env
```

2. Fill in your API keys in `.env`:
```
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ANTHROPIC_API_KEY=your_anthropic_key
ALPHA_VANTAGE_API_KEY=your_key
FINNHUB_API_KEY=your_key
NEWSAPI_API_KEY=your_key
```

3. Review `config/settings.yaml` for trading parameters.

### Running

```bash
python -m uvicorn web.app:app --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080` to view the live dashboard. The system scans automatically at scheduled times and begins filling the watchlist immediately at market open. Use the **Force Scan** button to run a scan on demand.

### Paper vs Live Trading

The system defaults to **paper trading** mode via Alpaca's paper trading API. To switch to live:

1. Set `paper_trading: false` in `config/settings.yaml`
2. Update `.env` with live Alpaca API keys and `ALPACA_BASE_URL=https://api.alpaca.markets`

---

## Tech Stack

- **AI Engine**: Anthropic Claude Haiku 4.5 — research synthesis, conviction scoring
- **Market Data**: Yahoo Finance, Alpha Vantage, Finnhub
- **News**: NewsAPI, Finnhub
- **SEC Filings**: SEC EDGAR (Form 4 insider transactions)
- **Broker**: Alpaca (paper + live)
- **Dashboard**: FastAPI + WebSocket (real-time updates, live activity feed)
- **Database**: SQLite
- **Language**: Python 3.12, fully async (asyncio)
