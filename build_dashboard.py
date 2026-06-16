"""
build_dashboard.py
------------------
Builds a single, self-contained dashboard.html from the saved CSVs.

Real data (sample-day prices, daily P&L, revenue stack) is read at build time
and embedded directly into the HTML as JSON literals, so the resulting file
opens in any browser with no server and no network access except the Chart.js
CDN. Run this whenever the underlying data changes:

    python build_dashboard.py
"""

import pandas as pd
import json
import os
import webbrowser

# ── Inputs ───────────────────────────────────────────────────────────────────

PRICES_MONTH  = os.path.join("data", "prices_2025-05.csv")
RESULTS_FILE  = os.path.join("data", "arbitrage_results.csv")
FORECAST_FILE = os.path.join("data", "forecast_results.csv")
SWEEP_FILE    = os.path.join("data", "lookback_sweep.csv")
OUTPUT_HTML   = "dashboard.html"

SAMPLE_DATE  = "2025-05-14"   # a Wednesday — typical weekday price shape
POWER_MW     = 50

# Number of half-hour periods charged / discharged per day (matches the model)
PERIODS_PER_CYCLE = 4

# Real-world GB BESS revenue stack (2025, £/MW/yr). Four streams are published
# benchmarks; "Wholesale arbitrage (achieved)" is computed at build time from
# forecast_arbitrage.py (None below = filled by load_achieved_arbitrage()).
# Order: bottom → top of the stacked bar.
REVENUE_STACK = [
    ("Balancing Mechanism",          28_000, "#2f6f9f"),
    ("Frequency response (DC etc.)", 18_000, "#e08a1e"),
    ("Wholesale arbitrage (achieved)", None, "#3a9d5d"),
    ("Capacity Market",               7_000, "#8a6bbf"),
    ("Other (DM, DR, triad)",         4_000, "#9c6b58"),
]


def load_achieved_arbitrage() -> int:
    """
    Achieved (no-foresight) wholesale arbitrage, £/MW/yr — computed by
    forecast_arbitrage.py's 7-day forecast model, not assumed. Read live so the
    dashboard stays in sync if that model is re-run.
    """
    fc = pd.read_csv(FORECAST_FILE)
    return round(fc["realised_net_gbp"].sum() / POWER_MW)


def resolved_stack(achieved: int) -> list:
    """The revenue stack with the computed achieved-arbitrage amount filled in."""
    return [(label, achieved if amount is None else amount, colour)
            for label, amount, colour in REVENUE_STACK]


# ── Build the embedded data ──────────────────────────────────────────────────

def build_sample_day() -> dict:
    """48 half-hourly prices for the sample day, tagged charge/discharge/idle."""
    df = pd.read_csv(PRICES_MONTH, parse_dates=["datetime_utc"])
    day = df[df["settlement_date"] == SAMPLE_DATE].sort_values("datetime_utc")

    prices = day["mid_price_gbp_mwh"].tolist()
    times  = [t.strftime("%H:%M") for t in day["datetime_utc"]]

    # Rank periods by price to find the cheapest (charge) and dearest (discharge)
    order = sorted(range(len(prices)), key=lambda i: prices[i])
    charge_idx    = set(order[:PERIODS_PER_CYCLE])
    discharge_idx = set(order[-PERIODS_PER_CYCLE:])

    roles = []
    for i in range(len(prices)):
        if i in charge_idx:
            roles.append("charge")
        elif i in discharge_idx:
            roles.append("discharge")
        else:
            roles.append("idle")

    return {"times": times, "prices": prices, "roles": roles}


def build_daily_pnl() -> dict:
    """Daily net revenue for 2025 from the simulation output."""
    res = pd.read_csv(RESULTS_FILE, parse_dates=["date"]).sort_values("date")
    return {
        "dates": [d.strftime("%Y-%m-%d") for d in res["date"]],
        "net":   [round(v, 0) for v in res["net_revenue_gbp"]],
    }


