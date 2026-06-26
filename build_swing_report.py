"""
build_swing_report.py
---------------------
Builds a self-contained HTML report from CSV outputs of
analyse_swing.py and score_swing.py.

    python build_swing_report.py
"""

import json
import os
import webbrowser

import pandas as pd

RESULTS_FILE = os.path.join("data", "swing_results.csv")
SCORES_FILE  = os.path.join("data", "swing_scores.csv")
OUTPUT_HTML  = "swing_report.html"


def load_results() -> dict:
    return pd.read_csv(RESULTS_FILE).iloc[0].to_dict()


def load_scores() -> list[dict]:
    return pd.read_csv(SCORES_FILE).to_dict(orient="records")


def build_radar_payload(scores: list[dict]) -> dict:
    label_map = {
        "elbow_angle_deg": "Elbow Angle",
        "shoulder_hip_diff_deg": "Kinetic Chain",
        "knee_bend_deg": "Knee Bend",
        "wrist_height_ratio": "Wrist Height",
        "body_lean_deg": "Body Lean",
    }
    labels, values = [], []
    for row in scores:
        if row["metric"] in label_map:
            labels.append(label_map[row["metric"]])
            values.append(row["score"])
    return {"labels": labels, "values": values}


def build_report(
    results_file: str = RESULTS_FILE,
    scores_file:  str = SCORES_FILE,
    output_html:  str = OUTPUT_HTML,
) -> str:
    results = pd.read_csv(results_file).iloc[0].to_dict()
    scores  = pd.read_csv(scores_file).to_dict(orient="records")
    radar   = build_radar_payload(scores)
    overall = round(sum(r["score"] for r in scores) / len(scores), 1) if scores else 0
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps({"results": results, "scores": scores, "radar": radar, "overall": overall}))
    with open(output_html, "w", encoding="utf-8") as f:
        f.write(html)
    return output_html


