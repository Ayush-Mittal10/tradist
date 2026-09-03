"""Tests for Black-Scholes pricing, IV, and Greeks."""

import numpy as np
import pytest

from core.research.black_scholes import (
    bs_price,
    greeks,
    implied_volatility,
    DEFAULT_RISK_FREE_RATE,
)


class TestBSPricing:
    """Test Black-Scholes option pricing."""

    def test_atm_call_positive(self):
        """ATM call should have positive value."""
        price = bs_price(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert price > 0

    def test_atm_put_positive(self):
        """ATM put should have positive value."""
        price = bs_price(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="PE")
        assert price > 0

    def test_deep_itm_call_near_intrinsic(self):
        """Deep ITM call should be close to intrinsic value."""
        S, K = 25000, 24000
        price = bs_price(S=S, K=K, T=7/365, r=0.07, sigma=0.15, option_type="CE")
        intrinsic = S - K
        assert price >= intrinsic * 0.99  # Should be at least intrinsic

    def test_deep_otm_call_near_zero(self):
        """Deep OTM call with short expiry should be near zero."""
        price = bs_price(S=25000, K=27000, T=1/365, r=0.07, sigma=0.15, option_type="CE")
        assert price < 1.0

    def test_put_call_parity(self):
        """Put-call parity: C - P = S - K*exp(-rT)."""
        S, K, T, r, sigma = 25000, 25000, 30/365, 0.07, 0.20
        call = bs_price(S, K, T, r, sigma, "CE")
        put = bs_price(S, K, T, r, sigma, "PE")
        parity_rhs = S - K * np.exp(-r * T)
        assert abs((call - put) - parity_rhs) < 0.5  # Allow small float error

    def test_higher_vol_higher_price(self):
        """Higher vol should give higher price (for both calls and puts)."""
        low_vol = bs_price(S=25000, K=25000, T=30/365, r=0.07, sigma=0.10, option_type="CE")
        high_vol = bs_price(S=25000, K=25000, T=30/365, r=0.07, sigma=0.30, option_type="CE")
        assert high_vol > low_vol

    def test_vectorized(self):
        """Should work with numpy arrays."""
        strikes = np.array([24800, 25000, 25200])
        prices = bs_price(S=25000, K=strikes, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert len(prices) == 3
        # Lower strike = higher call price
        assert prices[0] > prices[1] > prices[2]

    def test_expired_option_intrinsic(self):
        """Expired option should return intrinsic value."""
        price = bs_price(S=25000, K=24800, T=0, r=0.07, sigma=0.15, option_type="CE")
        assert abs(price - 200) < 0.01


class TestImpliedVolatility:
    """Test implied volatility solver."""

    def test_iv_round_trip(self):
        """Compute price → extract IV → should recover original sigma."""
        S, K, T, r = 25000, 25000, 30/365, 0.07
        original_sigma = 0.18

        price = bs_price(S, K, T, r, original_sigma, "CE")
        recovered_iv = implied_volatility(price, S, K, T, r, "CE")

        assert abs(recovered_iv - original_sigma) < 0.001

    def test_iv_round_trip_put(self):
        """IV round-trip should work for puts too."""
        S, K, T, r = 25000, 25200, 30/365, 0.07
        original_sigma = 0.22

        price = bs_price(S, K, T, r, original_sigma, "PE")
        recovered_iv = implied_volatility(price, S, K, T, r, "PE")

        assert abs(recovered_iv - original_sigma) < 0.001

    def test_iv_expired_returns_nan(self):
        """Expired option should return NaN."""
        iv = implied_volatility(100, 25000, 25000, 0, 0.07, "CE")
        assert np.isnan(iv)

    def test_iv_zero_price_returns_nan(self):
        """Zero price should return NaN."""
        iv = implied_volatility(0, 25000, 25000, 30/365, 0.07, "CE")
        assert np.isnan(iv)

    def test_iv_reasonable_range(self):
        """IV for typical NIFTY options should be 5-80%."""
        S, K, T, r = 25000, 25000, 30/365, 0.07
        price = bs_price(S, K, T, r, 0.15, "CE")
        iv = implied_volatility(price, S, K, T, r, "CE")
        assert 0.05 < iv < 0.80


class TestGreeks:
    """Test Greeks calculations."""

    def test_call_delta_positive(self):
        """Call delta should be positive (0 to 1)."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert 0 < g.delta < 1

    def test_put_delta_negative(self):
        """Put delta should be negative (-1 to 0)."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="PE")
        assert -1 < g.delta < 0

    def test_atm_call_delta_near_05(self):
        """ATM call delta should be approximately 0.5."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert 0.4 < g.delta < 0.65

    def test_gamma_positive(self):
        """Gamma should be positive for both calls and puts."""
        g_call = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        g_put = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="PE")
        assert g_call.gamma > 0
        assert g_put.gamma > 0

    def test_gamma_same_for_call_put(self):
        """Gamma should be the same for calls and puts at same strike."""
        g_call = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        g_put = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="PE")
        assert abs(g_call.gamma - g_put.gamma) < 1e-10

    def test_theta_negative(self):
        """Theta should be negative (time decay)."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert g.theta < 0

    def test_vega_positive(self):
        """Vega should be positive for long options."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert g.vega > 0

    def test_call_rho_positive(self):
        """Call rho should be positive (higher rates → higher call value)."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="CE")
        assert g.rho > 0

    def test_put_rho_negative(self):
        """Put rho should be negative."""
        g = greeks(S=25000, K=25000, T=30/365, r=0.07, sigma=0.15, option_type="PE")
        assert g.rho < 0
