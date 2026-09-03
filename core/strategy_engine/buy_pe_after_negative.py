"""
Buy ATM PE After Negative Day Strategy.

Rules:
  1. If previous day's underlying close < day before's close (negative day),
     buy ATM Put at nearest expiry
  2. Exit at expiry

Simple mean-reversion / trend-following directional strategy.
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class BuyPEAfterNegative(Strategy):

    @property
    def name(self) -> str:
        return "Buy PE After Negative Day"

    @property
    def description(self) -> str:
        return (
            "Buy ATM Put after a negative day (underlying closed lower). "
            "Simple momentum strategy betting on continued downside. Max loss = premium paid."
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
                help_text="Minimum negative % move to trigger entry. 0 = any negative close.",
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

        if market.previous_close is None or market.previous_close <= 0:
            return None

        move_pct = (market.underlying_close - market.previous_close) / market.previous_close * 100

        # Looking for negative move (move_pct < 0)
        if move_pct >= -min_move_pct:
            return None

        chain = market.option_chain
        if chain.empty:
            return None

        expiry = market.get_nearest_expiry()
        atm = market.get_atm_strike()

        pe_price = market.get_option_price(atm, OptionType.PE, expiry)
        if pe_price is None or pe_price < 0.5:
            return None

        legs = [
            OptionLeg(strike=atm, option_type=OptionType.PE, side=Side.BUY, lots=lots),
        ]

        premium = pe_price * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Negative day ({move_pct:+.2f}%): Buy {atm}PE={pe_price:.1f}, "
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
                    side=Side.BUY if f.side == Side.SELL else Side.SELL,
                    lots=f.lots,
                )
                for f in position.legs
            ]
            return Signal(action="EXIT", legs=exit_legs, reason="Expiry reached")
        return None
