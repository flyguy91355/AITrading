# AITrading: AI-Powered Stock Research & Autonomous Trading System

## System Specification & Design Prompt

---

## 1. Vision

AITrading is a locally-hosted, AI-driven stock research and trading system. It continuously researches publicly traded companies using deep fundamental analysis, insider activity tracking, news sentiment analysis, and market data — then generates high-conviction buy, hold, and sell decisions. When a signal triggers, it automatically executes trades through a connected brokerage account, logs the reasoning, and reports every action live.

The system is powered by Claude (via Claude Code / Anthropic API) as the core reasoning engine. It does not rely on simple technical indicators or pattern matching. It performs the kind of thorough, multi-angle research a team of analysts would do — reading filings, tracking insider transactions, monitoring breaking news, evaluating financials — and it does this continuously, around the clock.

**Core Philosophy: Never lose money.** Every trade must be backed by overwhelming research conviction. The system is designed to be patient, selective, and risk-averse. It waits for asymmetric opportunities where the downside is limited and the upside is significant. If the research is not conclusive, the system does not trade.

---

## 2. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        AITrading System                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │   Data       │  │   Research   │  │   Decision Engine     │  │
│  │   Ingestion  │──│   Engine     │──│   (Claude AI)         │  │
│  │   Layer      │  │   (Claude)   │  │                       │  │
│  └──────────────┘  └──────────────┘  └───────────┬───────────┘  │
│                                                  │              │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────▼───────────┐  │
│  │   Risk       │  │   Execution  │  │   Signal Generator    │  │
│  │   Management │──│   Engine     │◄─│   & Reporter          │  │
│  │   Gate       │  │              │  │                       │  │
│  └──────────────┘  └──────────────┘  └───────────────────────┘  │
│                          │                                      │
│                    ┌─────▼──────┐                                │
│                    │  Broker    │                                │
│                    │  API       │                                │
│                    │ Alpaca /   │                                │
│                    │ Robinhood  │                                │
│                    └────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Brokers

The system supports multiple brokers through a common abstraction layer. The active broker is selected in `config/settings.yaml`. Only one broker is active at a time, but switching is a single config change.

### 3.1 Alpaca (Recommended for Development & Paper Trading)

Alpaca is purpose-built for algorithmic trading and is the recommended starting broker:

- **Built-in paper trading**: Toggle between live and paper with a single API URL change — same code, same endpoints, no simulated fills needed
- Commission-free stock trading
- Official, well-documented REST and streaming API (`alpaca-trade-api` Python SDK)
- Supports market, limit, stop, stop-limit, and trailing stop orders natively
- Supports fractional shares
- Real-time market data streaming (IEX free, SIP paid)
- Websocket order status updates
- No minimum account balance for paper trading
- Easy API key provisioning (separate keys for paper vs live)

### 3.2 Robinhood

Robinhood is a secondary broker option for live trading:

- Commission-free stock trading
- API access via `robin_stocks` Python library (unofficial but well-maintained)
- Supports market, limit, stop, and stop-limit orders
- Supports fractional shares (useful for high-priced stocks)
- Real-time order status and portfolio tracking
- Supports options if the system expands later

### 3.3 Binance US (Future — Crypto Module)

Binance US is a cryptocurrency exchange and does not support US equities. It remains available as a future module if the system expands into crypto trading.

### 3.4 Why Alpaca First

Alpaca's native paper trading environment is a major advantage. With Robinhood, paper trading must be simulated locally (fake fills, virtual portfolio). With Alpaca, paper trading goes through the real API with the real order lifecycle — the only difference is no real money moves. This means the exact same code runs in paper and live mode, reducing bugs when transitioning to real trading.

---

## 4. Research Engine — The Core

The Research Engine is the heart of the system. It uses Claude AI to perform deep, multi-dimensional analysis on every stock under consideration. Research is not a one-time scan — it runs continuously, re-evaluating positions and watchlist stocks as new data arrives.

### 4.1 Research Dimensions

#### A. Fundamental Analysis
- Revenue growth trajectory (quarterly and annual)
- Earnings per share (EPS) trend and surprises
- Profit margins (gross, operating, net) and direction
- Free cash flow generation and consistency
- Debt-to-equity ratio and debt servicing ability
- Price-to-earnings (P/E) relative to sector and historical average
- Price-to-book, price-to-sales, PEG ratio
- Return on equity (ROE) and return on invested capital (ROIC)
- Dividend yield and payout sustainability (if applicable)
- Balance sheet strength: cash position, current ratio, quick ratio

