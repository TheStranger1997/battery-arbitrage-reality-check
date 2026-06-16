"""
cycles_sweep.py
---------------
Sensitivity analysis: how much extra arbitrage revenue is available if the
battery is allowed MORE than one cycle per day?

The base model caps dispatch at 1 cycle/day. On volatile days there is often a
second, smaller buy-low/sell-high opportunity the base model leaves on the
table. This script relaxes the cap to 1 and 2 cycles/day and reports the gain.

Important caveat (printed in the output): extra cycles are NOT free. Each cycle
adds wear; warranties are typically written around a fixed number of equivalent
full cycles per year, so a 2-cycle strategy trades battery life for revenue.
The base case stays at 1 cycle/day for exactly this reason.

Outputs:
  data/cycles_sweep.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

plt.style.use("seaborn-v0_8-whitegrid")

POWER_MW = 50
RTE = 0.85
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5          # 25 MWh per half-hour
PERIODS_PER_CYCLE = 4                            # 2-hour battery: 4 periods to fill/empty

MAX_CYCLES = [1, 2]                              # scenarios to compare

PRICES_FILE = os.path.join("data", "prices_2025-all.csv")
PLOT_FILE   = os.path.join("data", "cycles_sweep.png")


def day_revenue(prices: pd.Series, max_cycles: int) -> float:
    """
    Greedy perfect-foresight revenue for up to `max_cycles` cycles in one day.

    Cycle c uses the c-th cheapest block of 4 periods to charge and the c-th
    dearest block of 4 periods to discharge. Each cycle is only added if its
    own marginal net revenue is positive, so a flat day still does 0-1 cycles.
    """
    s = prices.sort_values().to_numpy()
    energy_sold = ENERGY_PER_PERIOD_MWH * RTE       # 21.25 MWh sold per period

    total = 0.0
    for c in range(max_cycles):
        lo = c * PERIODS_PER_CYCLE
        hi = lo + PERIODS_PER_CYCLE
        charge_block    = s[lo:hi]                   # c-th cheapest 4 periods
        discharge_block = s[len(s) - hi: len(s) - lo]  # c-th dearest 4 periods

        cost    = charge_block.sum() * ENERGY_PER_PERIOD_MWH
        revenue = discharge_block.sum() * energy_sold
        marginal = revenue - cost

        if marginal > 0:        # only run this cycle if it pays
            total += marginal
        else:
            break               # later cycles have smaller spreads, so stop
    return total


def main():
    df = pd.read_csv(PRICES_FILE)
    days = [g["mid_price_gbp_mwh"].reset_index(drop=True)
            for _, g in df.groupby("settlement_date") if len(g) == 48]
    print(f"Loaded {len(days)} full days from {PRICES_FILE}\n")

    rows = []
    for k in MAX_CYCLES:
        total = sum(day_revenue(p, k) for p in days)
        rows.append({"max_cycles": k, "total": total, "per_mw": total / POWER_MW})

    results = pd.DataFrame(rows)
    base = results.loc[results["max_cycles"] == 1, "per_mw"].iloc[0]

    print("=" * 60)
    print("ARBITRAGE BY CYCLE CAP — 2025  (50 MW / 2h, perfect foresight)")
    print("=" * 60)
    for _, r in results.iterrows():
        uplift = r["per_mw"] / base - 1
        print(f"  {int(r['max_cycles'])} cycle/day max : "
              f"£{r['per_mw']:>9,.0f} /MW/yr   ({uplift:+.0%} vs 1 cycle)")
    print()
    print("  The 2nd cycle exploits a shallower, second-best daily spread, so it")
    print("  adds less than the first. And it doubles wear: at ~£/MWh warranty")
    print("  cost per cycle, much of the uplift can be eaten by degradation.")
    print("  Base case stays at 1 cycle/day.")

    # ── Chart ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 5))
    labels = [f"{int(k)} cycle/day" for k in results["max_cycles"]]
    colours = ["#3a9d5d", "#08519c"]
    bars = ax.bar(labels, results["per_mw"], color=colours, width=0.55)
    ax.bar_label(bars, labels=[f"£{v:,.0f}" for v in results["per_mw"]],
                 padding=3, fontsize=10)
    ax.set_ylabel("£/MW/year")
    ax.set_title("Arbitrage revenue vs daily cycle cap\n(2025, 50 MW / 2h, perfect foresight)")
    ax.margins(y=0.15)
    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")


if __name__ == "__main__":
    main()
