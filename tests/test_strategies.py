"""Tests for strategy signal generation."""

import os
from datetime import date, datetime

import pytest
import pandas as pd

from core.data_engine.csv_parser import parse_csv
from core.data_engine.normalizer import normalize
from core.data_engine.providers import HistoricalProvider
from core.data_engine.schema import OptionType, Position, Side, Fill

# Import strategies to register them
import core.strategy_engine.short_straddle     # noqa: F401
import core.strategy_engine.short_strangle     # noqa: F401
import core.strategy_engine.bull_call_spread   # noqa: F401
import core.strategy_engine.bear_call_spread   # noqa: F401
import core.strategy_engine.buy_ce_after_positive  # noqa: F401
import core.strategy_engine.buy_pe_after_negative  # noqa: F401

from core.strategy_engine.base import get_strategy, get_all_strategies

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES_DIR, "sample_nifty.csv")


@pytest.fixture
def provider():
    """Create a HistoricalProvider from sample data."""
    df, _ = parse_csv(SAMPLE_CSV)
    df = normalize(df)
    return HistoricalProvider(df)


@pytest.fixture
def market_state(provider):
    """Get a market state for the first trading day."""
    dates = provider.get_trading_dates(date(2025, 6, 1), date(2025, 6, 30))
    return provider.get_market_state(datetime.combine(dates[0], datetime.min.time()))


class TestStrategyRegistry:
    """Test strategy registration and lookup."""

    def test_all_strategies_registered(self):
        """All 6 strategies should be registered."""
        strategies = get_all_strategies()
        assert len(strategies) >= 6

    def test_get_strategy_by_name(self):
        """Should be able to get a strategy by name."""
        strategy = get_strategy("Short ATM Straddle")
        assert strategy.name == "Short ATM Straddle"

    def test_unknown_strategy_raises(self):
        """Unknown strategy name should raise ValueError."""
        with pytest.raises(ValueError):
            get_strategy("Nonexistent Strategy")


class TestShortStraddle:
    """Test Short ATM Straddle strategy signals."""

    def test_entry_signal(self, market_state):
        """Should generate an entry signal when no positions are open."""
        strategy = get_strategy("Short ATM Straddle")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        assert signal is not None
        assert signal.action == "ENTER"
        assert len(signal.legs) == 2  # CE + PE

    def test_entry_has_sell_legs(self, market_state):
        """Straddle entry should sell both CE and PE."""
        strategy = get_strategy("Short ATM Straddle")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        assert all(leg.side == Side.SELL for leg in signal.legs)

    def test_same_strike_for_both_legs(self, market_state):
        """Both legs should be at the same (ATM) strike."""
        strategy = get_strategy("Short ATM Straddle")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        strikes = [leg.strike for leg in signal.legs]
        assert len(set(strikes)) == 1  # Both at same strike

    def test_no_entry_when_max_positions(self, market_state):
        """Should not enter when max positions reached."""
        strategy = get_strategy("Short ATM Straddle")
        fake_position = Position(
            entry_timestamp=datetime.now(),
            strategy_name="test",
            legs=[],
            expiry=date(2025, 6, 5),
        )
        signal = strategy.should_enter(market_state, [fake_position], 500000, 65)
        assert signal is None


class TestBullCallSpread:
    """Test Bull Call Spread strategy signals."""

    def test_entry_signal(self, market_state):
        """Should generate a debit spread entry."""
        strategy = get_strategy("Bull Call Spread")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        assert signal is not None
        assert signal.action == "ENTER"
        assert len(signal.legs) == 2

    def test_one_buy_one_sell(self, market_state):
        """Should have one buy leg and one sell leg."""
        strategy = get_strategy("Bull Call Spread")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        sides = [leg.side for leg in signal.legs]
        assert Side.BUY in sides
        assert Side.SELL in sides

    def test_all_ce_legs(self, market_state):
        """All legs should be CE for a bull call spread."""
        strategy = get_strategy("Bull Call Spread")
        signal = strategy.should_enter(market_state, [], 500000, 65)
        assert all(leg.option_type == OptionType.CE for leg in signal.legs)


class TestDirectionalStrategies:
    """Test directional strategies (Buy CE/PE after +/- day)."""

    def test_ce_after_positive_on_positive_day(self, provider):
        """CE strategy should trigger after a positive day."""
        strategy = get_strategy("Buy CE After Positive Day")
        dates = provider.get_trading_dates(date(2025, 6, 1), date(2025, 6, 30))

        # Day 2 (Jun 3) follows a day with no previous close context from provider
        # Day 3 (Jun 4) follows Jun 3 which was +50 (positive)
        # We need to check the day after a positive day
        for d in dates[1:]:  # Skip first day (no previous close)
            market = provider.get_market_state(datetime.combine(d, datetime.min.time()))
            if market.previous_close and market.underlying_close > market.previous_close:
                # This is a day following a positive day
                # Next day should trigger CE entry
                pass  # The signal check happens on the positive day itself

        # Check that the strategy generates signals on some days
        signals_generated = False
        for d in dates[1:]:
            market = provider.get_market_state(datetime.combine(d, datetime.min.time()))
            signal = strategy.should_enter(market, [], 500000, 65)
            if signal is not None:
                signals_generated = True
                assert signal.legs[0].option_type == OptionType.CE
                assert signal.legs[0].side == Side.BUY
                break

        assert signals_generated, "CE strategy should trigger on at least one positive day"
