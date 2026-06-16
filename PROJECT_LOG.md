# Project Log

Dated record of key decisions and findings as the project develops.

---

## 2026-06-16 — Lookback sensitivity sweep + seasonal breakdown + methodology explainer

Three additions to close the main gaps identified after the computed-capture-rate commit.

**Lookback sensitivity sweep (`forecast_arbitrage.py`):** `run_sweep()` runs the forecast model at lookbacks of 1, 3, 7, 14, and 30 days and saves results to `data/lookback_sweep.csv` + `assets/lookback_sweep.png`. Key finding: 7-day is the genuine optimum — shorter windows miss the time-of-day shape; longer windows over-smooth. The curve peaks and then falls back to ~32% at 14–30 days. This justifies the 7-day headline choice empirically rather than by assertion.

**Seasonal breakdown (`build_dashboard.py`):** `build_monthly_breakdown()` groups oracle and forecast results by calendar month from the existing CSVs and returns `{months, oracle, achieved, capturePct}`. Exposed in the dashboard as Chart 6 — a grouped-bar chart with a capture-rate line. January oracle is dominant (scarcity spike); summer months show higher capture (routine diurnal spread). Annual aggregate buried this finding.

**Methodology explainer (dashboard HTML):** Added a `<details><summary>How this works</summary>` block between the KPI section and the first chart. Three columns — Oracle (red), Achieved (blue), Real stack (green) — each with a plain-English explanation. Closes the gap for non-technical readers who couldn't tell what "no-foresight forecast" meant. Also updated the eyebrow text to include "data: Jan–Dec 2025".

Dashboard now has 6 charts (was 4). All 13 tests still pass. Headlines unchanged.

---

## 2026-06-16 — Forecast-based achievable arbitrage (computed capture rate)

`forecast_arbitrage.py`. Replaced the project's last *assumed* number — the implied £15k "achieved wholesale arbitrage" (oracle × a guessed ~23% capture) — with a **computed** figure from a no-perfect-foresight model.

**Method:** each day the battery commits charge/discharge windows using only past prices (it forecasts today's price *shape*, picks the 4 lowest-forecast periods to charge and 4 highest to discharge, and trades only if the forecast says it's profitable), then is settled at today's **actual** prices — wrong days included, no `max(0,·)` clamp. Same imbalance series, same battery, and (like the base oracle) no intraday SoC ordering constraint, so the **capture rate = achievable ÷ oracle** isolates exactly one thing: foresight.

**Two forecast rules:**
- Persistence (today ≈ yesterday): **£11,030/MW, 17% capture**, 133/362 loss-making days.
- Trailing 7-day shape (headline): **£23,269/MW, 36% capture**, 88/356 loss days.

Chose the 7-day model as the headline achievable figure: no desk trades off literally only yesterday, and it has far fewer loss days. Persistence is reported as a conservative floor. **The gap to the £65k ceiling is the scarcity tail** — the 8 Jan £2,900/MWh event dominates the oracle total but can't be forecast from 7 Jan, so a shape-based forecast captures the routine overnight-to-peak spread and misses the spikes.

**Wiring (kept in sync, not hard-coded):** `revenue_comparison.py` and `build_dashboard.py` now read the achieved figure live from `data/forecast_results.csv` (mirroring how the oracle is read from `arbitrage_results.csv`). Knock-on changes: the revenue stack total rose £72k → **£80,269/MW** (arbitrage slice 15k → 23.3k, now the 2nd-largest stream at 29%); capture rate shown everywhere moved 23% → 36%. The thesis is unchanged and slightly stronger — the £65k oracle ceiling still sits **below** real all-stream revenue (£80k). Added 3 forecast tests to `test_arbitrage.py` (perfect forecast captures the full oracle; no forecast beats foresight; a reversed forecast underperforms) — 13/13 pass. README revenue-comparison table, caveats, run steps, structure and next-steps updated; charts refreshed in `assets/`.

---

## 2026-06-16 — Imbalance vs traded wholesale prices (item 7)

`market_index_compare.py`. Reran the oracle on the Market Index Price (MID, Elexon `datasets/MID`) — the volume-weighted price of real short-term wholesale trades — as a more defensible proxy for what a battery actually trades against than imbalance cash-out prices.

**Data handling:** MID is published per period by two providers (APXMIDP, N2EXMIDP); N2EX frequently reports zero volume, so prices are **volume-weighted** across providers and zero-volume periods are dropped. The `from`/`to` query filters on `startTime` and the API rejects wide ranges (400), so fetch is per-day; cached to `data/mid_2025-all.csv`.

**Apples-to-apples fix:** dropping untraded periods leaves only 206 days with a complete 48-period MID profile (vs 363 for imbalance). Comparing the raw sums would conflate price level with day count (initial naive run showed a misleading 31%). Fixed by measuring BOTH series over the same 206 days and annualising:
- Imbalance: £35,610/MW over common days → £63,095/MW annualised
- MID: £20,313/MW over common days → £35,991/MW annualised
- MID is **57%** of the imbalance ceiling on identical days.

The annualised common-day imbalance (£63,095) ≈ the full-year headline (£65,179), so the 206 days are representative. **Conclusion:** realistic perfect-foresight wholesale arbitrage is ~£36k/MW, not £65k — the imbalance headline's scarcity tail roughly doubles it. This is the single most important caveat on the £65k figure, now quantified. Kept the £65k as the documented base/headline; this is an additive reality-check.

---

## 2026-06-16 — Sensitivity analyses + tests (items 8, 9, 10)

Additive analyses around the base case. The £65,179/MW headline (2h, 1 cycle, imbalance, greedy) is preserved; these add context rather than replace it.

### Cycling sensitivity (`cycles_sweep.py`)
1 vs 2 cycles/day: £65,179 → £111,395/MW/yr (+71%). Notable equivalence: a 2h battery cycling twice selects the same 8 cheapest + 8 dearest half-hours as a 4h battery cycling once, hence the identical £111,395 — same revenue, but bought with wear (degradation) instead of capex (steel). Base case stays at 1 cycle/day to reflect warranty/degradation limits.

### Ordering-constrained oracle (`ordering_oracle.py`)
Built a per-day DP that enforces state-of-charge ordering (can't discharge before charging). Greedy £65,179 vs ordering-constrained £62,487 — the greedy upper bound overstates by only **4.1%** (ordering binds on 164/363 days but weakly). Validates that the headline is a genuine, only-modestly-loose upper bound.

### Tests + CI (`test_arbitrage.py`, `.github/workflows/tests.yml`)
10 synthetic-data sanity checks (no downloaded data needed): RTE application, greedy==ordered when trough precedes peak, ordered<greedy when peak precedes trough, ordered≤greedy always, flat-day→0, cycle monotonicity, and the settlement-period→UTC mapping. All pass. GitHub Actions runs them on every push.

### Co-author trailer
Scrubbed `Co-Authored-By` from all commit messages via `git filter-branch` (history not yet pushed).

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