#### B. Insider Activity Tracking
- SEC Form 4 filings: officer and director buys and sells
- Cluster buying detection (multiple insiders buying in a short window)
- Insider buy/sell ratio trending
- Size of insider transactions relative to their holdings
- Distinguish routine scheduled sales (10b5-1 plans) from discretionary trades
- Flag unusual insider buying as a strong bullish signal
- Flag heavy insider selling (outside of scheduled plans) as a warning

#### C. News & Sentiment Analysis
- Breaking news monitoring via financial news APIs
- Earnings call transcript analysis (tone, guidance language, confidence)
- SEC filing alerts (10-K, 10-Q, 8-K, proxy statements)
- Social media sentiment scanning (filtered for noise)
- Analyst upgrades/downgrades and price target changes
- Sector-wide news that impacts the stock
- Regulatory or legal developments
- Product launches, partnerships, contract wins

#### D. Competitive Position
- Market share within sector
- Competitive moat assessment (brand, network effects, switching costs, patents)
- Comparison to direct competitors on key metrics
- Industry tailwinds or headwinds
- Management quality and track record

#### E. Technical Context (Supporting Role Only)
- Current price relative to 50-day and 200-day moving averages
- Relative Strength Index (RSI) for overbought/oversold context
- Volume trends (accumulation vs distribution)
- Support and resistance levels for entry/exit timing
- NOTE: Technicals inform timing only — they never drive the buy/sell decision

### 4.2 Research Output Format

For every stock analyzed, the Research Engine produces a structured report:

```
═══════════════════════════════════════════════════════
RESEARCH REPORT: [TICKER] — [COMPANY NAME]
Generated: [TIMESTAMP]
═══════════════════════════════════════════════════════

CONVICTION LEVEL: [1-10] (10 = highest)
SIGNAL: [STRONG BUY | BUY | HOLD | SELL | STRONG SELL | NO ACTION]
RISK LEVEL: [LOW | MODERATE | HIGH]

── THESIS ──
[2-3 sentence summary of why this stock deserves attention]

── FUNDAMENTAL SCORE ──
[Summary of key financial metrics and what they indicate]

── INSIDER ACTIVITY ──
[Recent insider transactions and what they signal]

── NEWS & CATALYSTS ──
[Key recent developments and upcoming catalysts]

── COMPETITIVE POSITION ──
[Where this company stands vs peers]

── RISK FACTORS ──
[What could go wrong — every trade must have this section]

── RECOMMENDED ACTION ──
Action: [BUY / SELL / HOLD / WATCH]
Entry Price: [target entry or current if immediate]
Position Size: [% of portfolio — never exceed risk limits]
Stop Loss: [price level where we exit to protect capital]
Take Profit Targets: [T1, T2, T3 price levels]
Time Horizon: [days / weeks / months]

── REASONING ──
[Detailed explanation of why this action is recommended,
 connecting all research dimensions together]
═══════════════════════════════════════════════════════
```

---

## 5. Decision Engine Rules

### 5.1 The Cardinal Rule: Never Lose Money

This is enforced through multiple mechanisms:

1. **Position Sizing**: No single position exceeds 10% of total portfolio value. Starting positions are smaller (2-5%) and scale up only with confirmed thesis.

2. **Stop Losses Are Mandatory**: Every position has a stop loss set at purchase. The maximum acceptable loss per trade is 2% of total portfolio value.

3. **Conviction Threshold**: A trade is only executed when the research conviction score is 7/10 or higher. Below that, the stock goes on the watchlist.

4. **Asymmetric Risk/Reward**: The potential upside must be at least 3x the potential downside. If the stop loss is 5% below entry, the target must be at least 15% above.

5. **Cash Preservation**: The system always maintains a minimum cash reserve (at least 30% of portfolio) to capitalize on sudden opportunities and avoid forced selling.

6. **Trailing Stops**: Once a position is profitable, the stop loss moves up to lock in gains. Profits are never allowed to turn into losses.

7. **Correlation Check**: The system avoids concentrating in a single sector. If 3 positions are already in tech, a 4th tech stock requires exceptional conviction.

8. **Drawdown Circuit Breaker**: If total portfolio drops 5% from peak in a single day, all new buying is halted. At 10% drawdown, the system moves to defensive mode (tighten all stops, reduce position sizes). At 15%, all positions are reviewed for immediate exit.

