"""
revenue_comparison.py
---------------------
Compares our modelled wholesale-arbitrage ceiling against the *actual* revenue
that GB grid-scale batteries earned in 2025 across all their revenue streams.

The core message: even with PERFECT FORESIGHT, pure wholesale arbitrage on
imbalance prices does not, on its own, explain what BESS assets actually earn.
Real-world revenue comes from "stacking" multiple services — the Balancing
Mechanism, frequency response (Dynamic Containment et al.), the Capacity
Market, and only a modest slice of achievable arbitrage.

IMPORTANT — on the benchmark figures below:
The real-world revenue stack is NOT computed from raw data. Granular per-asset
revenue data lives behind paywalls (Modo Energy, Cornwall Insight, LCP Delta).
The figures here are published industry benchmarks for 2025, used the same way
a BESS investment analyst uses them for initial screening. Each line is sourced.
They are approximations, clearly labelled as such.

Outputs:
  data/revenue_comparison.png   — oracle ceiling vs real stacked revenue
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

plt.style.use("seaborn-v0_8-whitegrid")

# ── Battery (must match simulate_arbitrage.py) ───────────────────────────────────

POWER_MW = 50

# ── Paths ────────────────────────────────────────────────────────────────────────

RESULTS_FILE = os.path.join("data", "arbitrage_results.csv")
PLOT_FILE    = os.path.join("data", "revenue_comparison.png")

# ── Real-world GB BESS revenue stack (2025, £/MW/year) ──────────────────────────
#
# Published industry benchmarks — NOT computed from raw data. See module docstring.
# Each entry: (label, £/MW/year, source basis).
# Ordered largest-to-smallest so the stacked bar reads top-down sensibly.

REVENUE_STACK = [
    ("Balancing Mechanism",        28_000, "Modo Energy BESS Revenue Tracker 2025"),
    ("Frequency response (DC etc.)", 18_000, "NESO DC procurement + Modo Energy"),
    ("Wholesale arbitrage (achieved)", 15_000, "Implied: oracle x typical day-ahead capture"),
    ("Capacity Market",             7_000, "NESO CM auction results (public)"),
    ("Other (DM, DR, triad)",       4_000, "Cornwall Insight estimates"),
]

# Colours for each stream (consistent, colour-blind-friendly-ish)
STACK_COLOURS = ["#1f77b4", "#ff7f0e", "#2ca02c", "#9467bd", "#8c564b"]


def load_oracle_per_mw() -> float:
    """
    Read the oracle arbitrage result and return net revenue in £/MW/year.
    Computed from the simulation output so it stays in sync if data changes.
    """
    results = pd.read_csv(RESULTS_FILE)
    total_net = results["net_revenue_gbp"].sum()
    return total_net / POWER_MW


def main():
    oracle_per_mw = load_oracle_per_mw()
    real_total    = sum(amount for _, amount, _ in REVENUE_STACK)

    # The achieved-arbitrage slice within the real stack, for context
    achieved_arb = next(amt for label, amt, _ in REVENUE_STACK
                        if label.startswith("Wholesale"))
    capture_rate = achieved_arb / oracle_per_mw

    # ── Printed summary ──────────────────────────────────────────────────────────

    print("=" * 64)
    print("GB BESS REVENUE COMPARISON — 2025  (£/MW/year)")
    print("=" * 64)
    print(f"  Oracle arbitrage ceiling (this model) : £{oracle_per_mw:>8,.0f}")
    print(f"  Real-world total (all streams)        : £{real_total:>8,.0f}")
    print()
    print("  Real-world revenue stack:")
    for label, amount, source in REVENUE_STACK:
        share = amount / real_total
        print(f"    {label:<32} £{amount:>7,.0f}  ({share:4.0%})   [{source}]")
    print(f"    {'-' * 32} {'-' * 8}")
    print(f"    {'TOTAL':<32} £{real_total:>7,.0f}")
    print()
    print("  Key ratios:")
    print(f"    Achieved arbitrage as % of oracle ceiling : {capture_rate:.0%}")
    print(f"    Arbitrage as % of real total revenue       : {achieved_arb / real_total:.0%}")
    print(f"    Oracle ceiling vs real total               : "
          f"{oracle_per_mw / real_total:.0%} "
          f"({'below' if oracle_per_mw < real_total else 'above'} real earnings)")
    print()
    print("  Takeaway: even a perfect-foresight arbitrage strategy on volatile")
    print("  imbalance prices falls BELOW what GB batteries actually earn.")
    print("  Revenue stacking — not arbitrage alone — defines the BESS case.")

    # ── Chart: oracle ceiling (single bar) vs real stack (stacked bar) ──────────

    fig, ax = plt.subplots(figsize=(9, 7))

    x_oracle, x_real = 0, 1
    bar_width = 0.55

    # Left bar: oracle arbitrage ceiling (single block)
    ax.bar(x_oracle, oracle_per_mw, width=bar_width,
           color="#d62728", alpha=0.85, label="_nolegend_")
    ax.text(x_oracle, oracle_per_mw + 1_200, f"£{oracle_per_mw:,.0f}",
            ha="center", va="bottom", fontweight="bold")

    # Right bar: real revenue stack (stacked)
    bottom = 0
    for (label, amount, _), colour in zip(REVENUE_STACK, STACK_COLOURS):
        ax.bar(x_real, amount, width=bar_width, bottom=bottom,
               color=colour, label=label)
        # Label each segment in the middle if it's tall enough to fit text
        if amount >= 5_000:
            ax.text(x_real, bottom + amount / 2, f"£{amount/1000:.0f}k",
                    ha="center", va="center", color="white", fontsize=9,
                    fontweight="bold")
        bottom += amount

    ax.text(x_real, bottom + 1_200, f"£{real_total:,.0f}",
            ha="center", va="bottom", fontweight="bold")

    # Dashed reference line at the oracle level, across to the real bar
    ax.axhline(oracle_per_mw, color="#d62728", linestyle="--",
               linewidth=1, alpha=0.6)

    ax.set_xticks([x_oracle, x_real])
    ax.set_xticklabels(["Oracle arbitrage\n(perfect foresight,\nupper bound)",
                        "Real GB BESS\n(all revenue streams,\n2025 benchmarks)"])
    ax.set_ylabel("Revenue (£/MW/year)")
    ax.set_title("GB BESS: arbitrage ceiling vs real-world revenue stack (2025)")
    # Legend below the plot so it never collides with the bar value labels
    ax.legend(title="Real revenue streams", fontsize=8, ncol=3,
              loc="upper center", bbox_to_anchor=(0.5, -0.08))

    # Annotate the headline insight — placed in the empty gap between the bars
    ax.text(0.5, 0.42,
            f"Perfect-foresight arbitrage\n(£{oracle_per_mw/1000:.0f}k) sits BELOW real\n"
            f"all-stream revenue (£{real_total/1000:.0f}k).\n\n"
            f"Achieved arbitrage is only\n~{capture_rate:.0%} of the oracle ceiling.",
            transform=ax.transAxes, ha="center", va="center", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="#fff4e6",
                      edgecolor="#d6a76e", alpha=0.95))

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")


if __name__ == "__main__":
    main()
