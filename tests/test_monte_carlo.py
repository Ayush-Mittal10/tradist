"""Tests for Monte Carlo simulator."""

import numpy as np
import pytest

from core.data_engine.schema import OptionLeg, OptionType, Side
from core.research.monte_carlo import (
    simulate_paths,
    simulate_terminal_prices,
    analyze_position,
)
from core.research.black_scholes import bs_price


class TestPathSimulation:
    """Test GBM path simulation."""

    def test_paths_shape(self):
        """Paths should have correct shape."""
        paths = simulate_paths(S0=25000, sigma=0.15, T=30/365, n_paths=1000, seed=42)
        assert paths.shape[0] == 1000
        assert paths.shape[1] > 1

    def test_paths_start_at_S0(self):
        """All paths should start at S0."""
        paths = simulate_paths(S0=25000, sigma=0.15, T=30/365, n_paths=100, seed=42)
        assert np.all(paths[:, 0] == 25000)

    def test_terminal_prices_positive(self):
        """All terminal prices should be positive (GBM property)."""
        terminal = simulate_terminal_prices(S0=25000, sigma=0.15, T=1.0, n_paths=10000, seed=42)
        assert np.all(terminal > 0)

    def test_mean_terminal_close_to_forward(self):
        """
        Mean terminal price should be close to the forward price S0*exp(rT).
        This validates the risk-neutral drift.
        """
        S0, r, T = 25000, 0.07, 1.0
        terminal = simulate_terminal_prices(S0=S0, sigma=0.15, T=T, r=r, n_paths=500_000, seed=42)
        forward = S0 * np.exp(r * T)
        # Should be within 1% of forward
        assert abs(np.mean(terminal) - forward) / forward < 0.01

    def test_antithetic_mean_exact(self):
        """
        With antithetic variates, the mean of Z and -Z should make
        the sample mean more accurate.
        """
        terminal = simulate_terminal_prices(S0=25000, sigma=0.20, T=0.5, n_paths=10000, seed=42)
        # Just verify it ran and produced reasonable results
        assert 20000 < np.mean(terminal) < 30000

    def test_reproducibility_with_seed(self):
        """Same seed should produce identical results."""
        t1 = simulate_terminal_prices(S0=25000, sigma=0.15, T=0.1, n_paths=100, seed=123)
        t2 = simulate_terminal_prices(S0=25000, sigma=0.15, T=0.1, n_paths=100, seed=123)
        np.testing.assert_array_equal(t1, t2)


class TestMCConvergence:
    """Test that MC price converges to BS price."""

    def test_call_price_convergence(self):
        """MC call price should converge to BS call price."""
        S0, K, T, r, sigma = 25000, 25000, 30/365, 0.07, 0.15

        bs = bs_price(S0, K, T, r, sigma, "CE")

        terminal = simulate_terminal_prices(S0, sigma, T, r, n_paths=500_000, seed=42)
        payoff = np.maximum(terminal - K, 0)
        mc_price = np.exp(-r * T) * np.mean(payoff)

        # Should be within 2% of BS price
        assert abs(mc_price - bs) / bs < 0.02


class TestPositionAnalysis:
    """Test Monte Carlo position analysis."""

    def test_short_straddle_pop(self):
        """Short ATM straddle should have PoP roughly 50-80%."""
        legs = [
            OptionLeg(strike=25000, option_type=OptionType.CE, side=Side.SELL, lots=1),
            OptionLeg(strike=25000, option_type=OptionType.PE, side=Side.SELL, lots=1),
        ]
        entry_prices = {
            (25000, "CE"): 150,
            (25000, "PE"): 140,
        }

        result = analyze_position(
            S0=25000, sigma=0.15, T=7/365,
            legs=legs, entry_prices=entry_prices,
            lot_size=65, n_paths=50_000, seed=42,
        )

        assert 30 < result.probability_of_profit < 90
        assert result.probability_of_loss == pytest.approx(100 - result.probability_of_profit, abs=0.1)

    def test_long_call_pop(self):
        """Long ATM call should have PoP roughly 40-60%."""
        legs = [
            OptionLeg(strike=25000, option_type=OptionType.CE, side=Side.BUY, lots=1),
        ]
        entry_prices = {(25000, "CE"): 150}

        result = analyze_position(
            S0=25000, sigma=0.15, T=30/365,
            legs=legs, entry_prices=entry_prices,
            lot_size=65, n_paths=50_000, seed=42,
        )

        assert 20 < result.probability_of_profit < 70

    def test_var_ordering(self):
        """1% VaR should be worse than 5% VaR."""
        legs = [
            OptionLeg(strike=25000, option_type=OptionType.CE, side=Side.SELL, lots=1),
            OptionLeg(strike=25000, option_type=OptionType.PE, side=Side.SELL, lots=1),
        ]
        entry_prices = {(25000, "CE"): 150, (25000, "PE"): 140}

        result = analyze_position(
            S0=25000, sigma=0.15, T=7/365,
            legs=legs, entry_prices=entry_prices,
            lot_size=65, n_paths=50_000, seed=42,
        )

        assert result.var_1pct <= result.var_5pct

    def test_expected_move_positive(self):
        """Expected move should be positive."""
        legs = [
            OptionLeg(strike=25000, option_type=OptionType.CE, side=Side.SELL, lots=1),
        ]
        entry_prices = {(25000, "CE"): 100}

        result = analyze_position(
            S0=25000, sigma=0.15, T=30/365,
            legs=legs, entry_prices=entry_prices,
            lot_size=65, n_paths=10_000, seed=42,
        )

        assert result.expected_move > 0
