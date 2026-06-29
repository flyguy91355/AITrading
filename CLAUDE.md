# AITrading

AI-Powered Stock Research & Autonomous Trading System.

## Quick Reference

- **Language:** Python 3.12
- **Config:** `config/settings.yaml`
- **Credentials:** `config/credentials.env` (never commit)
- **Spec:** `SYSTEM_SPEC.md`

## Commands

```bash
# Run the system
python -m src.main

# Run tests
pytest tests/

# Install dependencies
pip install -r requirements.txt
```

## Architecture

- `src/data/` — Data ingestion (market data, insider tracking, news, SEC filings)
- `src/research/` — Claude-powered research engine and analysis modules
- `src/decision/` — Signal generation, risk management, portfolio tracking
- `src/execution/` — Broker abstraction (Alpaca, Robinhood), order management
- `src/reporting/` — Live dashboard, trade logging, alerts
- `src/utils/` — Config loader, scheduler

## Key Rules

- Paper trading mode must be validated before any live trading
- Every trade requires conviction score >= 7/10 and risk/reward >= 3:1
- Max 2% portfolio risk per trade, 30% minimum cash reserve
- Stop losses are mandatory on every position