def main() -> None:
    results = load_results()
    scores  = load_scores()
    radar   = build_radar_payload(scores)
    overall = round(sum(r["score"] for r in scores) / len(scores), 1) if scores else 0
    html = HTML_TEMPLATE.replace("__DATA__", json.dumps({"results": results, "scores": scores, "radar": radar, "overall": overall}))
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Built {OUTPUT_HTML}  (overall score: {overall}/100)")
    webbrowser.open(OUTPUT_HTML)


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
  th { text-align: left; color: #888; font-weight: 500; padding: 6px 8px; border-bottom: 1px solid #2a2d3a; }
  td { padding: 10px 8px; border-bottom: 1px solid #1e2130; vertical-align: middle; }
  .bar-wrap { width: 120px; background: #2a2d3a; border-radius: 4px; height: 8px; display: inline-block; }
  .bar-fill { height: 8px; border-radius: 4px; }
  .rating-E { color: #3a9d5d; font-weight: 600; }
  .rating-G { color: #4ea3d4; font-weight: 600; }
  .rating-F { color: #e08a1e; font-weight: 600; }
  .rating-P { color: #c0392b; font-weight: 600; }
  .coaching { background: #1a1d27; border-radius: 10px; padding: 20px; margin-bottom: 24px; }
  .coaching h2 { font-size: 1rem; font-weight: 600; margin-bottom: 12px; color: #ccc; }
  .fix-item { background: #0f1117; border-left: 3px solid #e08a1e; padding: 10px 14px; margin-bottom: 10px; border-radius: 4px; }
  .fix-item .metric-name { font-weight: 600; font-size: 0.8rem; color: #e08a1e; text-transform: uppercase; margin-bottom: 4px; }
  .fix-item .fix-text { font-size: 0.85rem; color: #ccc; }
  footer { font-size: 0.75rem; color: #555; margin-top: 16px; }
</style>
</head>
<body>
<h1>Tennis Swing Analysis</h1>
<p class="subtitle">AI-powered biomechanical feedback &mdash; forehand drive</p>
<div class="kpi-row" id="kpis"></div>
<div class="grid">
  <div class="card"><h2>Metric Scores</h2><canvas id="radarChart"></canvas></div>
  <div class="card"><h2>All Metrics</h2>
    <table id="metricsTable"><thead><tr><th>Metric</th><th>Value</th><th>Ideal</th><th>Score</th><th>Rating</th></tr></thead><tbody></tbody></table>
  </div>
</div>
<div class="coaching" id="coaching"><h2>Priority Fixes</h2></div>
<footer>Generated by build_swing_report.py</footer>
<script>
const DATA = __DATA__;
function scoreColor(s){return s>=90?"#3a9d5d":s>=70?"#4ea3d4":s>=50?"#e08a1e":"#c0392b";}
function ratingClass(r){return{"Excellent":"rating-E","Good":"rating-G","Fair":"rating-F","Poor":"rating-P"}[r]||""}
function labelFor(m){return{"elbow_angle_deg":"Elbow Angle","shoulder_hip_diff_deg":"Kinetic Chain","knee_bend_deg":"Knee Bend","wrist_height_ratio":"Wrist Height","body_lean_deg":"Body Lean","shoulder_angle_deg":"Shoulder Angle","hip_angle_deg":"Hip Angle","contact_time_sec":"Contact Time","swing_tempo_frac":"Swing Tempo"}[m]||m;}
const kpiEl=document.getElementById("kpis"),r=DATA.results;
[{label:"Overall Score",value:DATA.overall,unit:"/ 100",style:`color:${scoreColor(DATA.overall)}`},{label:"Contact Time",value:r.contact_time_sec?r.contact_time_sec.toFixed(2):"—",unit:"sec"},{label:"Elbow Angle",value:r.elbow_angle_deg?r.elbow_angle_deg.toFixed(1):"—",unit:"°"},{label:"Kinetic Chain",value:r.shoulder_hip_diff_deg?r.shoulder_hip_diff_deg.toFixed(1):"—",unit:"°"}].forEach(k=>{kpiEl.innerHTML+=`<div class="kpi"><div class="label">${k.label}</div><div class="value" style="${k.style||''}">${k.value}</div><div class="unit">${k.unit}</div></div>`;});
new Chart(document.getElementById("radarChart"),{type:"radar",data:{labels:DATA.radar.labels,datasets:[{label:"Your Score",data:DATA.radar.values,backgroundColor:"rgba(78,163,212,0.2)",borderColor:"#4ea3d4",pointBackgroundColor:"#4ea3d4"}]},options:{scales:{r:{min:0,max:100,ticks:{color:"#666",stepSize:25},grid:{color:"#2a2d3a"},pointLabels:{color:"#ccc"}}},plugins:{legend:{display:false}}}});
const tbody=document.querySelector("#metricsTable tbody");DATA.scores.forEach(s=>{const c=scoreColor(s.score);tbody.innerHTML+=`<tr><td>${labelFor(s.metric)}</td><td>${parseFloat(s.value).toFixed(2)} <span style="color:#666">${s.unit||""}</span></td><td style="color:#666">${s.ideal_low}–${s.ideal_high}</td><td><span class="bar-wrap"><span class="bar-fill" style="width:${s.score}%;background:${c}"></span></span><span style="margin-left:6px;font-size:0.8rem">${s.score}</span></td><td class="${ratingClass(s.rating)}">${s.rating}</td></tr><tr><td colspan="5" style="color:#777;font-size:0.78rem;padding:2px 8px 10px">${s.feedback}</td></tr>`;});
const coachingEl=document.getElementById("coaching");const worst=[...DATA.scores].sort((a,b)=>a.score-b.score).slice(0,2);worst.length===0?coachingEl.innerHTML+="<p style='color:#888'>No scored metrics available.</p>":worst.forEach(s=>{coachingEl.innerHTML+=`<div class="fix-item"><div class="metric-name">${labelFor(s.metric)} &mdash; ${s.score}/100</div><div class="fix-text">${s.feedback}</div></div>`;});
</script></body></html>"""


if __name__ == "__main__":
    main()