def build_kpis(daily_pnl: dict, stack: list, achieved: int) -> dict:
    oracle_per_mw = sum(daily_pnl["net"]) / POWER_MW
    real_total    = sum(amount for _, amount, _ in stack)
    pct_of_ceiling = round(achieved / oracle_per_mw * 100)
    return {
        "oracle_per_mw":  round(oracle_per_mw),
        "achieved":       achieved,
        "real_total":     real_total,
        "pct_of_ceiling": pct_of_ceiling,
    }


def build_stack(stack: list) -> dict:
    return {
        "labels": [label for label, _, _ in stack],
        "values": [amount for _, amount, _ in stack],
        "colours": [colour for _, _, colour in stack],
    }


def build_duration() -> dict:
    """
    Rerun the oracle model at 1h / 2h / 4h durations (power fixed at 50 MW)
    to show the per-MW vs per-MWh-of-capacity trade-off. Computed here from the
    full-year price file so the dashboard stays self-contained.
    """
    all_prices = os.path.join("data", "prices_2025-all.csv")
    df = pd.read_csv(all_prices)
    days = [g["mid_price_gbp_mwh"].reset_index(drop=True)
            for _, g in df.groupby("settlement_date") if len(g) == 48]

    energy_per_period = POWER_MW * 0.5          # 25 MWh per half-hour
    energy_sold = energy_per_period * 0.85      # RTE applied at discharge

    per_mw, per_mwh = [], []
    for duration in (1, 2, 4):
        capacity = POWER_MW * duration
        n = int(capacity / energy_per_period)   # periods per cycle: 2 / 4 / 8
        total = 0.0
        for prices in days:
            s = prices.sort_values()
            net = (s.iloc[-n:] * energy_sold).sum() - (s.iloc[:n] * energy_per_period).sum()
            if net > 0:
                total += net
        per_mw.append(round(total / POWER_MW))
        per_mwh.append(round(total / capacity))

    return {"labels": ["1-hour", "2-hour", "4-hour"], "perMw": per_mw, "perMwh": per_mwh}


def build_lookback_sweep() -> dict:
    """Load the lookback sensitivity sweep for the dashboard chart."""
    df = pd.read_csv(SWEEP_FILE)
    return {
        "lookbacks":   [str(int(lb)) for lb in df["lookback_days"]],
        "perMw":       df["per_mw_gbp"].tolist(),
        "capturePct":  df["capture_pct"].tolist(),
    }


def build_monthly_breakdown() -> dict:
    """Oracle and achieved arbitrage per calendar month."""
    oracle   = pd.read_csv(RESULTS_FILE,  parse_dates=["date"])
    forecast = pd.read_csv(FORECAST_FILE, parse_dates=["date"])

    oracle["month"]   = oracle["date"].dt.month
    forecast["month"] = forecast["date"].dt.month

    months       = list(range(1, 13))
    month_labels = ["Jan","Feb","Mar","Apr","May","Jun",
                    "Jul","Aug","Sep","Oct","Nov","Dec"]

    o_by_m = oracle.groupby("month")["net_revenue_gbp"].sum()   / POWER_MW
    a_by_m = forecast.groupby("month")["realised_net_gbp"].sum() / POWER_MW

    oracle_vals   = [round(o_by_m.get(m, 0))   for m in months]
    achieved_vals = [round(a_by_m.get(m, 0))   for m in months]
    capture_pct   = [
        round(a_by_m.get(m, 0) / o_by_m.get(m, 1) * 100, 1) if o_by_m.get(m, 0) > 0 else 0
        for m in months
    ]

    return {
        "months":     month_labels,
        "oracle":     oracle_vals,
        "achieved":   achieved_vals,
        "capturePct": capture_pct,
    }


