"""
Market data provider abstraction.

This is the seam between the strategy engine and the data source.
- HistoricalProvider: feeds CSV/Parquet data (Phase 1)
- LiveDataProvider: feeds real-time Upstox data (Phase 3)

Strategies don't know which provider they're running against.
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


class LiveDataProvider(MarketDataProvider):
    """
    Provides real-time MarketState from Upstox API.

    Same interface as HistoricalProvider — strategies can't tell
    the difference between historical and live data.
    """

    def __init__(self, upstox_client):
        """
        Args:
            upstox_client: Authenticated UpstoxClient instance
        """
        from core.data_engine.upstox_client import UpstoxClient
        self._client: UpstoxClient = upstox_client
        self._previous_close: float | None = None
        self._last_close: float | None = None

    def get_trading_dates(self, start: date, end: date) -> list[date]:
        """
        Not meaningful for live data.
        Returns today's date if within range.
        """
        today = date.today()
        if start <= today <= end:
            return [today]
        return []

    def get_market_state(self, timestamp: datetime | None = None) -> MarketState:
        """
        Fetch current live option chain and build MarketState.

        The timestamp parameter is ignored for live data — we always
        fetch the latest available state.
        """
        if timestamp is None:
            timestamp = datetime.now()

        # Rotate previous close
        if self._last_close is not None:
            self._previous_close = self._last_close

        # Fetch live data
        try:
            underlying_close = self._client.get_nifty_ltp()
            option_chain = self._client.get_option_chain("current_week")
        except Exception:
            # Return empty state on API failure
            return MarketState(
                timestamp=timestamp,
                underlying="NIFTY",
                underlying_close=self._last_close or 0.0,
                option_chain=pd.DataFrame(),
                previous_close=self._previous_close,
            )

        self._last_close = underlying_close

        return MarketState(
            timestamp=timestamp,
            underlying="NIFTY",
            underlying_close=underlying_close,
            option_chain=option_chain,
            previous_close=self._previous_close,
        )
