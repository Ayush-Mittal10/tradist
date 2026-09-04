"""
Paper trading tab — full implementation.

Provides:
1. Upstox connection flow
2. Strategy selection & session controls
3. Live dashboard with open positions, MTM P&L, trade log
4. Session results (same analytics as backtest)
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from core.data_engine.providers import LiveDataProvider
from core.execution_engine.costs import CostPreset
from core.strategy_engine.base import get_all_strategies, get_strategy
from paper_trader.engine import PaperTradeEngine
from paper_trader.session import TradingSession
from ui.auth_flow import render_auth_flow
from ui.results_dashboard import render_results


def render_paper_trade_tab():
    """Render the complete paper trading tab."""

    # ── Connection ──────────────────────────────────────────────────
    st.markdown(
        '<div class="section-header">📡 Paper Trading</div>',
        unsafe_allow_html=True,
    )

    client = render_auth_flow()

    if client is None:
        # Not connected — show instructions
        _render_setup_guide()
        return

    # ── Connected — show trading interface ──────────────────────────
    config_col, dashboard_col = st.columns([1, 2], gap="large")

    with config_col:
        _render_session_controls(client)

    with dashboard_col:
        session = st.session_state.get("paper_session")

        if session and session.is_running:
            _render_live_dashboard(session)
        elif "paper_results" in st.session_state:
            _render_session_results()
        else:
            _render_waiting()


def _render_session_controls(client):
    """Render strategy selection and session controls."""

    # NIFTY LTP
    try:
        ltp = client.get_nifty_ltp()
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">NIFTY 50</div>
            <div class="metric-value">{ltp:,.2f}</div>
            <div class="metric-subtext">Last traded price</div>
        </div>
        """, unsafe_allow_html=True)
    except Exception:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-label">NIFTY 50</div>
            <div class="metric-value">—</div>
            <div class="metric-subtext">Market may be closed</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Strategy selection
    st.markdown(
        '<div class="section-header">🎯 Strategy</div>',
        unsafe_allow_html=True,
    )

    strategies = get_all_strategies()
    strategy_names = list(strategies.keys())
    selected = st.selectbox(
        "Select strategy",
        strategy_names,
        label_visibility="collapsed",
    )
    strategy = get_strategy(selected)
    st.caption(strategy.description)

    # Parameters
    params = {}
    if strategy.parameters:
        st.markdown(
            '<div class="section-header">⚙️ Parameters</div>',
            unsafe_allow_html=True,
        )
        for param in strategy.parameters:
            if param.type == "int":
                params[param.name] = st.number_input(
                    param.label,
                    value=int(param.default),
                    step=int(param.step) if param.step else 1,
                )
            elif param.type == "float":
                params[param.name] = st.number_input(
                    param.label,
                    value=float(param.default),
                    step=float(param.step) if param.step else 1.0,
                )

    # Capital
    st.markdown(
        '<div class="section-header">💰 Capital</div>',
        unsafe_allow_html=True,
    )
    capital = st.number_input(
        "Paper Capital (₹)",
        min_value=50_000,
        max_value=1_00_00_000,
        value=5_00_000,
        step=50_000,
    )

    lot_size = st.number_input("Lot Size", value=65, min_value=1)

    poll_interval = st.slider(
        "Poll interval (seconds)",
        min_value=10,
        max_value=300,
        value=30,
        help="How often to check for signals",
    )

    st.markdown("<br>", unsafe_allow_html=True)

    # Session controls
    session = st.session_state.get("paper_session")

    if session and session.is_running:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("⏹️ Stop Session", use_container_width=True, type="primary"):
                result = session.stop()
                st.session_state["paper_results"] = result
                del st.session_state["paper_session"]
                st.rerun()
        with col2:
            if st.button("🔄 Manual Tick", use_container_width=True):
                tick_result = session.manual_tick()
                st.toast(f"{tick_result['action']}: {tick_result['details']}")
                st.rerun()
    else:
        if st.button(
            "▶️  START PAPER TRADING",
            use_container_width=True,
            type="primary",
        ):
            # Build components
            provider = LiveDataProvider(client)
            trading_session = TradingSession(
                strategy=strategy,
                live_provider=provider,
                lot_size=lot_size,
                cost_preset=CostPreset.REALISTIC,
                poll_interval=poll_interval,
            )
            trading_session.start(capital=capital, params=params)
            st.session_state["paper_session"] = trading_session
            st.rerun()


