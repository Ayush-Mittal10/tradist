"""
Results dashboard UI component.

Displays backtest results: metric cards, statistical warnings,
equity curve, drawdown, P&L distribution, monthly heatmap,
and the full trade table.
"""

from __future__ import annotations

import streamlit as st
import pandas as pd

from core.analytics.metrics import compute_metrics, metrics_to_dict, PerformanceMetrics
from core.analytics.charts import (
    equity_curve,
    drawdown_chart,
    pnl_distribution,
    monthly_returns_heatmap,
    trade_scatter,
)
from core.data_engine.schema import BacktestResult


def render_results(result: BacktestResult, data_warnings: list[str] | None = None):
    """
    Render the complete results dashboard.

    Args:
        result: BacktestResult from the backtest engine
        data_warnings: Warnings from data validation
    """
    all_warnings = (data_warnings or []) + result.warnings

    if not result.trades:
        st.markdown(
            '<div class="section-header">📊 Backtest Completed — 0 Trades Executed</div>',
            unsafe_allow_html=True,
        )
        if all_warnings:
            st.markdown("### ⚠️ Diagnostics & Warnings")
            for warning in all_warnings:
                st.markdown(
                    f'<div class="warning-badge" style="margin-bottom: 0.75rem;">{warning}</div>',
                    unsafe_allow_html=True,
                )

        st.markdown("""
        <div style="
            padding: 1.5rem;
            background: var(--bg-card, #151525);
            border: 1px solid var(--border, #2a2a3e);
            border-radius: 10px;
            margin-top: 1rem;
            line-height: 1.7;
        ">
            <h4 style="color: var(--text-primary, #e8e8f0); margin-bottom: 0.5rem;">💡 Diagnostic Guidance</h4>
            <ul style="color: var(--text-secondary, #8888aa); margin-left: 1rem; line-height: 1.8;">
                <li><b>Margin Requirements:</b> Naked short strategies (Short Straddles & Strangles) require ~₹1.75L SPAN margin per leg (~₹3.5L per straddle lot). If your capital is below this, trades are blocked by the Risk Engine.</li>
                <li><b>Capital Sizing:</b> For Short Straddles with 1 lot, set capital to <b>₹4,50,000+</b>.</li>
                <li><b>Defined-Risk Alternatives:</b> For smaller capital (₹50,000–₹1,00,000), switch to <b>Bull Call Spread</b> or <b>Bear Call Spread</b>, which require only ~₹50,000 margin per lot.</li>
                <li><b>Date Range:</b> Ensure your backtest start and end dates overlap with the timestamps in the uploaded dataset.</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
        return

    # Compute metrics
    metrics = compute_metrics(
        trades=result.trades,
        initial_capital=result.initial_capital,
        equity_curve=result.equity_curve,
        data_warnings=all_warnings,
    )

    # ── Warnings ────────────────────────────────────────────────────
    if metrics.warnings:
        for warning in metrics.warnings:
            st.markdown(
                f'<div class="warning-badge">{warning}</div>',
                unsafe_allow_html=True,
            )
        st.markdown("<br>", unsafe_allow_html=True)

    # ── Top-level metrics ───────────────────────────────────────────
    _render_primary_metrics(metrics)

    st.markdown("<br>", unsafe_allow_html=True)
    _render_secondary_metrics(metrics)

    # ── Charts ──────────────────────────────────────────────────────
    if not result.equity_curve.empty:
        st.markdown("<br>", unsafe_allow_html=True)
        st.plotly_chart(
            equity_curve(result.equity_curve, result.initial_capital),
            width="stretch",
            config={"displayModeBar": False},
        )

    if not result.equity_curve.empty:
        st.plotly_chart(
            drawdown_chart(result.equity_curve),
            width="stretch",
            config={"displayModeBar": False},
        )

    if result.trades:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(
                pnl_distribution(result.trades),
                width="stretch",
                config={"displayModeBar": False},
            )
        with col2:
            st.plotly_chart(
                trade_scatter(result.trades),
                width="stretch",
                config={"displayModeBar": False},
            )

        st.plotly_chart(
            monthly_returns_heatmap(result.trades),
            width="stretch",
            config={"displayModeBar": False},
        )

    # ── Trade table ─────────────────────────────────────────────────
    if result.trades:
        _render_trade_table(result)


def _render_primary_metrics(m: PerformanceMetrics):
    """Render the top row of key metrics."""
    cols = st.columns(4)

    with cols[0]:
        pnl_sign = m.net_pnl >= 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">NET P&L</div>
            <div class="metric-value {'profit' if pnl_sign else 'loss'}">
                ₹{m.net_pnl:+,.0f}
            </div>
            <div class="metric-subtext">on ₹{m.initial_capital:,.0f} capital</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">RETURN</div>
            <div class="metric-value {'profit' if m.return_on_capital >= 0 else 'loss'}">
                {m.return_on_capital:+.1f}%
            </div>
            <div class="metric-subtext">CAGR: {m.cagr:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">WIN RATE</div>
            <div class="metric-value">{m.win_rate:.1f}%</div>
            <div class="metric-subtext">{m.winning_trades}W / {m.losing_trades}L of {m.total_trades} trades</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        dd_color = "loss" if m.max_drawdown_pct > 15 else ""
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">MAX DRAWDOWN</div>
            <div class="metric-value {dd_color}">₹{m.max_drawdown:,.0f}</div>
            <div class="metric-subtext">{m.max_drawdown_pct:.1f}% from peak</div>
        </div>
        """, unsafe_allow_html=True)