### 5.2 Buy Decision Flow

```
Research identifies opportunity
        │
        ▼
Conviction score ≥ 7/10?  ──NO──▶  Add to watchlist, continue monitoring
        │
       YES
        │
        ▼
Risk/reward ratio ≥ 3:1?  ──NO──▶  Wait for better entry price
        │
       YES
        │
        ▼
Position size within limits? ──NO──▶  Reduce size or skip
        │
       YES
        │
        ▼
Portfolio cash reserve OK?  ──NO──▶  Must sell existing position first
        │
       YES
        │
        ▼
No correlation overload?   ──NO──▶  Skip or reduce size
        │
       YES
        │
        ▼
  ╔═══════════════════╗
  ║   EXECUTE BUY     ║
  ║   Set stop loss   ║
  ║   Log reasoning   ║
  ║   Report live     ║
  ╚═══════════════════╝
```

### 5.3 Sell Decision Flow

Sells are triggered by any of:
- Stop loss hit (automatic, non-negotiable)
- Take profit target reached
- Thesis invalidated by new information (earnings miss, insider selling, negative news)
- Better opportunity requires freeing capital
- Time horizon expired without expected move

---

## 6. Data Sources & APIs

### 6.1 Market Data
- **Yahoo Finance** (`yfinance`): Free real-time and historical stock data, financials, earnings
- **Alpha Vantage**: Fundamental data, earnings, economic indicators (free tier available)
- **Finnhub**: Real-time quotes, news, SEC filings, insider transactions (free tier)

### 6.2 Insider Trading Data
- **SEC EDGAR**: Direct access to Form 4 filings (free, official source)
- **Finnhub Insider Transactions API**: Structured insider trading data
- **OpenInsider** (web scraping fallback): Aggregated insider trading data

### 6.3 News & Sentiment
- **Finnhub News API**: Company-specific and market news
- **NewsAPI**: Broad news coverage with keyword filtering
- **Reddit/StockTwits**: Social sentiment (filtered and weighted low)

### 6.4 AI Engine
- **Claude API (Anthropic)**: Core reasoning, analysis, and decision-making
- **Claude Code**: System orchestration, code generation, live interaction

### 6.5 Broker Execution
- **alpaca-trade-api**: Official Alpaca SDK (recommended)
  - REST API for orders, positions, account info
  - Websocket streaming for order updates and market data
  - Native paper trading (separate API URL, same code)
  - Trailing stop orders built-in
- **robin_stocks**: Python library for Robinhood API access
  - Login with MFA support
  - Place market/limit/stop orders
  - Query positions, order status, portfolio value
  - Cancel/modify open orders

---

## 7. System Components & Directory Structure

```
AITrading/
├── SYSTEM_SPEC.md              # This document
├── CLAUDE.md                   # Claude Code project instructions
├── config/
│   ├── settings.yaml           # System configuration
│   ├── credentials.env         # API keys (gitignored)
│   └── watchlist.yaml          # Stocks being monitored
├── src/
│   ├── __init__.py
│   ├── main.py                 # System entry point & orchestrator
│   ├── data/
│   │   ├── __init__.py
│   │   ├── market_data.py      # Stock price & financial data fetching
│   │   ├── insider_tracker.py  # SEC Form 4 / insider transaction monitoring
│   │   ├── news_feed.py        # News aggregation & filtering
│   │   └── sec_filings.py      # SEC EDGAR filing retrieval
│   ├── research/
│   │   ├── __init__.py
│   │   ├── engine.py           # Core research engine (Claude-powered)
│   │   ├── fundamental.py      # Fundamental analysis module
│   │   ├── sentiment.py        # News & sentiment analysis
│   │   ├── insider_analysis.py # Insider activity analysis
│   │   └── competitor.py       # Competitive analysis
│   ├── decision/
│   │   ├── __init__.py
│   │   ├── signal_generator.py # Generates buy/sell/hold signals
│   │   ├── risk_manager.py     # Risk management & position sizing
│   │   └── portfolio.py        # Portfolio state & tracking
│   ├── execution/
│   │   ├── __init__.py
│   │   ├── broker.py           # Broker abstraction layer (common interface)
│   │   ├── alpaca_broker.py    # Alpaca implementation (paper + live)
│   │   ├── robinhood_broker.py # Robinhood implementation
│   │   └── order_manager.py    # Order lifecycle management
│   ├── reporting/
│   │   ├── __init__.py
│   │   ├── live_display.py     # Real-time terminal dashboard
│   │   ├── trade_logger.py     # Trade history & reasoning log
│   │   └── alerts.py           # Notifications & alerts
│   └── utils/
│       ├── __init__.py
│       ├── config.py           # Configuration loader
│       └── scheduler.py        # Research cycle scheduling
├── data/
│   ├── research_reports/       # Generated research reports
│   ├── trade_history/          # Executed trade logs with reasoning
│   ├── market_cache/           # Cached market data
│   └── insider_cache/          # Cached insider transaction data
├── tests/
│   ├── test_research.py
│   ├── test_risk_manager.py
│   ├── test_signals.py
│   └── test_execution.py
├── requirements.txt
└── .gitignore
```

