"""
Buy ATM CE After Positive Day Strategy.

Rules:
  1. If previous day's underlying close > day before's close (positive day),
     buy ATM Call at nearest expiry
  2. Exit at expiry
  
This is a simple trend-following directional strategy.
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class BuyCEAfterPositive(Strategy):

    @property
    def name(self) -> str:
        return "Buy CE After Positive Day"

    @property
    def description(self) -> str:
        return (
            "Buy ATM Call after a positive day (underlying closed higher). "
            "Simple momentum/trend-following strategy. Max loss = premium paid."
        )

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter(
                name="min_move_pct",
                label="Min Move (%)",
                type="float",
                default=0.0,
                min_val=0.0,
                max_val=5.0,
                step=0.1,
                help_text="Minimum positive % move to trigger entry. 0 = any positive close.",
            ),
            StrategyParameter(
                name="lots_per_trade",
                label="Lots per Trade",
                type="int",
                default=1,
                min_val=1,
                max_val=10,
                step=1,
            ),
        ]

    def should_enter(
        self,
        market: MarketState,
        open_positions: list[Position],
        capital: float,
        lot_size: int,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        params = params or {}
        min_move_pct = params.get("min_move_pct", 0.0)
        lots = params.get("lots_per_trade", 1)

        if len(open_positions) >= 1:
            return None

        # Need previous close to determine if day was positive
        if market.previous_close is None or market.previous_close <= 0:
            return None

        # Check if previous day was positive
        # Note: we're using the current underlying_close as "today's close"
        # and previous_close as "yesterday's close"
        move_pct = (market.underlying_close - market.previous_close) / market.previous_close * 100

        if move_pct <= min_move_pct:
            return None

        chain = market.option_chain
        if chain.empty:
            return None

        expiry = market.get_nearest_expiry()
        atm = market.get_atm_strike()

        ce_price = market.get_option_price(atm, OptionType.CE, expiry)
        if ce_price is None or ce_price < 0.5:
            return None

        legs = [
            OptionLeg(strike=atm, option_type=OptionType.CE, side=Side.BUY, lots=lots),
        ]

        premium = ce_price * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Positive day ({move_pct:+.2f}%): Buy {atm}CE={ce_price:.1f}, "
                   f"premium=₹{premium:,.0f}",
        )

    def should_exit(
        self,
        market: MarketState,
        position: Position,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        current_date = market.timestamp.date()
        if current_date >= position.expiry:
            exit_legs = [
                OptionLeg(
                    strike=f.strike, option_type=f.option_type,
                    side=Side.SELL, lots=f.lots,
                )
                for f in position.legs
            ]
            return Signal(action="EXIT", legs=exit_legs, reason="Expiry reached")
        return None
