"""
test_arbitrage.py
-----------------
Lightweight sanity tests for the core arbitrage logic. No external test runner
required and no downloaded data needed — every test builds its own synthetic
price series, so this runs in CI on a clean checkout.

    python test_arbitrage.py        # exits 0 if all pass, 1 otherwise
"""

import sys
import pandas as pd

import simulate_arbitrage as sim
import ordering_oracle as oo
import cycles_sweep as cyc
import fetch_prices as fp

EPS = 0.01
_failures = []


def check(name: str, condition: bool, detail: str = ""):
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        _failures.append(name)


def series(values) -> pd.Series:
    """Helper: build a 48-period price Series from a list of 48 numbers."""
    assert len(values) == 48, "need exactly 48 periods"
    return pd.Series(values, dtype=float)


def main():
    print("Running arbitrage sanity tests...\n")

    # Monotonically increasing prices: cheapest periods come first, dearest last.
    rising = series(list(range(1, 49)))            # 1..48
    falling = series(list(range(48, 0, -1)))       # 48..1
    flat = series([50.0] * 48)

    # 1) simulate_day matches the standalone greedy calc on the same day
    sim_net = sim.simulate_day(rising)["net_revenue_gbp"]
    greedy = oo.greedy_day(rising.tolist())
    check("simulate_day == greedy_day on rising prices",
          abs(sim_net - greedy) < EPS, f"{sim_net} vs {greedy}")

    # 2) RTE is applied: discharge energy is 85% of charge energy
    #    Greedy net = sell*0.85*25 - buy*25 ; reconstruct and compare
    s = sorted(rising.tolist())
    expected = sum(s[-4:]) * 25 * 0.85 - sum(s[:4]) * 25
    check("greedy net uses 85% round-trip efficiency",
          abs(greedy - expected) < EPS, f"{greedy} vs {expected}")

    # 3) Ordering doesn't bind when cheap precedes dear -> ordered == greedy
    check("ordered == greedy when trough precedes peak (rising)",
          abs(oo.ordered_day(rising.tolist()) - oo.greedy_day(rising.tolist())) < EPS)

    # 4) Ordering binds when dear precedes cheap -> ordered < greedy
    check("ordered < greedy when peak precedes trough (falling)",
          oo.ordered_day(falling.tolist()) < oo.greedy_day(falling.tolist()) - EPS)

    # 5) Ordered optimum is never above the greedy upper bound
    import random
    random.seed(0)
    rand = series([random.uniform(-50, 300) for _ in range(48)])
    check("ordered <= greedy on a random day",
          oo.ordered_day(rand.tolist()) <= oo.greedy_day(rand.tolist()) + EPS)

    # 6) A perfectly flat day is never loss-making: net == 0, not traded
    flat_res = sim.simulate_day(flat)
    check("flat day -> net 0 and not traded",
          flat_res["net_revenue_gbp"] == 0.0 and flat_res["traded"] is False)

    # 7) Allowing a 2nd cycle never reduces revenue (and helps on volatile days)
    check("2 cycles/day >= 1 cycle/day (rising)",
          cyc.day_revenue(rising, 2) >= cyc.day_revenue(rising, 1) - EPS)
    check("2 cycles/day > 1 cycle/day on a volatile day",
          cyc.day_revenue(rand, 2) > cyc.day_revenue(rand, 1))

    # 8) Settlement-period -> UTC mapping (the easy-to-get-wrong bit)
    p1 = fp.period_to_datetime("2025-05-01", 1)    # 23:00 the PREVIOUS day
    p3 = fp.period_to_datetime("2025-05-01", 3)    # 00:00 the settlement day
    check("period 1 maps to 23:00 UTC previous day",
          str(p1) == "2025-04-30 23:00:00+00:00", str(p1))
    check("period 3 maps to 00:00 UTC settlement day",
          str(p3) == "2025-05-01 00:00:00+00:00", str(p3))

    print()
    if _failures:
        print(f"FAILED {len(_failures)} test(s): {', '.join(_failures)}")
        sys.exit(1)
    print("All tests passed.")
    sys.exit(0)


if __name__ == "__main__":
    main()
