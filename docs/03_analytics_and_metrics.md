# Deep Dive into Analytics, Metrics & Charts

NIFTY Quant Lab provides a robust results dashboard. Understanding these metrics is the difference between gambling and systematic trading.

## Primary Metrics

### 1. NET P&L & Return on Capital (CAGR)
*   **What it implies:** The absolute profit or loss after all transaction costs (STT, brokerage, etc.). CAGR (Compound Annual Growth Rate) normalizes this return over time.
*   **How to use it:** Don't chase the highest Net P&L. A strategy with 50% CAGR might have a 60% drawdown, making it un-tradeable in reality. Look for consistent, moderate returns (e.g., 20-30% CAGR).

### 2. MAX DRAWDOWN (Absolute & %)
*   **What it implies:** The largest peak-to-trough drop in your equity curve. If you started with ₹1,00,000, grew it to ₹1,50,000, and then dropped to ₹1,20,000 before hitting new highs, your Max Drawdown is ₹30,000 (20%).
*   **How to use it:** This is the **most important metric**. Can you stomach a 30% drop in your portfolio without turning off the system? If no, tweak your Stop Loss percentage or reduce your position sizing.

### 3. WIN RATE & Expected Value (EV)
*   **What it implies:** 
    *   **Win Rate:** Percentage of trades that were profitable. 
    *   **EV:** The mathematical average amount you make per trade over the long run.
*   **How to use it:** A 90% win rate is useless if EV is negative (meaning your 10% losses wipe out all your 90% small wins). Trend following systems often have 35-40% win rates but highly positive EV because winners are huge. Straddles have high win rates but require strict stop losses to maintain a positive EV.

### 4. PROFIT FACTOR
*   **What it implies:** Gross Profits / Gross Losses. 
*   **How to use it:** 
    *   `< 1.0`: You are losing money.
    *   `1.0 - 1.5`: Marginally profitable, likely will fail in a live market due to unseen slippages.
    *   `> 1.5`: Strong edge. Highly tradeable.
    *   `> 2.5`: Exceptional (or slightly overfitted, be careful).

### 5. SHARPE RATIO
*   **What it implies:** Risk-adjusted return. How much excess return you are receiving for the extra volatility you endure.
*   **How to use it:** Aim for > 1.0. A Sharpe of 0.5 means your equity curve is a wild rollercoaster for very little payout.

---

## Interactive Charts

### 1. Equity Curve
*   **What it is:** A line chart showing your capital over time.
*   **What to look for:** Look for a 45-degree angle going up and to the right. Avoid curves that are flat for 3 years and then spike in 1 month—this means your strategy relies on rare black swan events and isn't consistent.

### 2. Underwater Drawdown Chart
*   **What it is:** Shows how deep in a hole you are at any given time.
*   **What to look for:** Look at the *duration* of drawdowns. If the chart shows you spend 80% of the year in a drawdown, it's psychologically exhausting. Aim for quick recoveries.

### 3. P&L Distribution (Histogram)
*   **What it is:** Shows the frequency of different profit/loss amounts.
*   **What to look for:** 
    *   A fat tail on the right (profits) is good. 
    *   A fat tail on the left (losses) means your Stop Loss parameter is too loose or non-existent.

### 4. Monthly Returns Heatmap
*   **What it is:** A grid showing % return for every month of every year.
*   **What to look for:** Consistency. If 2024 was completely red but 2025 made up for it, the strategy is highly dependent on specific market regimes (e.g., low VIX vs high VIX). Use this to know when your strategy is *supposed* to underperform.
