"""
Market data provider abstraction.

This is the seam between the strategy engine and the data source.
In Phase 1, only HistoricalProvider is implemented. Phase 3 adds
LiveProvider for paper trading — but strategies don't change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

import pandas as pd

from core.data_engine.schema import MarketState


class MarketDataProvider(ABC):
    """
    Abstract base class for market data providers.

    Strategies and the backtest engine interact with market data
    exclusively through this interface. This ensures the same
    strategy code works identically with historical CSV data
    and live market feeds.
    """

    @abstractmethod
    def get_trading_dates(
        self, start: date, end: date
    ) -> list[date]:
        """Return all trading dates in the range."""
        ...

    @abstractmethod
    def get_market_state(self, timestamp: datetime) -> MarketState:
        """
        Build a MarketState snapshot at the given timestamp.

        CRITICAL: Must only include data available AT OR BEFORE
        the timestamp. This is the primary look-ahead bias prevention.
        """
        ...


class HistoricalProvider(MarketDataProvider):
    """
    Provides market data from a pre-loaded canonical DataFrame.

    Used by the backtester to feed historical data into strategies
    one timestamp at a time.
    """

    def __init__(self, df: pd.DataFrame, underlying: str = "NIFTY"):
        """
        Args:
            df: Canonical-format DataFrame with all historical data
            underlying: Name of the underlying instrument
        """
        self._df = df.copy()
        self._underlying = underlying

        # Pre-compute trading dates and underlying closes for fast lookup
        self._df["_date"] = self._df["timestamp"].dt.date
        self._trading_dates = sorted(self._df["_date"].unique())

        # Build underlying close lookup by date
        self._underlying_closes: dict[date, float] = {}
        for d in self._trading_dates:
            day_data = self._df[self._df["_date"] == d]
            if "underlying_close" in day_data.columns:
                uc = day_data["underlying_close"].dropna()
                if not uc.empty:
                    self._underlying_closes[d] = float(uc.iloc[0])

    def get_trading_dates(self, start: date, end: date) -> list[date]:
        return [d for d in self._trading_dates if start <= d <= end]

    def get_market_state(self, timestamp: datetime) -> MarketState:
        """
        Build a MarketState with ONLY data at or before the timestamp.

        For EOD data, we include data from the current day's date
        (since EOD prices represent the end of the trading day).
        """
        current_date = timestamp.date() if isinstance(timestamp, datetime) else timestamp

        # Filter to current day only (for EOD data)
        day_data = self._df[self._df["_date"] == current_date].copy()

        # Remove our internal column before exposing
        if "_date" in day_data.columns:
            day_data = day_data.drop(columns=["_date"])

        # Get underlying close
        underlying_close = self._underlying_closes.get(current_date, 0.0)

        # Get previous day's close
        previous_close = None
        date_idx = self._trading_dates.index(current_date) if current_date in self._trading_dates else -1
        if date_idx > 0:
            prev_date = self._trading_dates[date_idx - 1]
            previous_close = self._underlying_closes.get(prev_date)

        ts = timestamp if isinstance(timestamp, datetime) else datetime.combine(
            timestamp, datetime.min.time()
        )

        return MarketState(
            timestamp=ts,
            underlying=self._underlying,
            underlying_close=underlying_close,
            option_chain=day_data.reset_index(drop=True),
            previous_close=previous_close,
        )
