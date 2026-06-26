"""
build_swing_report.py
---------------------
Builds a single, self-contained swing_report.html from the CSV outputs of
analyse_swing.py and score_swing.py. Data is embedded as JSON so the file
opens in any browser with no server and no network access.

    python build_swing_report.py
"""

import json
import os
import webbrowser

import pandas as pd

# ── Inputs / outputs ──────────────────────────────────────────────────────────

RESULTS_FILE = os.path.join("data", "swing_results.csv")
SCORES_FILE  = os.path.join("data", "swing_scores.csv")
OUTPUT_HTML  = "swing_report.html"

# ── Data loaders ──────────────────────────────────────────────────────────────

def load_results() -> dict:
    df = pd.read_csv(RESULTS_FILE)
    return df.iloc[0].to_dict()


def load_scores() -> list[dict]:
    df = pd.read_csv(SCORES_FILE)
    return df.to_dict(orient="records")


def build_radar_payload(scores: list[dict]) -> dict:
    labels, values = [], []
    label_map = {
        "elbow_angle_deg":       "Elbow Angle",
        "shoulder_hip_diff_deg": "Kinetic Chain",
        "knee_bend_deg":         "Knee Bend",
        "wrist_height_ratio":    "Wrist Height",
        "body_lean_deg":         "Body Lean",
    }
    for row in scores:
        metric = row["metric"]
        if metric in label_map:
            labels.append(label_map[metric])
            values.append(row["score"])
    return {"labels": labels, "values": values}


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    results = load_results()
    scores  = load_scores()
    radar   = build_radar_payload(scores)

    overall = round(sum(r["score"] for r in scores) / len(scores), 1) if scores else 0

    payload = {
        "results": results,
        "scores":  scores,
        "radar":   radar,
        "overall": overall,
    }

    html = HTML_TEMPLATE.replace("__DATA__", json.dumps(payload))
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Built {OUTPUT_HTML}  (overall score: {overall}/100)")
    webbrowser.open(OUTPUT_HTML)


