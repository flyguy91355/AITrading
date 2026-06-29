"""Research cycle scheduling."""

from datetime import datetime


class ResearchScheduler:
    def __init__(self, config: dict):
        self.config = config
        self.watchlist_interval = config["research"]["watchlist_scan_interval_minutes"]
        self.broad_scan_interval = config["research"]["broad_scan_interval_hours"]
        self.last_watchlist_scan: datetime | None = None
        self.last_broad_scan: datetime | None = None

    def should_run_watchlist_scan(self) -> bool:
        if self.last_watchlist_scan is None:
            return True
        elapsed = (datetime.now() - self.last_watchlist_scan).total_seconds() / 60
        return elapsed >= self.watchlist_interval

    def should_run_broad_scan(self) -> bool:
        if self.last_broad_scan is None:
            return True
        elapsed = (datetime.now() - self.last_broad_scan).total_seconds() / 3600
        return elapsed >= self.broad_scan_interval

    def mark_watchlist_scan(self):
        self.last_watchlist_scan = datetime.now()

    def mark_broad_scan(self):
        self.last_broad_scan = datetime.now()
