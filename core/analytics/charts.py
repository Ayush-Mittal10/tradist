"""
Plotly chart generators for backtest results.

All charts follow a consistent dark theme with the lab's color palette.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from core.data_engine.schema import Trade

# ── Color palette ──────────────────────────────────────────────────────

COLORS = {
    "bg": "#0f0f1a",
    "card_bg": "#1a1a2e",
    "grid": "#2a2a3e",
    "text": "#e0e0e0",
    "text_dim": "#8888aa",
    "accent": "#4f8cff",
    "profit": "#00d26a",
    "loss": "#ff4757",
    "warning": "#ffa502",
    "line": "#6c5ce7",
    "fill": "rgba(79, 140, 255, 0.1)",
}

CHART_LAYOUT = dict(
    paper_bgcolor=COLORS["bg"],
    plot_bgcolor=COLORS["card_bg"],
    font=dict(family="Inter, sans-serif", color=COLORS["text"], size=13),
    margin=dict(l=60, r=30, t=50, b=50),
    xaxis=dict(
        gridcolor=COLORS["grid"],
        zerolinecolor=COLORS["grid"],
    ),
    yaxis=dict(
        gridcolor=COLORS["grid"],
        zerolinecolor=COLORS["grid"],
    ),
    hovermode="x unified",
)


def _apply_layout(fig: go.Figure, title: str = "") -> go.Figure:
    """Apply consistent styling to a chart."""
    fig.update_layout(**CHART_LAYOUT)
    if title:
        fig.update_layout(title=dict(text=title, font=dict(size=16)))
    return fig


# ── Chart generators ───────────────────────────────────────────────────

def equity_curve(equity_df: pd.DataFrame, initial_capital: float) -> go.Figure:
    """
    Interactive equity curve chart with trade markers.

    Args:
        equity_df: DataFrame with 'timestamp' and 'capital' columns
        initial_capital: Starting capital for reference line
    """
    fig = go.Figure()

    # Main equity line
    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=equity_df["capital"],
        mode="lines",
        name="Capital",
        line=dict(color=COLORS["accent"], width=2.5),
        fill="tozeroy",
        fillcolor=COLORS["fill"],
    ))

    # Initial capital reference line
    fig.add_hline(
        y=initial_capital,
        line_dash="dash",
        line_color=COLORS["text_dim"],
        annotation_text=f"Initial: ₹{initial_capital:,.0f}",
        annotation_position="bottom right",
        annotation_font_color=COLORS["text_dim"],
    )

    _apply_layout(fig, "📈 Equity Curve")
    fig.update_yaxis(title_text="Capital (₹)", tickformat=",")
    fig.update_xaxis(title_text="Date")

    return fig


def drawdown_chart(equity_df: pd.DataFrame) -> go.Figure:
    """
    Underwater/drawdown chart showing peak-to-trough declines.
    """
    capital = equity_df["capital"].values
    peak = np.maximum.accumulate(capital)
    drawdown_pct = (capital - peak) / peak * 100

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=equity_df["timestamp"],
        y=drawdown_pct,
        mode="lines",
        name="Drawdown",
        line=dict(color=COLORS["loss"], width=1.5),
        fill="tozeroy",
        fillcolor="rgba(255, 71, 87, 0.2)",
    ))

    _apply_layout(fig, "📉 Drawdown")
    fig.update_yaxis(title_text="Drawdown (%)", ticksuffix="%")
    fig.update_xaxis(title_text="Date")

    return fig


def pnl_distribution(trades: list[Trade]) -> go.Figure:
    """
    Histogram of trade P&L distribution.
    """
    pnls = [t.net_pnl for t in trades]

    # Color bins by sign
    colors = [COLORS["profit"] if p > 0 else COLORS["loss"] for p in pnls]

    fig = go.Figure()

    fig.add_trace(go.Histogram(
        x=pnls,
        nbinsx=min(30, max(10, len(pnls) // 3)),
        marker_color=COLORS["accent"],
        opacity=0.8,
        name="P&L",
    ))

    # Add mean line
    if pnls:
        mean_pnl = float(np.mean(pnls))
        fig.add_vline(
            x=mean_pnl,
            line_dash="dash",
            line_color=COLORS["warning"],
            annotation_text=f"Mean: ₹{mean_pnl:+,.0f}",
            annotation_font_color=COLORS["warning"],
        )

    # Add zero line
    fig.add_vline(x=0, line_color=COLORS["text_dim"], line_width=1)

    _apply_layout(fig, "📊 P&L Distribution")
    fig.update_xaxis(title_text="Trade P&L (₹)", tickformat=",")
    fig.update_yaxis(title_text="Frequency")

    return fig


def monthly_returns_heatmap(trades: list[Trade]) -> go.Figure:
    """
    Monthly returns heatmap (months × years grid).
    """
    if not trades:
        fig = go.Figure()
        _apply_layout(fig, "📅 Monthly Returns")
        return fig

    # Build monthly P&L
    monthly_pnl: dict[tuple[int, int], float] = {}
    for t in trades:
        key = (t.exit_timestamp.year, t.exit_timestamp.month)
        monthly_pnl[key] = monthly_pnl.get(key, 0) + t.net_pnl

    if not monthly_pnl:
        fig = go.Figure()
        _apply_layout(fig, "📅 Monthly Returns")
        return fig

    years = sorted(set(k[0] for k in monthly_pnl))
    months = list(range(1, 13))
    month_names = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]

    # Build matrix
    z = []
    text = []
    for year in years:
        row = []
        text_row = []
        for month in months:
            val = monthly_pnl.get((year, month), 0)
            row.append(val)
            if val != 0:
                text_row.append(f"₹{val:+,.0f}")
            else:
                text_row.append("")
        z.append(row)
        text.append(text_row)

    fig = go.Figure(data=go.Heatmap(
        z=z,
        x=month_names,
        y=[str(y) for y in years],
        text=text,
        texttemplate="%{text}",
        textfont=dict(size=11),
        colorscale=[
            [0, COLORS["loss"]],
            [0.5, COLORS["card_bg"]],
            [1, COLORS["profit"]],
        ],
        zmid=0,
        showscale=True,
        colorbar=dict(title="P&L (₹)", tickformat=","),
    ))

    _apply_layout(fig, "📅 Monthly Returns")
    fig.update_layout(
        yaxis=dict(autorange="reversed"),
    )

    return fig


def trade_scatter(trades: list[Trade]) -> go.Figure:
    """
    Scatter plot of individual trades (date vs P&L).
    """
    dates = [t.exit_timestamp for t in trades]
    pnls = [t.net_pnl for t in trades]
    colors = [COLORS["profit"] if p > 0 else COLORS["loss"] for p in pnls]

    hover_texts = []
    for t in trades:
        hover_texts.append(
            f"Strategy: {t.strategy_name}<br>"
            f"Entry: {t.entry_timestamp.strftime('%d-%b')}<br>"
            f"Exit: {t.exit_timestamp.strftime('%d-%b')}<br>"
            f"P&L: ₹{t.net_pnl:+,.0f}<br>"
            f"Duration: {t.duration_days}d"
        )

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates,
        y=pnls,
        mode="markers",
        marker=dict(
            color=colors,
            size=8,
            line=dict(width=1, color=COLORS["text_dim"]),
        ),
        text=hover_texts,
        hoverinfo="text",
        name="Trades",
    ))

    fig.add_hline(y=0, line_color=COLORS["text_dim"], line_width=1)

    _apply_layout(fig, "🎯 Trade P&L Scatter")
    fig.update_xaxis(title_text="Date")
    fig.update_yaxis(title_text="Net P&L (₹)", tickformat=",")

    return fig
