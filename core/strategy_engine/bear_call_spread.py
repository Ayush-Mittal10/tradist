"""
Bear Call Spread Strategy.

Rules:
  1. Sell ATM (or slightly OTM) Call
  2. Buy further OTM Call at ATM + width
  3. Credit spread — bearish/neutral position
  4. Exit at expiry
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class BearCallSpread(Strategy):

    @property
    def name(self) -> str:
        return "Bear Call Spread"

    @property
    def description(self) -> str:
        return (
            "Sell ATM Call + Buy OTM Call. Bearish/neutral credit spread. "
            "Max profit = net credit received. Max loss = width - credit."
        )

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter(
                name="width",
                label="Spread Width (pts)",
                type="float",
                default=200.0,
                min_val=50.0,
                max_val=1000.0,
                step=50.0,
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

    def _find_nearest_strike(self, chain, target, option_type, expiry):
        filtered = chain[
            (chain["option_type"] == option_type) &
            (chain["expiry"].dt.date == expiry)
        ]
        if filtered.empty:
            return None
        strikes = filtered["strike"].unique()
        return float(min(strikes, key=lambda s: abs(s - target)))

    def should_enter(
        self,
        market: MarketState,
        open_positions: list[Position],
        capital: float,
        lot_size: int,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        params = params or {}
        width = params.get("width", 200.0)
        lots = params.get("lots_per_trade", 1)

        if len(open_positions) >= 1:
            return None

        chain = market.option_chain
        if chain.empty:
            return None

        expiry = market.get_nearest_expiry()
        atm = market.get_atm_strike()

        sell_strike = atm
        buy_target = atm + width
        buy_strike = self._find_nearest_strike(chain, buy_target, "CE", expiry)

        if buy_strike is None:
            return None

        sell_price = market.get_option_price(sell_strike, OptionType.CE, expiry)
        buy_price = market.get_option_price(buy_strike, OptionType.CE, expiry)

        if sell_price is None or buy_price is None:
            return None
        if sell_price <= buy_price:
            return None  # No credit available

        legs = [
            OptionLeg(strike=sell_strike, option_type=OptionType.CE, side=Side.SELL, lots=lots),
            OptionLeg(strike=buy_strike, option_type=OptionType.CE, side=Side.BUY, lots=lots),
        ]

        net_credit = (sell_price - buy_price) * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Bear call spread: Sell {sell_strike}CE={sell_price:.1f}, "
                   f"Buy {buy_strike}CE={buy_price:.1f}, credit=₹{net_credit:,.0f}",
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
                    side=Side.SELL if f.side == Side.BUY else Side.BUY,
                    lots=f.lots,
                )
                for f in position.legs
            ]
            return Signal(action="EXIT", legs=exit_legs, reason="Expiry reached")
        return None
