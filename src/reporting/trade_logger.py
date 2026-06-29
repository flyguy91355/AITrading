"""Trade history and reasoning log."""

import json
from datetime import datetime
from pathlib import Path


class TradeLogger:
    def __init__(self, config: dict):
        self.config = config
        self.log_dir = Path("data/trade_history")
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log_trade(self, signal):
        entry = {
            "ticker": signal.ticker,
            "signal": signal.signal.value,
            "conviction": signal.conviction,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "shares": signal.shares,
            "position_size": signal.position_size_dollars,
            "reasoning": signal.reasoning,
            "timestamp": datetime.now().isoformat(),
        }

        log_file = self.log_dir / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        with open(log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def get_trade_history(self, days: int = 30) -> list[dict]:
        trades = []
        for log_file in sorted(self.log_dir.glob("*.jsonl"), reverse=True)[:days]:
            with open(log_file) as f:
                for line in f:
                    trades.append(json.loads(line))
        return trades
