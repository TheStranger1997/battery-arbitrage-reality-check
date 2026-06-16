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
- Returns 48 half-hourly Settlement System Prices (System Sell Price + System Buy Price) per day.
- Price used in this model: mid-point of SSP and SBP (`mid_price = (SSP + SBP) / 2`).

> **Note on price series:** Settlement system prices (imbalance prices) are more volatile than day-ahead or intraday market prices, because they reflect real-time scarcity. Using them for arbitrage modelling produces a higher — and less achievable — ceiling than a day-ahead price series would. See Caveats below.

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

---

## Caveats

- **Perfect foresight overstates achievable arbitrage.** A real battery cannot know future prices. Day-ahead price forecasting typically captures 60–80% of the oracle spread.
- **Imbalance prices (SSP/SBP) are more volatile than traded prices.** Using day-ahead or intraday market prices would produce a lower, cleaner arbitrage estimate. The £65k figure should be read as an imbalance-price upper bound, not a day-ahead arbitrage estimate.
- **Clock-change days skipped.** 30 March (46 periods, BST transition) and 26 October (50 periods, GMT transition) are excluded — 2 of 365 days.
- **One-cycle-per-day cap.** The model does not allow partial cycles or multiple cycles, even on days with multiple price spikes.

---

## How to run

```bash
# 1. Create and activate the virtual environment
python -m venv venv
.\venv\Scripts\activate        # Windows PowerShell
# source venv/bin/activate    # macOS / Linux

# 2. Install dependencies
pip install requests pandas matplotlib

# 3. Fetch a full year of half-hourly prices (skips months already downloaded)
python fetch_prices.py

# 4. Run the arbitrage simulation
python simulate_arbitrage.py
```

Outputs are saved to `data/` (gitignored — re-fetch locally):
- `data/prices_2025-MM.csv` — raw monthly price files
- `data/prices_2025-all.csv` — combined annual file
- `data/arbitrage_results.csv` — daily P&L breakdown
- `data/daily_pnl_plot.png` — full-year chart

---

## Project structure

```
bess-arbitrage/
├── fetch_prices.py        # Downloads Elexon half-hourly prices → data/
├── simulate_arbitrage.py  # Oracle arbitrage model → daily P&L + chart
├── data/                  # Downloaded prices and results (gitignored)
├── venv/                  # Python virtual environment (gitignored)
├── README.md
└── PROJECT_LOG.md
```

---

## Next steps

- Compare oracle arbitrage revenues against real GB BESS revenue streams (BM, FFR, DC, Capacity Market).
- Build an interactive dashboard (Streamlit or Panel).
- Explore a heuristic or day-ahead forecast model to estimate *achievable* arbitrage.
