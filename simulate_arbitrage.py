"""
simulate_arbitrage.py
---------------------
Simulates perfect-foresight price arbitrage for a 50 MW / 100 MWh BESS
over a full year of half-hourly GB settlement prices.

"Perfect foresight" (oracle) means the battery knows all 48 prices for the
day in advance and picks the globally optimal charge/discharge windows.
This is an UPPER BOUND on achievable arbitrage revenue — a real battery bids
into markets without knowing future prices.

Outputs:
  data/arbitrage_results.csv   — daily P&L breakdown
  data/daily_pnl_plot.png      — daily revenue bars + monthly summary
"""

import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import os

plt.style.use("seaborn-v0_8-whitegrid")

# ── Battery parameters ─────────────────────────────────────────────────────────

POWER_MW     = 50               # nameplate power (MW)
DURATION_H   = 2                # duration (hours) → 2-hour battery
CAPACITY_MWH = POWER_MW * DURATION_H   # 100 MWh usable storage

# Round-trip efficiency: for every 1 MWh drawn from the grid to charge,
# only 0.85 MWh can be delivered back to the grid when discharging.
RTE = 0.85

# Each half-hour period at full power moves this much energy
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5   # 25 MWh per period

# Periods to complete one full charge (or discharge) at rated power
PERIODS_PER_CYCLE = int(CAPACITY_MWH / ENERGY_PER_PERIOD_MWH)   # = 4

# ── Paths ──────────────────────────────────────────────────────────────────────

PRICES_FILE  = os.path.join("data", "prices_2025-all.csv")
RESULTS_FILE = os.path.join("data", "arbitrage_results.csv")

# ── Core logic ─────────────────────────────────────────────────────────────────

def simulate_day(prices: pd.Series) -> dict:
    """
    Perfect-foresight arbitrage for a single day.

    Given all 48 half-hourly prices, we:
      1. Sort periods by price (ascending).
      2. Designate the 4 cheapest periods as CHARGE windows.
         → We buy 100 MWh from the grid (4 × 25 MWh).
      3. Designate the 4 most expensive periods as DISCHARGE windows.
         → We sell 85 MWh to the grid (100 MWh × 0.85 RTE).
      4. Skip the day entirely if net revenue would be negative.

    No intraday SoC tracking is needed here because we're computing the
    upper-bound P&L, not scheduling a real dispatch. The SoC constraint
    (can't discharge what you haven't charged) is satisfied implicitly
    because we charge 100 MWh before assessing discharge revenue.
    """
    prices_sorted = prices.sort_values()

    charge_prices    = prices_sorted.iloc[:PERIODS_PER_CYCLE]   # 4 cheapest
    discharge_prices = prices_sorted.iloc[-PERIODS_PER_CYCLE:]  # 4 most expensive

    # Cost: buy 25 MWh at each of the 4 charge prices
    charge_cost_gbp = (charge_prices * ENERGY_PER_PERIOD_MWH).sum()

    # Revenue: sell 25 × 0.85 = 21.25 MWh at each of the 4 discharge prices
    # (RTE applied at discharge: every MWh charged → 0.85 MWh available to sell)
    energy_sold_per_period = ENERGY_PER_PERIOD_MWH * RTE   # 21.25 MWh
    discharge_revenue_gbp  = (discharge_prices * energy_sold_per_period).sum()

    net_revenue_gbp = discharge_revenue_gbp - charge_cost_gbp

    # A rational operator doesn't trade if it costs money
    if net_revenue_gbp <= 0:
        return {
            "traded":                    False,
            "charge_cost_gbp":           0.0,
            "discharge_revenue_gbp":     0.0,
            "net_revenue_gbp":           0.0,
            "avg_charge_price_gbp_mwh":  None,
            "avg_discharge_price_gbp_mwh": None,
            "price_spread_gbp_mwh":      None,
        }

    return {
        "traded":                    True,
        "charge_cost_gbp":           round(charge_cost_gbp, 2),
        "discharge_revenue_gbp":     round(discharge_revenue_gbp, 2),
        "net_revenue_gbp":           round(net_revenue_gbp, 2),
        "avg_charge_price_gbp_mwh":  round(charge_prices.mean(), 2),
        "avg_discharge_price_gbp_mwh": round(discharge_prices.mean(), 2),
        # Effective spread the battery exploits each day
        "price_spread_gbp_mwh":      round(discharge_prices.mean() - charge_prices.mean(), 2),
    }