def main():
    sample_day = build_sample_day()
    daily_pnl  = build_daily_pnl()
    achieved   = load_achieved_arbitrage()
    stack_rows = resolved_stack(achieved)
    kpis       = build_kpis(daily_pnl, stack_rows, achieved)
    stack      = build_stack(stack_rows)
    duration   = build_duration()
    sweep      = build_lookback_sweep()
    monthly    = build_monthly_breakdown()

    payload = {
        "sampleDate": SAMPLE_DATE,
        "sampleDay":  sample_day,
        "dailyPnl":   daily_pnl,
        "stack":      stack,
        "duration":   duration,
        "kpis":       kpis,
        "oracle":     kpis["oracle_per_mw"],
        "sweep":      sweep,
        "monthly":    monthly,
    }

    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
    # KPI text values injected directly so they show even before JS runs
    html = (html
            .replace("__KPI_ORACLE__",   f"{kpis['oracle_per_mw']:,}")
            .replace("__KPI_ACHIEVED__", f"{kpis['achieved']:,}")
            .replace("__KPI_REAL__",     f"{kpis['real_total']:,}")
            .replace("__KPI_PCT__",      f"{kpis['pct_of_ceiling']}"))

    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)

    # Also write index.html: this is what GitHub Pages serves at the site root,
    # so the published URL shows the dashboard directly. Identical content.
    with open("index.html", "w", encoding="utf-8") as f:
        f.write(html)

    abspath = os.path.abspath(OUTPUT_HTML)
    print(f"Built {OUTPUT_HTML} and index.html (GitHub Pages entry point)")
    print(f"  Oracle: £{kpis['oracle_per_mw']:,}/MW/yr | "
          f"Achieved: £{kpis['achieved']:,} | "
          f"Real: £{kpis['real_total']:,} | "
          f"Achieved/ceiling: {kpis['pct_of_ceiling']}%")
    print(f"  Sample day: {SAMPLE_DATE} ({len(sample_day['prices'])} periods)")
    print(f"  Daily P&L points: {len(daily_pnl['net'])}")
    webbrowser.open(f"file:///{abspath.replace(os.sep, '/')}")
    print(f"Opened in browser: {abspath}")


