# GB BESS Arbitrage Dashboard

A Python analysis of how much a grid-scale battery in Great Britain could earn from wholesale electricity price arbitrage — and how that compares with what GB batteries actually earn across all their revenue streams. The goal is to demonstrate an understanding of the GB BESS market, not just to make charts.

---

## Project summary

Battery Energy Storage Systems (BESS) in Great Britain earn revenue from several sources: wholesale price arbitrage, the Balancing Mechanism, frequency response services (FFR, DC), and the Capacity Market. This project isolates the wholesale arbitrage component, computes a theoretical upper bound using full-year 2025 half-hourly imbalance prices, and contextualises it against published real-world BESS revenue figures (~£72k/MW/year across all streams). The gap between the oracle ceiling and real-world earnings shows concretely why revenue stacking — not pure arbitrage — defines the GB BESS investment case.

---

## Data source

**Elexon Insights API** — free, public, no API key required.

- Base URL: `https://data.elexon.co.uk/bmrs/api/v1`
- Endpoint used: `/balancing/settlement/system-prices/{date}?format=json`
- Returns 48 half-hourly settlement (imbalance) prices per day.
- **Single imbalance price:** GB moved to a single cash-out price in 2015 (BSC modification P305), so the System Sell Price and System Buy Price are identical in every period. Verified across the full dataset: `sell != buy` in **0 of 17,520 rows**. This project keeps both columns for transparency but uses their common value as the price series.

> **Note on price series:** Settlement (imbalance) prices are more volatile than day-ahead or intraday market prices, because they reflect real-time scarcity. Using them for arbitrage modelling produces a higher — and less achievable — ceiling than a day-ahead price series would. See Caveats below.

---

## Battery assumptions

| Parameter | Value |
|---|---|
| Nameplate power | 50 MW |
| Usable capacity | 100 MWh |
| Duration | 2 hours |
| Round-trip efficiency | 85% (applied at discharge: energy out = energy in × 0.85) |
| Cycle limit | 1 full cycle per day (100 MWh in, 85 MWh out) |

---

## Method

**Greedy perfect-foresight ("oracle") arbitrage:**

For each day, the model sorts all 48 half-hourly prices and:
1. Charges in the 4 cheapest periods (50 MW × 0.5 h × 4 = 100 MWh drawn from the grid).
2. Discharges in the 4 most expensive periods (100 MWh × 0.85 RTE = 85 MWh delivered to the grid).
3. Skips the day if net revenue would be negative.

This is an **upper bound** — it assumes perfect knowledge of future prices. A real battery bids into markets without knowing what prices will do.

---

## Key findings (2025)

| Metric | Value |
|---|---|
| Oracle arbitrage ceiling | **£65,179 /MW/year** |
| Best month | January 2025 — £11,080/MW |
| Best single day | 8 January 2025 — £245,881 on the 50 MW battery |
| Worst month | December 2025 — £3,458/MW |
| Real GB BESS revenues (all streams) | ~£72,000 /MW/year |

**January 2025 dominance:** On 8 January, a cold spell combined with low wind drove settlement prices to £2,900/MWh in some periods. A single day contributed ~£246k — more than any other month except January itself. This illustrates a key feature of GB imbalance prices: they are mean-reverting but fat-tailed. Arbitrage revenue is not steady; it is concentrated in a handful of stress events.

**The gap is the story:** The oracle arbitrage ceiling of ~£65k/MW sits *below* what batteries actually earn (~£72k/MW). Pure arbitrage — even at the theoretical maximum — does not explain BESS revenues in GB. Frequency response, the Balancing Mechanism, and the Capacity Market are what close (and exceed) the gap.

![Daily arbitrage P&L for 2025](assets/daily_pnl_2025.png)

*Daily perfect-foresight P&L across 2025. The 8 January scarcity spike (~£246k in a single day) dwarfs every other day — arbitrage revenue is concentrated in a handful of events, not earned steadily.*

---

## Revenue comparison: arbitrage vs the real revenue stack

`revenue_comparison.py` places the oracle arbitrage ceiling next to the *actual* GB BESS revenue stack for 2025. The real-world stack below uses **published industry benchmarks** (£/MW/year) — it is **not** computed from raw data, because granular per-asset revenue sits behind paywalls (Modo Energy, Cornwall Insight, LCP Delta). These figures are used the same way a BESS investment analyst uses them for initial screening: as sourced approximations, clearly labelled.

| Revenue stream | £/MW/year | Share | Source basis |
|---|---|---|---|
| Balancing Mechanism | 28,000 | 39% | Modo Energy BESS Revenue Tracker 2025 |
| Frequency response (DC etc.) | 18,000 | 25% | NESO DC procurement + Modo Energy |
| Wholesale arbitrage (achieved) | 15,000 | 21% | Implied: oracle × typical day-ahead capture |
| Capacity Market | 7,000 | 10% | NESO CM auction results (public) |
| Other (DM, DR, triad) | 4,000 | 6% | Cornwall Insight estimates |
| **Total** | **72,000** | | |

