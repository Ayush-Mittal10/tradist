"""
Paper trading engine.

Drives a strategy with live market data using the SAME strategy
interface as the backtester. The only difference: MarketState comes
from LiveDataProvider instead of HistoricalProvider.

Architecture:
    tick():
        1. Fetch live MarketState from LiveDataProvider
        2. Check exit signals on open positions
        3. Check entry signals if capital allows
        4. Update paper order book
        5. Record equity snapshot
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pandas as pd

from core.data_engine.providers import LiveDataProvider
from core.data_engine.schema import (
    BacktestResult,
    Fill,
    OptionLeg,
    Side,
    Signal,
)
from core.execution_engine.costs import CostPreset
from core.execution_engine.simulator import ExecutionSimulator
from core.risk_engine.risk import RiskEngine
from core.strategy_engine.base import Strategy
from paper_trader.order_book import PaperOrderBook


class PaperTradeEngine:
    """
    Drives a strategy with live market data for paper trading.

    Uses the exact same Strategy interface as BacktestEngine.
    Same code, different data source.
    """

    def __init__(
        self,
        strategy: Strategy,
        live_provider: LiveDataProvider,
        lot_size: int = 65,
        cost_preset: CostPreset = CostPreset.REALISTIC,
    ):
        self.strategy = strategy
        self.provider = live_provider
        self.lot_size = lot_size
        self.cost_preset = cost_preset
        self.simulator = ExecutionSimulator(
            lot_size=lot_size, cost_preset=cost_preset
        )

        # State
        self._order_book: PaperOrderBook | None = None
        self._risk_engine: RiskEngine | None = None
        self._params: dict[str, Any] = {}
        self._start_time: datetime | None = None
        self._tick_count: int = 0
        self._is_running: bool = False

    @property
    def is_running(self) -> bool:
        return self._is_running

    @property
    def order_book(self) -> PaperOrderBook | None:
        return self._order_book

    def start_session(
        self,
        capital: float = 500_000.0,
        params: dict[str, Any] | None = None,
    ) -> None:
        """
        Start a new paper trading session.

        Args:
            capital: Starting capital
            params: Strategy-specific parameters
        """
        self._order_book = PaperOrderBook(
            initial_capital=capital,
            lot_size=self.lot_size,
            cost_preset=self.cost_preset,
        )
        self._risk_engine = RiskEngine(capital)
        self._params = params or {}
        self._start_time = datetime.now()
        self._tick_count = 0
        self._is_running = True

    def tick(self) -> dict:
        """
        Execute one tick of the paper trading loop.

        Called periodically (e.g., every 30 seconds) during market hours.

        Returns:
            Dict with tick summary:
            - action: "ENTRY" | "EXIT" | "HOLD" | "ERROR"
            - details: Description of what happened
        """
        if not self._is_running or self._order_book is None:
            return {"action": "ERROR", "details": "Session not started"}

        self._tick_count += 1
        now = datetime.now()

        try:
            # Fetch live market state
            market = self.provider.get_market_state(now)

            if market.option_chain.empty:
                return {"action": "HOLD", "details": "No market data available"}

            result = {"action": "HOLD", "details": "No signals"}

            # ── Phase 1: Check exits ────────────────────────────────
            for order in list(self._order_book.open_positions):
                position = order.to_position()
                exit_signal = self.strategy.should_exit(
                    market, position, self._params
                )

                if exit_signal is not None and exit_signal.action == "EXIT":
                    exit_fills = self.simulator.execute_signal(
                        exit_signal, market, order.expiry
                    )
                    if exit_fills is not None:
                        trade = self._order_book.close_position(
                            order.order_id, exit_fills, now
                        )
                        if trade:
                            result = {
                                "action": "EXIT",
                                "details": (
                                    f"Closed {order.strategy_name} "
                                    f"P&L: ₹{trade.net_pnl:+,.0f}"
                                ),
                            }

            # ── Phase 2: Check entries ──────────────────────────────
            open_positions = [o.to_position() for o in self._order_book.open_positions]
            entry_signal = self.strategy.should_enter(
                market,
                open_positions,
                self._order_book.current_capital,
                self.lot_size,
                self._params,
            )

            if entry_signal is not None and entry_signal.action == "ENTER":
                expiry = market.get_nearest_expiry()
                entry_fills = self.simulator.execute_signal(
                    entry_signal, market, expiry
                )

                if entry_fills is not None:
                    can_trade, reason = self._risk_engine.can_trade(entry_fills)
                    if can_trade:
                        self._order_book.open_position(
                            fills=entry_fills,
                            strategy_name=self.strategy.name,
                            expiry=expiry,
                            timestamp=now,
                        )
                        self._risk_engine.open_position(entry_fills)

                        entry_cost = sum(
                            f.fill_price * f.lots * f.lot_size
                            for f in entry_fills
                        )
                        result = {
                            "action": "ENTRY",
                            "details": (
                                f"Opened {self.strategy.name} "
                                f"Premium: ₹{entry_cost:,.0f}"
                            ),
                        }
                    else:
                        result = {
                            "action": "ERROR",
                            "details": f"Trade rejected by Risk Engine: {reason}",
                        }

            # ── Record equity snapshot ──────────────────────────────
            unrealized = self._order_book.mark_to_market(market)
            self._order_book.record_equity(now, unrealized)

            return result

        except Exception as e:
            return {"action": "ERROR", "details": str(e)}

    def stop_session(self) -> BacktestResult:
        """
        Stop the paper trading session and return results.

        Returns BacktestResult in the same format as the backtester,
        so all analytics work identically.
        """
        self._is_running = False

        if self._order_book is None:
            return BacktestResult(
                trades=[],
                equity_curve=pd.DataFrame(columns=["timestamp", "capital"]),
                initial_capital=0,
                final_capital=0,
                strategy_name=self.strategy.name,
                start_date=date.today(),
                end_date=date.today(),
                lot_size=self.lot_size,
                cost_preset=self.cost_preset.value,
                warnings=["No session was active"],
            )

        trades = self._order_book.completed_trades
        equity_data = self._order_book.get_equity_snapshots()
        equity_curve = pd.DataFrame(equity_data) if equity_data else pd.DataFrame(columns=["timestamp", "capital"])

        warnings = []
        if self._order_book.open_positions:
            warnings.append(
                f"{len(self._order_book.open_positions)} position(s) still open at session end"
            )

        start_date = self._start_time.date() if self._start_time else date.today()

        return BacktestResult(
            trades=trades,
            equity_curve=equity_curve,
            initial_capital=self._order_book.initial_capital,
            final_capital=self._order_book.current_capital,
            strategy_name=self.strategy.name,
            start_date=start_date,
            end_date=date.today(),
            lot_size=self.lot_size,
            cost_preset=self.cost_preset.value,
            warnings=warnings,
        )

    def get_status(self) -> dict:
        """Get current session status for the UI."""
        if self._order_book is None:
            return {"running": False}

        summary = self._order_book.get_session_summary()
        summary["running"] = self._is_running
        summary["ticks"] = self._tick_count
        summary["strategy"] = self.strategy.name
        summary["start_time"] = self._start_time.isoformat() if self._start_time else None
        return summary
