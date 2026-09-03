"""
Monte Carlo simulator for options positions.

Uses Geometric Brownian Motion (GBM) to simulate underlying price paths
and evaluates multi-leg options positions against them. Employs antithetic
variates for variance reduction.

The key output: for any position, what is the probability of profit,
expected P&L, and tail risk (VaR)?
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.data_engine.schema import OptionLeg, OptionType, Side


# ── Data structures ───────────────────────────────────────────────────

@dataclass
class MonteCarloResult:
    """Results from Monte Carlo simulation of a position."""
    # Raw simulation data
    terminal_prices: np.ndarray         # Final underlying prices (n_paths,)
    position_pnls: np.ndarray           # P&L for each path (n_paths,)

    # Probability metrics
    probability_of_profit: float        # % of paths where P&L > 0
    probability_of_loss: float          # % of paths where P&L <= 0

    # P&L statistics
    expected_pnl: float                 # Mean P&L
    median_pnl: float                   # Median P&L
    std_pnl: float                      # Std dev of P&L

    # Tail risk
    var_5pct: float                     # 5th percentile P&L (Value at Risk)
    var_1pct: float                     # 1st percentile P&L (worst-case)
    best_case_5pct: float               # 95th percentile P&L

    # Expected move
    expected_move: float                # ±1σ expected move in underlying
    prob_inside_expected: float         # % of paths inside ±1σ

    # Metadata
    n_paths: int = 0
    volatility_used: float = 0.0
    time_to_expiry: float = 0.0


# ── Path simulation ──────────────────────────────────────────────────

def simulate_paths(
    S0: float,
    sigma: float,
    T: float,
    r: float = 0.07,
    n_paths: int = 100_000,
    n_steps: int | None = None,
    seed: int | None = None,
) -> np.ndarray:
    """
    Simulate underlying price paths using Geometric Brownian Motion.

    Uses antithetic variates: for each random path Z, we also simulate
    the path -Z. This halves the variance without extra random draws.

    Args:
        S0: Current underlying price
        sigma: Volatility (annualized)
        T: Time to expiry (years)
        r: Risk-free rate (drift)
        n_paths: Number of simulation paths (will be rounded to even)
        n_steps: Steps per path (defaults to trading days remaining)
        seed: Random seed for reproducibility

    Returns:
        Array of shape (n_paths, n_steps+1) with price paths.
        Column 0 is S0, column -1 is terminal price.
    """
    if T <= 0:
        return np.full((n_paths, 1), S0)

    if n_steps is None:
        n_steps = max(1, int(T * 252))  # Trading days

    if seed is not None:
        np.random.seed(seed)

    dt = T / n_steps
    half_paths = n_paths // 2

    # Generate random shocks for half the paths
    Z = np.random.standard_normal((half_paths, n_steps))

    # Antithetic variates: use both Z and -Z
    Z_anti = np.vstack([Z, -Z])

    # GBM: S(t+dt) = S(t) * exp((r - 0.5σ²)dt + σ√dt · Z)
    drift = (r - 0.5 * sigma**2) * dt
    diffusion = sigma * np.sqrt(dt) * Z_anti

    log_returns = drift + diffusion
    cumulative = np.cumsum(log_returns, axis=1)

    # Build full paths including S0
    paths = np.zeros((Z_anti.shape[0], n_steps + 1))
    paths[:, 0] = S0
    paths[:, 1:] = S0 * np.exp(cumulative)

    return paths


def simulate_terminal_prices(
    S0: float,
    sigma: float,
    T: float,
    r: float = 0.07,
    n_paths: int = 100_000,
    seed: int | None = None,
) -> np.ndarray:
    """
    Simulate only terminal prices (faster than full paths).

    Directly samples from the log-normal distribution of GBM terminal values.
    """
    if T <= 0:
        return np.full(n_paths, S0)

    if seed is not None:
        np.random.seed(seed)

    half = n_paths // 2
    Z = np.random.standard_normal(half)
    Z_anti = np.concatenate([Z, -Z])

    drift = (r - 0.5 * sigma**2) * T
    diffusion = sigma * np.sqrt(T) * Z_anti

    return S0 * np.exp(drift + diffusion)


# ── Position analysis ─────────────────────────────────────────────────

def _option_payoff_at_expiry(
    terminal_price: np.ndarray,
    strike: float,
    option_type: OptionType,
) -> np.ndarray:
    """Compute intrinsic value / payoff at expiry."""
    if option_type == OptionType.CE:
        return np.maximum(terminal_price - strike, 0)
    else:
        return np.maximum(strike - terminal_price, 0)


def analyze_position(
    S0: float,
    sigma: float,
    T: float,
    legs: list[OptionLeg],
    entry_prices: dict[tuple[float, str], float],
    lot_size: int = 65,
    r: float = 0.07,
    n_paths: int = 100_000,
    seed: int | None = None,
) -> MonteCarloResult:
    """
    Run Monte Carlo simulation for a multi-leg options position.

    For each simulated terminal price, compute the P&L of the position
    (payoff at expiry minus entry cost).

    Args:
        S0: Current underlying price
        sigma: Volatility to use for simulation
        T: Time to expiry (years)
        legs: List of OptionLeg defining the position
        entry_prices: Dict mapping (strike, option_type) → entry price per unit
        lot_size: Contract lot size
        r: Risk-free rate
        n_paths: Number of Monte Carlo paths
        seed: Random seed

    Returns:
        MonteCarloResult with probability, P&L, and risk metrics
    """
    # Simulate terminal prices
    terminal = simulate_terminal_prices(S0, sigma, T, r, n_paths, seed)

    # Compute P&L for each path
    pnls = np.zeros(len(terminal))

    for leg in legs:
        payoff = _option_payoff_at_expiry(terminal, leg.strike, leg.option_type)
        entry_key = (leg.strike, leg.option_type.value)
        entry_price = entry_prices.get(entry_key, 0)

        if leg.side == Side.SELL:
            # Sold: received premium, pay payoff at expiry
            leg_pnl = (entry_price - payoff) * leg.lots * lot_size
        else:
            # Bought: paid premium, receive payoff at expiry
            leg_pnl = (payoff - entry_price) * leg.lots * lot_size

        pnls += leg_pnl

    # Compute statistics
    expected_move = S0 * sigma * np.sqrt(T)
    actual_moves = terminal - S0
    inside_expected = np.abs(actual_moves) <= expected_move

    return MonteCarloResult(
        terminal_prices=terminal,
        position_pnls=pnls,
        probability_of_profit=float(np.mean(pnls > 0) * 100),
        probability_of_loss=float(np.mean(pnls <= 0) * 100),
        expected_pnl=float(np.mean(pnls)),
        median_pnl=float(np.median(pnls)),
        std_pnl=float(np.std(pnls)),
        var_5pct=float(np.percentile(pnls, 5)),
        var_1pct=float(np.percentile(pnls, 1)),
        best_case_5pct=float(np.percentile(pnls, 95)),
        expected_move=expected_move,
        prob_inside_expected=float(np.mean(inside_expected) * 100),
        n_paths=len(terminal),
        volatility_used=sigma,
        time_to_expiry=T,
    )


def quick_pop(
    S0: float,
    sigma: float,
    T: float,
    legs: list[OptionLeg],
    entry_prices: dict[tuple[float, str], float],
    lot_size: int = 65,
    r: float = 0.07,
) -> float:
    """
    Quick probability-of-profit calculation using 50K paths.

    Faster than full analyze_position — use for batch computations
    during backtesting.
    """
    result = analyze_position(
        S0=S0, sigma=sigma, T=T, legs=legs,
        entry_prices=entry_prices, lot_size=lot_size,
        r=r, n_paths=50_000, seed=42,
    )
    return result.probability_of_profit
