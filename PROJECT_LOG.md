# Project Log

Dated record of key decisions and findings as the project develops.

---

## 2026-06-16 — Pre-publish polish (dashboard + duration analysis)

Round of improvements before publishing, chosen for value-for-effort with no destabilising of headline numbers.

### Single imbalance pricing (credibility fix)
Verified from the data that `systemSellPrice == systemBuyPrice` in **all 17,520 rows**. GB has used a single cash-out (imbalance) price since 2015 (BSC mod P305), so the earlier "SSP vs SBP spread" framing was wrong. Corrected the README and `fetch_prices.py` comments; the `mid_price` column is simply the single imbalance price (kept as-is, no number change).

### Verified the 8 Jan scarcity spike is real
The single biggest day (£245,881, ~19% of the annual oracle total) is driven by prices pinned at **£2,900/MWh across periods 31–38 (14:00–17:30)** on 8 Jan — a genuine cold, low-wind evening scarcity event, not a data artefact. Year max = £2,900 at that timestamp. Headline £65,179/MW/yr holds.

### Duration sensitivity (new analysis — `duration_sweep.py`)
Reran the oracle at 1h/2h/4h, power fixed at 50 MW:
- 1h (50 MWh): £36,010/MW/yr — £36,010/MWh-cap
- 2h (100 MWh): £65,179/MW/yr — £32,589/MWh-cap (base)
- 4h (200 MWh): £111,395/MW/yr (+71%) — £27,849/MWh-cap
Per-MW revenue rises with duration (captures more of each spike); per-MWh-of-capacity falls (diminishing returns). This is the live GB 2h-vs-4h trade-off. Does not change existing headline numbers; adds new ones.

### Dashboard refinements
- Capped the daily-P&L y-axis at £40k and added a self-contained canvas plugin (no extra CDN) labelling the off-scale 8 Jan spike, so the rest of the year is legible.
- Added a fourth chart (duration sweep, dual y-axis) computed at build time from `prices_2025-all.csv`.

### Repo presentation
Added `requirements.txt` (pinned), MIT `LICENSE`, and an `assets/` folder of committed charts embedded in the README (`.gitignore` updated to allow `assets/*.png` while still ignoring other PNGs).

### Deferred to a v2 (deliberately not done today)
- Replace the implied £15k "achieved arbitrage" with a computed no-foresight/day-ahead model (would change the 23% headline — wanted stable numbers for publish).
- Switch imbalance → Market Index (day-ahead) prices for a more defensible ceiling.

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
- [x] Revenue comparison: oracle arbitrage vs real GB BESS revenue breakdown (BM, FFR, DC, CM). — `revenue_comparison.py`
- [ ] Improved arbitrage model: heuristic or day-ahead forecast to show achievable vs oracle.
- [ ] Dashboard: Streamlit or Panel interface to make the analysis interactive.
- [ ] Possibly: switch price series to MIP for a cleaner day-ahead arbitrage comparison.

---

## 2026-06-16 — Revenue comparison

### Approach: benchmark stack, not computed
Built `revenue_comparison.py` to set the oracle arbitrage ceiling against the actual GB BESS revenue stack for 2025. Decided to use **published industry benchmark figures** rather than computing each stream from raw data. Reason: granular per-asset revenue (BM accepted volumes by BMU, DC contract values, etc.) sits behind paywalls (Modo Energy, Cornwall Insight, LCP Delta). Parsing Elexon BM data to identify battery BMUs and sum accepted bids/offers would be a substantial sub-project in its own right. For a portfolio piece, sourced benchmarks — the same inputs an analyst uses for initial screening — keep the focus on the comparison story. The benchmark nature is flagged clearly in the script docstring, the README table, and the README caveats.

### Revenue stack used (£/MW/year, 2025)
- Balancing Mechanism — £28,000 (39%) [Modo Energy BESS Revenue Tracker 2025]
- Frequency response (DC etc.) — £18,000 (25%) [NESO DC procurement + Modo Energy]
- Wholesale arbitrage (achieved) — £15,000 (21%) [implied: oracle × typical day-ahead capture]
- Capacity Market — £7,000 (10%) [NESO CM auction results]
- Other (DM, DR, triad) — £4,000 (6%) [Cornwall Insight estimates]
- **Total — £72,000**

The oracle figure is read live from `data/arbitrage_results.csv` (summed net revenue / 50 MW), so it stays in sync if the simulation is re-run.

### Key insight
Even with perfect foresight, arbitrage on imbalance prices (£65k/MW) falls **below** real all-stream revenue (£72k/MW). Achieved arbitrage (£15k) is only **~23% of the oracle ceiling** and ~21% of real total revenue. Confirms the project thesis: GB BESS economics are defined by **revenue stacking**, not arbitrage alone.

### Chart note
First version placed the insight annotation at top-centre, where it collided with the bar value labels; moved it into the empty gap between the two bars and gave it a border. Legend moved below the plot for the same reason.
