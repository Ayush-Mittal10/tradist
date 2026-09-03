"""
Black-Scholes pricing, implied volatility, and Greeks.

Vectorized implementation using numpy/scipy for processing entire
option chains efficiently. All functions accept both scalar and
array inputs.

Convention:
- S  = spot/underlying price
- K  = strike price
- T  = time to expiry in years (T > 0)
- r  = risk-free rate (annualized, continuous compounding)
- σ  = volatility (annualized)
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


# ── Constants ──────────────────────────────────────────────────────────

TRADING_DAYS_PER_YEAR = 252
DEFAULT_RISK_FREE_RATE = 0.07  # India 10Y ~7%

# IV solver bounds
IV_MIN = 0.001   # 0.1%
IV_MAX = 5.0     # 500%


# ── Data structures ───────────────────────────────────────────────────

@dataclass
class GreeksResult:
    """Greeks for a single option or array of options."""
    delta: float | np.ndarray
    gamma: float | np.ndarray
    theta: float | np.ndarray   # Per calendar day (not trading day)
    vega: float | np.ndarray    # Per 1% move in vol (not per 1.0)
    rho: float | np.ndarray     # Per 1% move in rate

    def to_dict(self) -> dict:
        """Convert to dict (scalar values only)."""
        return {
            "delta": float(self.delta) if np.isscalar(self.delta) else self.delta,
            "gamma": float(self.gamma) if np.isscalar(self.gamma) else self.gamma,
            "theta": float(self.theta) if np.isscalar(self.theta) else self.theta,
            "vega": float(self.vega) if np.isscalar(self.vega) else self.vega,
            "rho": float(self.rho) if np.isscalar(self.rho) else self.rho,
        }


# ── Core Black-Scholes functions ──────────────────────────────────────

def _d1(S, K, T, r, sigma):
    """Compute d1 in the Black-Scholes formula."""
    with np.errstate(divide="ignore", invalid="ignore"):
        return (np.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))


def _d2(S, K, T, r, sigma):
    """Compute d2 in the Black-Scholes formula."""
    return _d1(S, K, T, r, sigma) - sigma * np.sqrt(T)


def bs_price(
    S: float | np.ndarray,
    K: float | np.ndarray,
    T: float | np.ndarray,
    r: float,
    sigma: float | np.ndarray,
    option_type: str = "CE",
) -> float | np.ndarray:
    """
    Black-Scholes European option price.

    Args:
        S: Spot price
        K: Strike price
        T: Time to expiry (years). Must be > 0.
        r: Risk-free rate (e.g., 0.07 for 7%)
        sigma: Volatility (e.g., 0.20 for 20%)
        option_type: "CE" for call, "PE" for put

    Returns:
        Theoretical option price
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)

    # Handle T <= 0 (expired): return intrinsic value
    expired = T <= 0

    d1 = _d1(S, K, np.maximum(T, 1e-10), r, np.maximum(sigma, 1e-10))
    d2 = d1 - sigma * np.sqrt(np.maximum(T, 1e-10))

    if option_type.upper() in ("CE", "CALL", "C"):
        price = S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
        intrinsic = np.maximum(S - K, 0)
    else:
        price = K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
        intrinsic = np.maximum(K - S, 0)

    # Use intrinsic for expired options
    result = np.where(expired, intrinsic, price)
    return float(result) if result.ndim == 0 else result


def greeks(
    S: float | np.ndarray,
    K: float | np.ndarray,
    T: float | np.ndarray,
    r: float,
    sigma: float | np.ndarray,
    option_type: str = "CE",
) -> GreeksResult:
    """
    Compute all Greeks for a European option.

    Returns GreeksResult with delta, gamma, theta (per day),
    vega (per 1% vol), and rho (per 1% rate).
    """
    S = np.asarray(S, dtype=float)
    K = np.asarray(K, dtype=float)
    T = np.asarray(T, dtype=float)
    sigma = np.asarray(sigma, dtype=float)

    # Guard against division by zero
    T_safe = np.maximum(T, 1e-10)
    sigma_safe = np.maximum(sigma, 1e-10)

    d1 = _d1(S, K, T_safe, r, sigma_safe)
    d2 = d1 - sigma_safe * np.sqrt(T_safe)

    pdf_d1 = norm.pdf(d1)
    sqrt_T = np.sqrt(T_safe)

    is_call = option_type.upper() in ("CE", "CALL", "C")

    # ── Delta ───────────────────────────────────────────────────────
    if is_call:
        delta = norm.cdf(d1)
    else:
        delta = norm.cdf(d1) - 1

    # ── Gamma (same for calls and puts) ─────────────────────────────
    gamma = pdf_d1 / (S * sigma_safe * sqrt_T)

    # ── Theta (per calendar day) ────────────────────────────────────
    common_theta = -(S * pdf_d1 * sigma_safe) / (2 * sqrt_T)
    if is_call:
        theta = common_theta - r * K * np.exp(-r * T_safe) * norm.cdf(d2)
    else:
        theta = common_theta + r * K * np.exp(-r * T_safe) * norm.cdf(-d2)
    theta = theta / 365  # Convert to per calendar day

    # ── Vega (per 1% move in vol) ───────────────────────────────────
    vega = S * pdf_d1 * sqrt_T / 100  # Divide by 100 for per-1% interpretation

    # ── Rho (per 1% move in rate) ───────────────────────────────────
    if is_call:
        rho = K * T_safe * np.exp(-r * T_safe) * norm.cdf(d2) / 100
    else:
        rho = -K * T_safe * np.exp(-r * T_safe) * norm.cdf(-d2) / 100

    return GreeksResult(
        delta=float(delta) if delta.ndim == 0 else delta,
        gamma=float(gamma) if gamma.ndim == 0 else gamma,
        theta=float(theta) if theta.ndim == 0 else theta,
        vega=float(vega) if vega.ndim == 0 else vega,
        rho=float(rho) if rho.ndim == 0 else rho,
    )


