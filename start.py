#!/usr/bin/env python3
"""Convenience launcher for AITrading — double-click or run to start."""

from __future__ import annotations

import argparse
import signal
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start AITrading services.")
    parser.add_argument(
        "--mode",
        choices=["main", "web", "both"],
        default="web",
        help="Service mode to run (default: web)",
    )
    parser.add_argument("--host", default="0.0.0.0", help="Host for web mode")
    parser.add_argument("--port", type=int, default=8080, help="Port for web mode")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    return parser.parse_args()


def wait_and_open_browser(port: int, timeout: int = 30):
    """Wait for the server to accept connections, then open the browser."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                webbrowser.open(f"http://localhost:{port}")
                return
        except OSError:
            time.sleep(0.5)


def launch(command: list[str]) -> subprocess.Popen:
    return subprocess.Popen(command)


def main() -> int:
    root = Path(__file__).resolve().parent
    args = parse_args()

    processes: list[subprocess.Popen] = []

    if args.mode in {"main", "both"}:
        processes.append(launch([sys.executable, "-m", "src.main"]))

    if args.mode in {"web", "both"}:
        processes.append(
            launch(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "web.app:app",
                    "--host",
                    args.host,
                    "--port",
                    str(args.port),
                ]
            )
        )
        if not args.no_browser:
            threading.Thread(
                target=wait_and_open_browser, args=(args.port,), daemon=True
            ).start()

    def handle_signal(sig: int, frame: object) -> None:
        del sig, frame
        for proc in processes:
            if proc.poll() is None:
                proc.terminate()
        for proc in processes:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        exit_codes = [proc.wait() for proc in processes]
        return max(exit_codes) if exit_codes else 0
    except KeyboardInterrupt:
        handle_signal(signal.SIGINT, None)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
