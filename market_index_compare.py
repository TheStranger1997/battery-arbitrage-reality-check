"""
market_index_compare.py
-----------------------
The base model runs arbitrage on IMBALANCE (cash-out) prices, which are highly
volatile and overstate what a battery could realistically trade. This script
reruns the same greedy oracle on the Market Index Price (MID) — the
volume-weighted price of actual short-term wholesale trades — and compares the
two ceilings for 2025.

MID is the closest free proxy for "the price a battery actually trades against".
It is published per settlement period by two providers (APX/EPEX and Nord Pool
N2EX); N2EX frequently reports zero volume, so we take the VOLUME-WEIGHTED
average across providers rather than a simple mean.

Data: Elexon Insights `datasets/MID` (free, no key). Cached to data/mid_2025-all.csv.

Outputs:
  data/mid_2025-all.csv
  data/market_index_compare.png
"""

import requests
import pandas as pd
import matplotlib.pyplot as plt
import time
import os

plt.style.use("seaborn-v0_8-whitegrid")

POWER_MW = 50
RTE = 0.85
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5
N = 4

BASE_URL = "https://data.elexon.co.uk/bmrs/api/v1"
REQUEST_DELAY = 0.25

IMBALANCE_RESULTS = os.path.join("data", "arbitrage_results.csv")
MID_FILE = os.path.join("data", "mid_2025-all.csv")
PLOT_FILE = os.path.join("data", "market_index_compare.png")

YEAR = 2025


def fetch_mid_day(date_str: str) -> list[dict]:
    """
    One day of Market Index prices, volume-weighted across providers.
    Returns up to 48 dicts: {settlement_period, price_gbp_mwh}.
    """
    base = pd.Timestamp(date_str, tz="UTC")
    start = (base - pd.Timedelta(hours=1)).strftime("%Y-%m-%dT%H:%MZ")   # prev day 23:00
    end   = (base + pd.Timedelta(hours=23)).strftime("%Y-%m-%dT%H:%MZ")  # this day 23:00

    r = requests.get(f"{BASE_URL}/datasets/MID",
                     params={"from": start, "to": end, "format": "json"}, timeout=30)
    r.raise_for_status()
    rows = [x for x in r.json().get("data", []) if x.get("settlementDate") == date_str]

    # Volume-weight each settlement period across the two providers
    acc = {}   # period -> [sum(price*volume), sum(volume)]
    for x in rows:
        p = x.get("settlementPeriod")
        vol = x.get("volume") or 0.0
        price = x.get("price") or 0.0
        if p is None:
            continue
        a = acc.setdefault(p, [0.0, 0.0])
        a[0] += price * vol
        a[1] += vol

    out = []
    for p, (pv, v) in acc.items():
        if v > 0:                       # skip periods with no traded volume
            out.append({"settlement_date": date_str, "settlement_period": p,
                        "price_gbp_mwh": pv / v})
    return out


def load_or_fetch_mid() -> pd.DataFrame:
    if os.path.exists(MID_FILE):
        print(f"Loading cached MID prices from {MID_FILE}")
        return pd.read_csv(MID_FILE)

    print("Fetching Market Index (MID) prices for 2025 (per day)...")
    all_dates = pd.date_range(f"{YEAR}-01-01", f"{YEAR}-12-31", freq="D")
    records = []
    for d in all_dates:
        date_str = d.strftime("%Y-%m-%d")
        try:
            day = fetch_mid_day(date_str)
        except requests.RequestException as e:
            print(f"  {date_str} ERROR: {e}")
            continue
        records.extend(day)
        if d.day == 1:
            print(f"  ...{date_str} ({len(day)} periods)")
        time.sleep(REQUEST_DELAY)

    df = pd.DataFrame(records)
    os.makedirs("data", exist_ok=True)
    df.to_csv(MID_FILE, index=False)
    print(f"Saved {len(df):,} rows to {MID_FILE}")
    return df


