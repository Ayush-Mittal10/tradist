"""
Trade execution simulator.

Simulates realistic order fills by modeling bid/ask spreads,
slippage, and all transaction costs. Used by both the backtester
(historical mode) and paper trader (live mode).
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from core.data_engine.schema import (
    Fill, MarketState, OptionLeg, OptionType, Side, Signal,
)
from core.execution_engine.costs import (
    COST_PRESETS,
    CostConfig,
    CostPreset,
    calculate_costs,
)


class ExecutionSimulator:
    """
    Simulates trade execution with realistic pricing.

    If bid/ask data is available, fills at mid ± slippage.
    If only close data is available, fills at close with an
    estimated spread based on moneyness.
    """

    def __init__(
        self,
        lot_size: int = 65,
        cost_preset: CostPreset = CostPreset.REALISTIC,
        cost_config: CostConfig | None = None,
    ):
        self.lot_size = lot_size
        self.cost_config = cost_config or COST_PRESETS[cost_preset]

    def _estimate_fill_price(
        self,
        leg: OptionLeg,
        market: MarketState,
        expiry=None,
    ) -> float | None:
        """
        Estimate the fill price for a leg.

        Priority:
        1. Mid of bid/ask if available
        2. Close price with estimated spread
        """
        if expiry is None:
            expiry = market.get_nearest_expiry()

        options = market.get_options(
            expiry=expiry,
            option_type=leg.option_type,
            strike=leg.strike,
        )

        if options.empty:
            return None

        row = options.iloc[0]

        # Try bid/ask first
        bid = row.get("bid")
        ask = row.get("ask")
        if pd.notna(bid) and pd.notna(ask) and bid > 0 and ask > 0:
            mid = (bid + ask) / 2
            spread = ask - bid
            # Buyer pays slightly above mid, seller receives slightly below
            if leg.side == Side.BUY:
                return mid + spread * 0.1  # Pay 10% above mid
            else:
                return mid - spread * 0.1  # Receive 10% below mid

        # Fall back to close price
        close = row.get("close")
        if pd.notna(close) and close > 0:
            # Estimate a small spread based on price level
            # Higher-priced options tend to have tighter relative spreads
            estimated_spread_pct = 0.005  # 0.5% of option price
            spread = close * estimated_spread_pct

            if leg.side == Side.BUY:
                return close + spread * 0.5
            else:
                return close - spread * 0.5

        return None

    def execute_signal(
        self,
        signal: Signal,
        market: MarketState,
        expiry=None,
    ) -> list[Fill] | None:
        """
        Execute all legs of a signal and return Fill objects.

        Returns None if any leg cannot be filled (e.g., no price data).
        """
        if not signal.legs:
            return None

        fills: list[Fill] = []

        for leg in signal.legs:
            fill_price = self._estimate_fill_price(leg, market, expiry)
            if fill_price is None or fill_price <= 0:
                return None  # Cannot fill this leg

            # Calculate premium
            premium = fill_price * leg.lots * self.lot_size

            # Calculate costs
            is_buy = leg.side == Side.BUY
            cost_breakdown = calculate_costs(
                premium=premium,
                is_buy=is_buy,
                config=self.cost_config,
            )

            fill = Fill(
                timestamp=market.timestamp,
                strike=leg.strike,
                option_type=leg.option_type,
                side=leg.side,
                lots=leg.lots,
                fill_price=fill_price,
                lot_size=self.lot_size,
                brokerage=cost_breakdown.brokerage,
                stt=cost_breakdown.stt,
                exchange_charges=cost_breakdown.exchange_charges,
                sebi_fees=cost_breakdown.sebi_fees,
                gst=cost_breakdown.gst,
                stamp_duty=cost_breakdown.stamp_duty,
                slippage=cost_breakdown.slippage,
            )
            fills.append(fill)

        return fills
