"""
Tests for paper trading engine, paper order book, and trading session.

Verifies:
- PaperOrder and PaperOrderBook state, position tracking, capital debit/credit, and MTM P&L
- PaperTradeEngine tick loop, entry/exit signal execution, equity snapshotting
- Compatibility: PaperTradeEngine produces BacktestResult that integrates seamlessly with analytics
- TradingSession start/stop lifecycle and market hours checks
"""

from __future__ import annotations

from datetime import date, datetime, time as dt_time, timedelta
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from core.analytics.metrics import compute_metrics
from core.data_engine.providers import LiveDataProvider
from core.data_engine.schema import (
    BacktestResult,
    Fill,
    MarketState,
    OptionLeg,
    OptionType,
    Position,
    Side,
    Signal,
    Trade,
)
from core.execution_engine.costs import CostPreset
from core.strategy_engine.base import Strategy
from paper_trader.engine import PaperTradeEngine
from paper_trader.order_book import PaperOrder, PaperOrderBook
from paper_trader.session import TradingSession


# ── Helpers & Dummy Strategy ──────────────────────────────────────────


class MockStrategy(Strategy):
    """A deterministic test strategy that triggers entry then exit."""

    def __init__(self, name="MockStrategy", description="Test Mock Strategy"):
        self._name = name
        self._description = description
        self.entry_called = 0
        self.exit_called = 0
        self.should_enter_signal = True
        self.should_exit_signal = False

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    def should_enter(self, market_state, open_positions, capital, lot_size, params):
        self.entry_called += 1
        if self.should_enter_signal and len(open_positions) == 0:
            return Signal(
                action="ENTER",
                legs=[
                    OptionLeg(strike=24500.0, option_type=OptionType.CE, side=Side.SELL, lots=1),
                    OptionLeg(strike=24500.0, option_type=OptionType.PE, side=Side.SELL, lots=1),
                ],
                reason="Sell ATM straddle",
            )
        return Signal(action="HOLD")

    def should_exit(self, market_state, position, params):
        self.exit_called += 1
        if self.should_exit_signal:
            return Signal(
                action="EXIT",
                legs=[
                    OptionLeg(strike=24500.0, option_type=OptionType.CE, side=Side.BUY, lots=1),
                    OptionLeg(strike=24500.0, option_type=OptionType.PE, side=Side.BUY, lots=1),
                ],
                reason="Target reached",
            )
        return Signal(action="HOLD")


def create_sample_market_state(
    nifty_close: float = 24500.0,
    ce_price: float = 120.0,
    pe_price: float = 110.0,
    timestamp: datetime | None = None,
) -> MarketState:
    ts = timestamp or datetime(2026, 9, 4, 10, 0, 0)
    expiry = pd.Timestamp(ts.date() + timedelta(days=5))

    df = pd.DataFrame([
        {
            "timestamp": ts,
            "underlying": "NIFTY",
            "underlying_close": nifty_close,
            "expiry": expiry,
            "strike": 24500.0,
            "option_type": "CE",
            "open": ce_price,
            "high": ce_price + 5,
            "low": ce_price - 5,
            "close": ce_price,
            "volume": 10000,
            "oi": 50000,
            "bid": ce_price - 0.5,
            "ask": ce_price + 0.5,
        },
        {
            "timestamp": ts,
            "underlying": "NIFTY",
            "underlying_close": nifty_close,
            "expiry": expiry,
            "strike": 24500.0,
            "option_type": "PE",
            "open": pe_price,
            "high": pe_price + 5,
            "low": pe_price - 5,
            "close": pe_price,
            "volume": 10000,
            "oi": 50000,
            "bid": pe_price - 0.5,
            "ask": pe_price + 0.5,
        },
    ])

    return MarketState(
        timestamp=ts,
        underlying="NIFTY",
        underlying_close=nifty_close,
        option_chain=df,
    )


# ── Test PaperOrder & PaperOrderBook ──────────────────────────────────


