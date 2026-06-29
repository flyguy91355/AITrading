# AITrading

AI-Powered Stock Research & Autonomous Trading System that uses Claude AI to analyze stocks, generate trade signals, and execute trades automatically through Alpaca's brokerage API.

## What It Does

AITrading scans 50 major stocks at strategic times during market hours, runs each through a multi-dimensional research pipeline, and autonomously buys/sells based on high-conviction signals. It's designed around one principle: **never lose money** — every trade requires strong conviction, favorable risk/reward, and mandatory stop losses.

### The Research Pipeline

For each stock, the system gathers and analyzes:

1. **Fundamentals** — P/E ratio, net margin, ROE, debt-to-equity via Yahoo Finance and Alpha Vantage
2. **Technicals** — SMA50/200, RSI, support/resistance levels, volume analysis
3. **Insider Activity** — SEC Form 4 filings over 90 days, cluster buying detection
4. **News & Sentiment** — 7-day news aggregation with positive/negative sentiment scoring
5. **Competitive Moat** — Industry position and competitive advantage assessment

All five dimensions feed into **Claude AI** (Haiku 4.5), which synthesizes them into a structured recommendation: conviction score (1-10), signal (STRONG BUY through STRONG SELL), entry price, stop loss, and three take-profit targets.

### Trade Execution Rules

- Minimum conviction score: **7/10** to trigger a buy
- Minimum risk/reward ratio: **3:1**
- Maximum **2%** portfolio risk per trade
- Maximum **10%** of portfolio in any single position
- **30%** minimum cash reserve at all times
- Maximum **3 positions** per sector
- **Stop losses are mandatory** on every position
- Trailing stops activate automatically at +5% P&L

### Scan Schedule

The system runs **3 full scans per day** at strategic times (all Eastern):

| Scan | Time | Purpose |
|------|------|---------|
| Morning | 9:45 AM | Post-open — opening volatility settles, first signals |
| Midday | 12:30 PM | Catch morning reactions and lunch-break reversals |
| Pre-close | 3:30 PM | End-of-day signals, set up overnight thesis |

### Position Monitoring

Held stocks get additional attention:

- **Every 60 minutes** — Full re-analysis of all held positions with fresh data
- **Every 30 seconds** — Price updates, stop-loss checks, trailing stop adjustments
- **Automatic sells** when conviction drops to 4/10 or below
- **Portfolio rotation** — weakest holdings are swapped for stronger candidates when portfolio is full

### Risk Management

- **Daily loss limit**: Trading halts if portfolio drops 2% in a day
- **Drawdown protection**: Defensive mode at 5%, halt at 10%, full exit review at 15%
- **Staged take-profits**: Sells 1/3 of position at each of three profit targets
- **Trailing stops**: Automatically ratchet upward as positions gain

## Architecture

```
src/
  data/           Market data, insider tracking, news, SEC filings
  research/       Claude AI research engine, fundamental/sentiment/insider/competitor analysis
  decision/       Signal generation, risk management, portfolio tracking
  execution/      Broker abstraction (Alpaca, Robinhood), order management
  reporting/      Live dashboard, trade logging, alerts
  utils/          Config loader, scheduler

web/
  app.py          FastAPI web dashboard with real-time WebSocket updates
  templates/      Dashboard HTML
  static/         CSS/JS assets

config/
  settings.yaml   System configuration (scan times, risk limits, etc.)
  watchlist.yaml   Stock watchlist
  credentials.env  API key template (never committed)
```

## Setup

### Prerequisites

- Python 3.12+
- Alpaca brokerage account (paper or live)
- Anthropic API key (Claude AI)
- API keys for data sources (Alpha Vantage, Finnhub, NewsAPI)

### Installation

```bash
# Clone the repo
git clone https://github.com/flyguy91355/AITrading.git
cd AITrading

# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. Copy the credentials template and fill in your API keys:
```bash
cp config/credentials.env .env
```

2. Edit `.env` with your keys:
```
ALPACA_API_KEY=your_key
ALPACA_SECRET_KEY=your_secret
ALPACA_BASE_URL=https://paper-api.alpaca.markets
ANTHROPIC_API_KEY=your_anthropic_key
ALPHA_VANTAGE_API_KEY=your_key
FINNHUB_API_KEY=your_key
NEWSAPI_API_KEY=your_key
```

3. Review `config/settings.yaml` for trading parameters (risk limits, scan times, etc.)

### Running

```bash
# Start the web dashboard (recommended)
python start.py

# Or run directly
python web/app.py
```

Open `http://localhost:8080` to view the dashboard. The system will automatically scan at scheduled times during market hours. Use the **Force Scan** button to run a scan outside market hours.

### Paper vs Live Trading

The system defaults to **paper trading** mode. To switch to live trading:

1. Set `paper_trading: false` in `config/settings.yaml`
2. Add live Alpaca API keys to `.env`
3. The system will require you to type `CONFIRM` before starting with real money

## Tech Stack

- **AI Engine**: Anthropic Claude (Haiku 4.5) for research synthesis
- **Market Data**: Yahoo Finance, Alpha Vantage, Finnhub
- **News**: NewsAPI
- **SEC Filings**: SEC EDGAR
- **Broker**: Alpaca (paper + live), Robinhood (planned)
- **Dashboard**: FastAPI + WebSocket for real-time updates
- **Database**: SQLite (aiosqlite)
- **Language**: Python 3.12, fully async
