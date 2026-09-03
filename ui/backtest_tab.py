"""
Backtest configuration panel UI.

Renders strategy selection, parameter inputs, date range,
capital settings, and the RUN BACKTEST button.
"""

from __future__ import annotations

from datetime import date, timedelta

import streamlit as st
import pandas as pd

from core.strategy_engine.base import get_all_strategies, get_strategy, StrategyParameter
from core.execution_engine.costs import CostPreset


def render_backtest_config(df: pd.DataFrame | None) -> dict | None:
    """
    Render the backtest configuration panel.

    Returns:
        Configuration dict if RUN BACKTEST is clicked, None otherwise.
    """
    # ── Strategy selection ──────────────────────────────────────────
    st.markdown('<div class="section-header">🎯 Strategy</div>', unsafe_allow_html=True)

    strategies = get_all_strategies()
    strategy_names = list(strategies.keys())

    if not strategy_names:
        st.error("No strategies registered. Check strategy imports.")
        return None

    selected_name = st.selectbox(
        "Select strategy",
        strategy_names,
        index=0,
        label_visibility="collapsed",
    )

    strategy = get_strategy(selected_name)
    st.caption(strategy.description)

    # ── Strategy parameters ─────────────────────────────────────────
    params = {}
    strategy_params = strategy.parameters
    if strategy_params:
        st.markdown('<div class="section-header">⚙️ Strategy Parameters</div>', unsafe_allow_html=True)
        for param in strategy_params:
            params[param.name] = _render_parameter(param)

    # ── Date range ──────────────────────────────────────────────────
    st.markdown('<div class="section-header">📅 Date Range</div>', unsafe_allow_html=True)

    # Try to detect available date range from data
    min_date = date(2020, 1, 1)
    max_date = date.today()
    if df is not None and "timestamp" in df.columns:
        min_date = df["timestamp"].dt.date.min()
        max_date = df["timestamp"].dt.date.max()

    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start date",
            value=min_date,
            min_value=min_date,
            max_value=max_date,
        )
    with col2:
        end_date = st.date_input(
            "End date",
            value=max_date,
            min_value=min_date,
            max_value=max_date,
        )

    # ── Capital & lot size ──────────────────────────────────────────
    st.markdown('<div class="section-header">💰 Capital</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        capital = st.number_input(
            "Initial Capital (₹)",
            min_value=50_000,
            max_value=1_00_00_000,
            value=5_00_000,
            step=50_000,
            format="%d",
        )
    with col2:
        lot_size = st.number_input(
            "NIFTY Lot Size",
            min_value=1,
            max_value=500,
            value=65,
            step=1,
            help="Current NIFTY lot size is 65 (effective Jan 2026)",
        )

    # ── Transaction costs ───────────────────────────────────────────
    st.markdown('<div class="section-header">💸 Transaction Costs</div>', unsafe_allow_html=True)

    cost_presets = {
        CostPreset.ZERO.value: CostPreset.ZERO,
        CostPreset.REALISTIC.value: CostPreset.REALISTIC,
        CostPreset.CONSERVATIVE.value: CostPreset.CONSERVATIVE,
    }

    cost_selection = st.selectbox(
        "Cost model",
        list(cost_presets.keys()),
        index=1,  # Default to Realistic
        label_visibility="collapsed",
    )

    cost_descriptions = {
        CostPreset.ZERO.value: "No costs — theoretical analysis only",
        CostPreset.REALISTIC.value: "STT 0.15%, brokerage ₹20/order, exchange charges, GST, stamp duty",
        CostPreset.CONSERVATIVE.value: "Realistic + 0.1% additional slippage buffer",
    }
    st.caption(cost_descriptions.get(cost_selection, ""))

    # ── RUN button ──────────────────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)

    if st.button("🚀  RUN BACKTEST", use_container_width=True, type="primary"):
        if df is None or df.empty:
            st.error("Please upload data first")
            return None

        return {
            "strategy_name": selected_name,
            "params": params,
            "start_date": start_date,
            "end_date": end_date,
            "capital": float(capital),
            "lot_size": int(lot_size),
            "cost_preset": cost_presets[cost_selection],
        }

    return None


def _render_parameter(param: StrategyParameter):
    """Render a single strategy parameter input widget."""
    if param.type == "int":
        return st.number_input(
            param.label,
            min_value=int(param.min_val) if param.min_val is not None else 0,
            max_value=int(param.max_val) if param.max_val is not None else 100,
            value=int(param.default),
            step=int(param.step) if param.step else 1,
            help=param.help_text,
        )
    elif param.type == "float":
        return st.number_input(
            param.label,
            min_value=float(param.min_val) if param.min_val is not None else 0.0,
            max_value=float(param.max_val) if param.max_val is not None else 100.0,
            value=float(param.default),
            step=float(param.step) if param.step else 1.0,
            help=param.help_text,
        )
    elif param.type == "select":
        options = param.options or []
        return st.selectbox(
            param.label,
            options,
            index=options.index(param.default) if param.default in options else 0,
            help=param.help_text,
        )
    elif param.type == "bool":
        return st.checkbox(
            param.label,
            value=bool(param.default),
            help=param.help_text,
        )
    else:
        return st.text_input(param.label, value=str(param.default), help=param.help_text)
