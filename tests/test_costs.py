"""Tests for transaction cost calculations."""

import pytest

from core.execution_engine.costs import (
    COST_PRESETS,
    CostConfig,
    CostPreset,
    calculate_costs,
)


class TestCostCalculation:
    """Test Indian options transaction cost model."""

    def test_zero_costs(self):
        """Zero preset should have no costs."""
        costs = calculate_costs(
            premium=100_000,
            is_buy=True,
            config=COST_PRESETS[CostPreset.ZERO],
        )
        assert costs.total == 0.0

    def test_realistic_sell_costs(self):
        """Sell-side costs should include STT."""
        costs = calculate_costs(
            premium=100_000,
            is_buy=False,
            config=COST_PRESETS[CostPreset.REALISTIC],
        )
        assert costs.stt > 0, "STT should be charged on sell side"
        assert costs.brokerage == 20.0, "Brokerage should be ₹20"
        assert costs.gst > 0, "GST should be charged"
        assert costs.stamp_duty == 0, "No stamp duty on sell side"

    def test_realistic_buy_costs(self):
        """Buy-side costs should include stamp duty but not STT."""
        costs = calculate_costs(
            premium=100_000,
            is_buy=True,
            config=COST_PRESETS[CostPreset.REALISTIC],
        )
        assert costs.stt == 0, "No STT on buy side"
        assert costs.stamp_duty > 0, "Stamp duty on buy side"
        assert costs.brokerage == 20.0

    def test_stt_rate(self):
        """STT should be 0.15% on sell premium."""
        premium = 1_00_000
        costs = calculate_costs(premium=premium, is_buy=False)
        expected_stt = premium * 0.0015
        assert abs(costs.stt - expected_stt) < 0.01

    def test_gst_calculation(self):
        """GST should be 18% on (brokerage + exchange + SEBI)."""
        costs = calculate_costs(premium=1_00_000, is_buy=True)
        gst_base = costs.brokerage + costs.exchange_charges + costs.sebi_fees
        expected_gst = gst_base * 0.18
        assert abs(costs.gst - expected_gst) < 0.01

    def test_conservative_has_slippage(self):
        """Conservative preset should add slippage."""
        costs = calculate_costs(
            premium=100_000,
            is_buy=True,
            config=COST_PRESETS[CostPreset.CONSERVATIVE],
        )
        assert costs.slippage > 0, "Conservative should have slippage"

    def test_total_is_sum_of_components(self):
        """Total cost should equal sum of all components."""
        costs = calculate_costs(premium=50_000, is_buy=False)
        expected = (costs.brokerage + costs.stt + costs.exchange_charges +
                    costs.sebi_fees + costs.gst + costs.stamp_duty + costs.slippage)
        assert abs(costs.total - expected) < 0.001

    def test_realistic_cost_order_of_magnitude(self):
        """
        Sanity check: for a ₹1,00,000 premium sell trade,
        total costs should be roughly ₹200-400.
        """
        costs = calculate_costs(premium=1_00_000, is_buy=False)
        assert 100 < costs.total < 500, f"Costs = ₹{costs.total:.2f}, seems unreasonable"