def _render_live_dashboard(session: TradingSession):
    """Render the live trading dashboard."""
    status = session.get_status()

    # Status badges
    cols = st.columns(4)
    with cols[0]:
        mkt = "🟢 OPEN" if status.get("market_open") else "🔴 CLOSED"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">MARKET</div>
            <div class="metric-value" style="font-size: 1.1rem;">{mkt}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">TICKS</div>
            <div class="metric-value">{status.get('total_ticks', 0)}</div>
            <div class="metric-subtext">every {status.get('poll_interval', 30)}s</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        realized = status.get("realized_pnl", 0)
        pnl_class = "profit" if realized >= 0 else "loss"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">REALIZED P&L</div>
            <div class="metric-value {pnl_class}">₹{realized:+,.0f}</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        open_pos = status.get("open_positions", 0)
        completed = status.get("completed_trades", 0)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">POSITIONS</div>
            <div class="metric-value">{open_pos} open</div>
            <div class="metric-subtext">{completed} completed</div>
        </div>
        """, unsafe_allow_html=True)

    # Open positions table
    if session.engine.order_book:
        open_orders = session.engine.order_book.open_positions
        if open_orders:
            st.markdown(
                '<div class="section-header">📋 Open Positions</div>',
                unsafe_allow_html=True,
            )
            pos_data = []
            for order in open_orders:
                legs_str = ", ".join(
                    f"{f.option_type.value} {f.strike} ({f.side.value})"
                    for f in order.entry_legs
                )
                pos_data.append({
                    "Strategy": order.strategy_name,
                    "Legs": legs_str,
                    "Entry": order.entry_timestamp.strftime("%H:%M:%S"),
                    "Expiry": str(order.expiry),
                })
            st.dataframe(
                pd.DataFrame(pos_data),
                use_container_width=True,
                hide_index=True,
            )

        # Completed trades
        completed_trades = session.engine.order_book.completed_trades
        if completed_trades:
            st.markdown(
                '<div class="section-header">✅ Completed Trades</div>',
                unsafe_allow_html=True,
            )
            trade_data = [t.summary_dict() for t in completed_trades[-10:]]
            st.dataframe(
                pd.DataFrame(trade_data),
                use_container_width=True,
                hide_index=True,
            )

    # Recent tick log
    recent = status.get("recent_actions", [])
    if recent:
        st.markdown(
            '<div class="section-header">📡 Activity Log</div>',
            unsafe_allow_html=True,
        )
        for entry in reversed(recent):
            action = entry.get("action", "")
            icon = {"ENTRY": "🟢", "EXIT": "🔴", "HOLD": "⏸️", "ERROR": "⚠️"}.get(
                action, "❓"
            )
            ts = entry.get("timestamp", "")[:19]
            st.caption(f"{icon} `{ts}` — {entry.get('details', '')}")

    # Auto-refresh
    st.markdown(
        f"<small style='color: var(--text-dim);'>Auto-refreshes every {status.get('poll_interval', 30)}s</small>",
        unsafe_allow_html=True,
    )


def _render_session_results():
    """Render completed session results using the same dashboard as backtest."""
    result = st.session_state.get("paper_results")
    if result:
        st.markdown(
            '<div class="section-header">📊 Session Results</div>',
            unsafe_allow_html=True,
        )
        render_results(result)

        if st.button("Clear Results"):
            del st.session_state["paper_results"]
            st.rerun()


def _render_waiting():
    """Render waiting screen before session starts."""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 4rem 2rem;
        color: var(--text-secondary, #8888aa);
    ">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📡</div>
        <h2 style="color: var(--text-primary, #e8e8f0); margin-bottom: 0.5rem;">
            Ready to Paper Trade
        </h2>
        <p style="max-width: 450px; margin: 0 auto; line-height: 1.6;">
            Connected to Upstox. Select a strategy, set your capital,
            and click <b>START PAPER TRADING</b> to begin.
        </p>
        <div style="
            margin-top: 2rem;
            padding: 1rem;
            background: var(--bg-card, #151525);
            border: 1px solid var(--border, #2a2a3e);
            border-radius: 10px;
            display: inline-block;
            text-align: left;
            font-size: 0.85rem;
        ">
            <b style="color: var(--accent, #4f8cff);">How it works:</b><br>
            • Same strategies as backtester<br>
            • Live NIFTY option chain data from Upstox<br>
            • Simulated fills with realistic costs<br>
            • No real orders placed — paper only
        </div>
    </div>
    """, unsafe_allow_html=True)


def _render_setup_guide():
    """Render setup instructions when not connected."""
    st.markdown("""
    <div style="
        padding: 2rem;
        background: var(--bg-card, #151525);
        border: 1px solid var(--border, #2a2a3e);
        border-radius: 12px;
        margin: 1rem 0;
    ">
        <h3 style="color: var(--text-primary, #e8e8f0);">Setup Guide</h3>
        <ol style="color: var(--text-secondary, #8888aa); line-height: 2;">
            <li>Go to <a href="https://account.upstox.com/developer/apps" target="_blank">
                Upstox Developer Console</a></li>
            <li>Create a new App</li>
            <li>Set Redirect URI to <code>http://localhost:8501/callback</code></li>
            <li>Copy your <b>API Key</b> and <b>API Secret</b></li>
            <li>Enter them above and click <b>Login with Upstox</b></li>
        </ol>
        <p style="color: var(--text-dim, #555570); font-size: 0.8rem; margin-top: 1rem;">
            🔒 Credentials are stored only in your browser session.
            No real trades will be placed — this is paper trading only.
        </p>
    </div>
    """, unsafe_allow_html=True)
