"""
Generate a synthetic NIFTY options dataset for testing.

Creates a small but realistic dataset with known expected outcomes,
allowing us to validate the backtest engine deterministically.
"""

import csv
import os
from datetime import date, timedelta


def generate_sample_data():
    """
    Generate 10 trading days of synthetic NIFTY options data.

    Scenario:
    - NIFTY starts at 25000, moves to 25200 over 10 days
    - One weekly expiry at day 5, one at day 10
    - Strikes: 24800, 25000, 25200, 25400 (CE and PE)
    - Prices follow simplified Black-Scholes-ish behavior
    """

    trading_days = []
    start_date = date(2025, 6, 2)  # Monday

    for i in range(10):
        d = start_date + timedelta(days=i)
        # Skip weekends
        if d.weekday() >= 5:
            d += timedelta(days=(7 - d.weekday()))
        trading_days.append(d)

    # Deduplicate and sort (simplified: just use business days)
    trading_days = [
        date(2025, 6, 2),   # Mon
        date(2025, 6, 3),   # Tue
        date(2025, 6, 4),   # Wed
        date(2025, 6, 5),   # Thu - expiry 1
        date(2025, 6, 6),   # Fri
        date(2025, 6, 9),   # Mon
        date(2025, 6, 10),  # Tue
        date(2025, 6, 11),  # Wed
        date(2025, 6, 12),  # Thu - expiry 2
        date(2025, 6, 13),  # Fri
    ]

    expiry1 = date(2025, 6, 5)    # Thursday
    expiry2 = date(2025, 6, 12)   # Thursday

    # Underlying prices (NIFTY spot)
    underlying_prices = {
        date(2025, 6, 2):  25000,
        date(2025, 6, 3):  25050,   # +50 (positive day)
        date(2025, 6, 4):  24980,   # -70 (negative day)
        date(2025, 6, 5):  25020,   # +40 (positive, expiry day)
        date(2025, 6, 6):  25100,   # +80 (positive)
        date(2025, 6, 9):  25080,   # -20 (negative)
        date(2025, 6, 10): 25150,   # +70 (positive)
        date(2025, 6, 11): 25200,   # +50 (positive)
        date(2025, 6, 12): 25180,   # -20 (negative, expiry day)
        date(2025, 6, 13): 25220,   # +40 (positive)
    }

    strikes = [24800, 25000, 25200, 25400]

    rows = []

    for day in trading_days:
        spot = underlying_prices[day]

        # Determine which expiry is active
        if day <= expiry1:
            expiry = expiry1
            dte = (expiry1 - day).days
        else:
            expiry = expiry2
            dte = (expiry2 - day).days

        for strike in strikes:
            for opt_type in ["CE", "PE"]:
                # Simplified pricing
                intrinsic = max(0, spot - strike) if opt_type == "CE" else max(0, strike - spot)
                time_value = max(5, 50 * (dte / 5))  # Rough time decay

                if opt_type == "CE":
                    # CE price decreases as strike goes higher
                    otm_distance = max(0, strike - spot)
                    base_price = intrinsic + time_value * max(0.2, 1 - otm_distance / 500)
                else:
                    # PE price decreases as strike goes lower
                    otm_distance = max(0, spot - strike)
                    base_price = intrinsic + time_value * max(0.2, 1 - otm_distance / 500)

                # On expiry day, price = intrinsic value
                if dte == 0:
                    base_price = max(0.05, intrinsic)

                close_price = round(max(0.05, base_price), 2)
                open_price = round(close_price * 1.02, 2)
                high_price = round(close_price * 1.05, 2)
                low_price = round(close_price * 0.95, 2)

                rows.append({
                    "Date": day.strftime("%d-%b-%Y"),
                    "Symbol": "NIFTY",
                    "Expiry Date": expiry.strftime("%d-%b-%Y"),
                    "Strike Price": strike,
                    "Option Type": opt_type,
                    "Open": open_price,
                    "High": high_price,
                    "Low": low_price,
                    "Close": close_price,
                    "Volume": 50000 + (10000 if abs(strike - spot) < 200 else 0),
                    "Open Interest": 100000,
                    "Underlying Value": spot,
                })

    return rows


def write_sample_csv(filepath: str = None):
    """Write the sample dataset to a CSV file."""
    if filepath is None:
        filepath = os.path.join(os.path.dirname(__file__), "fixtures", "sample_nifty.csv")

    rows = generate_sample_data()
    fieldnames = list(rows[0].keys())

    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return filepath


if __name__ == "__main__":
    path = write_sample_csv()
    print(f"Generated sample data: {path}")
    print(f"Rows: {len(generate_sample_data())}")
