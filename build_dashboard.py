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

PRICES_MONTH = os.path.join("data", "prices_2025-05.csv")
RESULTS_FILE = os.path.join("data", "arbitrage_results.csv")
OUTPUT_HTML  = "dashboard.html"

SAMPLE_DATE  = "2025-05-14"   # a Wednesday — typical weekday price shape
POWER_MW     = 50

# Number of half-hour periods charged / discharged per day (matches the model)
PERIODS_PER_CYCLE = 4

# Real-world GB BESS revenue stack (2025, £/MW/yr) — published benchmarks.
# Order: bottom → top of the stacked bar.
REVENUE_STACK = [
    ("Balancing Mechanism",          28_000, "#2f6f9f"),
    ("Frequency response (DC etc.)", 18_000, "#e08a1e"),
    ("Wholesale arbitrage (achieved)", 15_000, "#3a9d5d"),
    ("Capacity Market",               7_000, "#8a6bbf"),
    ("Other (DM, DR, triad)",         4_000, "#9c6b58"),
]
ACHIEVED_ARBITRAGE = 15_000   # the "achieved wholesale" line, for the KPIs


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


def build_kpis(daily_pnl: dict) -> dict:
    oracle_per_mw = sum(daily_pnl["net"]) / POWER_MW
    real_total    = sum(amount for _, amount, _ in REVENUE_STACK)
    pct_of_ceiling = round(ACHIEVED_ARBITRAGE / oracle_per_mw * 100)
    return {
        "oracle_per_mw":  round(oracle_per_mw),
        "achieved":       ACHIEVED_ARBITRAGE,
        "real_total":     real_total,
        "pct_of_ceiling": pct_of_ceiling,
    }


def build_stack() -> dict:
    return {
        "labels": [label for label, _, _ in REVENUE_STACK],
        "values": [amount for _, amount, _ in REVENUE_STACK],
        "colours": [colour for _, _, colour in REVENUE_STACK],
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


def main():
    sample_day = build_sample_day()
    daily_pnl  = build_daily_pnl()
    kpis       = build_kpis(daily_pnl)
    stack      = build_stack()
    duration   = build_duration()

    payload = {
        "sampleDate": SAMPLE_DATE,
        "sampleDay":  sample_day,
        "dailyPnl":   daily_pnl,
        "stack":      stack,
        "duration":   duration,
        "kpis":       kpis,
        "oracle":     kpis["oracle_per_mw"],
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

    abspath = os.path.abspath(OUTPUT_HTML)
    print(f"Built {OUTPUT_HTML}")
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

  @media (max-width: 720px) {
    .kpis { grid-template-columns: repeat(2, 1fr); }
    h1 { font-size: 32px; }
  }
</style>
</head>
<body>
<div class="wrap">

  <p class="eyebrow">GB power markets · weekend build</p>
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
      <div class="label">Achieved (implied)</div>
      <div class="value">£__KPI_ACHIEVED__</div>
      <div class="unit">/MW/yr · real capture</div>
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

  <div class="takeaway">
    <h2>Key takeaway</h2>
    <ul>
      <li>Achieved wholesale arbitrage is only <b>~__KPI_PCT__%</b> of the theoretical maximum. Perfect foresight is impossible, and the biggest price spikes are nearly unforecastable.</li>
      <li>Even the theoretical maximum (<b>£__KPI_ORACLE__</b>/MW/yr) sits <b>below</b> all-stream revenue (<b>£__KPI_REAL__</b>/MW/yr). Revenue stacking, not arbitrage, defines the GB BESS investment case.</li>
    </ul>
  </div>

  <footer>
    <div class="sources"><b>Data sources:</b> Elexon Insights API (half-hourly imbalance prices); NESO Capacity Market auction results; revenue-stack benchmarks from Modo Energy and Cornwall Insight. Real-world stack figures are published benchmarks, not computed from raw data.</div>
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
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
