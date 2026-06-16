"""
ordering_oracle.py
------------------
How much does the greedy "pick the 4 cheapest and 4 dearest periods" model
overstate arbitrage by ignoring TIME ORDER within the day?

A real battery starts each day empty: it cannot discharge in the morning peak
and then "buy back" cheaply in the afternoon to cover it. The greedy model in
simulate_arbitrage.py ignores this — it just takes the 4 lowest and 4 highest
prices regardless of when they occur. That makes it a true upper bound.

This script computes the ORDERING-CONSTRAINED optimum for each day with a small
dynamic program: choose up to 4 charge and 4 discharge half-hours, left to
right, never discharging more than has been charged so far (state of charge
stays >= 0). Comparing the two isolates the cost of the no-foresight-on-ordering
assumption and validates how loose the greedy upper bound really is.

Outputs:
  data/ordering_oracle.png
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

plt.style.use("seaborn-v0_8-whitegrid")

POWER_MW = 50
RTE = 0.85
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5     # 25 MWh per period
N = 4                                       # periods per full charge / discharge
NEG_INF = float("-inf")

PRICES_FILE = os.path.join("data", "prices_2025-all.csv")
PLOT_FILE   = os.path.join("data", "ordering_oracle.png")


def greedy_day(prices) -> float:
    """Base model: 4 cheapest charge, 4 dearest discharge, ignoring order."""
    s = sorted(prices)
    cost    = sum(s[:N]) * ENERGY_PER_PERIOD_MWH
    revenue = sum(s[-N:]) * ENERGY_PER_PERIOD_MWH * RTE
    return max(0.0, revenue - cost)


def ordered_day(prices) -> float:
    """
    Ordering-constrained optimum via DP.

    State (c, d) = charges used, discharges used after processing periods so far.
    Constraint: d <= c at all times (can't sell energy not yet stored).
    Transitions per period at price p:
      idle     : carry state forward
      charge   : c -> c+1,  objective -= p * 25        (if c < N)
      discharge: d -> d+1,  objective += p * 21.25     (if d < c and d < N)
    Answer: best objective over all end states (>= 0; doing nothing earns 0).
    """
    charge_cost = ENERGY_PER_PERIOD_MWH                 # 25 MWh bought per period
    sell_energy = ENERGY_PER_PERIOD_MWH * RTE           # 21.25 MWh sold per period

    # dp[c][d] = best objective so far; start empty
    dp = [[NEG_INF] * (N + 1) for _ in range(N + 1)]
    dp[0][0] = 0.0

    for p in prices:
        nxt = [row[:] for row in dp]                    # idle baseline
        for c in range(N + 1):
            for d in range(c + 1):                      # d <= c invariant
                base = dp[c][d]
                if base == NEG_INF:
                    continue
                if c < N:                               # charge here
                    val = base - p * charge_cost
                    if val > nxt[c + 1][d]:
                        nxt[c + 1][d] = val
                if d < c and d < N:                     # discharge here
                    val = base + p * sell_energy
                    if val > nxt[c][d + 1]:
                        nxt[c][d + 1] = val
        dp = nxt

    best = max(v for row in dp for v in row if v != NEG_INF)
    return max(0.0, best)


def main():
    df = pd.read_csv(PRICES_FILE)
    days = [g["mid_price_gbp_mwh"].tolist()
            for _, g in df.groupby("settlement_date") if len(g) == 48]
    print(f"Loaded {len(days)} full days from {PRICES_FILE}\n")

    greedy_total  = sum(greedy_day(p)  for p in days)
    ordered_total = sum(ordered_day(p) for p in days)

    greedy_mw  = greedy_total  / POWER_MW
    ordered_mw = ordered_total / POWER_MW
    gap = 1 - ordered_mw / greedy_mw

    # How many days does ordering actually bind?
    n_diff = sum(1 for p in days if greedy_day(p) - ordered_day(p) > 1.0)

    print("=" * 62)
    print("GREEDY UPPER BOUND vs ORDERING-CONSTRAINED OPTIMUM — 2025")
    print("=" * 62)
    print(f"  Greedy (base, ignores order)   : £{greedy_mw:>9,.0f} /MW/yr")
    print(f"  Ordering-constrained optimum   : £{ordered_mw:>9,.0f} /MW/yr")
    print(f"  Overstatement by greedy        : {gap:.1%}")
    print(f"  Days where ordering binds      : {n_diff} of {len(days)}")
    print()
    print("  Takeaway: the greedy figure is a genuine but loose upper bound.")
    print("  On most days the cheapest periods already precede the dearest")
    print("  (overnight trough -> evening peak), so ordering rarely binds and")
    print(f"  the headline £{greedy_mw:,.0f}/MW is only modestly optimistic on this axis.")

    # ── Chart ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(7, 5))
    labels = ["Greedy\n(upper bound)", "Ordering-\nconstrained"]
    bars = ax.bar(labels, [greedy_mw, ordered_mw],
                  color=["#c2453b", "#3a9d5d"], width=0.55)
    ax.bar_label(bars, labels=[f"£{greedy_mw:,.0f}", f"£{ordered_mw:,.0f}"],
                 padding=3, fontsize=10)
    ax.set_ylabel("£/MW/year")
    ax.set_title(f"Greedy upper bound vs ordering-constrained optimum\n"
                 f"(2025, 50 MW / 2h — greedy overstates by {gap:.1%})")
    ax.margins(y=0.15)
    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")


if __name__ == "__main__":
    main()