def main():
    # ── Load prices ────────────────────────────────────────────────────────────

    df = pd.read_csv(PRICES_FILE, index_col="datetime_utc", parse_dates=True)
    year = df["settlement_date"].iloc[0][:4]
    print(f"Loaded {len(df):,} half-hourly prices from {PRICES_FILE}")
    print(f"Battery: {POWER_MW} MW / {CAPACITY_MWH} MWh | RTE {RTE:.0%} | max 1 cycle/day")
    print(f"Charge: {PERIODS_PER_CYCLE} periods × {ENERGY_PER_PERIOD_MWH} MWh = {CAPACITY_MWH} MWh in")
    print(f"Discharge: {PERIODS_PER_CYCLE} periods × {ENERGY_PER_PERIOD_MWH * RTE} MWh = {CAPACITY_MWH * RTE} MWh out\n")

    # ── Simulate each day ──────────────────────────────────────────────────────

    records = []
    for date_str, group in df.groupby("settlement_date"):
        prices = group["mid_price_gbp_mwh"]

        if len(prices) != 48:
            print(f"  Skipping {date_str}: only {len(prices)} periods (expected 48)")
            continue

        result = simulate_day(prices)
        result["date"] = date_str
        records.append(result)

    results = pd.DataFrame(records).set_index("date")
    results.index = pd.to_datetime(results.index)
    results = results.sort_index()

    # ── Print summary ──────────────────────────────────────────────────────────

    n_days    = len(results)
    n_traded  = results["traded"].sum()
    total_rev = results["discharge_revenue_gbp"].sum()
    total_cost= results["charge_cost_gbp"].sum()
    total_net = results["net_revenue_gbp"].sum()

    print("=" * 60)
    print(f"ANNUAL ARBITRAGE SUMMARY  {year}  (perfect foresight — upper bound)")
    print("=" * 60)
    print(f"  Days simulated          : {n_days}")
    print(f"  Days traded             : {n_traded}  (skipped {n_days - n_traded} loss-making days)")
    print(f"  Total charge cost       : £{total_cost:>10,.0f}")
    print(f"  Total discharge revenue : £{total_rev:>10,.0f}")
    print(f"  Net revenue             : £{total_net:>10,.0f}")
    print(f"  Net revenue / MW        : £{total_net / POWER_MW:>10,.0f} /MW/year")
    print()

    # Monthly breakdown — shows seasonality clearly
    monthly = results.resample("ME").agg(
        days_traded=("traded", "sum"),
        net_revenue_gbp=("net_revenue_gbp", "sum"),
        avg_spread=("price_spread_gbp_mwh", "mean"),
    )
    monthly["net_per_mw"] = (monthly["net_revenue_gbp"] / POWER_MW).round(0)
    monthly.index = monthly.index.strftime("%b %Y")
    print("Monthly breakdown:")
    print(monthly[["days_traded", "net_revenue_gbp", "net_per_mw", "avg_spread"]]
          .rename(columns={"days_traded": "days_traded",
                           "net_revenue_gbp": "net_rev_£",
                           "net_per_mw": "£/MW",
                           "avg_spread": "avg_spread_£/MWh"})
          .to_string())
    print()

    cols = ["avg_charge_price_gbp_mwh", "avg_discharge_price_gbp_mwh",
            "price_spread_gbp_mwh", "net_revenue_gbp"]
    print("Top 5 days by net revenue:")
    print(results[cols].nlargest(5, "net_revenue_gbp").to_string())
    print()
    print("Bottom 5 days:")
    print(results[cols].nsmallest(5, "net_revenue_gbp").to_string())

    # ── Save results ───────────────────────────────────────────────────────────

    results.to_csv(RESULTS_FILE)
    print(f"\nFull results saved to {RESULTS_FILE}")

    # ── Plot ───────────────────────────────────────────────────────────────────

    fig, axes = plt.subplots(2, 1, figsize=(18, 8), sharex=True)

    # Top panel: daily net revenue bars
    ax1 = axes[0]
    colours = ["#2ca02c" if v >= 0 else "#d62728" for v in results["net_revenue_gbp"]]
    ax1.bar(results.index, results["net_revenue_gbp"], color=colours, width=0.7)
    ax1.axhline(0, color="black", linewidth=0.8)
    ax1.set_ylabel("Net revenue (£/day)")
    ax1.set_title(
        f"GB BESS arbitrage — {year}  |  {POWER_MW} MW / {CAPACITY_MWH} MWh  |  "
        f"Perfect foresight (upper bound)"
    )
    ax1.text(0.01, 0.97, f"Annual total: £{total_net:,.0f}  |  £{total_net/POWER_MW:,.0f}/MW",
             transform=ax1.transAxes, va="top", fontsize=9,
             bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))

    # Add vertical lines at month boundaries so seasonality is easy to read
    for month_start in pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS"):
        ax1.axvline(month_start, color="grey", linewidth=0.5, linestyle="--", alpha=0.6)

    # Bottom panel: avg charge vs discharge price each day
    ax2 = axes[1]
    ax2.plot(results.index, results["avg_charge_price_gbp_mwh"],
             marker="o", markersize=2, label="Avg charge price", color="#1f77b4")
    ax2.plot(results.index, results["avg_discharge_price_gbp_mwh"],
             marker="o", markersize=2, label="Avg discharge price", color="#ff7f0e")
    ax2.fill_between(results.index,
                     results["avg_charge_price_gbp_mwh"],
                     results["avg_discharge_price_gbp_mwh"],
                     alpha=0.15, color="grey", label="Exploited spread")
    ax2.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax2.set_ylabel("Price (£/MWh)")
    ax2.set_xlabel("Date")
    ax2.legend(fontsize=8)
    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%b"))

    for month_start in pd.date_range(f"{year}-01-01", f"{year}-12-01", freq="MS"):
        ax2.axvline(month_start, color="grey", linewidth=0.5, linestyle="--", alpha=0.6)

    plt.tight_layout()
    plot_path = os.path.join("data", "daily_pnl_plot.png")
    plt.savefig(plot_path, dpi=150)
    plt.close()
    print(f"Chart saved to {plot_path}")


if __name__ == "__main__":
    main()
