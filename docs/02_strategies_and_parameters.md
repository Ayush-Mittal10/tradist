# Strategies and Parameters Deep Dive

NIFTY Quant Lab includes 6 foundational strategies. Understanding their mechanics, ideal market conditions, and parameters is crucial for profitability.

---

## 1. Short Straddle (ATM)
**Mechanics:** Sell 1 ATM Call (CE) and 1 ATM Put (PE) at the nearest expiry.
**Ideal Market:** Sideways/Range-bound markets. High Implied Volatility (IV) that is expected to crush.
**Risk Profile:** Undefined risk. If the market makes a massive directional move, losses can be theoretically infinite.

## 2. Short Strangle (OTM)
**Mechanics:** Sell 1 OTM CE and 1 OTM PE.
**Ideal Market:** Sideways markets with a slightly wider expected range than a Straddle.
**Risk Profile:** Undefined risk, but higher probability of profit (Win Rate) than a Straddle due to wider strikes. Lower premium collected.

## 3. Bull Call Spread
**Mechanics:** Buy 1 ITM/ATM CE, Sell 1 OTM CE.
**Ideal Market:** Mildly to strongly bullish markets.
**Risk Profile:** Defined risk. Max loss is limited to the net premium paid. Max profit is limited to (Strike Difference - Net Premium). Margin friendly.

## 4. Bear Call Spread
**Mechanics:** Sell 1 ITM/ATM CE, Buy 1 OTM CE.
**Ideal Market:** Mildly to strongly bearish markets.
**Risk Profile:** Defined risk. Max loss is limited to (Strike Difference - Net Premium). Max profit is limited to net premium received. Margin friendly.

## 5. Buy CE (+Day) / Momentum
**Mechanics:** Buy 1 ATM/OTM CE based on momentum indicators.
**Ideal Market:** Explosive breakout days (Bullish).
**Risk Profile:** Defined risk (premium paid). Very low win rate, but extremely high Reward-to-Risk ratio.

## 6. Buy PE (-Day) / Momentum
**Mechanics:** Buy 1 ATM/OTM PE.
**Ideal Market:** Explosive breakdown days (Bearish).
**Risk Profile:** Defined risk (premium paid).

---

## Universal Strategy Parameters

All strategies share a set of configurable parameters that dictate risk management.

### 1. `stop_loss_pct` (Stop Loss Percentage)
*   **How it works:** Exits the trade if the position's P&L drops below this threshold relative to the entry premium. 
*   **Usage:** Set this to cap your losses. For example, in a Short Straddle, if you collect ₹10,000 in premium and set `stop_loss_pct=25.0`, the system will exit the trade if the combined premium of the short legs increases such that you lose ₹2,500.
*   **Danger:** Setting it too tight (e.g., 5%) will cause you to get stopped out constantly by normal market noise (whipsaws).

### 2. `profit_target_pct` (Profit Target Percentage)
*   **How it works:** Exits the trade early if the P&L reaches this threshold.
*   **Usage:** For a Short Straddle, you might target 50% of the max possible profit. If you collect ₹10,000, setting `profit_target_pct=50.0` will exit the trade once you are up ₹5,000, without waiting for expiry.
*   **Danger:** Setting it too low caps your winners, ruining the Expected Value of the system.

### 3. `lots_per_trade`
*   **How it works:** The number of lots executed per leg. (1 NIFTY lot = usually 25 or 50 or 75 qty depending on the era, in this lab it's configurable).
*   **Usage:** Scale your strategy size. Ensure your `Capital` setting in the UI is sufficient to cover the margin for this many lots.

### 4. `max_positions`
*   **How it works:** Limits how many concurrent trades the strategy can have open at the same time.
*   **Usage:** Set to 1 for a purely sequential strategy (wait for trade to finish before taking another). Set higher if you want to ladder entries across different days.
