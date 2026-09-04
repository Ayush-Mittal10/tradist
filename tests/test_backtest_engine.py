"""Tests for the backtest engine integration."""

import os
from datetime import date

import pytest
import pandas as pd

from core.data_engine.csv_parser import parse_csv
from core.data_engine.normalizer import normalize
from core.data_engine.providers import HistoricalProvider
from core.execution_engine.costs import CostPreset

# Import strategies to register them
import core.strategy_engine.short_straddle     # noqa: F401
import core.strategy_engine.short_strangle     # noqa: F401
import core.strategy_engine.bull_call_spread   # noqa: F401
import core.strategy_engine.bear_call_spread   # noqa: F401
import core.strategy_engine.buy_ce_after_positive  # noqa: F401
import core.strategy_engine.buy_pe_after_negative  # noqa: F401

from core.strategy_engine.base import get_strategy
from backtester.engine import BacktestEngine

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES_DIR, "sample_nifty.csv")


@pytest.fixture
def provider():
    df, _ = parse_csv(SAMPLE_CSV)
    df = normalize(df)
    return HistoricalProvider(df)


class TestBacktestEngine:
    """Integration tests for the full backtest pipeline."""

    def test_short_straddle_produces_trades(self, provider):
        """Short straddle should produce at least one trade."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.REALISTIC,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        assert len(result.trades) > 0, "Should produce at least one trade"

    def test_backtest_result_structure(self, provider):
        """BacktestResult should have all required fields."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.REALISTIC,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        assert result.initial_capital == 500_000
        assert result.strategy_name == "Short ATM Straddle"
        assert isinstance(result.equity_curve, pd.DataFrame)
        assert "timestamp" in result.equity_curve.columns
        assert "capital" in result.equity_curve.columns

    def test_equity_curve_has_entries(self, provider):
        """Equity curve should have entries for trading days."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        assert len(result.equity_curve) > 0

    def test_trades_have_costs(self, provider):
        """With realistic costs, trades should have non-zero costs."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.REALISTIC,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        if result.trades:
            total_costs = sum(t.total_costs for t in result.trades)
            assert total_costs > 0, "Realistic costs should be non-zero"

    def test_zero_cost_preset(self, provider):
        """Zero cost preset should have zero transaction costs."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.ZERO,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        if result.trades:
            total_costs = sum(t.total_costs for t in result.trades)
            assert total_costs == 0, "Zero costs should mean zero costs"

    def test_bull_call_spread_runs(self, provider):
        """Bull call spread should complete without errors."""
        strategy = get_strategy("Bull Call Spread")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        assert isinstance(result.trades, list)

    def test_all_strategies_run_without_error(self, provider):
        """Every registered strategy should complete a backtest without errors."""
        from core.strategy_engine.base import get_all_strategies

        for name in get_all_strategies():
            strategy = get_strategy(name)
            engine = BacktestEngine(
                strategy=strategy,
                data_provider=provider,
                lot_size=65,
            )
            result = engine.run(
                start_date=date(2025, 6, 1),
                end_date=date(2025, 6, 30),
                initial_capital=500_000,
            )
            assert isinstance(result.trades, list), f"Strategy '{name}' failed"

    def test_final_capital_accounts_for_pnl(self, provider):
        """Final capital should equal initial + sum of trade P&Ls."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.ZERO,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=500_000,
        )
        total_pnl = sum(t.net_pnl for t in result.trades)
        expected = 500_000 + total_pnl
        assert abs(result.final_capital - expected) < 1.0, (
            f"Final={result.final_capital}, Expected={expected}"
        )

    def test_insufficient_capital_generates_risk_warning(self, provider):
        """When capital is too low to trade, warnings must explain margin requirement."""
        strategy = get_strategy("Short ATM Straddle")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            lot_size=65,
        )
        result = engine.run(
            start_date=date(2025, 6, 1),
            end_date=date(2025, 6, 30),
            initial_capital=50_000,
        )
        assert len(result.trades) == 0
        assert len(result.warnings) > 0
        assert any("Risk Engine" in w and "margin" in w.lower() for w in result.warnings)
