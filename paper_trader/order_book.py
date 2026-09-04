"""
Paper order book and position tracker.

Manages simulated trades in-memory. Tracks open positions,
computes mark-to-market P&L, and produces completed Trade objects
in the same format as the backtester.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

import numpy as np

from core.data_engine.schema import (
    Fill,
    MarketState,
    OptionLeg,
    OptionType,
    Position,
    Side,
    Signal,
    Trade,
)
from core.execution_engine.costs import CostPreset
from core.execution_engine.simulator import ExecutionSimulator


@dataclass
class PaperOrder:
    """A paper trade (open or closed)."""
    order_id: str
    entry_timestamp: datetime
    strategy_name: str
    entry_legs: list[Fill]
    expiry: date
    status: Literal["OPEN", "CLOSED", "EXPIRED"] = "OPEN"
    exit_timestamp: datetime | None = None
    exit_legs: list[Fill] | None = None

    def to_position(self) -> Position:
        """Convert to Position for strategy exit checks."""
        return Position(
            entry_timestamp=self.entry_timestamp,
            strategy_name=self.strategy_name,
            legs=self.entry_legs,
            expiry=self.expiry,
        )

    def to_trade(self) -> Trade | None:
        """Convert to completed Trade (only if closed)."""
        if self.status == "OPEN" or self.exit_legs is None:
            return None
        return Trade(
            entry_timestamp=self.entry_timestamp,
            exit_timestamp=self.exit_timestamp or datetime.now(),
            strategy_name=self.strategy_name,
            entry_legs=self.entry_legs,
            exit_legs=self.exit_legs,
            expiry=self.expiry,
        )


class PaperOrderBook:
    """
    Tracks paper trades and positions in-memory.

    Produces the same Trade dataclass used by the backtester,
    so all analytics and charts work on paper trading results too.
    """

    def __init__(
        self,
        initial_capital: float = 500_000,
        lot_size: int = 65,
        cost_preset: CostPreset = CostPreset.REALISTIC,
    ):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.lot_size = lot_size
        self.simulator = ExecutionSimulator(lot_size=lot_size, cost_preset=cost_preset)
        self._orders: dict[str, PaperOrder] = {}
        self._trade_log: list[Trade] = []
        self._equity_snapshots: list[dict] = []

    @property
    def open_positions(self) -> list[PaperOrder]:
        """All currently open positions."""
        return [o for o in self._orders.values() if o.status == "OPEN"]

    @property
    def completed_trades(self) -> list[Trade]:
        """All completed trades."""
        return list(self._trade_log)

    def open_position(
        self,
        fills: list[Fill],
        strategy_name: str,
        expiry: date,
        timestamp: datetime | None = None,
    ) -> PaperOrder:
        """Record a new paper position."""
        order_id = str(uuid.uuid4())[:8]
        order = PaperOrder(
            order_id=order_id,
            entry_timestamp=timestamp or datetime.now(),
            strategy_name=strategy_name,
            entry_legs=fills,
            expiry=expiry,
        )
        self._orders[order_id] = order

        # Debit/credit capital based on premium
        for fill in fills:
            premium = fill.fill_price * fill.lots * fill.lot_size
            if fill.side == Side.BUY:
                self.current_capital -= premium + fill.total_cost
            else:
                self.current_capital += premium - fill.total_cost

        return order

    def close_position(
        self,
        order_id: str,
        exit_fills: list[Fill],
        timestamp: datetime | None = None,
    ) -> Trade | None:
        """Close an open position and record the completed trade."""
        order = self._orders.get(order_id)
        if order is None or order.status != "OPEN":
            return None

        order.status = "CLOSED"
        order.exit_timestamp = timestamp or datetime.now()
        order.exit_legs = exit_fills

        # Update capital
        for fill in exit_fills:
            premium = fill.fill_price * fill.lots * fill.lot_size
            if fill.side == Side.BUY:
                self.current_capital -= premium + fill.total_cost
            else:
                self.current_capital += premium - fill.total_cost

        trade = order.to_trade()
        if trade:
            self._trade_log.append(trade)
        return trade

    def mark_to_market(self, market_state: MarketState) -> float:
        """
        Compute unrealized P&L for all open positions.

        Args:
            market_state: Current market state for price lookup

        Returns:
            Total unrealized P&L across all open positions
        """
        unrealized = 0.0

        for order in self.open_positions:
            for fill in order.entry_legs:
                current_price = market_state.get_option_price(
                    fill.strike, fill.option_type, order.expiry
                )
                if current_price is not None:
                    if fill.side == Side.SELL:
                        unrealized += (fill.fill_price - current_price) * fill.lots * fill.lot_size
                    else:
                        unrealized += (current_price - fill.fill_price) * fill.lots * fill.lot_size

        return unrealized

    def record_equity(self, timestamp: datetime, unrealized_pnl: float = 0.0):
        """Record an equity curve snapshot."""
        self._equity_snapshots.append({
            "timestamp": timestamp,
            "capital": self.current_capital + unrealized_pnl,
        })

    def get_equity_snapshots(self) -> list[dict]:
        """Return all equity snapshots."""
        return list(self._equity_snapshots)

    def get_session_summary(self) -> dict:
        """Get summary of current session state."""
        realized_pnl = sum(t.net_pnl for t in self._trade_log)
        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "realized_pnl": realized_pnl,
            "open_positions": len(self.open_positions),
            "completed_trades": len(self._trade_log),
            "winning_trades": sum(1 for t in self._trade_log if t.is_winner),
            "losing_trades": sum(1 for t in self._trade_log if not t.is_winner),
        }
