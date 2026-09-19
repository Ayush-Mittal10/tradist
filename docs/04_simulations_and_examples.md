# Example Simulations & Sample Trades

This document provides concrete examples of what a simulation looks like in NIFTY Quant Lab, contrasting a Backtest run with a Live Paper Trade run.

---

## 1. Historical Simulation: The "Safe" Short Strangle

### Scenario
We want to test if selling far OTM options (Short Strangle) generates consistent premium with low risk during the year 2023.

### Configuration
*   **Data:** 1 Year of 1-minute NIFTY option chain data (Jan 2023 - Dec 2023)
*   **Strategy:** Short Strangle
*   **Capital:** ₹5,00,000
*   **Lot Size:** 50 (Nifty lot size in 2023)
*   **Parameters:**
    *   `stop_loss_pct`: 30.0% (Exit if premium spikes by 30%)
    *   `profit_target_pct`: 60.0% (Book profit early if we capture 60% of max possible)
    *   `lots_per_trade`: 1

### Expected Output & Interpretation
1.  **Trade Log:** The engine simulates finding the nearest expiry, finding OTM strikes (e.g., NIFTY at 18000, sells 18300 CE and 17700 PE). 
2.  **Costs:** It deducts ₹20 brokerage per leg, plus 0.15% STT on the sell side.
3.  **Result Example:** 
    *   **Win Rate:** 85% (Strangles win often).
    *   **Max Drawdown:** 12% (The 30% stop loss prevented account blowups during unexpected rallies).
    *   **Profit Factor:** 1.8. 
    *   **Action:** This is a highly viable system. Move to Paper Trading.

---

## 2. Live Paper Trade: Momentum Breakout

### Scenario
We found an edge in backtesting: buying ATM Calls when NIFTY breaks a specific morning range. We now want to validate it live without risking real capital.

### Configuration
*   **Tab:** 📡 Paper Trading
*   **Strategy:** Buy CE (+Day)
*   **Capital:** ₹1,00,000 (Defined risk strategy requires much less margin)
*   **Poll Interval:** 30 seconds (Engine checks Upstox live feed every 30s)
*   **Parameters:**
    *   `stop_loss_pct`: 15.0%
    *   `profit_target_pct`: 100.0% (Looking for 1:1 or better payouts on explosive moves)

### Live Dashboard Experience
1.  **9:15 AM:** You hit **START PAPER TRADING**. The dashboard shows "🟢 OPEN" and begins ticking.
2.  **10:30 AM (Signal Generated):** The strategy logic triggers. The engine fetches the *live* Upstox option chain, finds the ATM CE, and simulates a BUY order.
3.  **10:30 AM (Order Book):** The "Open Positions" table populates with the CE leg, showing live entry price. 
4.  **10:31 AM (MTM Tracking):** As NIFTY moves, the "REALIZED P&L" updates dynamically on every 30s tick based on the live Bid/Ask spreads from Upstox.
5.  **11:45 AM (Exit Triggered):** NIFTY stalls. The option premium drops 15% from entry. The `stop_loss_pct` logic fires an EXIT signal. 
6.  **Post-Trade:** The trade moves to "Completed Trades". The dashboard calculates the exact simulated loss, *including* the GST and STT that would have been charged by the broker.

### Why this is critical?
If the backtest said you would have lost ₹1,500 on this trade, but the live paper trade lost ₹1,800, you have discovered **Slippage**. The live market bid/ask spreads were wider than the historical CSV implied. You must now adjust your backtest assumptions to account for this reality before trading with real money!