# ── Implied Volatility ────────────────────────────────────────────────

def implied_volatility(
    market_price: float,
    S: float,
    K: float,
    T: float,
    r: float = DEFAULT_RISK_FREE_RATE,
    option_type: str = "CE",
) -> float:
    """
    Compute implied volatility using Brentq root-finding.

    Finds sigma such that bs_price(S, K, T, r, sigma) == market_price.

    Returns NaN if:
    - T <= 0 (expired)
    - Price is below intrinsic (arbitrage)
    - No solution found in [IV_MIN, IV_MAX]
    """
    if T <= 0 or market_price <= 0:
        return float("nan")

    # Check arbitrage bounds
    is_call = option_type.upper() in ("CE", "CALL", "C")
    intrinsic = max(S - K, 0) if is_call else max(K - S, 0)
    if market_price < intrinsic * 0.99:  # Allow tiny float error
        return float("nan")

    def objective(sigma):
        return bs_price(S, K, T, r, sigma, option_type) - market_price

    try:
        # Check that bounds bracket the root
        low_val = objective(IV_MIN)
        high_val = objective(IV_MAX)
        if low_val * high_val > 0:
            return float("nan")
        return brentq(objective, IV_MIN, IV_MAX, xtol=1e-6, maxiter=100)
    except (ValueError, RuntimeError):
        return float("nan")


def implied_volatility_chain(
    df: pd.DataFrame,
    underlying_price: float,
    r: float = DEFAULT_RISK_FREE_RATE,
) -> pd.Series:
    """
    Compute IV for an entire option chain DataFrame.

    Expects canonical columns: 'strike', 'option_type', 'close', 'expiry'.
    Also needs a reference date to compute T (uses the 'timestamp' column
    or assumes all rows are for the same date).

    Returns a Series of IV values aligned with the DataFrame index.
    """
    ivs = []

    for _, row in df.iterrows():
        try:
            # Compute T in years
            if "timestamp" in df.columns and pd.notna(row.get("timestamp")):
                current = pd.Timestamp(row["timestamp"])
            else:
                current = pd.Timestamp.now()

            expiry = pd.Timestamp(row["expiry"])
            T = max((expiry - current).days / 365.25, 1e-10)

            iv = implied_volatility(
                market_price=float(row["close"]),
                S=underlying_price,
                K=float(row["strike"]),
                T=T,
                r=r,
                option_type=str(row["option_type"]),
            )
            ivs.append(iv)
        except Exception:
            ivs.append(float("nan"))

    return pd.Series(ivs, index=df.index, name="iv")


def enrich_chain(
    df: pd.DataFrame,
    underlying_price: float,
    r: float = DEFAULT_RISK_FREE_RATE,
) -> pd.DataFrame:
    """
    Enrich an option chain with IV and all Greeks.

    Adds columns: iv, delta, gamma, theta, vega, rho.

    Args:
        df: Canonical option chain DataFrame
        underlying_price: Current spot/underlying price
        r: Risk-free rate

    Returns:
        DataFrame with additional columns
    """
    enriched = df.copy()

    # Compute IV
    enriched["iv"] = implied_volatility_chain(df, underlying_price, r)

    # Compute Greeks using the IV
    deltas, gammas, thetas, vegas, rhos = [], [], [], [], []

    for _, row in enriched.iterrows():
        iv = row.get("iv", float("nan"))
        if pd.isna(iv) or iv <= 0:
            deltas.append(float("nan"))
            gammas.append(float("nan"))
            thetas.append(float("nan"))
            vegas.append(float("nan"))
            rhos.append(float("nan"))
            continue

        if "timestamp" in enriched.columns and pd.notna(row.get("timestamp")):
            current = pd.Timestamp(row["timestamp"])
        else:
            current = pd.Timestamp.now()
        expiry = pd.Timestamp(row["expiry"])
        T = max((expiry - current).days / 365.25, 1e-10)

        g = greeks(
            S=underlying_price,
            K=float(row["strike"]),
            T=T,
            r=r,
            sigma=iv,
            option_type=str(row["option_type"]),
        )
        deltas.append(g.delta)
        gammas.append(g.gamma)
        thetas.append(g.theta)
        vegas.append(g.vega)
        rhos.append(g.rho)

    enriched["delta"] = deltas
    enriched["gamma"] = gammas
    enriched["theta"] = thetas
    enriched["vega"] = vegas
    enriched["rho"] = rhos

    return enriched
