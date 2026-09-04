"""
Backtest engine: orchestrates historical mode.

Feeds historical market states into a strategy one day at a time,
simulates execution, tracks positions, and produces results.

The key invariant: the strategy NEVER sees data after the current
timestamp. This is enforced by the MarketDataProvider.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from core.data_engine.providers import MarketDataProvider
from core.data_engine.schema import (
    BacktestResult,
    Fill,
    Position,
    Side,
    Trade,
)
from core.execution_engine.costs import CostPreset
from core.execution_engine.simulator import ExecutionSimulator
from core.risk_engine.risk import RiskEngine
from core.strategy_engine.base import Strategy


class BacktestEngine:
    """
    Drives a strategy through historical data, producing BacktestResult.

    Architecture:
        for each trading day:
            1. Build MarketState (only data at or before this day)
            2. Check exit signals on open positions
            3. Check entry signals if capital allows
            4. Record equity
    """

    def __init__(
        self,
        strategy: Strategy,
        data_provider: MarketDataProvider,
        lot_size: int = 65,
        cost_preset: CostPreset = CostPreset.REALISTIC,
    ):
        self.strategy = strategy
        self.data_provider = data_provider
        self.lot_size = lot_size
        self.cost_preset = cost_preset
        self.simulator = ExecutionSimulator(
            lot_size=lot_size, cost_preset=cost_preset
        )

    def run(
        self,
        start_date: date,
        end_date: date,
        initial_capital: float = 500_000.0,
        params: dict[str, Any] | None = None,
    ) -> BacktestResult:
        """
        Run the backtest over the specified date range.

        Args:
            start_date: First trading day (inclusive)
            end_date: Last trading day (inclusive)
            initial_capital: Starting capital in ₹
            params: Strategy-specific parameters

        Returns:
            BacktestResult with trades, equity curve, and metadata
        """
        risk_engine = RiskEngine(initial_capital)
        open_positions: list[Position] = []
        completed_trades: list[Trade] = []
        equity_records: list[dict] = []
        warnings: list[str] = []
        total_entry_signals = 0
        fill_failures = 0
        risk_rejections: dict[str, int] = {}

        trading_dates = self.data_provider.get_trading_dates(start_date, end_date)

        if not trading_dates:
            warnings.append("No trading dates found in the specified range")
            return BacktestResult(
                trades=[],
                equity_curve=pd.DataFrame(columns=["timestamp", "capital"]),
                initial_capital=initial_capital,
                final_capital=initial_capital,
                strategy_name=self.strategy.name,
                start_date=start_date,
                end_date=end_date,
                lot_size=self.lot_size,
                cost_preset=self.cost_preset.value,
                warnings=warnings,
            )

        for current_date in trading_dates:
            timestamp = datetime.combine(current_date, datetime.min.time())

            # Build market state — ONLY data at or before current_date
            market = self.data_provider.get_market_state(timestamp)

            if market.option_chain.empty:
                # No data for this day — skip
                equity_records.append({
                    "timestamp": timestamp,
                    "capital": risk_engine.current_capital,
                })
                continue

            # ── Phase 1: Check exits ────────────────────────────────
            positions_to_close = []
            for position in open_positions:
                exit_signal = self.strategy.should_exit(
                    market, position, params
                )
                if exit_signal is not None and exit_signal.action == "EXIT":
                    # Execute exit
                    exit_fills = self.simulator.execute_signal(
                        exit_signal, market, position.expiry
                    )
                    if exit_fills is not None:
                        # Create completed trade
                        trade = Trade(
                            entry_timestamp=position.entry_timestamp,
                            exit_timestamp=timestamp,
                            strategy_name=self.strategy.name,
                            entry_legs=position.legs,
                            exit_legs=exit_fills,
                            expiry=position.expiry,
                        )
                        completed_trades.append(trade)
                        risk_engine.close_position(position.legs, trade.net_pnl)
                        positions_to_close.append(position)

            # Remove closed positions
            for pos in positions_to_close:
                open_positions.remove(pos)

            # ── Phase 2: Check entries ──────────────────────────────
            entry_signal = self.strategy.should_enter(
                market,
                open_positions,
                risk_engine.current_capital,
                self.lot_size,
                params,
            )

            if entry_signal is not None and entry_signal.action == "ENTER":
                total_entry_signals += 1
                expiry = market.get_nearest_expiry()
                entry_fills = self.simulator.execute_signal(
                    entry_signal, market, expiry
                )

                if entry_fills is not None:
                    # Check risk constraints
                    can_trade, reason = risk_engine.can_trade(entry_fills)
                    if can_trade:
                        position = Position(
                            entry_timestamp=timestamp,
                            strategy_name=self.strategy.name,
                            legs=entry_fills,
                            expiry=expiry,
                        )
                        open_positions.append(position)
                        risk_engine.open_position(entry_fills)
                    else:
                        risk_rejections[reason] = risk_rejections.get(reason, 0) + 1
                else:
                    fill_failures += 1

            # ── Record equity ───────────────────────────────────────
            # Mark-to-market open positions
            mtm_pnl = 0.0
            for pos in open_positions:
                for fill in pos.legs:
                    current_price = market.get_option_price(
                        fill.strike, fill.option_type, pos.expiry
                    )
                    if current_price is not None:
                        if fill.side == Side.SELL:
                            # We sold at fill_price, current cost to buy back = current_price
                            mtm_pnl += (fill.fill_price - current_price) * fill.lots * fill.lot_size
                        else:
                            # We bought at fill_price, current value = current_price
                            mtm_pnl += (current_price - fill.fill_price) * fill.lots * fill.lot_size

            equity_records.append({
                "timestamp": timestamp,
                "capital": risk_engine.current_capital + mtm_pnl,
            })

        # ── Force-close any remaining positions at end ──────────────
        if open_positions:
            last_date = trading_dates[-1]
            last_timestamp = datetime.combine(last_date, datetime.min.time())
            last_market = self.data_provider.get_market_state(last_timestamp)

            for position in open_positions:
                # Build exit signal
                exit_legs = []
                from core.data_engine.schema import OptionLeg
                for fill in position.legs:
                    exit_side = Side.BUY if fill.side == Side.SELL else Side.SELL
                    exit_legs.append(OptionLeg(
                        strike=fill.strike,
                        option_type=fill.option_type,
                        side=exit_side,
                        lots=fill.lots,
                    ))

                from core.data_engine.schema import Signal
                exit_signal = Signal(action="EXIT", legs=exit_legs, reason="End of backtest period")
                exit_fills = self.simulator.execute_signal(
                    exit_signal, last_market, position.expiry
                )

                if exit_fills:
                    trade = Trade(
                        entry_timestamp=position.entry_timestamp,
                        exit_timestamp=last_timestamp,
                        strategy_name=self.strategy.name,
                        entry_legs=position.legs,
                        exit_legs=exit_fills,
                        expiry=position.expiry,
                    )
                    completed_trades.append(trade)
                    risk_engine.close_position(position.legs, trade.net_pnl)

        # ── Diagnostics for empty trades or rejected entries ────────
        if len(completed_trades) == 0:
            if risk_rejections:
                for reason, count in risk_rejections.items():
                    warnings.append(
                        f"0 trades executed: {count} entry attempt(s) blocked by Risk Engine ({reason}). "
                        f"Short option positions require SPAN margin (~₹1.75L per naked leg, ~₹3.5L per straddle). "
                        f"Try increasing initial capital or switching to a defined-risk spread."
                    )
            elif total_entry_signals == 0:
                warnings.append(
                    f"0 trades executed: '{self.strategy.name}' generated no entry signals in the selected date range. "
                    f"Check strategy parameters or date range."
                )
            elif fill_failures > 0:
                warnings.append(
                    f"0 trades executed: {fill_failures} entry attempt(s) could not be filled "
                    f"(missing option price data in chain for required strikes)."
                )
        elif risk_rejections:
            for reason, count in risk_rejections.items():
                warnings.append(f"{count} additional entry attempt(s) blocked by Risk Engine: {reason}")

        # ── Build equity curve DataFrame ────────────────────────────
        equity_curve = pd.DataFrame(equity_records)
        if equity_curve.empty:
            equity_curve = pd.DataFrame(columns=["timestamp", "capital"])

        final_capital = risk_engine.current_capital

        return BacktestResult(
            trades=completed_trades,
            equity_curve=equity_curve,
            initial_capital=initial_capital,
            final_capital=final_capital,
            strategy_name=self.strategy.name,
            start_date=start_date,
            end_date=end_date,
            lot_size=self.lot_size,
            cost_preset=self.cost_preset.value,
            warnings=warnings,
        )
