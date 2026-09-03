"""
NIFTY Quant Lab — Streamlit Entry Point.

A unified NIFTY options backtesting and paper-trading laboratory.
Two execution modes, one strategy engine.
"""

import streamlit as st

# Import all strategies to register them
import core.strategy_engine.short_straddle     # noqa: F401
import core.strategy_engine.short_strangle     # noqa: F401
import core.strategy_engine.bull_call_spread   # noqa: F401
import core.strategy_engine.bear_call_spread   # noqa: F401
import core.strategy_engine.buy_ce_after_positive  # noqa: F401
import core.strategy_engine.buy_pe_after_negative  # noqa: F401

from ui.theme import configure_page, render_header
from ui.data_upload import render_data_upload
from ui.backtest_tab import render_backtest_config
from ui.results_dashboard import render_results
from ui.paper_trade_tab import render_paper_trade_tab

from core.data_engine.providers import HistoricalProvider
from core.strategy_engine.base import get_strategy
from backtester.engine import BacktestEngine


def main():
    """Main application entry point."""
    configure_page()
    render_header()

    # ── Tabs ────────────────────────────────────────────────────────
    tab_backtest, tab_paper = st.tabs(["🧪 Backtest", "📡 Paper Trading"])

    # ── Backtest Tab ────────────────────────────────────────────────
    with tab_backtest:
        # Layout: config on left, results on right
        config_col, results_col = st.columns([1, 2], gap="large")

        with config_col:
            # Data upload
            df, report = render_data_upload()

            # Backtest configuration
            config = render_backtest_config(df)

            if config is not None:
                st.session_state["backtest_config"] = config
                st.session_state["run_backtest"] = True

        with results_col:
            # Check if we should run a backtest
            if st.session_state.get("run_backtest", False):
                config = st.session_state["backtest_config"]
                df = st.session_state.get("dataset")
                report = st.session_state.get("dataset_report")

                if df is not None:
                    _run_backtest(config, df, report)
                    st.session_state["run_backtest"] = False

            elif "backtest_result" in st.session_state:
                # Show previous results
                result = st.session_state["backtest_result"]
                report = st.session_state.get("dataset_report")
                data_warnings = report.warnings if report else []
                render_results(result, data_warnings)

            else:
                _render_welcome()

    # ── Paper Trading Tab ───────────────────────────────────────────
    with tab_paper:
        render_paper_trade_tab()


def _run_backtest(config: dict, df, report):
    """Execute the backtest with the given configuration."""
    with st.spinner(f"Running {config['strategy_name']} backtest..."):
        try:
            # Build provider
            provider = HistoricalProvider(df)

            # Build strategy
            strategy = get_strategy(config["strategy_name"])

            # Build engine
            engine = BacktestEngine(
                strategy=strategy,
                data_provider=provider,
                lot_size=config["lot_size"],
                cost_preset=config["cost_preset"],
            )

            # Run
            result = engine.run(
                start_date=config["start_date"],
                end_date=config["end_date"],
                initial_capital=config["capital"],
                params=config["params"],
            )

            # Store and display
            st.session_state["backtest_result"] = result
            data_warnings = report.warnings if report else []
            render_results(result, data_warnings)

        except Exception as e:
            st.error(f"Backtest failed: {str(e)}")
            import traceback
            with st.expander("Error details"):
                st.code(traceback.format_exc())


def _render_welcome():
    """Render the welcome screen before any backtest is run."""
    st.markdown("""
    <div style="
        text-align: center;
        padding: 6rem 2rem;
        color: var(--text-secondary, #8888aa);
    ">
        <div style="font-size: 5rem; margin-bottom: 1rem;">🔬</div>
        <h2 style="
            color: var(--text-primary, #e8e8f0);
            margin-bottom: 0.5rem;
            font-weight: 700;
        ">
            Welcome to NIFTY Quant Lab
        </h2>
        <p style="
            max-width: 520px;
            margin: 0.5rem auto 2rem auto;
            line-height: 1.7;
            font-size: 0.95rem;
        ">
            Upload historical NIFTY options data, select a strategy,
            and run a backtest with realistic Indian market transaction costs.
        </p>
        <div style="
            display: flex;
            justify-content: center;
            gap: 2rem;
            flex-wrap: wrap;
        ">
            <div style="
                padding: 1.5rem;
                background: var(--bg-card, #151525);
                border: 1px solid var(--border, #2a2a3e);
                border-radius: 12px;
                width: 180px;
            ">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">📁</div>
                <div style="font-weight: 600; color: var(--text-primary, #e8e8f0);">
                    1. Upload Data
                </div>
                <div style="font-size: 0.8rem; margin-top: 0.3rem;">
                    CSV with NIFTY option prices
                </div>
            </div>
            <div style="
                padding: 1.5rem;
                background: var(--bg-card, #151525);
                border: 1px solid var(--border, #2a2a3e);
                border-radius: 12px;
                width: 180px;
            ">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🎯</div>
                <div style="font-weight: 600; color: var(--text-primary, #e8e8f0);">
                    2. Pick Strategy
                </div>
                <div style="font-size: 0.8rem; margin-top: 0.3rem;">
                    6 strategies available
                </div>
            </div>
            <div style="
                padding: 1.5rem;
                background: var(--bg-card, #151525);
                border: 1px solid var(--border, #2a2a3e);
                border-radius: 12px;
                width: 180px;
            ">
                <div style="font-size: 2rem; margin-bottom: 0.5rem;">🚀</div>
                <div style="font-weight: 600; color: var(--text-primary, #e8e8f0);">
                    3. Run Backtest
                </div>
                <div style="font-size: 0.8rem; margin-top: 0.3rem;">
                    Full analytics & charts
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
