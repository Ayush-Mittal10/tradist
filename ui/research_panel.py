"""
Research panel UI component.

Displays Monte Carlo probability analysis, Greeks table,
volatility dashboard, and model calibration results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core.analytics.charts import COLORS, _apply_layout
from core.data_engine.schema import BacktestResult, OptionLeg, OptionType, Side
from core.research.monte_carlo import analyze_position, MonteCarloResult
from core.research.volatility import (
    VolatilityAnalysis,
    VolRegime,
    analyze_volatility,
    realized_volatility,
)
from core.research.black_scholes import enrich_chain
from core.research.calibration import calibrate_trades, CalibrationReport


def render_research_panel(
    result: BacktestResult,
    df: pd.DataFrame | None = None,
):
    """
    Render the full research panel below backtest results.

    Args:
        result: BacktestResult from the backtest engine
        df: The full canonical dataset (for vol analysis)
    """
    st.markdown(
        '<div class="section-header">🔬 Research Analysis</div>',
        unsafe_allow_html=True,
    )

    if not result.trades:
        st.info("No trades to analyze. Run a backtest first.")
        return

    # ── Research controls ───────────────────────────────────────────
    col1, col2, col3 = st.columns(3)
    with col1:
        n_paths = st.selectbox(
            "Monte Carlo paths",
            [10_000, 50_000, 100_000, 500_000],
            index=2,
            format_func=lambda x: f"{x:,}",
        )
    with col2:
        risk_free = st.number_input(
            "Risk-free rate (%)",
            min_value=0.0, max_value=20.0,
            value=7.0, step=0.5,
        ) / 100
    with col3:
        vol_source = st.selectbox(
            "Volatility source",
            ["From data (RV-20)", "Manual"],
        )

    manual_vol = 0.15
    if vol_source == "Manual":
        manual_vol = st.slider("Volatility (%)", 5, 80, 15) / 100

    # ── Volatility Dashboard ────────────────────────────────────────
    if df is not None and "underlying_close" in df.columns:
        _render_volatility_dashboard(df, risk_free)

    # ── Monte Carlo on representative trade ─────────────────────────
    _render_monte_carlo_analysis(result, df, n_paths, risk_free, vol_source, manual_vol)

    # ── Greeks Table ────────────────────────────────────────────────
    if df is not None:
        _render_greeks_table(df, result, risk_free)

    # ── Calibration ─────────────────────────────────────────────────
    if len(result.trades) >= 10:
        _render_calibration(result, df, manual_vol, risk_free)


def _render_volatility_dashboard(df: pd.DataFrame, r: float):
    """Render volatility analysis section."""
    st.markdown("#### 📊 Volatility Dashboard")

    # Extract underlying prices
    underlying = df.groupby(df["timestamp"].dt.date)["underlying_close"].first()
    underlying = underlying.dropna()

    if len(underlying) < 25:
        st.caption("Not enough data for volatility analysis (need 25+ trading days)")
        return

    # Get option chain for latest date
    latest_date = df["timestamp"].dt.date.max()
    latest_chain = df[df["timestamp"].dt.date == latest_date]
    latest_price = float(underlying.iloc[-1])

    vol_analysis = analyze_volatility(
        underlying_prices=underlying,
        option_chain=latest_chain if not latest_chain.empty else None,
        underlying_price=latest_price,
        r=r,
    )

    # Metrics row
    cols = st.columns(5)

    with cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">ATM IV</div>
            <div class="metric-value">{vol_analysis.current_iv*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">RV (20D)</div>
            <div class="metric-value">{vol_analysis.current_rv_20*100:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        spread_color = "profit" if vol_analysis.iv_rv_spread > 0 else "loss"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">IV-RV SPREAD</div>
            <div class="metric-value {spread_color}">
                {vol_analysis.iv_rv_spread*100:+.1f}%
            </div>
            <div class="metric-subtext">
                {'IV overpriced' if vol_analysis.iv_rv_spread > 0 else 'IV underpriced'}
            </div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">IV PERCENTILE</div>
            <div class="metric-value">{vol_analysis.iv_percentile:.0f}th</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[4]:
        regime_colors = {
            VolRegime.LOW: "#4f8cff",
            VolRegime.NORMAL: "#00d26a",
            VolRegime.HIGH: "#ffa502",
            VolRegime.EXTREME: "#ff4757",
        }
        rc = regime_colors.get(vol_analysis.regime, "#fff")
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">REGIME</div>
            <div class="metric-value" style="color: {rc};">{vol_analysis.regime.value}</div>
        </div>
        """, unsafe_allow_html=True)

    st.caption(vol_analysis.regime_description)

    # RV time series chart
    if vol_analysis.rv_history is not None and not vol_analysis.rv_history.empty:
        fig = go.Figure()
        rv_series = vol_analysis.rv_history.dropna()
        fig.add_trace(go.Scatter(
            x=rv_series.index if hasattr(rv_series.index, '__iter__') else list(range(len(rv_series))),
            y=rv_series.values * 100,
            mode="lines",
            name="Realized Vol (20D)",
            line=dict(color=COLORS["accent"], width=2),
        ))
        _apply_layout(fig, "Realized Volatility (20-Day)")
        fig.update_yaxes(title_text="Volatility (%)", ticksuffix="%")
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    st.markdown("---")


