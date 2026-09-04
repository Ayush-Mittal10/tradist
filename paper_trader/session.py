"""
Trading session manager.

Manages the lifecycle of a paper trading session with background
polling. Runs the PaperTradeEngine.tick() in a background thread
at a configurable interval during NSE market hours.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime, time as dt_time
from typing import Any

from core.data_engine.providers import LiveDataProvider
from core.execution_engine.costs import CostPreset
from core.strategy_engine.base import Strategy
from paper_trader.engine import PaperTradeEngine


# NSE trading hours (IST)
MARKET_OPEN = dt_time(9, 15)
MARKET_CLOSE = dt_time(15, 30)


class TradingSession:
    """
    Manages a paper trading session with auto-polling.

    Runs the paper trading engine in a background thread,
    calling tick() at regular intervals during market hours.
    """

    def __init__(
        self,
        strategy: Strategy,
        live_provider: LiveDataProvider,
        lot_size: int = 65,
        cost_preset: CostPreset = CostPreset.REALISTIC,
        poll_interval: int = 30,
    ):
        """
        Args:
            strategy: Strategy to trade
            live_provider: Live data provider
            lot_size: NIFTY lot size
            cost_preset: Transaction cost model
            poll_interval: Seconds between ticks
        """
        self.engine = PaperTradeEngine(
            strategy=strategy,
            live_provider=live_provider,
            lot_size=lot_size,
            cost_preset=cost_preset,
        )
        self.poll_interval = poll_interval
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._tick_log: list[dict] = []

    @property
    def is_running(self) -> bool:
        return self.engine.is_running

    @property
    def tick_log(self) -> list[dict]:
        return list(self._tick_log)

    def start(self, capital: float = 500_000.0, params: dict | None = None):
        """
        Start the paper trading session.

        Begins the background polling loop.
        """
        self.engine.start_session(capital=capital, params=params)
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._polling_loop,
            daemon=True,
            name="paper-trade-session",
        )
        self._thread.start()

    def stop(self):
        """Stop the polling loop and return results."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        return self.engine.stop_session()

    def manual_tick(self) -> dict:
        """
        Execute a single tick manually (for testing or manual mode).

        Returns tick result dict.
        """
        result = self.engine.tick()
        self._tick_log.append({
            "timestamp": datetime.now().isoformat(),
            **result,
        })
        return result

    def _polling_loop(self):
        """Background polling loop."""
        while not self._stop_event.is_set():
            if self.is_market_open():
                result = self.engine.tick()
                self._tick_log.append({
                    "timestamp": datetime.now().isoformat(),
                    **result,
                })

            # Wait for next tick (check stop event frequently)
            for _ in range(self.poll_interval):
                if self._stop_event.is_set():
                    return
                time.sleep(1)

    @staticmethod
    def is_market_open() -> bool:
        """
        Check if NSE is currently open.

        NSE hours: 9:15 AM - 3:30 PM IST, Monday-Friday.
        Does not account for holidays.
        """
        now = datetime.now()

        # Weekend check (Mon=0, Sun=6)
        if now.weekday() >= 5:
            return False

        current_time = now.time()
        return MARKET_OPEN <= current_time <= MARKET_CLOSE

    def get_status(self) -> dict:
        """Get combined session + engine status."""
        status = self.engine.get_status()
        status["market_open"] = self.is_market_open()
        status["poll_interval"] = self.poll_interval
        status["total_ticks"] = len(self._tick_log)

        # Last few tick actions
        recent = self._tick_log[-5:] if self._tick_log else []
        status["recent_actions"] = recent

        return status
