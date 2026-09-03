"""
Paper trading engine stub (Phase 3).

This module will connect live market data to the same Strategy interface
used by the backtester. For now, it's a placeholder that demonstrates
the architecture's extensibility.
"""

from __future__ import annotations


class PaperTradeEngine:
    """
    Drives a strategy with live market data for paper trading.

    Will be implemented in Phase 3. Uses the exact same Strategy
    interface as BacktestEngine — the only difference is the
    MarketDataProvider (live instead of historical).

    Architecture:
        while market_open:
            1. Fetch live MarketState from LiveDataProvider
            2. Check exit signals on open positions
            3. Check entry signals
            4. Record paper trades
            5. Track live P&L
    """

    def __init__(self):
        raise NotImplementedError(
            "Paper trading will be implemented in Phase 3. "
            "The architecture is ready — we just need a live data provider."
        )