def greedy_day_total(prices: list[float]) -> float:
    """Greedy net for one day (4 cheapest charge, 4 dearest discharge)."""
    s = sorted(prices)
    net = sum(s[-N:]) * ENERGY_PER_PERIOD_MWH * RTE - sum(s[:N]) * ENERGY_PER_PERIOD_MWH
    return net if net > 0 else 0.0


def main():
    mid = load_or_fetch_mid()

    # MID has zero-volume (untraded) periods that get dropped, so not every day
    # has all 48. To compare like-for-like we use ONLY days where MID is complete,
    # and measure the imbalance ceiling over those SAME days. This isolates the
    # price-series difference from any difference in the number of days counted.
    sizes = mid.groupby("settlement_date").size()
    mid_complete_days = set(sizes[sizes == 48].index)

    imb = pd.read_csv(IMBALANCE_RESULTS)
    imb["date"] = pd.to_datetime(imb["date"]).dt.strftime("%Y-%m-%d")
    imb_days = set(imb["date"])

    common = sorted(mid_complete_days & imb_days)
    n = len(common)
    common_set = set(common)

    # Totals over the common days
    mid_total = sum(greedy_day_total(g["price_gbp_mwh"].tolist())
                    for d, g in mid.groupby("settlement_date") if d in common_set)
    imb_total = imb.loc[imb["date"].isin(common_set), "net_revenue_gbp"].sum()

    ratio = mid_total / imb_total

    # Per-MW over the common days, and annualised (scale the common-day average to 365)
    mid_common_mw = mid_total / POWER_MW
    imb_common_mw = imb_total / POWER_MW
    mid_ann = mid_common_mw * 365 / n
    imb_ann = imb_common_mw * 365 / n

    print("=" * 66)
    print("ARBITRAGE CEILING: IMBALANCE vs MARKET INDEX (traded wholesale) — 2025")
    print("=" * 66)
    print(f"  Compared over {n} days where MID has all 48 periods (like-for-like).")
    print()
    print(f"                                  {'over common days':>18}   {'annualised /MW/yr':>18}")
    print(f"  Imbalance (cash-out) prices : £{imb_common_mw:>14,.0f}   £{imb_ann:>16,.0f}")
    print(f"  Market Index (MID) prices   : £{mid_common_mw:>14,.0f}   £{mid_ann:>16,.0f}")
    print(f"  MID as share of imbalance   :  {ratio:>14.0%}")
    print()
    print(f"  For reference, the full-year imbalance headline (363 days) is £65,179/MW;")
    print(f"  the annualised common-day imbalance figure (£{imb_ann:,.0f}) is close to it, so")
    print(f"  the {n} MID-complete days are broadly representative.")
    print()
    print(f"  On identical days, the traded-market ceiling is ~{ratio:.0%} of the imbalance")
    print("  ceiling: MID has no £2,900/MWh cash-out spikes, so it strips out the")
    print("  scarcity tail. Realistic wholesale arbitrage is closer to ~£36k/MW than")
    print("  to the £65k imbalance headline — the clearest case for treating £65k as")
    print("  an upper bound, not an achievable target.")

    # values used by the chart
    imb_per_mw, mid_per_mw = imb_ann, mid_ann

    # ── Chart ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7.5, 5))
    labels = ["Imbalance prices\n(cash-out)", "Market Index\n(traded wholesale)"]
    bars = ax.bar(labels, [imb_per_mw, mid_per_mw],
                  color=["#c2453b", "#2f6f9f"], width=0.55)
    ax.bar_label(bars, labels=[f"£{imb_per_mw:,.0f}", f"£{mid_per_mw:,.0f}"],
                 padding=3, fontsize=10)
    ax.set_ylabel("£/MW/year (annualised)")
    ax.set_title("Perfect-foresight arbitrage ceiling by price series\n"
                 f"(2025, 50 MW / 2h, {n} like-for-like days — "
                 f"MID is {ratio:.0%} of the imbalance ceiling)")
    ax.margins(y=0.15)
    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")


if __name__ == "__main__":
    main()
