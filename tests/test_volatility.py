"""Tests for volatility analysis."""

import numpy as np
import pandas as pd
import pytest

from core.research.volatility import (
    realized_volatility,
    realized_volatility_multi,
    percentile_rank,
    classify_regime,
    VolRegime,
)


class TestRealizedVolatility:
    """Test realized volatility calculations."""

    def test_constant_prices_zero_vol(self):
        """Constant prices should give zero realized volatility."""
        prices = pd.Series([100.0] * 30)
        rv = realized_volatility(prices, window=10)
        # After initial NaN window, values should be 0 (or NaN)
        valid = rv.dropna()
        if len(valid) > 0:
            assert all(v == 0 or np.isnan(v) for v in valid)

    def test_rv_positive(self):
        """RV of a volatile series should be positive."""
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.015, 100)
        prices = pd.Series(100 * np.exp(np.cumsum(returns)))
        rv = realized_volatility(prices, window=20)
        valid = rv.dropna()
        assert len(valid) > 0
        assert all(v > 0 for v in valid)

    def test_rv_annualized(self):
        """Annualized RV should be roughly in 10-40% for typical market data."""
        np.random.seed(42)
        # Daily returns with ~15% annualized vol
        daily_vol = 0.15 / np.sqrt(252)
        returns = np.random.normal(0, daily_vol, 200)
        prices = pd.Series(100 * np.exp(np.cumsum(returns)))
        rv = realized_volatility(prices, window=20)
        valid = rv.dropna()
        # Should be in roughly the right ballpark
        mean_rv = valid.mean()
        assert 0.05 < mean_rv < 0.40

    def test_multi_windows(self):
        """Multi-window RV should return correct column names."""
        np.random.seed(42)
        prices = pd.Series(100 * np.exp(np.cumsum(np.random.normal(0, 0.01, 100))))
        result = realized_volatility_multi(prices, windows=[10, 20, 30])
        assert "rv_10" in result.columns
        assert "rv_20" in result.columns
        assert "rv_30" in result.columns


class TestPercentileRank:
    """Test percentile ranking."""

    def test_at_minimum(self):
        """Value at minimum should be near 0%."""
        history = pd.Series([10, 20, 30, 40, 50])
        rank = percentile_rank(5, history)
        assert rank == 0.0

    def test_at_maximum(self):
        """Value at maximum should be near 100%."""
        history = pd.Series([10, 20, 30, 40, 50])
        rank = percentile_rank(55, history)
        assert rank == 100.0

    def test_median(self):
        """Value at median should be near 50%."""
        history = pd.Series(range(100))
        rank = percentile_rank(50, history)
        assert 45 < rank < 55

    def test_range(self):
        """Rank should always be between 0 and 100."""
        history = pd.Series(np.random.normal(0.15, 0.05, 200))
        for val in [0.05, 0.10, 0.15, 0.20, 0.30]:
            rank = percentile_rank(val, history)
            assert 0 <= rank <= 100


class TestRegimeClassification:
    """Test volatility regime detection."""

    def test_low_regime(self):
        regime, _ = classify_regime(10)
        assert regime == VolRegime.LOW

    def test_normal_regime(self):
        regime, _ = classify_regime(50)
        assert regime == VolRegime.NORMAL

    def test_high_regime(self):
        regime, _ = classify_regime(80)
        assert regime == VolRegime.HIGH

    def test_extreme_regime(self):
        regime, _ = classify_regime(95)
        assert regime == VolRegime.EXTREME

    def test_boundary_25(self):
        """25th percentile should be NORMAL (not LOW)."""
        regime, _ = classify_regime(25)
        assert regime == VolRegime.NORMAL

    def test_boundary_75(self):
        """75th percentile should be HIGH (not NORMAL)."""
        regime, _ = classify_regime(75)
        assert regime == VolRegime.HIGH

    def test_description_not_empty(self):
        """Every regime should have a description."""
        for pct in [5, 30, 80, 95]:
            _, desc = classify_regime(pct)
            assert len(desc) > 10
