"""
forecast_arbitrage.py
---------------------
The oracle (simulate_arbitrage.py) assumes PERFECT FORESIGHT — it knows all 48
of today's prices before choosing when to charge and discharge. That is an
upper bound, not a tradeable strategy.

This script computes an ACHIEVABLE figure with NO foresight. Each morning the
battery must commit its charge/discharge windows using only PAST prices, then
it is settled at today's ACTUAL prices. The gap between this and the oracle is
the value of foresight; the ratio (achievable / oracle) is the CAPTURE RATE.

Forecast rule
  GB prices have a strong, repeating time-of-day shape: cheap overnight, dear
  at the evening peak. So we forecast today's price *shape* from recent history
  and pick the windows the forecast says are cheapest/dearest:

    - persistence  : today looks like YESTERDAY (the classic naive forecast)
    - trailing-7d  : today looks like the average of the last 7 days (smoother)

  We pick the 4 lowest-forecast periods to charge and the 4 highest-forecast
  periods to discharge, and we only trade if the FORECAST says the day is
  profitable. We are then paid today's real prices at those committed periods —
  including the days the forecast got wrong.

Consistency with the oracle
  Same price series (imbalance), same battery (50 MW / 2h, 85% RTE, 1 cycle/day),
  and — like the oracle — no intraday state-of-charge ordering constraint (the
  ordering_oracle.py analysis showed that is only a ~4% effect). So the capture
  rate isolates ONE thing: foresight. (A real desk would also trade day-ahead /
  MID rather than ex-post imbalance prices — that is a separate, additive
  caveat handled in market_index_compare.py.)

Outputs
  data/forecast_results.csv       — daily realised P&L for the headline model
  data/forecast_arbitrage.png     — oracle vs achievable, with capture rate
"""

import pandas as pd
import matplotlib.pyplot as plt
import os

plt.style.use("seaborn-v0_8-whitegrid")

# ── Battery parameters (match simulate_arbitrage.py) ───────────────────────────
POWER_MW              = 50
RTE                   = 0.85
ENERGY_PER_PERIOD_MWH = POWER_MW * 0.5    # 25 MWh per half-hour at full power
ENERGY_SOLD_PER_PERIOD = ENERGY_PER_PERIOD_MWH * RTE   # 21.25 MWh delivered
N                     = 4                 # periods per charge / discharge (2h)

LOOKBACK_7D = 7   # days in the trailing-average forecast

# ── Paths ──────────────────────────────────────────────────────────────────────
PRICES_FILE        = os.path.join("data", "prices_2025-all.csv")
ORACLE_FILE        = os.path.join("data", "arbitrage_results.csv")
RESULTS_FILE       = os.path.join("data", "forecast_results.csv")
PLOT_FILE          = os.path.join("data", "forecast_arbitrage.png")
SWEEP_FILE         = os.path.join("data", "lookback_sweep.csv")
SWEEP_PLOT_DATA    = os.path.join("data", "lookback_sweep.png")
SWEEP_PLOT_ASSETS  = os.path.join("assets", "lookback_sweep.png")


def realised_net(actual: list[float], charge_idx, discharge_idx) -> float:
    """
    P&L of committing to fixed charge/discharge periods and being paid today's
    ACTUAL prices at them. No max(0,·) clamp: once committed, you take the day
    you get — that is the whole point of trading without foresight.
    """
    charge_cost      = sum(actual[i] for i in charge_idx) * ENERGY_PER_PERIOD_MWH
    discharge_revenue = sum(actual[i] for i in discharge_idx) * ENERGY_SOLD_PER_PERIOD
    return discharge_revenue - charge_cost


def windows_from_forecast(forecast: list[float]):
    """Periods the forecast says are the 4 cheapest (charge) and 4 dearest
    (discharge). Returns (charge_idx, discharge_idx, forecast_net)."""
    order = sorted(range(len(forecast)), key=lambda i: forecast[i])
    charge_idx    = order[:N]
    discharge_idx = order[-N:]
    forecast_net = (sum(forecast[i] for i in discharge_idx) * ENERGY_SOLD_PER_PERIOD
                    - sum(forecast[i] for i in charge_idx) * ENERGY_PER_PERIOD_MWH)
    return charge_idx, discharge_idx, forecast_net