# ── HTML template (token __DATA__ replaced with embedded JSON) ───────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Battery arbitrage reality check</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root {
    --bg: #FBFAF7;
    --card: #ffffff;
    --ink: #1d1d1b;
    --muted: #6b6862;
    --line: #ece8e1;
    --green: #3a9d5d;
    --orange: #e08a1e;
    --red: #c2453b;
    --accent: #2f6f9f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--bg);
    color: var(--ink);
    font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
    line-height: 1.5;
    -webkit-font-smoothing: antialiased;
  }
  .wrap { max-width: 980px; margin: 0 auto; padding: 56px 24px 72px; }

  .eyebrow {
    font-size: 12px; font-weight: 600; letter-spacing: .08em;
    text-transform: uppercase; color: var(--muted); margin: 0 0 10px;
  }
  h1 { font-size: 40px; font-weight: 700; letter-spacing: -.02em; margin: 0 0 12px; }
  .subhead { font-size: 18px; color: var(--muted); margin: 0 0 18px; max-width: 660px; }
  .spec {
    display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 13px;
    color: var(--ink); background: #f2efe8; border: 1px solid var(--line);
    border-radius: 999px; padding: 6px 14px;
  }

  .kpis {
    display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px;
    margin: 36px 0 8px;
  }
  .kpi {
    background: var(--card); border: 1px solid var(--line); border-radius: 14px;
    padding: 20px 18px;
  }
  .kpi .label { font-size: 12px; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: .05em; margin-bottom: 12px; }
  .kpi .value { font-family: 'IBM Plex Mono', monospace; font-size: 27px; font-weight: 600;
    letter-spacing: -.01em; }
  .kpi .unit { font-size: 13px; color: var(--muted); margin-top: 4px; }
  .kpi.k-oracle .value { color: var(--red); }
  .kpi.k-real .value { color: var(--green); }

  .card {
    background: var(--card); border: 1px solid var(--line); border-radius: 16px;
    padding: 24px 24px 20px; margin-top: 22px;
  }
  .card h2 { font-size: 19px; font-weight: 600; margin: 0 0 4px; letter-spacing: -.01em; }
  .card .lead { font-size: 14px; color: var(--muted); margin: 0 0 18px; }
  .chart-box { position: relative; width: 100%; }
  .h-sample { height: 300px; }
  .h-pnl { height: 300px; }
  .h-stack { height: 360px; }

  .chips { display: flex; gap: 16px; margin-top: 14px; font-size: 13px; color: var(--muted); }
  .chip { display: inline-flex; align-items: center; gap: 7px; }
  .dot { width: 11px; height: 11px; border-radius: 3px; display: inline-block; }

  .takeaway {
    background: #fff7ec; border: 1px solid #f0dcc0; border-radius: 16px;
    padding: 22px 24px; margin-top: 28px;
  }
  .takeaway h2 { font-size: 17px; margin: 0 0 12px; }
  .takeaway ul { margin: 0; padding-left: 20px; }
  .takeaway li { margin-bottom: 8px; font-size: 15px; }
  .takeaway b { font-family: 'IBM Plex Mono', monospace; font-weight: 600; }

  footer {
    margin-top: 40px; padding-top: 22px; border-top: 1px solid var(--line);
    font-size: 13px; color: var(--muted);
  }
  footer .sources { margin-bottom: 8px; }
  footer b { color: var(--ink); font-weight: 600; }

  .method-box {
    background: var(--card); border: 1px solid var(--line); border-radius: 16px;
    padding: 18px 24px; margin-top: 22px;
  }
  .method-box summary {
    font-size: 14px; font-weight: 600; color: var(--muted); cursor: pointer;
    user-select: none; letter-spacing: .02em;
  }
  .method-box summary::-webkit-details-marker { display: none; }
  .method-grid {
    display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px;
    margin-top: 18px;
  }
  .method-label { font-size: 13px; font-weight: 700; margin: 0 0 6px; }
  .method-grid p { font-size: 14px; color: var(--muted); margin: 0 0 6px; }

  @media (max-width: 720px) {
    .kpis { grid-template-columns: repeat(2, 1fr); }
    h1 { font-size: 32px; }
    .method-grid { grid-template-columns: 1fr; }
  }