Two numbers carry the message:
- **£65k** — the oracle arbitrage *ceiling* (perfect foresight on imbalance prices).
- **£15k** — *achieved* arbitrage within the real stack, just **~23% of that ceiling**.

No operator captures the full spread: forecasts are imperfect and the largest spikes (8 January's £2,900/MWh) are nearly impossible to position for in advance. Arbitrage is a supporting player (~21% of revenue); the Balancing Mechanism and frequency response dominate. This is why GB BESS economics are about **revenue stacking**, not arbitrage alone.

![Oracle arbitrage vs real revenue stack](assets/revenue_comparison.png)

---

## Duration sensitivity (1h / 2h / 4h)

`duration_sweep.py` reruns the oracle model at different durations, holding power fixed at 50 MW, to surface the live GB "how long should a battery be?" trade-off.

| Duration | Capacity | £/MW/year | £/MWh-of-capacity/year | vs 2h |
|---|---|---|---|---|
| 1-hour | 50 MWh | £36,010 | £36,010 | −45% |
| 2-hour | 100 MWh | £65,179 | £32,589 | (base) |
| 4-hour | 200 MWh | £111,395 | £27,849 | +71% |

**The trade-off in one table:** revenue *per MW of power* rises steeply with duration (+71% for a 4-hour battery), because longer batteries capture more of each price spike — on 8 January, prices sat at £2,900/MWh for eight consecutive half-hours, but a 2-hour battery can only discharge into four of them. Yet revenue *per MWh of capacity* falls with duration: each additional MWh is dispatched onto shallower, less profitable parts of the price curve. This is exactly why GB has seen a shift toward longer-duration (2h→4h) batteries even as the per-MWh return diminishes.

![Arbitrage by battery duration](assets/duration_sweep.png)

---

## Caveats

- **Perfect foresight overstates achievable arbitrage.** A real battery cannot know future prices. Day-ahead price forecasting typically captures 60–80% of the oracle spread.
- **Imbalance prices are more volatile than traded prices.** Using day-ahead or intraday market prices would produce a lower, cleaner arbitrage estimate. The £65k figure should be read as an imbalance-price upper bound, not a day-ahead arbitrage estimate.
- **Clock-change days skipped.** 30 March (46 periods, BST transition) and 26 October (50 periods, GMT transition) are excluded — 2 of 365 days.
- **One-cycle-per-day cap.** The model does not allow partial cycles or multiple cycles, even on days with multiple price spikes.
- **The real-world revenue stack is benchmark-based, not computed.** The £72k/MW figure and its breakdown come from published industry sources (see the table above), not from raw market data. The "achieved arbitrage" line (£15k) is itself a benchmark estimate, internally consistent with the ~23% capture rate but not independently derived here.

---

## How to run

```bash
# 1. Create and activate the virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows PowerShell
# source venv/bin/activate    # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Fetch a full year of half-hourly prices (skips months already downloaded)
python fetch_prices.py

# 4. Run the arbitrage simulation
python simulate_arbitrage.py

# 5. Compare against the real-world BESS revenue stack
python revenue_comparison.py

# 6. Duration sensitivity sweep (1h / 2h / 4h)
python duration_sweep.py

# 7. Build the self-contained HTML dashboard (opens in your browser)
python build_dashboard.py
```

Outputs are saved to `data/` (gitignored — re-fetch locally):
- `data/prices_2025-MM.csv` — raw monthly price files
- `data/prices_2025-all.csv` — combined annual file
- `data/arbitrage_results.csv` — daily P&L breakdown
- `data/daily_pnl_plot.png` — full-year arbitrage chart
- `data/revenue_comparison.png` — arbitrage ceiling vs real revenue stack
- `data/duration_sweep.png` — revenue by battery duration

`dashboard.html` (project root) is a single self-contained file with all data embedded — open it directly in any browser.

---

## Project structure

```
bess-arbitrage/
├── fetch_prices.py         # Downloads Elexon half-hourly prices → data/
├── simulate_arbitrage.py   # Oracle arbitrage model → daily P&L + chart
├── revenue_comparison.py   # Arbitrage ceiling vs real revenue stack → chart
├── duration_sweep.py       # Arbitrage by battery duration (1h/2h/4h) → chart
├── build_dashboard.py      # Reads CSVs → self-contained dashboard.html
├── dashboard.html          # Single-file interactive dashboard (generated)
├── requirements.txt        # Pinned dependencies
├── assets/                 # Curated charts embedded in this README
├── data/                   # Downloaded prices and results (gitignored)
├── venv/                   # Python virtual environment (gitignored)
├── README.md
└── PROJECT_LOG.md
```

---

## Next steps

- ~~Compare oracle arbitrage revenues against real GB BESS revenue streams (BM, FFR, DC, Capacity Market).~~ ✅ Done — see `revenue_comparison.py`.
- ~~Build an interactive dashboard.~~ ✅ Done — see `build_dashboard.py` / `dashboard.html`.
- Explore a heuristic or day-ahead forecast model to estimate *achievable* arbitrage (replacing the implied £15k figure with a computed one).
- Optionally replace benchmark revenue figures with values computed from raw Elexon BM data.