def run_forecast_model(days: list[tuple[str, list[float]]], lookback: int):
    """
    days: ordered list of (date_str, 48 actual prices).
    For each day we forecast the price shape from the previous `lookback` days
    (period-by-period mean), choose windows, decide to trade if the forecast is
    profitable, and realise at today's actual prices.

    Returns a per-day DataFrame.
    """
    records = []
    for t in range(len(days)):
        date_str, actual = days[t]
        if t < lookback:
            continue   # not enough history yet to form a forecast

        # Forecast shape = mean price per settlement period over the window
        hist = [days[t - k][1] for k in range(1, lookback + 1)]
        forecast = [sum(h[p] for h in hist) / lookback for p in range(48)]

        charge_idx, discharge_idx, forecast_net = windows_from_forecast(forecast)

        if forecast_net <= 0:
            # Forecast says unprofitable → stay idle (no trade, no P&L)
            records.append({"date": date_str, "traded": False,
                            "realised_net_gbp": 0.0, "forecast_net_gbp": forecast_net})
            continue

        net = realised_net(actual, charge_idx, discharge_idx)
        records.append({"date": date_str, "traded": True,
                        "realised_net_gbp": round(net, 2),
                        "forecast_net_gbp": round(forecast_net, 2)})

    df = pd.DataFrame(records)
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


def run_sweep(days: list, oracle_per_mw: float,
              lookbacks: tuple = (1, 3, 7, 14, 30)) -> pd.DataFrame:
    """
    Run the forecast model at several lookback windows and return a summary.
    Used to justify the 7-day headline choice rather than hard-coding it.
    """
    rows = []
    for lb in lookbacks:
        df      = run_forecast_model(days, lookback=lb)
        per_mw  = df["realised_net_gbp"].sum() / POWER_MW
        capture = per_mw / oracle_per_mw
        n_loss  = int((df["realised_net_gbp"] < 0).sum())
        rows.append({
            "lookback_days": lb,
            "per_mw_gbp":   round(per_mw),
            "capture_pct":  round(capture * 100, 1),
            "loss_days":    n_loss,
        })
    return pd.DataFrame(rows)


