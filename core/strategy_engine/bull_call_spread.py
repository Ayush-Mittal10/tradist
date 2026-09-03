"""
Bull Call Spread Strategy.

Rules:
  1. Buy ATM (or slightly ITM) Call
  2. Sell OTM Call at ATM + width
  3. Limited risk, limited reward — bullish position
  4. Exit at expiry or stop-loss/profit-target
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class BullCallSpread(Strategy):

    @property
    def name(self) -> str:
        return "Bull Call Spread"

    @property
    def description(self) -> str:
        return (
            "Buy ATM Call + Sell OTM Call. Bullish strategy with defined risk. "
            "Max profit = strike width - net debit. Max loss = net debit paid."
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
                help_text="Distance between long and short strikes.",
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

        # Buy ATM CE, Sell OTM CE
        buy_strike = atm
        sell_target = atm + width
        sell_strike = self._find_nearest_strike(chain, sell_target, "CE", expiry)

        if sell_strike is None:
            return None

        buy_price = market.get_option_price(buy_strike, OptionType.CE, expiry)
        sell_price = market.get_option_price(sell_strike, OptionType.CE, expiry)

        if buy_price is None or sell_price is None:
            return None
        if buy_price <= sell_price:
            return None  # No debit spread possible

        legs = [
            OptionLeg(strike=buy_strike, option_type=OptionType.CE, side=Side.BUY, lots=lots),
            OptionLeg(strike=sell_strike, option_type=OptionType.CE, side=Side.SELL, lots=lots),
        ]

        net_debit = (buy_price - sell_price) * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Bull call spread: Buy {buy_strike}CE={buy_price:.1f}, "
                   f"Sell {sell_strike}CE={sell_price:.1f}, debit=₹{net_debit:,.0f}",
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
