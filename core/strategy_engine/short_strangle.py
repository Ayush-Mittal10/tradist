"""
Short ATM Strangle Strategy.

Rules:
  1. Find nearest expiry
  2. Sell OTM CE (ATM + width) and OTM PE (ATM - width)
  3. Exit at expiry or stop-loss/profit-target
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class ShortATMStrangle(Strategy):

    @property
    def name(self) -> str:
        return "Short ATM Strangle"

    @property
    def description(self) -> str:
        return (
            "Sell OTM Call + OTM Put at configurable distance from ATM. "
            "Wider range than a straddle; profits when NIFTY stays within the strikes."
        )

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
            StrategyParameter(
                name="width",
                label="Strike Width (pts from ATM)",
                type="float",
                default=200.0,
                min_val=50.0,
                max_val=1000.0,
                step=50.0,
                help_text="Distance from ATM for each leg (e.g., 200 = sell 200 pts OTM on each side).",
            ),
            StrategyParameter(
                name="stop_loss_pct",
                label="Stop Loss (%)",
                type="float",
                default=0.0,
                min_val=0.0,
                max_val=200.0,
                step=5.0,
                help_text="Exit if combined premium moves against by this %. 0 = no stop loss.",
            ),
            StrategyParameter(
                name="profit_target_pct",
                label="Profit Target (%)",
                type="float",
                default=0.0,
                min_val=0.0,
                max_val=100.0,
                step=5.0,
                help_text="Exit if premium decays to this % of entry. 0 = hold to expiry.",
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

    def _find_nearest_strike(self, chain, target: float, option_type: str, expiry) -> float | None:
        """Find the available strike nearest to the target price."""
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
        atm = market.underlying_close

        # Find nearest available strikes to our target OTM strikes
        ce_target = atm + width
        pe_target = atm - width

        ce_strike = self._find_nearest_strike(chain, ce_target, "CE", expiry)
        pe_strike = self._find_nearest_strike(chain, pe_target, "PE", expiry)

        if ce_strike is None or pe_strike is None:
            return None

        ce_price = market.get_option_price(ce_strike, OptionType.CE, expiry)
        pe_price = market.get_option_price(pe_strike, OptionType.PE, expiry)

        if ce_price is None or pe_price is None or ce_price < 0.5 or pe_price < 0.5:
            return None

        legs = [
            OptionLeg(strike=ce_strike, option_type=OptionType.CE, side=Side.SELL, lots=lots),
            OptionLeg(strike=pe_strike, option_type=OptionType.PE, side=Side.SELL, lots=lots),
        ]

        total_premium = (ce_price + pe_price) * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Short strangle: Sell {ce_strike}CE={ce_price:.1f} + "
                   f"{pe_strike}PE={pe_price:.1f}, premium=₹{total_premium:,.0f}",
        )

    def should_exit(
        self,
        market: MarketState,
        position: Position,
        params: dict[str, Any] | None = None,
    ) -> Signal | None:
        params = params or {}
        stop_loss_pct = params.get("stop_loss_pct", 0.0)
        profit_target_pct = params.get("profit_target_pct", 0.0)

        current_date = market.timestamp.date()
        if current_date >= position.expiry:
            exit_legs = []
            for fill in position.legs:
                exit_side = Side.BUY if fill.side == Side.SELL else Side.SELL
                exit_legs.append(OptionLeg(
                    strike=fill.strike, option_type=fill.option_type,
                    side=exit_side, lots=fill.lots,
                ))
            return Signal(action="EXIT", legs=exit_legs, reason="Expiry reached")

        if stop_loss_pct > 0 or profit_target_pct > 0:
            entry_premium = abs(position.entry_premium)
            if entry_premium <= 0:
                return None

            current_premium = 0.0
            for fill in position.legs:
                price = market.get_option_price(fill.strike, fill.option_type, position.expiry)
                if price is None:
                    return None
                current_premium += price * fill.lots * fill.lot_size

            pnl_pct = (entry_premium - current_premium) / entry_premium * 100

            if stop_loss_pct > 0 and pnl_pct < -stop_loss_pct:
                exit_legs = [
                    OptionLeg(strike=f.strike, option_type=f.option_type,
                              side=Side.BUY if f.side == Side.SELL else Side.SELL,
                              lots=f.lots)
                    for f in position.legs
                ]
                return Signal(action="EXIT", legs=exit_legs,
                              reason=f"Stop loss: P&L = {pnl_pct:.1f}%")

            if profit_target_pct > 0 and pnl_pct >= profit_target_pct:
                exit_legs = [
                    OptionLeg(strike=f.strike, option_type=f.option_type,
                              side=Side.BUY if f.side == Side.SELL else Side.SELL,
                              lots=f.lots)
                    for f in position.legs
                ]
                return Signal(action="EXIT", legs=exit_legs,
                              reason=f"Profit target: P&L = {pnl_pct:.1f}%")

        return None