def _render_secondary_metrics(m: PerformanceMetrics):
    """Render the secondary metrics row."""
    cols = st.columns(5)

    with cols[0]:
        pf_color = "profit" if m.profit_factor >= 1.5 else ("" if m.profit_factor >= 1.0 else "loss")
        pf_display = f"{m.profit_factor:.2f}" if m.profit_factor < 100 else "∞"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">PROFIT FACTOR</div>
            <div class="metric-value {pf_color}">{pf_display}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        sr_color = "profit" if m.sharpe_ratio > 1 else ("" if m.sharpe_ratio > 0 else "loss")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">SHARPE RATIO</div>
            <div class="metric-value {sr_color}">{m.sharpe_ratio:.2f}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        ev_sign = m.expected_value >= 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">EXPECTED VALUE</div>
            <div class="metric-value {'profit' if ev_sign else 'loss'}">₹{m.expected_value:+,.0f}</div>
            <div class="metric-subtext">per trade</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">AVG WIN / LOSS</div>
            <div class="metric-value">₹{m.avg_win:+,.0f}</div>
            <div class="metric-subtext">Loss: ₹{m.avg_loss:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[4]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">TOTAL COSTS</div>
            <div class="metric-value loss">₹{m.total_costs:,.0f}</div>
            <div class="metric-subtext">{m.avg_trade_duration:.0f} day avg duration</div>
        </div>
        """, unsafe_allow_html=True)


def _render_trade_table(result: BacktestResult):
    """Render the full trade log table."""
    st.markdown('<div class="section-header">📋 Trade Log</div>', unsafe_allow_html=True)

    trade_data = [t.summary_dict() for t in result.trades]
    trade_df = pd.DataFrame(trade_data)

    # Summary row
    st.caption(f"Showing all {len(result.trades)} trades")

    st.dataframe(
        trade_df,
        width="stretch",
        height=min(400, 35 * len(trade_df) + 38),
        hide_index=True,
    )

    # Download button
    csv = trade_df.to_csv(index=False)
    st.download_button(
        label="📥 Download Trade Log (CSV)",
        data=csv,
        file_name=f"trades_{result.strategy_name.replace(' ', '_').lower()}.csv",
        mime="text/csv",
    )