</style>
</head>
<body>
<div class="wrap">

  <p class="eyebrow">GB power markets · weekend build · data: Jan–Dec 2025</p>
  <h1>Battery arbitrage reality check</h1>
  <p class="subhead">How much could a grid-scale GB battery earn from wholesale price arbitrage alone, and how does that compare with what batteries actually earn across every revenue stream?</p>
  <div class="spec">50 MW / 100 MWh · 2-hour · 85% round-trip · 1 cycle/day cap</div>

  <div class="kpis">
    <div class="kpi k-oracle">
      <div class="label">Oracle arbitrage</div>
      <div class="value">£__KPI_ORACLE__</div>
      <div class="unit">/MW/yr · perfect foresight</div>
    </div>
    <div class="kpi">
      <div class="label">Achieved (modelled)</div>
      <div class="value">£__KPI_ACHIEVED__</div>
      <div class="unit">/MW/yr · 7-day shape forecast</div>
    </div>
    <div class="kpi k-real">
      <div class="label">Real GB stack</div>
      <div class="value">£__KPI_REAL__</div>
      <div class="unit">/MW/yr · all streams</div>
    </div>
    <div class="kpi">
      <div class="label">Achieved % of ceiling</div>
      <div class="value">__KPI_PCT__%</div>
      <div class="unit">forecasting is hard</div>
    </div>
  </div>

  <details class="method-box">
    <summary>How this works ▸</summary>
    <div class="method-grid">
      <div>
        <p class="method-label" style="color:var(--red)">Oracle (red KPI)</p>
        <p>Perfect foresight — the model is told all 48 half-hourly prices before the day starts, charges in the 4 cheapest half-hours, and discharges in the 4 most expensive. This is a <strong>theoretical upper bound</strong>, not a tradeable strategy. No real desk knows tomorrow's prices in full.</p>
      </div>
      <div>
        <p class="method-label" style="color:#2f6f9f">Achieved (modelled)</p>
        <p>Each morning the battery commits its windows based only on the <strong>average price shape of the last 7 days</strong> — no future data. It then settles at today's real prices at those committed periods, loss days included. This is the closest thing to what a simple systematic desk could actually do.</p>
      </div>
      <div>
        <p class="method-label" style="color:var(--green)">Real GB stack (green KPI)</p>
        <p>What GB grid-scale batteries actually earned in 2025 across <strong>all revenue streams</strong>: Balancing Mechanism dispatch, frequency response (DC etc.), the Capacity Market, and small other streams — plus the computed achievable arbitrage. The four benchmark streams are from published sources (Modo Energy, NESO, Cornwall Insight), not computed from raw data.</p>
      </div>
    </div>
  </details>

  <div class="card">
    <h2>Sample day price profile — <span id="sampleDateLabel"></span></h2>
    <p class="lead">One day of half-hourly GB prices. The model charges in the four cheapest half-hours and discharges in the four dearest.</p>
    <div class="chart-box h-sample"><canvas id="sampleChart"></canvas></div>
    <div class="chips">
      <span class="chip"><span class="dot" style="background:var(--green)"></span>Charge (buy)</span>
      <span class="chip"><span class="dot" style="background:var(--orange)"></span>Discharge (sell)</span>
      <span class="chip"><span class="dot" style="background:#c9c4bb"></span>Idle</span>
    </div>
  </div>

  <div class="card">
    <h2>Daily arbitrage P&amp;L — 2025</h2>
    <p class="lead">Net revenue per day under perfect foresight. Revenue concentrates in a handful of stress events. <b>8 January earned £245,881 in one day</b>: a cold, low-wind scarcity event with prices pinned at £2,900/MWh. The y-axis is capped at £40k so the rest of the year stays legible.</p>
    <div class="chart-box h-pnl"><canvas id="pnlChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Oracle arbitrage vs the real revenue stack</h2>
    <p class="lead">Even the theoretical arbitrage maximum (left) sits below what GB batteries actually earn across all streams (right).</p>
    <div class="chart-box h-stack"><canvas id="stackChart"></canvas></div>
  </div>

  <div class="card">
    <h2>How much does duration matter?</h2>
    <p class="lead">The same oracle model at 1-, 2- and 4-hour durations (power fixed at 50 MW). Revenue <b>per MW</b> rises with duration, since a 4-hour battery captures more of each spike, but revenue <b>per MWh of capacity</b> falls as the extra storage is dispatched onto shallower parts of the price curve. This is the live GB "2h vs 4h" trade-off.</p>
    <div class="chart-box h-stack"><canvas id="durationChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Forecast sensitivity — how many days of history?</h2>
    <p class="lead">The achieved figure uses a 7-day lookback. This chart shows the sensitivity: revenue and capture rate across 1, 3, 7, 14, and 30 days of trailing history. The 7-day window is the genuine optimum for 2025 — shorter windows miss the time-of-day shape; longer windows average out too much recent structure.</p>
    <div class="chart-box h-stack"><canvas id="sweepChart"></canvas></div>
  </div>

  <div class="card">
    <h2>Seasonal pattern — oracle vs achieved by month</h2>
    <p class="lead">Annual totals hide the seasonal story. January's oracle is huge (the 8 Jan scarcity spike); the forecast model captures a small fraction because extreme spikes don't repeat day-to-day. Summer months show higher capture rates — routine diurnal spreads are more forecastable than winter scarcity events.</p>
    <div class="chart-box h-stack"><canvas id="monthlyChart"></canvas></div>
  </div>

  <div class="takeaway">
    <h2>Key takeaway</h2>
    <ul>
      <li>A no-foresight forecast captures only <b>~__KPI_PCT__%</b> of the theoretical maximum (a computed figure, not an assumption). Perfect foresight is impossible, and the biggest price spikes are nearly unforecastable.</li>
      <li>Even the theoretical maximum (<b>£__KPI_ORACLE__</b>/MW/yr) sits <b>below</b> all-stream revenue (<b>£__KPI_REAL__</b>/MW/yr). Revenue stacking, not arbitrage, defines the GB BESS investment case.</li>
    </ul>
  </div>

  <footer>
    <div class="sources"><b>Data sources:</b> Elexon Insights API (half-hourly imbalance prices); NESO Capacity Market auction results; revenue-stack benchmarks from Modo Energy and Cornwall Insight. Achieved wholesale arbitrage is computed here from a no-foresight forecast model; the other four revenue streams are published benchmarks, not computed from raw data.</div>
  </footer>

