"""
Paper trading tab UI (Phase 3 stub).
"""

import streamlit as st


def render_paper_trade_tab():
    """Render the paper trading tab placeholder."""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 4rem 2rem;
        color: var(--text-secondary, #8888aa);
    ">
        <div style="font-size: 4rem; margin-bottom: 1rem;">📡</div>
        <h2 style="color: var(--text-primary, #e8e8f0); margin-bottom: 0.5rem;">
            Paper Trading — Coming in Phase 3
        </h2>
        <p style="max-width: 500px; margin: 0 auto; line-height: 1.6;">
            This tab will connect to live market data and use the
            <b>exact same strategy engine</b> as the backtester.
            Same code, different data source.
        </p>
        <div style="
            margin-top: 2rem;
            padding: 1.5rem;
            background: var(--bg-card, #151525);
            border: 1px solid var(--border, #2a2a3e);
            border-radius: 12px;
            display: inline-block;
            text-align: left;
        ">
            <div style="font-size: 0.85rem; color: var(--text-dim, #555570); margin-bottom: 0.5rem;">
                ARCHITECTURE READY
            </div>
            <div style="font-family: monospace; font-size: 0.8rem; line-height: 1.8;">
                <span style="color: var(--profit, #00d26a);">✓</span> Strategy interface<br>
                <span style="color: var(--profit, #00d26a);">✓</span> MarketDataProvider abstraction<br>
                <span style="color: var(--profit, #00d26a);">✓</span> Execution simulator<br>
                <span style="color: var(--profit, #00d26a);">✓</span> Risk engine<br>
                <span style="color: var(--warning, #ffa502);">○</span> LiveDataProvider<br>
                <span style="color: var(--warning, #ffa502);">○</span> Real-time position tracker<br>
                <span style="color: var(--warning, #ffa502);">○</span> Paper order book
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
