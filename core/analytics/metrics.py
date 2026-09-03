"""
Performance metrics calculation.

Computes all quantitative metrics from a list of completed trades,
plus generates statistical confidence warnings.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import numpy as np
import pandas as pd

from core.data_engine.schema import Trade


@dataclass
class PerformanceMetrics:
    """Complete performance metrics for a backtest."""
    # P&L
    total_pnl: float = 0.0
    total_costs: float = 0.0
    gross_pnl: float = 0.0
    net_pnl: float = 0.0

    # Returns
    return_on_capital: float = 0.0          # %
    cagr: float = 0.0                       # %

    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0                   # %

    # P&L distribution
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    median_pnl: float = 0.0

    # Risk-adjusted
    profit_factor: float = 0.0
    sharpe_ratio: float = 0.0
    expected_value: float = 0.0             # Per trade

    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0           # %

    # Duration
    avg_trade_duration: float = 0.0         # days
    total_days: int = 0

    # Capital
    initial_capital: float = 0.0
    final_capital: float = 0.0

    # Warnings
    warnings: list[str] = field(default_factory=list)


def compute_metrics(
    trades: list[Trade],
    initial_capital: float,
    equity_curve: pd.DataFrame | None = None,
    risk_free_rate: float = 0.07,           # India 10Y ~7%
    data_warnings: list[str] | None = None,
) -> PerformanceMetrics:
    """
    Compute comprehensive performance metrics from trade results.

    Args:
        trades: List of completed trades
        initial_capital: Starting capital
        equity_curve: DataFrame with 'timestamp' and 'capital' columns
        risk_free_rate: Annual risk-free rate (default 7% for India)
        data_warnings: Warnings from data validation to include

    Returns:
        PerformanceMetrics with all computed fields
    """
    m = PerformanceMetrics()
    m.initial_capital = initial_capital
    m.total_trades = len(trades)

    if not trades:
        m.final_capital = initial_capital
        m.warnings.append("No trades executed")
        return m

    # ── P&L calculations ────────────────────────────────────────────
    pnls = [t.net_pnl for t in trades]
    gross_pnls = [t.gross_pnl for t in trades]
    costs = [t.total_costs for t in trades]

    m.net_pnl = sum(pnls)
    m.gross_pnl = sum(gross_pnls)
    m.total_costs = sum(costs)
    m.total_pnl = m.net_pnl
    m.final_capital = initial_capital + m.net_pnl

    # ── Returns ─────────────────────────────────────────────────────
    m.return_on_capital = (m.net_pnl / initial_capital * 100) if initial_capital > 0 else 0

    # CAGR
    first_date = min(t.entry_timestamp for t in trades).date()
    last_date = max(t.exit_timestamp for t in trades).date()
    m.total_days = (last_date - first_date).days
    years = m.total_days / 365.25 if m.total_days > 0 else 1

    if m.final_capital > 0 and initial_capital > 0 and years > 0:
        m.cagr = ((m.final_capital / initial_capital) ** (1 / years) - 1) * 100
    else:
        m.cagr = 0.0

    # ── Trade statistics ────────────────────────────────────────────
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p <= 0]

    m.winning_trades = len(winners)
    m.losing_trades = len(losers)
    m.win_rate = (m.winning_trades / m.total_trades * 100) if m.total_trades > 0 else 0

    m.avg_win = float(np.mean(winners)) if winners else 0
    m.avg_loss = float(np.mean(losers)) if losers else 0
    m.largest_win = max(pnls) if pnls else 0
    m.largest_loss = min(pnls) if pnls else 0
    m.median_pnl = float(np.median(pnls))

    # ── Risk-adjusted metrics ───────────────────────────────────────
    gross_profit = sum(winners) if winners else 0
    gross_loss = abs(sum(losers)) if losers else 0
    m.profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf")

    # Expected value per trade
    if m.total_trades > 0:
        win_pct = m.winning_trades / m.total_trades
        loss_pct = m.losing_trades / m.total_trades
        m.expected_value = (win_pct * m.avg_win) + (loss_pct * m.avg_loss)

    # Sharpe ratio (annualized)
    if len(pnls) > 1:
        daily_returns = np.array(pnls) / initial_capital
        excess_returns = daily_returns - (risk_free_rate / 252)  # Daily risk-free
        if np.std(excess_returns) > 0:
            # Annualize: assume each trade is roughly one period
            trades_per_year = m.total_trades / years if years > 0 else m.total_trades
            m.sharpe_ratio = (
                float(np.mean(excess_returns) / np.std(excess_returns))
                * np.sqrt(trades_per_year)
            )

    # ── Drawdown ────────────────────────────────────────────────────
    if equity_curve is not None and not equity_curve.empty:
        capital_series = equity_curve["capital"].values
        peak = np.maximum.accumulate(capital_series)
        drawdown = peak - capital_series
        m.max_drawdown = float(np.max(drawdown))
        if np.max(peak) > 0:
            m.max_drawdown_pct = float(np.max(drawdown / peak) * 100)
    else:
        # Compute from trades
        running_capital = initial_capital
        peak = initial_capital
        max_dd = 0
        for t in trades:
            running_capital += t.net_pnl
            if running_capital > peak:
                peak = running_capital
            dd = peak - running_capital
            if dd > max_dd:
                max_dd = dd
        m.max_drawdown = max_dd
        m.max_drawdown_pct = (max_dd / peak * 100) if peak > 0 else 0

    # ── Duration ────────────────────────────────────────────────────
    durations = [t.duration_days for t in trades]
    m.avg_trade_duration = float(np.mean(durations)) if durations else 0

    # ── Warnings ────────────────────────────────────────────────────
    if data_warnings:
        m.warnings.extend(data_warnings)

    if m.total_trades < 10:
        m.warnings.append(
            f"⚠️ Only {m.total_trades} trades — no statistical significance whatsoever"
        )
    elif m.total_trades < 30:
        m.warnings.append(
            f"⚠️ {m.total_trades} trades only — statistical confidence is very low"
        )
    elif m.total_trades < 100:
        m.warnings.append(
            f"⚠️ {m.total_trades} trades — limited sample, results may not generalize"
        )

    if m.total_days < 180:
        m.warnings.append(
            "⚠️ Less than 6 months of data — insufficient for reliable conclusions"
        )

    if m.max_drawdown_pct > 30:
        m.warnings.append(
            f"⚠️ Max drawdown of {m.max_drawdown_pct:.1f}% — very high risk"
        )

    if m.profit_factor < 1.0 and m.total_trades > 10:
        m.warnings.append(
            "⚠️ Profit factor < 1.0 — this strategy loses money on average"
        )

    return m


def format_currency(value: float) -> str:
    """Format a value as Indian rupees."""
    if abs(value) >= 1_00_000:
        return f"₹{value:+,.0f}"
    return f"₹{value:+,.2f}"


def metrics_to_dict(m: PerformanceMetrics) -> dict[str, str]:
    """Convert metrics to a display-friendly dictionary."""
    return {
        "Total Return": format_currency(m.net_pnl),
        "Return on Capital": f"{m.return_on_capital:+.1f}%",
        "CAGR": f"{m.cagr:.1f}%",
        "Total Trades": str(m.total_trades),
        "Win Rate": f"{m.win_rate:.1f}%",
        "Profit Factor": f"{m.profit_factor:.2f}" if m.profit_factor < 100 else "∞",
        "Sharpe Ratio": f"{m.sharpe_ratio:.2f}",
        "Expected Value": format_currency(m.expected_value) + " / trade",
        "Avg Win": format_currency(m.avg_win),
        "Avg Loss": format_currency(m.avg_loss),
        "Largest Win": format_currency(m.largest_win),
        "Largest Loss": format_currency(m.largest_loss),
        "Max Drawdown": format_currency(-m.max_drawdown),
        "Max Drawdown %": f"{m.max_drawdown_pct:.1f}%",
        "Avg Duration": f"{m.avg_trade_duration:.1f} days",
        "Total Costs": format_currency(-m.total_costs),
        "Initial Capital": f"₹{m.initial_capital:,.0f}",
        "Final Capital": f"₹{m.final_capital:,.0f}",
    }