# ── HTML template ─────────────────────────────────────────────────────────────

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Tennis Swing Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
         background: #0f1117; color: #e0e0e0; padding: 24px; }
  h1 { font-size: 1.6rem; font-weight: 700; margin-bottom: 4px; }
  .subtitle { color: #888; font-size: 0.85rem; margin-bottom: 28px; }
  .kpi-row { display: flex; gap: 16px; margin-bottom: 32px; flex-wrap: wrap; }
  .kpi { background: #1a1d27; border-radius: 10px; padding: 18px 22px; min-width: 160px; flex: 1; }
  .kpi .label { font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: .05em; }
  .kpi .value { font-size: 2rem; font-weight: 700; margin-top: 4px; }
  .kpi .unit  { font-size: 0.8rem; color: #888; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; margin-bottom: 32px; }
  @media (max-width: 700px) { .grid { grid-template-columns: 1fr; } }
  .card { background: #1a1d27; border-radius: 10px; padding: 20px; }
  .card h2 { font-size: 1rem; font-weight: 600; margin-bottom: 16px; color: #ccc; }
  canvas { max-height: 300px; }
  table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
  th { text-align: left; color: #888; font-weight: 500; padding: 6px 8px;
       border-bottom: 1px solid #2a2d3a; }
  td { padding: 10px 8px; border-bottom: 1px solid #1e2130; vertical-align: middle; }
  .bar-wrap { width: 120px; background: #2a2d3a; border-radius: 4px; height: 8px; display: inline-block; }
  .bar-fill { height: 8px; border-radius: 4px; }
  .rating-E { color: #3a9d5d; font-weight: 600; }
  .rating-G { color: #4ea3d4; font-weight: 600; }
  .rating-F { color: #e08a1e; font-weight: 600; }
  .rating-P { color: #c0392b; font-weight: 600; }
  .coaching { background: #1a1d27; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  .coaching h2 { font-size: 1rem; font-weight: 600; margin-bottom: 12px; color: #ccc; }
  .fix-item { background: #0f1117; border-left: 3px solid #e08a1e;
              padding: 10px 14px; margin-bottom: 10px; border-radius: 4px; }
  .fix-item .metric-name { font-weight: 600; font-size: 0.8rem; color: #e08a1e;
                            text-transform: uppercase; margin-bottom: 4px; }
  .fix-item .fix-text { font-size: 0.85rem; color: #ccc; }
  footer { font-size: 0.75rem; color: #555; margin-top: 16px; }
  .score-ring { font-size: 3rem; font-weight: 800; }
</style>
</head>
<body>
<h1>Tennis Swing Analysis</h1>
<p class="subtitle">AI-powered biomechanical feedback &mdash; forehand drive</p>

<div class="kpi-row" id="kpis"></div>

<div class="grid">
  <div class="card">
    <h2>Metric Scores</h2>
    <canvas id="radarChart"></canvas>
  </div>
  <div class="card">
    <h2>All Metrics</h2>
    <table id="metricsTable">
      <thead><tr>
        <th>Metric</th><th>Value</th><th>Ideal</th><th>Score</th><th>Rating</th>
      </tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<div class="coaching" id="coaching">
  <h2>Priority Fixes</h2>
</div>

<footer>Generated by build_swing_report.py &mdash; data: analyse_swing.py + score_swing.py</footer>

<script>
const DATA = __DATA__;

function scoreColor(s) {
  if (s >= 90) return "#3a9d5d";
  if (s >= 70) return "#4ea3d4";
  if (s >= 50) return "#e08a1e";
  return "#c0392b";
}

function ratingClass(r) {
  return { "Excellent": "rating-E", "Good": "rating-G", "Fair": "rating-F", "Poor": "rating-P" }[r] || "";
}

function labelFor(metric) {
  const m = {
    "elbow_angle_deg":       "Elbow Angle",
    "shoulder_hip_diff_deg": "Kinetic Chain",
    "knee_bend_deg":         "Knee Bend",
    "wrist_height_ratio":    "Wrist Height",
    "body_lean_deg":         "Body Lean",
    "shoulder_angle_deg":    "Shoulder Angle",
    "hip_angle_deg":         "Hip Angle",
    "contact_time_sec":      "Contact Time",
    "swing_tempo_frac":      "Swing Tempo",
  };
  return m[metric] || metric;
}

// KPIs
const kpiEl = document.getElementById("kpis");
const r = DATA.results;
const kpis = [
  { label: "Overall Score", value: DATA.overall, unit: "/ 100", style: `color:${scoreColor(DATA.overall)}` },
  { label: "Contact Time",  value: r.contact_time_sec ? r.contact_time_sec.toFixed(2) : "—", unit: "sec" },
  { label: "Elbow Angle",   value: r.elbow_angle_deg  ? r.elbow_angle_deg.toFixed(1)  : "—", unit: "°"   },
  { label: "Kinetic Chain", value: r.shoulder_hip_diff_deg ? r.shoulder_hip_diff_deg.toFixed(1) : "—", unit: "°" },
];
kpis.forEach(k => {
  kpiEl.innerHTML += `<div class="kpi">
    <div class="label">${k.label}</div>
    <div class="value" style="${k.style||''}">${k.value}</div>
    <div class="unit">${k.unit}</div>
  </div>`;
});

// Radar chart
const radar = DATA.radar;
new Chart(document.getElementById("radarChart"), {
  type: "radar",
  data: {
    labels: radar.labels,
    datasets: [{
      label: "Your Score",
      data: radar.values,
      backgroundColor: "rgba(78,163,212,0.2)",
      borderColor: "#4ea3d4",
      pointBackgroundColor: "#4ea3d4",
    }]
  },
  options: {
    scales: { r: { min: 0, max: 100, ticks: { color: "#666", stepSize: 25 },
                   grid: { color: "#2a2d3a" }, pointLabels: { color: "#ccc" } } },
    plugins: { legend: { display: false } },
  }
});

// Metrics table
const tbody = document.querySelector("#metricsTable tbody");
DATA.scores.forEach(s => {
  const pct = s.score;
  const color = scoreColor(pct);
  tbody.innerHTML += `<tr>
    <td>${labelFor(s.metric)}</td>
    <td>${parseFloat(s.value).toFixed(2)} <span style="color:#666">${s.unit||""}</span></td>
    <td style="color:#666">${s.ideal_low}–${s.ideal_high}</td>
    <td>
      <span class="bar-wrap"><span class="bar-fill" style="width:${pct}%;background:${color}"></span></span>
      <span style="margin-left:6px;font-size:0.8rem">${pct}</span>
    </td>
    <td class="${ratingClass(s.rating)}">${s.rating}</td>
  </tr>
  <tr><td colspan="5" style="color:#777;font-size:0.78rem;padding:2px 8px 10px">${s.feedback}</td></tr>`;
});

// Coaching: show the 2 lowest-scoring scored metrics
const coachingEl = document.getElementById("coaching");
const sorted = [...DATA.scores].sort((a,b) => a.score - b.score);
const worst = sorted.slice(0, 2);
if (worst.length === 0) {
  coachingEl.innerHTML += "<p style='color:#888'>No scored metrics available.</p>";
} else {
  worst.forEach(s => {
    coachingEl.innerHTML += `<div class="fix-item">
      <div class="metric-name">${labelFor(s.metric)} &mdash; ${s.score}/100</div>
      <div class="fix-text">${s.feedback}</div>
    </div>`;
  });
}
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
