"""
Prediction vs Reality: model calibration tracking.

For each trade, compares what Monte Carlo predicted (probability of profit,
expected move) against what actually happened. Over many trades, this
reveals whether our probability model is well-calibrated.

If the model says "70% chance of profit" but only 55% of such trades
actually profit, the model is overconfident — a critical discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from core.data_engine.schema import Trade, OptionLeg, OptionType, Side
from core.research.monte_carlo import quick_pop, analyze_position


@dataclass
class TradeCalibration:
    """Calibration data for a single trade."""
    trade: Trade
    predicted_pop: float            # Monte Carlo predicted probability of profit
    actual_profitable: bool         # Did the trade actually profit?
    predicted_expected_move: float  # ±1σ expected move
    actual_move: float              # What underlying actually did
    within_expected: bool           # Was actual move inside ±1σ?


@dataclass
class CalibrationReport:
    """Aggregate calibration across many trades."""
    calibrations: list[TradeCalibration]

    # Calibration table: predicted bucket → actual frequency
    calibration_table: dict[str, dict[str, float]]
    # e.g. {"50%": {"predicted": 50, "actual": 52.3, "count": 45}, ...}

    # Overall scores
    calibration_score: str          # "GOOD", "FAIR", "POOR"
    mean_absolute_error: float      # Avg |predicted - actual| across buckets
    total_trades: int
    trades_with_prediction: int


def calibrate_trades(
    trades: list[Trade],
    underlying_prices: pd.Series | None = None,
    volatility: float = 0.15,
    lot_size: int = 65,
    r: float = 0.07,
) -> CalibrationReport:
    """
    Run calibration analysis on completed trades.

    For each trade, retrospectively compute what Monte Carlo would have
    predicted at entry time, then compare against the actual outcome.

    Args:
        trades: List of completed trades
        underlying_prices: Historical underlying close prices (indexed by date)
        volatility: Volatility to use for MC simulation (ideally from IV at entry)
        lot_size: Contract lot size
        r: Risk-free rate

    Returns:
        CalibrationReport with per-trade calibrations and aggregate table
    """
    calibrations: list[TradeCalibration] = []

    for trade in trades:
        try:
            # Reconstruct position at entry
            legs: list[OptionLeg] = []
            entry_prices: dict[tuple[float, str], float] = {}

            for fill in trade.entry_legs:
                legs.append(OptionLeg(
                    strike=fill.strike,
                    option_type=fill.option_type,
                    side=fill.side,
                    lots=fill.lots,
                ))
                entry_prices[(fill.strike, fill.option_type.value)] = fill.fill_price

            # Get underlying price at entry
            S0 = 0.0
            if underlying_prices is not None:
                entry_date = trade.entry_timestamp.date()
                # Find nearest date in the series
                if hasattr(underlying_prices.index, 'date'):
                    dates = underlying_prices.index.date if hasattr(underlying_prices.index, 'date') else underlying_prices.index
                    mask = pd.Series(dates) <= entry_date
                    if mask.any():
                        S0 = float(underlying_prices.iloc[mask.values.argmax()])

            # If no underlying price found, try to infer from strikes
            if S0 <= 0:
                S0 = float(np.mean([f.strike for f in trade.entry_legs]))

            # Time to expiry at entry
            T = max((trade.expiry - trade.entry_timestamp.date()).days / 365.25, 1e-6)

            # Run Monte Carlo prediction
            mc_result = analyze_position(
                S0=S0, sigma=volatility, T=T,
                legs=legs, entry_prices=entry_prices,
                lot_size=lot_size, r=r,
                n_paths=50_000, seed=42,
            )

            # What actually happened
            actual_move = 0.0
            if underlying_prices is not None:
                exit_date = trade.exit_timestamp.date()
                if hasattr(underlying_prices.index, 'date'):
                    dates = underlying_prices.index.date if hasattr(underlying_prices.index, 'date') else underlying_prices.index
                    exit_mask = pd.Series(dates) <= exit_date
                    if exit_mask.any():
                        S_exit = float(underlying_prices.iloc[exit_mask.values.argmax()])
                        actual_move = S_exit - S0

            calibrations.append(TradeCalibration(
                trade=trade,
                predicted_pop=mc_result.probability_of_profit,
                actual_profitable=trade.is_winner,
                predicted_expected_move=mc_result.expected_move,
                actual_move=actual_move,
                within_expected=abs(actual_move) <= mc_result.expected_move,
            ))

        except Exception:
            continue

    # Build calibration table
    calibration_table = _build_calibration_table(calibrations)
    mae = _compute_mae(calibration_table)

    if mae < 5:
        score = "GOOD"
    elif mae < 10:
        score = "FAIR"
    else:
        score = "POOR"

    return CalibrationReport(
        calibrations=calibrations,
        calibration_table=calibration_table,
        calibration_score=score,
        mean_absolute_error=mae,
        total_trades=len(trades),
        trades_with_prediction=len(calibrations),
    )


def _build_calibration_table(
    calibrations: list[TradeCalibration],
) -> dict[str, dict[str, float]]:
    """
    Build predicted-vs-actual frequency table.

    Groups trades by predicted PoP bucket (50%, 60%, 70%, 80%, 90%)
    and computes the actual win rate in each bucket.
    """
    buckets = [
        (40, 55, "50%"),
        (55, 65, "60%"),
        (65, 75, "70%"),
        (75, 85, "80%"),
        (85, 100, "90%"),
    ]

    table = {}
    for low, high, label in buckets:
        in_bucket = [c for c in calibrations if low <= c.predicted_pop < high]
        if len(in_bucket) >= 3:  # Need at least 3 trades for meaningful stat
            actual_rate = sum(1 for c in in_bucket if c.actual_profitable) / len(in_bucket) * 100
            table[label] = {
                "predicted": (low + high) / 2,
                "actual": actual_rate,
                "count": len(in_bucket),
            }

    return table


def _compute_mae(table: dict[str, dict[str, float]]) -> float:
    """Mean absolute error between predicted and actual across buckets."""
    if not table:
        return 0.0
    errors = [abs(v["predicted"] - v["actual"]) for v in table.values()]
    return float(np.mean(errors))
