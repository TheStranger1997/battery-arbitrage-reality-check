"""
fetch_prices.py
---------------
Downloads a full year of GB half-hourly settlement system prices from the
Elexon Insights API, one month at a time.

Each month is saved to data/prices_YYYY-MM.csv.  If a file already exists
it is skipped — so re-running is safe and fast.

A combined file data/prices_YYYY-all.csv is written at the end.

Settlement periods run 1–48, each covering 30 minutes starting at 23:00 UTC
the *previous* calendar day (GB electricity settlement convention).
We convert them to a clean UTC datetime index for simplicity.

Run with:  python fetch_prices.py
"""

import requests
import pandas as pd
import time
import os
import matplotlib.pyplot as plt
from datetime import date, timedelta

plt.style.use("seaborn-v0_8-whitegrid")

# ── Configuration ──────────────────────────────────────────────────────────────

# Year to fetch — all 12 months are downloaded; existing monthly files are skipped
YEAR = 2025

# Elexon Insights API base URL (no API key required)
BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"

OUTPUT_DIR    = "data"
COMBINED_FILE = os.path.join(OUTPUT_DIR, f"prices_{YEAR}-all.csv")

# Polite delay between API calls (seconds)
REQUEST_DELAY = 0.3

# ── Helpers ────────────────────────────────────────────────────────────────────

def fetch_day(settlement_date: str) -> list[dict]:
    """
    Fetch all 48 settlement periods for a single date.
    settlement_date: 'YYYY-MM-DD' string.
    Returns a list of dicts from the API's 'data' array.
    """
    url = f"{BASE_URL}/balancing/settlement/system-prices/{settlement_date}"
    response = requests.get(url, params={"format": "json"}, timeout=15)
    response.raise_for_status()  # blow up clearly if the API returns an error
    return response.json().get("data", [])


def period_to_datetime(settlement_date: str, period: int) -> pd.Timestamp:
    """
    Convert an Elexon settlement date + period number to a UTC timestamp.

    GB settlement convention:
      Period 1  = 23:00 UTC on the *previous* calendar day
      Period 2  = 23:30 UTC on the previous calendar day
      Period 3  = 00:00 UTC on the settlement date
      ...
      Period 48 = 22:30 UTC on the settlement date

    So period 1 maps to (settlement_date - 1 day) at 23:00 UTC.
    Each subsequent period adds 30 minutes.
    """
    base = pd.Timestamp(settlement_date, tz="UTC") - pd.Timedelta(hours=1)
    return base + pd.Timedelta(minutes=30 * (period - 1))


# ── Helpers ── (month boundaries) ─────────────────────────────────────────────

def month_date_range(year: int, month: int) -> list[date]:
    """Return every calendar date in the given year/month."""
    start = date(year, month, 1)
    end   = date(year, month + 1, 1) - timedelta(days=1) if month < 12 \
            else date(year + 1, 1, 1) - timedelta(days=1)
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def fetch_month(year: int, month: int) -> pd.DataFrame:
    """Download all days in a month and return a tidy DataFrame."""
    dates = month_date_range(year, month)
    records = []

    for d in dates:
        date_str = d.strftime("%Y-%m-%d")
        print(f"    {date_str}...", end=" ")

        try:
            raw = fetch_day(date_str)
        except requests.RequestException as e:
            print(f"ERROR: {e}")
            continue

        for item in raw:
            period = item.get("settlementPeriod")
            if period is None:
                continue
            records.append({
                "datetime_utc":       period_to_datetime(date_str, period),
                "settlement_date":    date_str,
                "settlement_period":  period,
                "sell_price_gbp_mwh": item.get("systemSellPrice"),
                "buy_price_gbp_mwh":  item.get("systemBuyPrice"),
            })

        print(f"{len(raw)} periods")
        time.sleep(REQUEST_DELAY)

    df = pd.DataFrame(records).sort_values("datetime_utc").set_index("datetime_utc")
    df["mid_price_gbp_mwh"] = (df["sell_price_gbp_mwh"] + df["buy_price_gbp_mwh"]) / 2
    return df


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    monthly_frames = []

    for month in range(1, 13):
        month_file = os.path.join(OUTPUT_DIR, f"prices_{YEAR}-{month:02d}.csv")
        month_label = date(YEAR, month, 1).strftime("%B %Y")

        if os.path.exists(month_file):
            print(f"  {month_label}: already downloaded — loading from {month_file}")
            df_month = pd.read_csv(month_file, index_col="datetime_utc", parse_dates=True)
        else:
            print(f"  {month_label}: fetching from API...")
            df_month = fetch_month(YEAR, month)
            df_month.to_csv(month_file)
            print(f"    → saved to {month_file}")

        monthly_frames.append(df_month)

    # Concatenate all months into one combined file
    combined = pd.concat(monthly_frames).sort_index()
    combined.to_csv(COMBINED_FILE)

    print(f"\nCombined file: {COMBINED_FILE}")
    print(f"Total rows: {len(combined):,}  (expected {365 * 48:,} for a non-leap year)")
    stats = combined["mid_price_gbp_mwh"].agg(["count", "min", "max", "mean"]).round(2)
    print(f"Mid price (£/MWh)  count={stats['count']:.0f}  "
          f"min={stats['min']}  max={stats['max']}  mean={stats['mean']}")


if __name__ == "__main__":
    main()