---

## 8. Operational Modes

### 8.1 Research Mode (Default)
The system continuously cycles through:
1. Pull latest data for all watchlist stocks
2. Run full research analysis via Claude
3. Generate/update conviction scores
4. Identify new opportunities from broader market scans
5. Produce research reports
6. Repeat on a configurable interval (default: every 30 minutes for watchlist, every 4 hours for broad scans)

### 8.2 Live Trading Mode
When enabled alongside Research Mode:
1. All Research Mode functions continue
2. When a signal triggers (conviction ≥ 7, all risk checks pass), the system:
   - Displays the signal with full reasoning in the live dashboard
   - Waits for a configurable confirmation window (default: 0 seconds for auto, or manual approval)
   - Executes the trade via the active broker (Alpaca or Robinhood)
   - Sets stop loss and take profit orders
   - Logs the complete trade with reasoning
   - Reports the execution result live

### 8.3 Paper Trading Mode (Enable/Disable Toggle)
Paper trading is a runtime toggle in `config/settings.yaml`:

```yaml
trading:
  paper_trading: true    # true = paper mode, false = live mode
  broker: alpaca         # alpaca | robinhood
```

**When `paper_trading: true`:**
- **Alpaca**: Routes all orders to Alpaca's paper trading API (`https://paper-api.alpaca.markets`). Orders go through the real Alpaca order lifecycle with simulated fills — no local simulation needed.
- **Robinhood**: Orders are intercepted locally. Simulated fills at current market price. Virtual portfolio tracked in SQLite.
- The dashboard shows **"PAPER"** prominently in the mode indicator.
- All research, signals, and risk management operate identically to live mode.

**When `paper_trading: false`:**
- Orders route to real brokerage accounts with real money.
- Requires explicit confirmation the first time the system is switched from paper to live.
- A startup safety check warns: *"LIVE TRADING ENABLED — real money at risk. Type CONFIRM to proceed."*

**Switching between modes** does not affect research history, watchlists, or trade logs. Paper and live trades are logged in separate tables so performance can be compared.

### 8.4 Backtest Mode
- Run the research and decision engine against historical data
- Evaluate how past signals would have performed
- Validate risk management rules
- Generate performance metrics (win rate, average gain, max drawdown, Sharpe ratio)

---

## 9. Live Dashboard

The terminal dashboard shows real-time system state:

```
╔══════════════════════════════════════════════════════════════════╗
║                    AITrading Live Dashboard                      ║
║               Mode: PAPER (Alpaca) | 2026-06-19 14:32:05         ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  PORTFOLIO                              CASH: $47,250 (63.0%)    ║
║  Total Value: $75,000    Day P/L: +$312 (+0.42%)                 ║
║                                                                  ║
║  POSITIONS                                                       ║
║  ┌────────┬────────┬────────┬──────────┬──────────┬───────────┐  ║
║  │ Ticker │ Shares │ Entry  │ Current  │   P/L    │ Stop Loss │  ║
║  ├────────┼────────┼────────┼──────────┼──────────┼───────────┤  ║
║  │ NVDA   │   15   │$121.50 │ $124.30  │ +$42.00  │  $118.00  │  ║
║  │ AMZN   │    8   │$189.20 │ $192.10  │ +$23.20  │  $185.00  │  ║
║  └────────┴────────┴────────┴──────────┴──────────┴───────────┘  ║
║                                                                  ║
║  ACTIVE SIGNALS                                                  ║
║  ● 14:30 — STRONG BUY AAPL (Conviction: 8/10)                   ║
║    Reason: Insider cluster buy + beat earnings + undervalued      ║
║    Action: Awaiting execution...                                 ║
║                                                                  ║
║  RECENT TRADES                                                   ║
║  ✓ 13:15 — BOUGHT 15 NVDA @ $121.50 (Limit)                     ║
║    Reason: AI chip demand thesis + strong FCF + insider buying    ║
║                                                                  ║
║  RESEARCH CYCLE                                                  ║
║  Last scan: 14:28 | Next scan: 14:58 | Stocks analyzed: 47      ║
║  Watchlist: AAPL, MSFT, GOOGL, AMZN, NVDA, META, TSLA + 12     ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
```