class TestPaperOrderBook:
    """Test order book position management, cash accounting, and MTM P&L."""

    def test_open_position_sell(self):
        book = PaperOrderBook(initial_capital=500_000.0, lot_size=65)
        now = datetime.now()
        expiry = (now + timedelta(days=5)).date()

        fills = [
            Fill(
                timestamp=now,
                strike=24500.0,
                option_type=OptionType.CE,
                side=Side.SELL,
                lots=1,
                fill_price=100.0,
                lot_size=65,
                brokerage=20.0,
                exchange_charges=5.0,
            ),
        ]

        order = book.open_position(fills, strategy_name="ShortCall", expiry=expiry, timestamp=now)

        assert order.status == "OPEN"
        assert len(book.open_positions) == 1
        assert order.order_id in book._orders
        # Selling receives premium (100 * 1 * 65 = 6500) minus costs (25) = +6475
        expected_capital = 500_000.0 + 6500.0 - 25.0
        assert pytest.approx(book.current_capital, 0.01) == expected_capital

    def test_open_position_buy(self):
        book = PaperOrderBook(initial_capital=500_000.0, lot_size=65)
        now = datetime.now()
        expiry = (now + timedelta(days=5)).date()

        fills = [
            Fill(
                timestamp=now,
                strike=24500.0,
                option_type=OptionType.CE,
                side=Side.BUY,
                lots=1,
                fill_price=100.0,
                lot_size=65,
                brokerage=20.0,
            ),
        ]

        order = book.open_position(fills, strategy_name="LongCall", expiry=expiry, timestamp=now)

        assert order.status == "OPEN"
        # Buying debits premium (6500) + costs (20) = -6520
        expected_capital = 500_000.0 - 6520.0
        assert pytest.approx(book.current_capital, 0.01) == expected_capital

    def test_close_position_realizes_pnl(self):
        book = PaperOrderBook(initial_capital=500_000.0, lot_size=65)
        now = datetime.now()
        expiry = (now + timedelta(days=5)).date()

        entry_fills = [
            Fill(
                timestamp=now,
                strike=24500.0,
                option_type=OptionType.CE,
                side=Side.SELL,
                lots=1,
                fill_price=100.0,
                lot_size=65,
                brokerage=20.0,
            ),
        ]
        order = book.open_position(entry_fills, strategy_name="ShortCall", expiry=expiry, timestamp=now)

        later = now + timedelta(hours=2)
        # Buy back at lower price 60.0 (profit: (100 - 60) * 65 = 2600 gross)
        exit_fills = [
            Fill(
                timestamp=later,
                strike=24500.0,
                option_type=OptionType.CE,
                side=Side.BUY,
                lots=1,
                fill_price=60.0,
                lot_size=65,
                brokerage=20.0,
            ),
        ]

        trade = book.close_position(order.order_id, exit_fills, timestamp=later)

        assert trade is not None
        assert order.status == "CLOSED"
        assert len(book.open_positions) == 0
        assert len(book.completed_trades) == 1
        assert trade.gross_pnl == pytest.approx(2600.0, 0.01)
        assert trade.total_costs == pytest.approx(40.0, 0.01)
        assert trade.net_pnl == pytest.approx(2560.0, 0.01)
        assert trade.is_winner

        # Check total capital = initial_capital + net_pnl
        assert pytest.approx(book.current_capital, 0.01) == 500_000.0 + 2560.0

    def test_mark_to_market(self):
        book = PaperOrderBook(initial_capital=500_000.0, lot_size=65)
        now = datetime.now()
        expiry = (now + timedelta(days=5)).date()

        fills = [
            Fill(
                timestamp=now,
                strike=24500.0,
                option_type=OptionType.CE,
                side=Side.SELL,
                lots=1,
                fill_price=100.0,
                lot_size=65,
            ),
        ]
        book.open_position(fills, strategy_name="ShortCall", expiry=expiry, timestamp=now)

        # Market price dropped to 80 -> gain of (100 - 80) * 65 = 1300
        market = create_sample_market_state(ce_price=80.0, timestamp=now)
        # Set market expiry to match order.expiry
        market.option_chain["expiry"] = pd.Timestamp(expiry)

        unrealized = book.mark_to_market(market)
        assert pytest.approx(unrealized, 0.01) == 1300.0

    def test_session_summary(self):
        book = PaperOrderBook(initial_capital=500_000.0, lot_size=65)
        summary = book.get_session_summary()

        assert summary["initial_capital"] == 500_000.0
        assert summary["realized_pnl"] == 0.0
        assert summary["open_positions"] == 0
        assert summary["completed_trades"] == 0


# ── Test PaperTradeEngine ─────────────────────────────────────────────


