"""
Risk engine: margin estimation, position sizing, and drawdown tracking.

Provides approximate margin requirements for NIFTY options positions
and enforces capital constraints during backtesting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from core.data_engine.schema import Fill, OptionType, Position, Side


@dataclass
class RiskConfig:
    """Configuration for risk management."""
    # Approximate SPAN margin for naked NIFTY option (per lot)
    naked_option_margin_per_lot: float = 175_000.0   # ~₹1.75L per lot
    # Spread margin discount (hedged positions require less margin)
    spread_margin_per_lot: float = 50_000.0          # ~₹50K per lot for defined-risk spreads
    # Max portfolio drawdown before halting new trades
    max_drawdown_pct: float = 25.0                   # 25% of initial capital
    # Capital reserve (don't deploy 100% of capital)
    capital_utilization_pct: float = 80.0             # Use max 80% of capital


class RiskEngine:
    """
    Manages risk constraints during backtesting and paper trading.

    Responsibilities:
    - Estimate margin requirements for positions
    - Check if a new trade is affordable
    - Track running drawdown
    - Generate risk warnings
    """

    def __init__(self, initial_capital: float, config: RiskConfig | None = None):
        self.initial_capital = initial_capital
        self.config = config or RiskConfig()

        # Running state
        self.current_capital = initial_capital
        self.peak_capital = initial_capital
        self.max_drawdown = 0.0
        self.max_drawdown_pct_observed = 0.0
        self._margin_used = 0.0

    def estimate_margin(self, fills: list[Fill]) -> float:
        """
        Estimate the margin required for a set of position legs.

        Logic:
        - If all legs are BUY: margin = total premium paid (no additional margin)
        - If any leg is SELL:
            - Check if it's a spread (has both BUY and SELL legs)
            - Spread: use reduced margin
            - Naked: use full margin
        """
        buy_legs = [f for f in fills if f.side == Side.BUY]
        sell_legs = [f for f in fills if f.side == Side.SELL]

        if not sell_legs:
            # Pure long position: margin = premium paid
            return sum(f.premium for f in buy_legs)

        total_sell_lots = sum(f.lots for f in sell_legs)

        if buy_legs:
            # Spread: reduced margin
            return total_sell_lots * self.config.spread_margin_per_lot
        else:
            # Naked short: full margin
            return total_sell_lots * self.config.naked_option_margin_per_lot

    def can_trade(self, fills: list[Fill]) -> tuple[bool, str]:
        """
        Check if we have enough capital and margin for a new trade.

        Returns (can_trade, reason_if_not).
        """
        required_margin = self.estimate_margin(fills)
        available = self.current_capital * (self.config.capital_utilization_pct / 100)
        available -= self._margin_used

        if required_margin > available:
            return False, (
                f"Insufficient capital: need ₹{required_margin:,.0f} margin, "
                f"only ₹{available:,.0f} available"
            )

        # Check drawdown limit
        if self.max_drawdown_pct_observed >= self.config.max_drawdown_pct:
            return False, (
                f"Max drawdown limit reached: {self.max_drawdown_pct_observed:.1f}% "
                f"≥ {self.config.max_drawdown_pct}%"
            )

        return True, ""

    def open_position(self, fills: list[Fill]) -> None:
        """Record that a position has been opened (margin consumed)."""
        margin = self.estimate_margin(fills)
        self._margin_used += margin

    def close_position(self, entry_fills: list[Fill], net_pnl: float) -> None:
        """Record that a position has been closed (margin freed, P&L realized)."""
        margin = self.estimate_margin(entry_fills)
        self._margin_used = max(0, self._margin_used - margin)

        # Update capital
        self.current_capital += net_pnl

        # Track peak and drawdown
        if self.current_capital > self.peak_capital:
            self.peak_capital = self.current_capital

        drawdown = self.peak_capital - self.current_capital
        if drawdown > self.max_drawdown:
            self.max_drawdown = drawdown
            self.max_drawdown_pct_observed = (
                drawdown / self.peak_capital * 100 if self.peak_capital > 0 else 0
            )

    def get_risk_summary(self) -> dict:
        """Return current risk state for display."""
        return {
            "initial_capital": self.initial_capital,
            "current_capital": self.current_capital,
            "peak_capital": self.peak_capital,
            "margin_used": self._margin_used,
            "available_capital": (
                self.current_capital * (self.config.capital_utilization_pct / 100)
                - self._margin_used
            ),
            "max_drawdown": self.max_drawdown,
            "max_drawdown_pct": self.max_drawdown_pct_observed,
        }
