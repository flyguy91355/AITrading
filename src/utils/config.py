"""Configuration loader."""

from pathlib import Path
import yaml
from dotenv import load_dotenv


def load_config(config_path: str = "config/settings.yaml") -> dict:
    load_dotenv(".env")

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(path) as f:
        return yaml.safe_load(f)


def load_watchlist(watchlist_path: str = "config/watchlist.yaml") -> list[dict]:
    path = Path(watchlist_path)
    if not path.exists():
        return []

    with open(path) as f:
        data = yaml.safe_load(f)
        return data.get("watchlist", [])