class TestPaperTradeEngine:
    """Test tick execution loop, entries, exits, and result generation."""

    def test_tick_before_start_returns_error(self):
        strategy = MockStrategy()
        provider = MagicMock(spec=LiveDataProvider)
        engine = PaperTradeEngine(strategy=strategy, live_provider=provider)

        result = engine.tick()
        assert result["action"] == "ERROR"

    def test_tick_entry_and_exit_lifecycle(self):
        strategy = MockStrategy()
        provider = MagicMock(spec=LiveDataProvider)

        market_entry = create_sample_market_state(ce_price=120.0, pe_price=110.0)
        provider.get_market_state.return_value = market_entry

        engine = PaperTradeEngine(
            strategy=strategy,
            live_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.ZERO,
        )
        engine.start_session(capital=500_000.0)

        # First tick: should enter position
        res1 = engine.tick()
        assert res1["action"] == "ENTRY"
        assert len(engine.order_book.open_positions) == 1

        # Second tick: hold (no exit signal yet)
        strategy.should_enter_signal = False
        res2 = engine.tick()
        assert res2["action"] == "HOLD"
        assert len(engine.order_book.open_positions) == 1

        # Third tick: trigger exit
        strategy.should_exit_signal = True
        market_exit = create_sample_market_state(ce_price=90.0, pe_price=80.0)
        provider.get_market_state.return_value = market_exit

        res3 = engine.tick()
        assert res3["action"] == "EXIT"
        assert len(engine.order_book.open_positions) == 0
        assert len(engine.order_book.completed_trades) == 1

    def test_stop_session_produces_valid_backtest_result(self):
        strategy = MockStrategy()
        provider = MagicMock(spec=LiveDataProvider)

        market = create_sample_market_state(ce_price=100.0, pe_price=100.0)
        provider.get_market_state.return_value = market

        engine = PaperTradeEngine(
            strategy=strategy,
            live_provider=provider,
            lot_size=65,
            cost_preset=CostPreset.REALISTIC,
        )
        engine.start_session(capital=500_000.0)
        engine.tick()

        # Stop session
        backtest_result = engine.stop_session()

        assert isinstance(backtest_result, BacktestResult)
        assert backtest_result.strategy_name == strategy.name
        assert backtest_result.initial_capital == 500_000.0
        assert backtest_result.lot_size == 65
        assert isinstance(backtest_result.equity_curve, pd.DataFrame)
        assert "capital" in backtest_result.equity_curve.columns

        # Verify it can be passed directly to compute_metrics without error
        metrics = compute_metrics(
            trades=backtest_result.trades,
            initial_capital=backtest_result.initial_capital,
            equity_curve=backtest_result.equity_curve,
        )
        assert metrics is not None


# ── Test TradingSession ───────────────────────────────────────────────


class TestTradingSession:
    """Test TradingSession lifecycle, market hours, and manual tick."""

    def test_manual_tick(self):
        strategy = MockStrategy()
        strategy.should_enter_signal = False

        provider = MagicMock(spec=LiveDataProvider)
        market = create_sample_market_state()
        provider.get_market_state.return_value = market

        session = TradingSession(
            strategy=strategy,
            live_provider=provider,
            poll_interval=10,
        )
        session.engine.start_session(capital=500_000.0)

        tick_res = session.manual_tick()
        assert tick_res["action"] == "HOLD"
        assert len(session.tick_log) == 1

    def test_start_and_stop_lifecycle(self):
        strategy = MockStrategy()
        strategy.should_enter_signal = False

        provider = MagicMock(spec=LiveDataProvider)
        provider.get_market_state.return_value = create_sample_market_state()

        session = TradingSession(
            strategy=strategy,
            live_provider=provider,
            poll_interval=1,
        )

        session.start(capital=500_000.0)
        assert session.is_running
        assert session._thread is not None and session._thread.is_alive()

        # Stop session
        result = session.stop()
        assert not session.is_running
        assert isinstance(result, BacktestResult)

    def test_is_market_open(self):
        # Weekend check: Saturday (weekday=5) or Sunday (weekday=6)
        with patch("paper_trader.session.datetime") as mock_dt:
            # Mock Saturday
            mock_dt.now.return_value = datetime(2026, 9, 5, 11, 0, 0)
            assert not TradingSession.is_market_open()

            # Mock Wednesday at 10:30 AM (open)
            mock_dt.now.return_value = datetime(2026, 9, 2, 10, 30, 0)
            assert TradingSession.is_market_open()

            # Mock Wednesday at 8:30 AM (before open)
            mock_dt.now.return_value = datetime(2026, 9, 2, 8, 30, 0)
            assert not TradingSession.is_market_open()

            # Mock Wednesday at 4:00 PM (after close)
            mock_dt.now.return_value = datetime(2026, 9, 2, 16, 0, 0)
            assert not TradingSession.is_market_open()
