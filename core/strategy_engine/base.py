"""
Abstract base class for all trading strategies.

Every strategy implements this interface. The backtester and paper trader
feed MarketState snapshots into it — the strategy doesn't know (or care)
whether the data is historical or live.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from core.data_engine.schema import MarketState, OptionLeg, Position, Signal


@dataclass
class StrategyParameter:
    """Describes a configurable strategy parameter for UI rendering."""
    name: str
    label: str
    type: str              # "int", "float", "select", "bool"
    default: Any
    options: list[Any] | None = None   # For "select" type
    min_val: float | None = None
    max_val: float | None = None
    step: float | None = None
    help_text: str = ""


class Strategy(ABC):
    """
    Abstract base class for all option strategies.

    Subclasses implement the decision logic:
    - should_enter: Given current market, should we open a new position?
    - should_exit: Given current market and an open position, should we close?
    - select_legs: Given the option chain, construct the position legs.

    The backtest/paper-trade engine calls these methods in sequence
    for each trading day, feeding ONLY data available at that point
    in time (no look-ahead).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable strategy name."""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """Brief description of the strategy logic."""
        ...

    @property
    def parameters(self) -> list[StrategyParameter]:
        """
        Configurable parameters for this strategy.

        Override in subclasses to expose strategy-specific settings
        to the UI (e.g., strangle width, stop-loss percentage).
        """
        return []

    @property
    def required_fields(self) -> list[str]:
        """
        Canonical fields this strategy requires.

        Default is just 'close'. Override if your strategy needs
        bid/ask, volume, OI, etc. The data validator will warn
        if the uploaded dataset is missing any of these.
        """
        return ["close"]

    @abstractmethod
    def should_enter(
        self,
        market: MarketState,
        open_positions: list[Position],
        capital: float,
        lot_size: int,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        """
        Evaluate whether to enter a new position.

        Args:
            market: Current market snapshot (no future data)
            open_positions: Currently open positions
            capital: Available capital
            lot_size: NIFTY lot size (e.g., 65)
            params: Strategy parameters from UI

        Returns:
            Signal with action="ENTER" and legs, or None to skip
        """
        ...

    @abstractmethod
    def should_exit(
        self,
        market: MarketState,
        position: Position,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        """
        Evaluate whether to exit an open position.

        Args:
            market: Current market snapshot
            position: The open position to evaluate
            params: Strategy parameters from UI

        Returns:
            Signal with action="EXIT" and legs, or None to hold
        """
        ...


# ── Strategy Registry ──────────────────────────────────────────────────

_STRATEGY_REGISTRY: dict[str, type[Strategy]] = {}


def register_strategy(cls: type[Strategy]) -> type[Strategy]:
    """Decorator to register a strategy class in the global registry."""
    # We instantiate temporarily to get the name
    instance = cls()
    _STRATEGY_REGISTRY[instance.name] = cls
    return cls


def get_all_strategies() -> dict[str, type[Strategy]]:
    """Return all registered strategies."""
    return dict(_STRATEGY_REGISTRY)


def get_strategy(name: str) -> Strategy:
    """Instantiate a strategy by name."""
    if name not in _STRATEGY_REGISTRY:
        available = ", ".join(_STRATEGY_REGISTRY.keys())
        raise ValueError(f"Unknown strategy '{name}'. Available: {available}")
    return _STRATEGY_REGISTRY[name]()