def main():
    df = pd.read_csv(PRICES_FILE)

    # Ordered list of (date, 48 prices); drop clock-change days (≠48 periods),
    # exactly as the oracle does, so the two are comparable.
    days = []
    for date_str, g in df.groupby("settlement_date"):
        prices = g.sort_values("settlement_period")["mid_price_gbp_mwh"].tolist()
        if len(prices) != 48:
            continue
        days.append((date_str, prices))
    days.sort(key=lambda x: x[0])

    # Oracle total over the same year, for the capture rate
    oracle = pd.read_csv(ORACLE_FILE)
    oracle_total = oracle["net_revenue_gbp"].sum()
    oracle_per_mw = oracle_total / POWER_MW

    # Headline achievable model: trailing 7-day shape (a simple but realistic
    # operational forecast). Persistence (today ≈ yesterday) is reported as a
    # conservative floor — no desk trades off literally only yesterday.
    persistence = run_forecast_model(days, lookback=1)
    trailing    = run_forecast_model(days, lookback=LOOKBACK_7D)

    trailing.to_csv(RESULTS_FILE)

    def summarise(name, res):
        total   = res["realised_net_gbp"].sum()
        per_mw  = total / POWER_MW
        n_days  = len(res)
        n_trade = int(res["traded"].sum())
        n_loss  = int((res["realised_net_gbp"] < 0).sum())
        capture = per_mw / oracle_per_mw
        return dict(name=name, per_mw=per_mw, n_days=n_days, n_trade=n_trade,
                    n_loss=n_loss, capture=capture)

    s_persist = summarise("Persistence (yesterday)", persistence)
    s_trail   = summarise(f"Trailing {LOOKBACK_7D}-day average", trailing)

    head = s_trail   # the figure that replaces the implied £15k

    print("=" * 70)
    print("ACHIEVABLE ARBITRAGE — NO PERFECT FORESIGHT (2025, 50 MW / 2h)")
    print("=" * 70)
    print(f"  Oracle ceiling (perfect foresight)   : £{oracle_per_mw:>8,.0f} /MW/yr")
    print()
    print(f"  {'Forecast rule':<28}{'£/MW/yr':>10}{'capture':>10}{'days traded':>14}{'loss days':>11}")
    for s in (s_persist, s_trail):
        print(f"  {s['name']:<28}£{s['per_mw']:>8,.0f}{s['capture']:>9.0%}"
              f"{s['n_trade']:>10}/{s['n_days']:<3}{s['n_loss']:>10}")
    print()
    print(f"  HEADLINE achievable (7-day forecast) : £{head['per_mw']:>8,.0f} /MW/yr")
    print(f"  Capture rate vs oracle               :  {head['capture']:>7.0%}")
    print(f"  Conservative floor (persistence)     : £{s_persist['per_mw']:>8,.0f} /MW/yr "
          f"({s_persist['capture']:.0%})")
    print()
    print("  Why so far below the oracle: imbalance prices are spiky and the")
    print("  spikes do NOT repeat day-to-day (the 8 Jan scarcity event can't be")
    print("  forecast from 7 Jan), so a shape-based forecast captures the routine")
    print("  overnight-to-peak spread but misses the scarcity tail that makes up")
    print("  much of the oracle total. This is the realistic, computed answer —")
    print("  it replaces the previously implied ~£15k 'achieved arbitrage'.")

    # ── Lookback sensitivity sweep ───────────────────────────────────────────────
    print("\nRunning lookback sensitivity sweep (1, 3, 7, 14, 30 days)...")
    sweep = run_sweep(days, oracle_per_mw)
    sweep.to_csv(SWEEP_FILE, index=False)

    print(f"\n  {'Lookback (days)':>16}{'£/MW/yr':>12}{'Capture':>10}{'Loss days':>11}")
    for _, row in sweep.iterrows():
        marker = "  ← headline" if int(row["lookback_days"]) == LOOKBACK_7D else ""
        print(f"  {int(row['lookback_days']):>16}  £{int(row['per_mw_gbp']):>8,}"
              f"  {row['capture_pct']:>7.1f}%  {int(row['loss_days']):>9}{marker}")

    fig2, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()
    lb_labels = [str(int(lb)) for lb in sweep["lookback_days"]]
    bars = ax1.bar(lb_labels, sweep["per_mw_gbp"], color="#2f6f9f", width=0.5, alpha=0.85)
    ax1.bar_label(bars, labels=[f"£{int(v):,.0f}" for v in sweep["per_mw_gbp"]],
                  padding=3, fontsize=9)
    ax2.plot(lb_labels, sweep["capture_pct"], color="#e08a1e", marker="o",
             linewidth=2, markersize=7, label="Capture rate (%)")
    ax1.set_xlabel("Forecast lookback (days)")
    ax1.set_ylabel("Achievable arbitrage (£/MW/yr)", color="#2f6f9f")
    ax2.set_ylabel("Capture rate (% of oracle ceiling)", color="#e08a1e")
    ax2.set_ylim(0, max(sweep["capture_pct"]) * 1.5)
    ax1.set_title("Forecast lookback sensitivity — how many days of history?\n"
                  "(2025, 50 MW / 2h, imbalance prices)")
    ax2.legend(loc="lower right")
    plt.tight_layout()
    for dest in (SWEEP_PLOT_DATA, SWEEP_PLOT_ASSETS):
        plt.savefig(dest, dpi=150)
    plt.close()
    print(f"\nSweep chart saved to {SWEEP_PLOT_ASSETS}")
    print(f"Sweep data saved to {SWEEP_FILE}")

    # ── Chart: oracle ceiling vs achievable, with capture rate ──────────────────
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    labels = ["Oracle\n(perfect foresight)",
              "Achievable\n(7-day forecast)"]
    vals   = [oracle_per_mw, head["per_mw"]]
    bars = ax.bar(labels, vals, color=["#c2453b", "#2f6f9f"], width=0.55)
    ax.bar_label(bars, labels=[f"£{v:,.0f}" for v in vals], padding=3,
                 fontsize=11, fontweight="bold")
    ax.set_ylabel("£/MW/year")
    ax.set_title("Arbitrage: perfect-foresight ceiling vs achievable\n"
                 f"(2025, 50 MW / 2h, imbalance prices — capture rate "
                 f"{head['capture']:.0%})")
    ax.margins(y=0.15)

    # Capture-rate annotation in the gap
    ax.text(0.5, 0.55,
            f"No-foresight forecast captures\nonly {head['capture']:.0%} of the "
            f"perfect-foresight\nceiling. The rest is the scarcity\ntail you "
            f"cannot predict.",
            transform=ax.transAxes, ha="center", va="center", fontsize=9,
            bbox=dict(boxstyle="round", facecolor="#fff4e6",
                      edgecolor="#d6a76e", alpha=0.95))

    plt.tight_layout()
    plt.savefig(PLOT_FILE, dpi=150)
    plt.close()
    print(f"\nChart saved to {PLOT_FILE}")
    print(f"Daily results saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
