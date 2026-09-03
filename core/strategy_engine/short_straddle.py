"""
Short ATM Straddle Strategy.

Rules:
  1. At each trading day, find the nearest weekly expiry
  2. Find the ATM strike (nearest to underlying close)
  3. Sell 1 lot CE + 1 lot PE at ATM strike
  4. Exit at expiry (or stop-loss / profit-target if configured)
"""

from __future__ import annotations

from typing import Any

from core.data_engine.schema import (
    MarketState, OptionLeg, OptionType, Position, Signal, Side,
)
from core.strategy_engine.base import Strategy, StrategyParameter, register_strategy


@register_strategy
class ShortATMStraddle(Strategy):

    @property
    def name(self) -> str:
        return "Short ATM Straddle"

    @property
    def description(self) -> str:
        return (
            "Sell ATM Call + ATM Put at the nearest expiry. "
            "Profits when NIFTY stays near the strike. "
            "Maximum loss is theoretically unlimited."
        )

    @property
    def parameters(self) -> list[StrategyParameter]:
        return [
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
                name="max_positions",
                label="Max Simultaneous Positions",
                type="int",
                default=1,
                min_val=1,
                max_val=5,
                step=1,
                help_text="Maximum number of straddles open at once.",
            ),
            StrategyParameter(
                name="lots_per_trade",
                label="Lots per Trade",
                type="int",
                default=1,
                min_val=1,
                max_val=10,
                step=1,
                help_text="Number of lots per leg.",
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
        max_positions = params.get("max_positions", 1)
        lots = params.get("lots_per_trade", 1)

        # Don't exceed max positions
        if len(open_positions) >= max_positions:
            return None

        # Need both CE and PE in the option chain
        chain = market.option_chain
        if chain.empty:
            return None

        expiry = market.get_nearest_expiry()
        atm_strike = market.get_atm_strike()

        # Verify both CE and PE exist at ATM strike for this expiry
        ce_price = market.get_option_price(atm_strike, OptionType.CE, expiry)
        pe_price = market.get_option_price(atm_strike, OptionType.PE, expiry)

        if ce_price is None or pe_price is None:
            return None

        # Don't enter if prices are unreasonably low (likely near expiry)
        if ce_price < 1.0 or pe_price < 1.0:
            return None

        legs = [
            OptionLeg(strike=atm_strike, option_type=OptionType.CE, side=Side.SELL, lots=lots),
            OptionLeg(strike=atm_strike, option_type=OptionType.PE, side=Side.SELL, lots=lots),
        ]

        total_premium = (ce_price + pe_price) * lots * lot_size
        return Signal(
            action="ENTER",
            legs=legs,
            reason=f"Short straddle at {atm_strike}: CE={ce_price:.1f} PE={pe_price:.1f}, "
                   f"premium=₹{total_premium:,.0f}, expiry={expiry}",
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

        # Exit at expiry
        current_date = market.timestamp.date()
        if current_date >= position.expiry:
            exit_legs = []
            for entry_fill in position.legs:
                # Reverse the position
                exit_side = Side.BUY if entry_fill.side == Side.SELL else Side.SELL
                exit_legs.append(OptionLeg(
                    strike=entry_fill.strike,
                    option_type=entry_fill.option_type,
                    side=exit_side,
                    lots=entry_fill.lots,
                ))
            return Signal(action="EXIT", legs=exit_legs, reason="Expiry reached")

        # Check stop-loss and profit target
        if stop_loss_pct > 0 or profit_target_pct > 0:
            entry_premium = abs(position.entry_premium)
            if entry_premium <= 0:
                return None

            # Calculate current position value
            current_premium = 0.0
            for fill in position.legs:
                price = market.get_option_price(
                    fill.strike, fill.option_type, position.expiry
                )
                if price is None:
                    return None
                current_premium += price * fill.lots * fill.lot_size

            # For short positions: we received premium at entry.
            # Loss = current_premium - entry_premium (if current > entry, we lose)
            pnl_pct = (entry_premium - current_premium) / entry_premium * 100

            # Stop loss: exit if loss exceeds threshold
            if stop_loss_pct > 0 and pnl_pct < -stop_loss_pct:
                exit_legs = []
                for fill in position.legs:
                    exit_side = Side.BUY if fill.side == Side.SELL else Side.SELL
                    exit_legs.append(OptionLeg(
                        strike=fill.strike,
                        option_type=fill.option_type,
                        side=exit_side,
                        lots=fill.lots,
                    ))
                return Signal(
                    action="EXIT",
                    legs=exit_legs,
                    reason=f"Stop loss triggered: P&L = {pnl_pct:.1f}%",
                )

            # Profit target: exit if profit exceeds threshold
            if profit_target_pct > 0 and pnl_pct >= profit_target_pct:
                exit_legs = []
                for fill in position.legs:
                    exit_side = Side.BUY if fill.side == Side.SELL else Side.SELL
                    exit_legs.append(OptionLeg(
                        strike=fill.strike,
                        option_type=fill.option_type,
                        side=exit_side,
                        lots=fill.lots,
                    ))
                return Signal(
                    action="EXIT",
                    legs=exit_legs,
                    reason=f"Profit target hit: P&L = {pnl_pct:.1f}%",
                )

        return None