def _render_monte_carlo_analysis(
    result: BacktestResult,
    df: pd.DataFrame | None,
    n_paths: int,
    r: float,
    vol_source: str,
    manual_vol: float,
):
    """Run and render Monte Carlo analysis on the first or selected trade."""
    st.markdown("#### 🎲 Monte Carlo Probability Analysis")

    if not result.trades:
        return

    # Use the first trade as a representative example
    trade = result.trades[0]

    # Reconstruct position
    legs = []
    entry_prices = {}
    for fill in trade.entry_legs:
        legs.append(OptionLeg(
            strike=fill.strike,
            option_type=fill.option_type,
            side=fill.side,
            lots=fill.lots,
        ))
        entry_prices[(fill.strike, fill.option_type.value)] = fill.fill_price

    # Get underlying price at entry
    S0 = float(np.mean([f.strike for f in trade.entry_legs]))
    if df is not None and "underlying_close" in df.columns:
        entry_data = df[df["timestamp"].dt.date == trade.entry_timestamp.date()]
        if not entry_data.empty:
            uc = entry_data["underlying_close"].dropna()
            if not uc.empty:
                S0 = float(uc.iloc[0])

    # Determine volatility
    sigma = manual_vol
    if vol_source == "From data (RV-20)" and df is not None:
        underlying = df.groupby(df["timestamp"].dt.date)["underlying_close"].first().dropna()
        rv = realized_volatility(underlying, window=20)
        rv_valid = rv.dropna()
        if not rv_valid.empty:
            sigma = float(rv_valid.iloc[-1])
            if sigma <= 0:
                sigma = manual_vol

    T = max((trade.expiry - trade.entry_timestamp.date()).days / 365.25, 1e-6)

    with st.spinner(f"Running {n_paths:,} Monte Carlo simulations..."):
        mc = analyze_position(
            S0=S0, sigma=sigma, T=T,
            legs=legs, entry_prices=entry_prices,
            lot_size=result.lot_size, r=r,
            n_paths=n_paths,
        )

    # Probability cards
    cols = st.columns(4)
    with cols[0]:
        pop_color = "profit" if mc.probability_of_profit > 50 else "loss"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">PROB. OF PROFIT</div>
            <div class="metric-value {pop_color}">{mc.probability_of_profit:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        ev_color = "profit" if mc.expected_pnl > 0 else "loss"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">EXPECTED P&L</div>
            <div class="metric-value {ev_color}">₹{mc.expected_pnl:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">5% WORST CASE</div>
            <div class="metric-value loss">₹{mc.var_5pct:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">1% WORST CASE</div>
            <div class="metric-value loss">₹{mc.var_1pct:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    # P&L distribution from MC
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=mc.position_pnls,
        nbinsx=80,
        marker_color=COLORS["accent"],
        opacity=0.75,
        name="Simulated P&L",
    ))

    # Shade profit/loss regions
    fig.add_vline(x=0, line_color=COLORS["text_dim"], line_width=2, line_dash="dash")
    fig.add_vline(
        x=mc.expected_pnl, line_color=COLORS["warning"],
        line_width=1.5, line_dash="dot",
        annotation_text=f"E[P&L] = ₹{mc.expected_pnl:+,.0f}",
        annotation_font_color=COLORS["warning"],
    )
    fig.add_vline(
        x=mc.var_5pct, line_color=COLORS["loss"],
        line_width=1, line_dash="dot",
        annotation_text=f"VaR 5% = ₹{mc.var_5pct:+,.0f}",
        annotation_font_color=COLORS["loss"],
    )

    _apply_layout(fig, f"Monte Carlo P&L Distribution ({mc.n_paths:,} paths, σ={sigma*100:.1f}%)")
    fig.update_xaxes(title_text="P&L (₹)", tickformat=",")
    fig.update_yaxes(title_text="Frequency")
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Extra stats
    st.caption(
        f"Expected move: ±₹{mc.expected_move:,.0f} | "
        f"Prob. inside expected: {mc.prob_inside_expected:.1f}% | "
        f"Median P&L: ₹{mc.median_pnl:+,.0f}"
    )

    st.markdown("---")


def _render_greeks_table(df: pd.DataFrame, result: BacktestResult, r: float):
    """Render Greeks table for the most recent expiry in the data."""
    st.markdown("#### 🔢 Greeks (Option Chain)")

    # Get latest date's option chain
    latest_date = df["timestamp"].dt.date.max()
    chain = df[df["timestamp"].dt.date == latest_date].copy()

    if chain.empty:
        st.caption("No option chain data available")
        return

    underlying_price = chain["underlying_close"].dropna().iloc[0] if "underlying_close" in chain.columns else 0

    if underlying_price <= 0:
        st.caption("Cannot compute Greeks: underlying price not available")
        return

    with st.spinner("Computing IV and Greeks..."):
        enriched = enrich_chain(chain, underlying_price, r)

    # Display a clean subset
    display_cols = ["strike", "option_type", "close", "iv", "delta", "gamma", "theta", "vega"]
    available = [c for c in display_cols if c in enriched.columns]
    display_df = enriched[available].copy()

    # Format for display
    if "iv" in display_df.columns:
        display_df["iv"] = display_df["iv"].apply(
            lambda x: f"{x*100:.1f}%" if pd.notna(x) and x > 0 else "—"
        )
    for col in ["delta", "gamma", "theta", "vega"]:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: f"{x:.4f}" if pd.notna(x) else "—"
            )
    if "close" in display_df.columns:
        display_df["close"] = display_df["close"].apply(lambda x: f"₹{x:.2f}")

    display_df.columns = [c.upper() for c in display_df.columns]

    st.dataframe(display_df, use_container_width=True, hide_index=True, height=300)
    st.markdown("---")


def _render_calibration(
    result: BacktestResult,
    df: pd.DataFrame | None,
    vol: float,
    r: float,
):
    """Render prediction vs reality calibration."""
    st.markdown("#### 🎯 Prediction vs Reality")

    if len(result.trades) < 10:
        st.caption("Need at least 10 trades for calibration analysis.")
        return

    # Build underlying price series
    underlying_prices = None
    if df is not None and "underlying_close" in df.columns:
        underlying_prices = df.groupby(df["timestamp"].dt.date)["underlying_close"].first().dropna()

    with st.spinner("Running calibration analysis..."):
        report = calibrate_trades(
            trades=result.trades,
            underlying_prices=underlying_prices,
            volatility=vol,
            lot_size=result.lot_size,
            r=r,
        )

    if not report.calibration_table:
        st.caption("Not enough trades in any prediction bucket for calibration.")
        return

    # Calibration score badge
    score_colors = {"GOOD": "#00d26a", "FAIR": "#ffa502", "POOR": "#ff4757"}
    sc = score_colors.get(report.calibration_score, "#fff")

    cols = st.columns([1, 1, 2])
    with cols[0]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">CALIBRATION</div>
            <div class="metric-value" style="color: {sc};">{report.calibration_score}</div>
            <div class="metric-subtext">MAE: {report.mean_absolute_error:.1f}%</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">TRADES ANALYZED</div>
            <div class="metric-value">{report.trades_with_prediction}</div>
            <div class="metric-subtext">of {report.total_trades} total</div>
        </div>
        """, unsafe_allow_html=True)

    # Calibration table
    with cols[2]:
        if report.calibration_table:
            table_data = []
            for bucket, vals in sorted(report.calibration_table.items()):
                table_data.append({
                    "Predicted PoP": bucket,
                    "Actual Win Rate": f"{vals['actual']:.1f}%",
                    "Trades": int(vals["count"]),
                    "Δ": f"{vals['actual'] - vals['predicted']:+.1f}%",
                })
            st.dataframe(
                pd.DataFrame(table_data),
                use_container_width=True,
                hide_index=True,
            )

    # Expected move accuracy
    if report.calibrations:
        within = sum(1 for c in report.calibrations if c.within_expected)
        total = len(report.calibrations)
        st.caption(
            f"Expected move accuracy: {within}/{total} trades "
            f"({within/total*100:.0f}%) stayed within ±1σ predicted range "
            f"(theory: ~68%)"
        )
