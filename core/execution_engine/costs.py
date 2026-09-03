"""
Indian options transaction cost model (2026 rates).

Accurately models all regulatory and brokerage charges for NIFTY options
traded on NSE. Provides three presets for different levels of realism.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class CostPreset(str, Enum):
    ZERO = "Zero Costs"
    REALISTIC = "Realistic"
    CONSERVATIVE = "Conservative"


@dataclass(frozen=True)
class CostConfig:
    """Configuration for transaction cost calculation."""
    # Brokerage
    brokerage_per_order: float = 20.0           # ₹20 per order (discount broker)

    # Securities Transaction Tax
    stt_sell_rate: float = 0.0015               # 0.15% on sell premium
    stt_exercise_rate: float = 0.0015           # 0.15% on intrinsic value at exercise

    # Exchange transaction charges
    exchange_rate: float = 0.0005               # ~0.05% on premium

    # SEBI turnover fee
    sebi_rate: float = 0.000001                 # 0.0001% (₹10 per crore)

    # GST on services (brokerage + exchange + SEBI)
    gst_rate: float = 0.18                      # 18%

    # Stamp duty (buy side only)
    stamp_duty_rate: float = 0.00003            # 0.003% on premium

    # Slippage (additional safety margin)
    slippage_pct: float = 0.0                   # Additional % slippage on execution


# Pre-defined cost configurations
COST_PRESETS: dict[CostPreset, CostConfig] = {
    CostPreset.ZERO: CostConfig(
        brokerage_per_order=0.0,
        stt_sell_rate=0.0,
        stt_exercise_rate=0.0,
        exchange_rate=0.0,
        sebi_rate=0.0,
        gst_rate=0.0,
        stamp_duty_rate=0.0,
        slippage_pct=0.0,
    ),
    CostPreset.REALISTIC: CostConfig(),  # Defaults are realistic 2026 rates
    CostPreset.CONSERVATIVE: CostConfig(
        slippage_pct=0.001,              # Extra 0.1% slippage
    ),
}


@dataclass
class CostBreakdown:
    """Detailed breakdown of all costs for a single leg execution."""
    brokerage: float = 0.0
    stt: float = 0.0
    exchange_charges: float = 0.0
    sebi_fees: float = 0.0
    gst: float = 0.0
    stamp_duty: float = 0.0
    slippage: float = 0.0

    @property
    def total(self) -> float:
        return (self.brokerage + self.stt + self.exchange_charges +
                self.sebi_fees + self.gst + self.stamp_duty + self.slippage)


def calculate_costs(
    premium: float,
    is_buy: bool,
    config: CostConfig | None = None,
    is_exercise: bool = False,
    intrinsic_value: float = 0.0,
) -> CostBreakdown:
    """
    Calculate all transaction costs for an option trade.

    Args:
        premium: Total premium amount (price × lots × lot_size)
        is_buy: True if buying, False if selling
        config: Cost configuration (defaults to REALISTIC)
        is_exercise: True if this is an exercise at expiry
        intrinsic_value: For exercise, the intrinsic value of the option

    Returns:
        Detailed cost breakdown
    """
    if config is None:
        config = COST_PRESETS[CostPreset.REALISTIC]

    costs = CostBreakdown()
    abs_premium = abs(premium)

    # Brokerage: flat per order
    costs.brokerage = config.brokerage_per_order

    # STT: only on sell side
    if not is_buy:
        if is_exercise:
            costs.stt = abs(intrinsic_value) * config.stt_exercise_rate
        else:
            costs.stt = abs_premium * config.stt_sell_rate

    # Exchange transaction charges: on premium
    costs.exchange_charges = abs_premium * config.exchange_rate

    # SEBI fees: on premium
    costs.sebi_fees = abs_premium * config.sebi_rate

    # GST: 18% on (brokerage + exchange + SEBI)
    gst_base = costs.brokerage + costs.exchange_charges + costs.sebi_fees
    costs.gst = gst_base * config.gst_rate

    # Stamp duty: buy side only
    if is_buy:
        costs.stamp_duty = abs_premium * config.stamp_duty_rate

    # Slippage
    costs.slippage = abs_premium * config.slippage_pct

    return costs


def format_cost_summary(costs: CostBreakdown) -> str:
    """Format a cost breakdown for display."""
    lines = [
        f"  Brokerage:    ₹{costs.brokerage:>10,.2f}",
        f"  STT:          ₹{costs.stt:>10,.2f}",
        f"  Exchange:     ₹{costs.exchange_charges:>10,.2f}",
        f"  SEBI:         ₹{costs.sebi_fees:>10,.2f}",
        f"  GST:          ₹{costs.gst:>10,.2f}",
        f"  Stamp Duty:   ₹{costs.stamp_duty:>10,.2f}",
        f"  Slippage:     ₹{costs.slippage:>10,.2f}",
        f"  ─────────────────────────",
        f"  Total:        ₹{costs.total:>10,.2f}",
    ]
    return "\n".join(lines)