</div>

<script>
const DATA = __DATA__;

const FONT = "'Inter', system-ui, sans-serif";
const MONO = "'IBM Plex Mono', monospace";
const INK = "#1d1d1b", MUTED = "#6b6862", LINE = "#ece8e1";
const GREEN = "#3a9d5d", ORANGE = "#e08a1e", RED = "#c2453b", GREY = "#c9c4bb", ACCENT = "#2f6f9f";
Chart.defaults.font.family = FONT;
Chart.defaults.color = MUTED;

const gbp = (v) => "£" + Math.round(v).toLocaleString("en-GB");

// ── Chart 1: sample day price profile ──────────────────────────────────────
document.getElementById("sampleDateLabel").textContent =
  new Date(DATA.sampleDate).toLocaleDateString("en-GB",
    { weekday: "long", day: "numeric", month: "long", year: "numeric" });

const roleColour = (r) => r === "charge" ? GREEN : r === "discharge" ? ORANGE : GREY;
const sd = DATA.sampleDay;

new Chart(document.getElementById("sampleChart"), {
  type: "line",
  data: {
    labels: sd.times,
    datasets: [{
      data: sd.prices,
      borderColor: "#b9b3a8",
      borderWidth: 1.5,
      tension: 0.25,
      fill: false,
      pointBackgroundColor: sd.roles.map(roleColour),
      pointBorderColor: sd.roles.map(roleColour),
      pointRadius: sd.roles.map(r => r === "idle" ? 0 : 5),
      pointHoverRadius: 6,
    }]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: (c) => gbp(c.raw) + "/MWh  ·  " + sd.roles[c.dataIndex],
        }
      }
    },
    scales: {
      x: { grid: { display: false },
           ticks: { maxTicksLimit: 12, autoSkip: true } },
      y: { grid: { color: LINE },
           title: { display: true, text: "£/MWh", color: MUTED },
           ticks: { font: { family: MONO } } }
    }
  }
});

// ── Chart 2: daily P&L 2025 ────────────────────────────────────────────────
const pnl = DATA.dailyPnl;
const PNL_CAP = 40000;   // y-axis cap so the £246k spike doesn't flatten the year
const SPIKE_DATE = "2025-01-08";

// Self-contained plugin (no CDN dependency): label the off-scale 8 Jan spike.
const spikeLabel = {
  id: "spikeLabel",
  afterDatasetsDraw(chart) {
    const idx = pnl.dates.indexOf(SPIKE_DATE);
    if (idx < 0) return;
    const bar = chart.getDatasetMeta(0).data[idx];
    if (!bar) return;
    const ctx = chart.ctx, top = chart.chartArea.top;
    ctx.save();
    ctx.strokeStyle = RED; ctx.lineWidth = 1.2;
    ctx.beginPath(); ctx.moveTo(bar.x, top + 34); ctx.lineTo(bar.x, top + 4); ctx.stroke();
    ctx.fillStyle = RED; ctx.textAlign = "left"; ctx.font = "600 12px " + FONT;
    ctx.fillText("8 Jan: £245,881", bar.x + 6, top + 14);
    ctx.font = "500 11px " + FONT;
    ctx.fillText("scarcity spike (off scale)", bar.x + 6, top + 29);
    ctx.restore();
  }
};

