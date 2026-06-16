"""
duration_sweep.py
-----------------
Sensitivity analysis: how does the perfect-foresight arbitrage ceiling change
with battery DURATION, holding power fixed at 50 MW?

GB is debating whether to build 1-hour, 2-hour or 4-hour batteries. Longer
duration costs more per MW but can capture more of a price spike. The 8 Jan 2025
scarcity event is the perfect illustration: prices sat at £2,900/MWh for EIGHT
consecutive half-hours, but a 2-hour battery can only discharge into four of
them. A 4-hour battery captures all eight.

This script reruns the same greedy oracle model for 1h / 2h / 4h and reports
revenue per MW and per MWh of capacity, so the diminishing-return trade-off
is visible.

Outputs:
  data/duration_sweep.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

plt.style.use("seaborn-v0_8-whitegrid")

# ── Fixed parameters ─────────────────────────────────────────────────────────

POWER_MW = 50                 # power rating held constant across the sweep
RTE = 0.85                    # round-trip efficiency
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5   # 25 MWh moved per half-hour at full power

DURATIONS_H = [1, 2, 4]       # the three cases to compare

PRICES_FILE = os.path.join("data", "prices_2025-all.csv")
PLOT_FILE   = os.path.join("data", "duration_sweep.png")


def simulate_year(prices_by_day: list[pd.Series], periods_per_cycle: int) -> float:
    """
    Total annual net revenue (£) for a given number of charge/discharge periods.
    Same greedy oracle logic as simulate_arbitrage.py: charge in the cheapest
    N periods, discharge in the dearest N, skip loss-making days.
    """
    energy_sold_per_period = ENERGY_PER_PERIOD_MWH * RTE   # RTE applied at discharge
    total_net = 0.0

    for prices in prices_by_day:
        s = prices.sort_values()
        charge    = s.iloc[:periods_per_cycle]
        discharge = s.iloc[-periods_per_cycle:]

        charge_cost       = (charge * ENERGY_PER_PERIOD_MWH).sum()
        discharge_revenue = (discharge * energy_sold_per_period).sum()
        net = discharge_revenue - charge_cost

        if net > 0:           # a rational operator only trades profitable days
            total_net += net

    return total_net


def main():
    df = pd.read_csv(PRICES_FILE)

    # Group into clean 48-period days (skip the two clock-change days)
    prices_by_day = []
    for _, group in df.groupby("settlement_date"):
        if len(group) == 48:
            prices_by_day.append(group["mid_price_gbp_mwh"].reset_index(drop=True))
    print(f"Loaded {len(prices_by_day)} full days from {PRICES_FILE}\n")

    rows = []
    for duration in DURATIONS_H:
        capacity_mwh      = POWER_MW * duration
        periods_per_cycle = int(capacity_mwh / ENERGY_PER_PERIOD_MWH)   # 2 / 4 / 8

        total_net  = simulate_year(prices_by_day, periods_per_cycle)
        per_mw     = total_net / POWER_MW
        per_mwh    = total_net / capacity_mwh   # revenue per MWh of capacity

        rows.append({
            "duration_h":  duration,
            "capacity_mwh": capacity_mwh,
            "periods":     periods_per_cycle,
            "total_net":   total_net,
            "per_mw":      per_mw,
            "per_mwh":     per_mwh,
        })

    results = pd.DataFrame(rows)

    # ── Print table ──────────────────────────────────────────────────────────

    base = results.loc[results["duration_h"] == 2, "per_mw"].iloc[0]
    print("=" * 68)
    print("ARBITRAGE BY BATTERY DURATION — 2025  (50 MW, perfect foresight)")
    print("=" * 68)
    print(f"  {'Duration':<10}{'Capacity':<12}{'£/MW/yr':<14}{'£/MWh-cap/yr':<16}{'vs 2h':<8}")
    for _, r in results.iterrows():
        rel = r["per_mw"] / base - 1
        print(f"  {int(r['duration_h'])}h{'':<8}"
              f"{int(r['capacity_mwh'])} MWh{'':<5}"
              f"£{r['per_mw']:>10,.0f}  "
              f"£{r['per_mwh']:>10,.0f}     "
              f"{rel:+.0%}")
    print()
    print("  Reading: per-MW revenue rises with duration (more spike captured),")
    print("  but per-MWh-of-capacity revenue FALLS — the marginal MWh is used on")
    print("  shallower, less profitable parts of the price curve. This is the")
    print("  core 2h-vs-4h trade-off in GB BESS investment.")

    # ── Chart: dual view (per MW and per MWh of capacity) ────────────────────

    fig, (axL, axR) = plt.subplots(1, 2, figsize=(13, 5))
    labels = [f"{int(d)}h" for d in results["duration_h"]]
    colours = ["#9ecae1", "#3a9d5d", "#08519c"]

    bars1 = axL.bar(labels, results["per_mw"], color=colours, width=0.6)
    axL.set_title("Revenue per MW of power")
    axL.set_ylabel("£/MW/year")
    axL.bar_label(bars1, labels=[f"£{v:,.0f}" for v in results["per_mw"]],
                  padding=3, fontsize=9)
    axL.margins(y=0.12)   # headroom so labels don't clip

    bars2 = axR.bar(labels, results["per_mwh"], color=colours, width=0.6)
    axR.set_title("Revenue per MWh of capacity")
    axR.set_ylabel("£/MWh-capacity/year")
    axR.bar_label(bars2, labels=[f"£{v:,.0f}" for v in results["per_mwh"]],
                  padding=3, fontsize=9)
    axR.margins(y=0.12)

    fig.suptitle("BESS arbitrage by duration — 2025 (50 MW, perfect-foresight ceiling)",
                 fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")


if __name__ == "__main__":
    main()