---

## 10. Safety & Controls

### 10.1 Safeguards
- **Manual Override**: Operator can pause all trading at any time
- **Daily Loss Limit**: Maximum daily loss of 2% of portfolio — trading halts if hit
- **Order Confirmation**: Optional manual approval before each trade
- **Dry Run First**: System must run in Paper Trading mode for at least 2 weeks before live trading
- **API Rate Limiting**: Respect all API rate limits with backoff and queuing
- **Credential Security**: All API keys stored in `.env` file, never committed to git

### 10.2 Logging
- Every research report is saved with timestamp
- Every trade is logged with complete reasoning chain
- Every signal (acted on or not) is recorded
- Portfolio snapshots taken hourly
- All Claude AI interactions logged for audit

### 10.3 Alerts & Notifications
- Trade executed: ticker, action, price, quantity, reasoning
- Stop loss triggered: ticker, loss amount, exit reasoning
- High-conviction signal detected
- System errors or API failures
- Daily portfolio summary

---

## 11. Startup Sequence

### Phase 1: Foundation (Current Sprint)
1. Set up project structure and dependencies
2. Build data ingestion layer (market data, insider data, news)
3. Build Claude-powered research engine
4. Build signal generator with risk management
5. Build live terminal dashboard
6. Paper trading mode operational

### Phase 2: Paper Trading Validation
1. Integrate Alpaca paper trading API
2. Order management and execution through Alpaca
3. Stop loss and take profit automation
4. Run paper trading for minimum 2 weeks
5. Validate signal accuracy and risk management
6. Compare paper results against actual market outcomes

### Phase 2.5: Live Trading
1. Switch Alpaca from paper to live API
2. Integrate Robinhood as secondary broker option
3. Go live with 1-2 stocks, small positions
4. Monitor closely, compare live vs paper performance

### Phase 3: Scale
1. Expand watchlist and scanning breadth
2. Add broad market scanning (screen all US stocks)
3. Optimize research cycle frequency
4. Add sector rotation detection
5. Add earnings calendar integration
6. Performance analytics and strategy refinement

---

## 12. Technology Stack

| Component           | Technology                                      |
|---------------------|-------------------------------------------------|
| Language            | Python 3.12                                     |
| AI Engine           | Claude API (Anthropic) / Claude Code            |
| Market Data         | yfinance, Alpha Vantage, Finnhub                |
| Insider Data        | SEC EDGAR, Finnhub                              |
| News                | Finnhub, NewsAPI                                |
| Broker (Primary)    | Alpaca via alpaca-trade-api (paper + live)       |
| Broker (Secondary)  | Robinhood via robin_stocks                      |
| Dashboard           | Rich (terminal UI library)                      |
| Scheduling          | APScheduler                                     |
| Configuration       | PyYAML, python-dotenv                           |
| Data Storage        | SQLite (trades, portfolio) + JSON (reports)     |
| Testing             | pytest                                          |

---

## 13. Key Design Principles

1. **Research first, trade second.** The system never trades on a hunch. Every action is backed by documented, multi-dimensional research.

2. **Capital preservation over capital growth.** Missing a winning trade is acceptable. Losing money is not. The system is designed to be right when it acts, even if it acts infrequently.

3. **Transparency in every decision.** Every trade comes with a full reasoning chain. If the AI cannot clearly articulate why it is making a trade, the trade does not happen.

4. **Start small, prove the system.** Begin with 1-2 stocks in paper trading. Validate the research quality and signal accuracy. Scale only after demonstrated success.

5. **Continuous improvement.** Every trade outcome (win or loss) feeds back into the system's understanding. Review past trades to refine the research and decision process.

6. **Defense in depth.** Multiple independent safety mechanisms (stop losses, position limits, drawdown breakers, cash reserves) ensure no single failure can cause catastrophic loss.

---

*This specification is a living document. It will be updated as the system evolves and as we learn what works best through paper trading and live operation.*
