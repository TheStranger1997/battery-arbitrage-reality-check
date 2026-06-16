# Project Log

Dated record of key decisions and findings as the project develops.

---

## 2026-06-16 — Initial build

### Data source: Elexon Insights API
Chose the Elexon Insights public API (`https://data.elexon.co.uk/bmrs/api/v1`) for GB half-hourly settlement system prices. Free, no API key required, returns 48 periods per day. Endpoint: `/balancing/settlement/system-prices/{date}`.

The alternative would be the Market Index Price (MIP) series at `/balancing/settlement/market-index/{date}`, which reflects actual traded volumes in day-ahead and intraday markets and would give a lower, cleaner arbitrage estimate. Imbalance prices (SSP/SBP) are more volatile and produce a higher theoretical ceiling — chosen for the first pass because the spikes are informative and the data is straightforward.

### Settlement period → UTC conversion
GB electricity settlement uses a convention where Period 1 of settlement date X begins at **23:00 UTC on date X−1** (i.e. the settlement day starts at 23:00 UTC / midnight BST in summer). Each subsequent period adds 30 minutes. Getting this right matters because a price spike in Period 2 (23:30 UTC) is an overnight event, not a lunchtime one. Implemented in `period_to_datetime()` in `fetch_prices.py`.

### Clock-change days
- **30 March 2025** (spring forward, BST): only 46 settlement periods — 2 periods shorter than normal.
- **26 October 2025** (fall back, GMT): 50 settlement periods — 2 periods longer than normal.
- Both days are skipped by the simulation (`len(prices) != 48` guard). Impact: 2 of 365 days excluded.

### Simulation method: greedy oracle (perfect foresight)
Chose a **greedy perfect-foresight ("oracle") model** as the first simulation step:
- Sort all 48 daily prices ascending.
- Charge in the 4 cheapest periods (100 MWh in at 50 MW).
- Discharge in the 4 most expensive periods (85 MWh out after 85% RTE).
- Skip the day if net revenue ≤ 0.

This gives a theoretical upper bound, not a tradeable strategy. Alternatives considered but deferred:
- Day-ahead heuristic (threshold-based) — more realistic, requires a threshold rule.
- Linear programming with intraday SoC constraints — most rigorous, added complexity.

Round-trip efficiency applied at discharge only (`energy_out = energy_in × 0.85`), consistent with the standard definition.

### Scope change: one month → full year
Initially fetched May 2025 only. Expanded to all 12 months of 2025 after confirming the fetch and simulation logic worked. `fetch_prices.py` now loops over all 12 months, skipping months where the CSV already exists (safe to re-run). Each month saved as `data/prices_2025-MM.csv`; combined file at `data/prices_2025-all.csv`.

### Key findings: 2025 annual simulation
- **Oracle ceiling: £65,179/MW/year** (363 days traded, 2 clock-change days skipped).
- **January 2025: £11,080/MW** — a single event (8 January cold spell / low wind) drove settlement prices to £2,900/MWh. One day = £245,881 on the 50 MW battery.
- **Monthly range:** £3,458/MW (December) to £11,080/MW (January). Summer months (Jul, Dec) are weakest; winter and stress-event months dominate.
- **May 2025 (original test month):** £5,117/MW — mid-table, broadly representative.
- **Real GB BESS revenues ~£72k/MW/year** across all streams (BM, FFR, DC, Capacity Market). The oracle arbitrage ceiling falls *below* real earnings, reinforcing that revenue stacking defines the GB BESS investment case.

### What's left to build
- [ ] Revenue comparison: oracle arbitrage vs real GB BESS revenue breakdown (BM, FFR, DC, CM).
- [ ] Improved arbitrage model: heuristic or day-ahead forecast to show achievable vs oracle.
- [ ] Dashboard: Streamlit or Panel interface to make the analysis interactive.
- [ ] Possibly: switch price series to MIP for a cleaner day-ahead arbitrage comparison.
