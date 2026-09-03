"""
Canonical data schema for the NIFTY Quant Lab.

Every strategy, backtest engine, and analytics module works against these
data structures. Raw CSV data is normalized into this format by the
csv_parser and normalizer modules.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Literal

import pandas as pd


class OptionType(str, Enum):
    CE = "CE"
    PE = "PE"


class Side(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


# ── Canonical columns ──────────────────────────────────────────────────
# Every normalized DataFrame has exactly these columns.

CANONICAL_COLUMNS = {
    # Required
    "timestamp": "datetime64[ns]",
    "underlying": "str",
    "underlying_close": "float64",
    "expiry": "datetime64[ns]",
    "strike": "float64",
    "option_type": "str",       # "CE" or "PE"
    "open": "float64",
    "high": "float64",
    "low": "float64",
    "close": "float64",
    # Optional (may be NaN)
    "volume": "float64",        # float to allow NaN
    "oi": "float64",
    "bid": "float64",
    "ask": "float64",
}

REQUIRED_COLUMNS = [
    "timestamp", "underlying", "underlying_close", "expiry",
    "strike", "option_type", "open", "high", "low", "close",
]

OPTIONAL_COLUMNS = ["volume", "oi", "bid", "ask"]


# ── Data structures used across the system ─────────────────────────────

@dataclass
class OptionLeg:
    """A single leg of a multi-leg options position."""
    strike: float
    option_type: OptionType
    side: Side
    lots: int = 1

    @property
    def quantity(self) -> int:
        """Signed quantity: positive for BUY, negative for SELL."""
        return self.lots if self.side == Side.BUY else -self.lots

    def __repr__(self) -> str:
        action = "Buy" if self.side == Side.BUY else "Sell"
        return f"{action} {self.lots}× {self.strike} {self.option_type.value}"


@dataclass
class Signal:
    """A trading signal produced by a strategy."""
    action: Literal["ENTER", "EXIT", "HOLD"]
    legs: list[OptionLeg] = field(default_factory=list)
    reason: str = ""


@dataclass
class Fill:
    """Represents the execution of a single leg."""
    timestamp: datetime
    strike: float
    option_type: OptionType
    side: Side
    lots: int
    fill_price: float
    lot_size: int
    # Cost breakdown
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    sebi_fees: float = 0.0
    gst: float = 0.0
    stamp_duty: float = 0.0
    slippage: float = 0.0

    @property
    def total_cost(self) -> float:
        return (self.brokerage + self.stt + self.exchange_charges +
                self.sebi_fees + self.gst + self.stamp_duty + self.slippage)

    @property
    def premium(self) -> float:
        """Total premium = price × lots × lot_size."""
        return self.fill_price * self.lots * self.lot_size

    def __repr__(self) -> str:
        action = "Buy" if self.side == Side.BUY else "Sell"
        return (f"Fill({action} {self.lots}×{self.lot_size} "
                f"{self.strike}{self.option_type.value} @ ₹{self.fill_price:.2f}, "
                f"cost=₹{self.total_cost:.2f})")


@dataclass
class Position:
    """An open multi-leg options position."""
    entry_timestamp: datetime
    strategy_name: str
    legs: list[Fill]
    expiry: date

    @property
    def entry_premium(self) -> float:
        """Net premium received (positive) or paid (negative) at entry."""
        total = 0.0
        for leg in self.legs:
            if leg.side == Side.SELL:
                total += leg.premium
            else:
                total -= leg.premium
        return total

    @property
    def entry_costs(self) -> float:
        return sum(leg.total_cost for leg in self.legs)

    @property
    def strikes(self) -> list[float]:
        return [leg.strike for leg in self.legs]


@dataclass
class Trade:
    """A completed trade (entry + exit)."""
    entry_timestamp: datetime
    exit_timestamp: datetime
    strategy_name: str
    entry_legs: list[Fill]
    exit_legs: list[Fill]
    expiry: date

    @property
    def entry_premium(self) -> float:
        total = 0.0
        for leg in self.entry_legs:
            if leg.side == Side.SELL:
                total += leg.premium
            else:
                total -= leg.premium
        return total

    @property
    def exit_premium(self) -> float:
        total = 0.0
        for leg in self.exit_legs:
            # On exit, we reverse: if we sold at entry, we buy back
            if leg.side == Side.BUY:
                total -= leg.premium
            else:
                total += leg.premium
        return total

    @property
    def gross_pnl(self) -> float:
        return self.entry_premium + self.exit_premium

    @property
    def total_costs(self) -> float:
        entry_costs = sum(leg.total_cost for leg in self.entry_legs)
        exit_costs = sum(leg.total_cost for leg in self.exit_legs)
        return entry_costs + exit_costs

    @property
    def net_pnl(self) -> float:
        return self.gross_pnl - self.total_costs

    @property
    def duration_days(self) -> int:
        return (self.exit_timestamp.date() - self.entry_timestamp.date()).days

    @property
    def is_winner(self) -> bool:
        return self.net_pnl > 0

    def summary_dict(self) -> dict:
        """Dictionary for display in trade table."""
        entry_desc = " + ".join(repr(l) for l in self.entry_legs)
        return {
            "Entry Date": self.entry_timestamp.strftime("%d-%b-%Y"),
            "Exit Date": self.exit_timestamp.strftime("%d-%b-%Y"),
            "Strategy": self.strategy_name,
            "Position": entry_desc,
            "Entry Premium": f"₹{abs(self.entry_premium):,.0f}",
            "Exit Premium": f"₹{abs(self.exit_premium):,.0f}",
            "Gross P&L": f"₹{self.gross_pnl:+,.0f}",
            "Costs": f"₹{self.total_costs:,.0f}",
            "Net P&L": f"₹{self.net_pnl:+,.0f}",
            "Days": self.duration_days,
        }


@dataclass
class MarketState:
    """
    A snapshot of the market at a specific point in time.

    This is the PRIMARY mechanism for preventing look-ahead bias.
    The data provider constructs this with ONLY data available at
    or before `timestamp`. Strategies receive this — they cannot
    peek into the future.
    """
    timestamp: datetime
    underlying: str
    underlying_close: float
    option_chain: pd.DataFrame  # Canonical-format DataFrame for this timestamp
    previous_close: float | None = None  # Previous day's underlying close

    def get_options(
        self,
        expiry: date | None = None,
        option_type: OptionType | None = None,
        strike: float | None = None,
    ) -> pd.DataFrame:
        """Filter option chain by criteria."""
        df = self.option_chain.copy()
        if expiry is not None:
            df = df[df["expiry"].dt.date == expiry]
        if option_type is not None:
            df = df[df["option_type"] == option_type.value]
        if strike is not None:
            df = df[df["strike"] == strike]
        return df

    def get_nearest_expiry(self) -> date:
        """Get the nearest expiry date that hasn't passed."""
        expiries = self.option_chain["expiry"].dt.date.unique()
        future_expiries = [e for e in expiries if e >= self.timestamp.date()]
        if not future_expiries:
            # All expiries have passed — return the latest one
            return max(expiries)
        return min(future_expiries)

    def get_atm_strike(self) -> float:
        """Get the strike price nearest to the underlying close."""
        strikes = self.option_chain["strike"].unique()
        if len(strikes) == 0:
            return self.underlying_close
        return float(min(strikes, key=lambda s: abs(s - self.underlying_close)))

    def get_option_price(
        self,
        strike: float,
        option_type: OptionType,
        expiry: date | None = None,
    ) -> float | None:
        """Get the close price of a specific option contract."""
        if expiry is None:
            expiry = self.get_nearest_expiry()
        matches = self.get_options(expiry=expiry, option_type=option_type, strike=strike)
        if matches.empty:
            return None
        return float(matches.iloc[0]["close"])


@dataclass
class DatasetReport:
    """Report generated after parsing and validating a CSV upload."""
    detected_fields: dict[str, str]       # canonical_name → original_col_name
    missing_required: list[str]
    missing_optional: list[str]
    date_range: tuple[date, date] | None
    trading_days: int
    expiry_count: int
    contract_count: int
    row_count: int
    warnings: list[str]

    @property
    def is_valid(self) -> bool:
        return len(self.missing_required) == 0


@dataclass
class BacktestResult:
    """Complete results from a backtest run."""
    trades: list[Trade]
    equity_curve: pd.DataFrame   # timestamp, capital
    initial_capital: float
    final_capital: float
    strategy_name: str
    start_date: date
    end_date: date
    lot_size: int
    cost_preset: str
    warnings: list[str] = field(default_factory=list)
