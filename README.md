# NIFTY Quant Lab

A unified NIFTY Options Research and Paper Trading Laboratory built with a shared strategy engine across historical and live modes.

```
                         ┌──────────────────────┐
                         │   Strategy Engine    │
                         │                      │
                         │  Short Straddle      │
                         │  Short Strangle      │
                         │  Bull Call Spread    │
                         │  Bear Call Spread    │
                         │  Buy CE (+Day)       │
                         │  Buy PE (-Day)       │
                         └──────────┬───────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
             HISTORICAL MODE                 LIVE MODE (Phase 3)
                    │                               │
             CSV / Parquet                   Live Option Chain
                    │                               │
                    ↓                               ↓
              Backtester                    Paper Trader
                    │                               │
                    └───────────────┬───────────────┘
                                    ↓
                         Execution Simulator & Costs
                         (STT 0.15%, GST, Stamp Duty)
                                    ↓
                               Analytics
                         (P&L, Drawdown, Heatmap)
```

---

## Features (Phase 1 — Backtesting Lab)

- **Single Strategy Engine**: Identical strategy logic is evaluated against historical data and live market snapshots.
- **Structural Look-Ahead Bias Prevention**: `MarketState` snapshots contain strictly the data known up to the current timestamp.
- **Smart CSV Ingestion & Validation**: Fuzzy column detection supporting various NSE export formats (e.g. `STRIKE_PR`, `SETTLE_PR`, `EXPIRY_DT`), automatic date normalization, and data validation reports.
- **Realistic Indian Market Costs**: Built-in 2026 transaction cost model:
  - STT: 0.15% on sell premium / exercise
  - Flat Brokerage: ₹20/order
  - Exchange transaction charges: ~0.05%
  - GST: 18% on services
  - Stamp duty: 0.003% (buy side)
  - SEBI turnover charges & configurable slippage buffer
- **Comprehensive Risk & Performance Analytics**:
  - Net P&L, Return on Capital, CAGR, Sharpe Ratio, Profit Factor, Expected Value, Win Rate.
  - Interactive Plotly equity curves, underwater drawdown charts, P&L distribution histograms, monthly return heatmaps, and trade scatter plots.
  - Statistical confidence warnings (alerting on small trade counts, EOD data limitations, or high drawdowns).
  - Exportable CSV trade logs.

---

## Quickstart

### 1. Activate Environment

```bash
source .venv/bin/activate
```

### 2. Run Test Suite

```bash
pytest tests/ -v
```

All 41 unit and integration tests validate column parsing, cost math, strategy signals, and backtest integrity.

### 3. Launch UI

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

A synthetic dataset is available for immediate testing at `tests/fixtures/sample_nifty.csv`.

---

## Architecture Roadmap

- **Phase 1 (Completed)**: Unified Backtester, Ingestion Layer, Execution Simulator, and Analytics Dashboard.
- **Phase 2**: Research Engine (Greeks, Implied Volatility, Monte Carlo path distributions, Probability of Profit).
- **Phase 3**: Paper Trading Engine with live market feeds (`LiveDataProvider`).
- **Phase 4**: Walk-forward validation, out-of-sample train/test splits, and calibration curves.
