"""
Volatility analysis: realized vol, IV-RV spread, percentile ranks,
and volatility regime classification.

This module answers the question: "Is options premium currently
cheap or expensive relative to history?"

A positive IV-RV spread means the market is pricing in more
volatility than has actually been realized — which is typically
when short-vol strategies (straddles, strangles) have an edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from core.research.black_scholes import implied_volatility_chain


class VolRegime(str, Enum):
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"
    EXTREME = "EXTREME"


@dataclass
class VolatilityAnalysis:
    """Complete volatility analysis for a point in time."""
    # Current readings
    current_iv: float               # ATM implied volatility
    current_rv_20: float            # 20-day realized volatility
    current_rv_10: float            # 10-day realized vol
    current_rv_60: float            # 60-day realized vol

    # IV-RV relationship
    iv_rv_spread: float             # IV - RV_20 (positive = IV overpriced)
    iv_rv_ratio: float              # IV / RV_20

    # Historical context
    iv_percentile: float            # Where current IV sits (0-100)
    rv_percentile: float            # Where current RV sits (0-100)

    # Regime
    regime: VolRegime
    regime_description: str

    # Time series (for charting)
    iv_history: pd.Series | None = None
    rv_history: pd.Series | None = None


# ── Realized Volatility ──────────────────────────────────────────────

def realized_volatility(
    prices: pd.Series,
    window: int = 20,
    annualize: bool = True,
) -> pd.Series:
    """
    Compute rolling realized (historical) volatility.

    Uses close-to-close log returns and annualizes by √252.

    Args:
        prices: Series of prices (e.g., underlying close)
        window: Rolling window in trading days
        annualize: If True, multiply by √252

    Returns:
        Series of annualized realized volatility
    """
    log_returns = np.log(prices / prices.shift(1))
    rv = log_returns.rolling(window=window).std()

    if annualize:
        rv = rv * np.sqrt(252)

    return rv


def realized_volatility_multi(
    prices: pd.Series,
    windows: list[int] | None = None,
) -> pd.DataFrame:
    """
    Compute realized volatility for multiple windows.

    Returns DataFrame with columns like 'rv_10', 'rv_20', etc.
    """
    if windows is None:
        windows = [10, 20, 30, 60]

    result = pd.DataFrame(index=prices.index)
    for w in windows:
        result[f"rv_{w}"] = realized_volatility(prices, window=w)

    return result


# ── ATM Implied Volatility ───────────────────────────────────────────

def atm_implied_volatility(
    option_chain: pd.DataFrame,
    underlying_price: float,
    r: float = 0.07,
) -> float:
    """
    Compute ATM implied volatility from an option chain.

    Finds the nearest-to-ATM CE and PE, computes their IVs,
    and averages them for a stable ATM IV estimate.
    """
    if option_chain.empty:
        return float("nan")

    # Find ATM strike
    strikes = option_chain["strike"].unique()
    atm_strike = float(min(strikes, key=lambda s: abs(s - underlying_price)))

    # Get CE and PE at ATM
    atm_options = option_chain[option_chain["strike"] == atm_strike]

    ivs = []
    for _, row in atm_options.iterrows():
        try:
            timestamp = pd.Timestamp(row["timestamp"]) if "timestamp" in atm_options.columns else pd.Timestamp.now()
            expiry = pd.Timestamp(row["expiry"])
            T = max((expiry - timestamp).days / 365.25, 1e-10)

            from core.research.black_scholes import implied_volatility
            iv = implied_volatility(
                market_price=float(row["close"]),
                S=underlying_price,
                K=atm_strike,
                T=T,
                r=r,
                option_type=str(row["option_type"]),
            )
            if not np.isnan(iv) and iv > 0:
                ivs.append(iv)
        except Exception:
            continue

    return float(np.mean(ivs)) if ivs else float("nan")


# ── Percentile Rank ──────────────────────────────────────────────────

def percentile_rank(current: float, history: pd.Series) -> float:
    """
    Compute where `current` sits in the historical distribution.

    Returns value between 0 and 100.
    0 = current is at the all-time low
    100 = current is at the all-time high
    """
    valid = history.dropna()
    if len(valid) == 0:
        return 50.0
    return float((valid < current).sum() / len(valid) * 100)


# ── Regime Classification ────────────────────────────────────────────

def classify_regime(iv_percentile: float) -> tuple[VolRegime, str]:
    """
    Classify the current volatility regime based on IV percentile.

    Returns (regime, description).
    """
    if iv_percentile < 25:
        return VolRegime.LOW, (
            "IV is in the bottom quartile. Options are cheap. "
            "Favor long-vol strategies (buying options) or skip short-vol."
        )
    elif iv_percentile < 75:
        return VolRegime.NORMAL, (
            "IV is in the normal range. No strong directional bias "
            "from a vol perspective."
        )
    elif iv_percentile < 90:
        return VolRegime.HIGH, (
            "IV is elevated. Options premium is rich. "
            "Short-vol strategies (straddles, strangles) tend to benefit."
        )
    else:
        return VolRegime.EXTREME, (
            "IV is extremely high (top 10%). Premium is very rich, "
            "but large moves are expected. Use defined-risk strategies "
            "(spreads, iron condors) rather than naked shorts."
        )


# ── Full Analysis ────────────────────────────────────────────────────

def analyze_volatility(
    underlying_prices: pd.Series,
    option_chain: pd.DataFrame | None = None,
    underlying_price: float | None = None,
    r: float = 0.07,
    iv_history: pd.Series | None = None,
) -> VolatilityAnalysis:
    """
    Run complete volatility analysis.

    Args:
        underlying_prices: Historical underlying close prices (indexed by date)
        option_chain: Current option chain (for IV computation)
        underlying_price: Current underlying price
        r: Risk-free rate
        iv_history: Historical IV series (if available from previous computations)

    Returns:
        VolatilityAnalysis with all metrics
    """
    # Realized volatility
    rv_10 = realized_volatility(underlying_prices, window=10)
    rv_20 = realized_volatility(underlying_prices, window=20)
    rv_60 = realized_volatility(underlying_prices, window=60)

    current_rv_10 = float(rv_10.iloc[-1]) if not rv_10.empty and pd.notna(rv_10.iloc[-1]) else 0.0
    current_rv_20 = float(rv_20.iloc[-1]) if not rv_20.empty and pd.notna(rv_20.iloc[-1]) else 0.0
    current_rv_60 = float(rv_60.iloc[-1]) if not rv_60.empty and pd.notna(rv_60.iloc[-1]) else 0.0

    # Implied volatility
    current_iv = 0.0
    if option_chain is not None and underlying_price is not None:
        current_iv = atm_implied_volatility(option_chain, underlying_price, r)
        if np.isnan(current_iv):
            current_iv = 0.0

    # If no IV available, estimate from RV
    if current_iv <= 0 and current_rv_20 > 0:
        current_iv = current_rv_20 * 1.1  # IV typically ~10% above RV

    # Spreads
    iv_rv_spread = current_iv - current_rv_20 if current_rv_20 > 0 else 0.0
    iv_rv_ratio = current_iv / current_rv_20 if current_rv_20 > 0 else 1.0

    # Percentiles
    if iv_history is not None and not iv_history.empty:
        iv_pct = percentile_rank(current_iv, iv_history)
    else:
        # Use RV as proxy if no IV history
        iv_pct = percentile_rank(current_rv_20, rv_20.dropna()) if not rv_20.empty else 50.0

    rv_pct = percentile_rank(current_rv_20, rv_20.dropna()) if not rv_20.empty else 50.0

    # Regime
    regime, description = classify_regime(iv_pct)

    return VolatilityAnalysis(
        current_iv=current_iv,
        current_rv_20=current_rv_20,
        current_rv_10=current_rv_10,
        current_rv_60=current_rv_60,
        iv_rv_spread=iv_rv_spread,
        iv_rv_ratio=iv_rv_ratio,
        iv_percentile=iv_pct,
        rv_percentile=rv_pct,
        regime=regime,
        regime_description=description,
        iv_history=iv_history,
        rv_history=rv_20,
    )