new Chart(document.getElementById("pnlChart"), {
  type: "bar",
  data: {
    labels: pnl.dates,
    datasets: [{
      data: pnl.net,
      backgroundColor: pnl.dates.map(d => d === SPIKE_DATE ? RED : GREEN),
      borderWidth: 0,
      barPercentage: 1.0,
      categoryPercentage: 0.92,
    }]
  },
  plugins: [spikeLabel],
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          title: (items) => new Date(items[0].label).toLocaleDateString("en-GB",
            { day: "numeric", month: "short", year: "numeric" }),
          label: (c) => gbp(c.raw) + " net",
        }
      }
    },
    scales: {
      x: {
        grid: { display: false },
        ticks: {
          autoSkip: false, maxRotation: 0,
          callback: function(value, index) {
            const d = new Date(pnl.dates[index]);
            return d.getUTCDate() === 1
              ? d.toLocaleDateString("en-GB", { month: "short" }) : "";
          }
        }
      },
      y: { grid: { color: LINE }, max: PNL_CAP,
           title: { display: true, text: "£/day", color: MUTED },
           ticks: { font: { family: MONO },
                    callback: (v) => "£" + (v/1000) + "k" } }
    }
  }
});

// ── Chart 3: oracle vs real stack ──────────────────────────────────────────
const stack = DATA.stack;
const stackDatasets = stack.labels.map((label, i) => ({
  label: label,
  data: [0, stack.values[i]],          // only contributes to the "Real" bar
  backgroundColor: stack.colours[i],
  stack: "real",
  borderWidth: 0,
}));
stackDatasets.unshift({
  label: "Oracle arbitrage (ceiling)",
  data: [DATA.oracle, 0],              // only contributes to the "Oracle" bar
  backgroundColor: RED,
  stack: "oracle",
  borderWidth: 0,
});

new Chart(document.getElementById("stackChart"), {
  type: "bar",
  data: {
    labels: [["Oracle arbitrage", "(perfect foresight)"], ["Real GB BESS", "(all streams, 2025)"]],
    datasets: stackDatasets,
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
      tooltip: { callbacks: { label: (c) => c.dataset.label + ": " + gbp(c.raw) + "/MW/yr" } }
    },
    scales: {
      x: { stacked: true, grid: { display: false } },
      y: { stacked: true, grid: { color: LINE },
           title: { display: true, text: "£/MW/yr", color: MUTED },
           ticks: { font: { family: MONO },
                    callback: (v) => "£" + (v/1000) + "k" } }
    }
  }
});

// ── Chart 4: duration sweep (per MW vs per MWh of capacity) ─────────────────
const dur = DATA.duration;
new Chart(document.getElementById("durationChart"), {
  type: "bar",
  data: {
    labels: dur.labels,
    datasets: [
      { label: "Revenue per MW of power", data: dur.perMw,
        backgroundColor: GREEN, yAxisID: "y", borderWidth: 0,
        categoryPercentage: 0.7, barPercentage: 0.9 },
      { label: "Revenue per MWh of capacity", data: dur.perMwh,
        backgroundColor: ACCENT, yAxisID: "y1", borderWidth: 0,
        categoryPercentage: 0.7, barPercentage: 0.9 },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
      tooltip: { callbacks: { label: (c) => c.dataset.label + ": " + gbp(c.raw) + "/yr" } }
    },
    scales: {
      x: { grid: { display: false } },
      y:  { position: "left",  grid: { color: LINE }, beginAtZero: true,
            title: { display: true, text: "£/MW/yr", color: GREEN },
            ticks: { font: { family: MONO }, callback: (v) => "£" + (v/1000) + "k" } },
      y1: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true,
            title: { display: true, text: "£/MWh-cap/yr", color: ACCENT },
            ticks: { font: { family: MONO }, callback: (v) => "£" + (v/1000) + "k" } }
    }
  }
});

// ── Chart 5: forecast lookback sensitivity ──────────────────────────────────
const sw = DATA.sweep;
new Chart(document.getElementById("sweepChart"), {
  type: "bar",
  data: {
    labels: sw.lookbacks.map(lb => lb + "-day"),
    datasets: [
      { label: "Achievable revenue (£/MW/yr)", data: sw.perMw,
        backgroundColor: ACCENT, yAxisID: "y", borderWidth: 0,
        categoryPercentage: 0.6, barPercentage: 0.9 },
      { label: "Capture rate (%)", data: sw.capturePct,
        type: "line", yAxisID: "y1",
        borderColor: ORANGE, backgroundColor: "transparent",
        pointBackgroundColor: ORANGE, pointRadius: 6, pointHoverRadius: 8,
        borderWidth: 2.5, tension: 0.3 },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
      tooltip: { callbacks: {
        label: (c) => c.dataset.yAxisID === "y"
          ? gbp(c.raw) + "/MW/yr"
          : c.raw.toFixed(1) + "% of oracle ceiling"
      }}
    },
    scales: {
      x: { grid: { display: false } },
      y:  { position: "left",  grid: { color: LINE }, beginAtZero: true,
            title: { display: true, text: "£/MW/yr", color: ACCENT },
            ticks: { font: { family: MONO }, callback: (v) => "£" + (v/1000) + "k" } },
      y1: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true,
            max: 60,
            title: { display: true, text: "Capture rate (%)", color: ORANGE },
            ticks: { font: { family: MONO }, callback: (v) => v + "%" } }
    }
  }
});

// ── Chart 6: monthly oracle vs achieved ─────────────────────────────────────
const mo = DATA.monthly;
new Chart(document.getElementById("monthlyChart"), {
  type: "bar",
  data: {
    labels: mo.months,
    datasets: [
      { label: "Oracle (perfect foresight)", data: mo.oracle,
        backgroundColor: RED + "cc", yAxisID: "y", borderWidth: 0,
        categoryPercentage: 0.75, barPercentage: 0.55 },
      { label: "Achieved (7-day forecast)", data: mo.achieved,
        backgroundColor: ACCENT + "cc", yAxisID: "y", borderWidth: 0,
        categoryPercentage: 0.75, barPercentage: 0.55 },
      { label: "Capture rate (%)", data: mo.capturePct,
        type: "line", yAxisID: "y1",
        borderColor: ORANGE, backgroundColor: "transparent",
        pointBackgroundColor: ORANGE, pointRadius: 4, pointHoverRadius: 6,
        borderWidth: 2, tension: 0.3 },
    ]
  },
  options: {
    responsive: true, maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 12, padding: 14, font: { size: 12 } } },
      tooltip: { callbacks: {
        label: (c) => c.dataset.yAxisID === "y"
          ? c.dataset.label + ": " + gbp(c.raw) + "/MW"
          : c.raw.toFixed(1) + "% capture"
      }}
    },
    scales: {
      x: { grid: { display: false } },
      y:  { position: "left",  grid: { color: LINE }, beginAtZero: true,
            title: { display: true, text: "£/MW (monthly)", color: MUTED },
            ticks: { font: { family: MONO }, callback: (v) => "£" + (v/1000) + "k" } },
      y1: { position: "right", grid: { drawOnChartArea: false }, beginAtZero: true,
            max: 100,
            title: { display: true, text: "Capture rate (%)", color: ORANGE },
            ticks: { font: { family: MONO }, callback: (v) => v + "%" } }
    }
  }
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
