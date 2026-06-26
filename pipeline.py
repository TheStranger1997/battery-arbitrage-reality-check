"""
pipeline.py
-----------
Orchestrates the full tennis swing analysis pipeline for a given video.
Writes all outputs to results/<analysis_id>/ and returns a summary dict
that can be serialised directly as a JSON API response.

Used by app.py; also importable from the CLI scripts.
"""

import os

import pandas as pd

from extract_pose import extract_pose_landmarks
from analyse_swing import detect_contact_frame, compute_metrics
from score_swing import (
    IDEAL_RANGES,
    score_all_metrics,
    overall_score as compute_overall,
    _rating,
    _feedback,
)
from build_swing_report import build_report

RESULTS_DIR = "results"


def run_analysis(video_path: str, analysis_id: str) -> dict:
    """
    Run extract → analyse → score → report for video_path.
    All files land in results/<analysis_id>/.
    Returns a JSON-serialisable summary dict.
    """
    work_dir = os.path.join(RESULTS_DIR, analysis_id)
    os.makedirs(work_dir, exist_ok=True)

    pose_csv    = os.path.join(work_dir, "pose_data.csv")
    results_csv = os.path.join(work_dir, "swing_results.csv")
    scores_csv  = os.path.join(work_dir, "swing_scores.csv")
    report_html = os.path.join(work_dir, "report.html")

    # 1. Extract pose landmarks from video
    extract_pose_landmarks(video_path, output_csv=pose_csv)

    # 2. Compute biomechanical metrics at the contact frame
    df = pd.read_csv(pose_csv)
    df.attrs["fps"] = 30.0
    contact_frame = detect_contact_frame(df)
    metrics = compute_metrics(df, contact_frame)
    pd.DataFrame([metrics]).to_csv(results_csv, index=False)

    # 3. Score each metric against ideal ranges
    scores_dict = score_all_metrics(metrics)
    overall = compute_overall(scores_dict)

    score_records = []
    for metric, (lo, hi, unit, _desc) in IDEAL_RANGES.items():
        if metric not in metrics:
            continue
        value = float(metrics[metric])
        sc = scores_dict.get(metric, 0.0)
        score_records.append({
            "metric":     metric,
            "value":      round(value, 3),
            "ideal_low":  lo,
            "ideal_high": hi,
            "unit":       unit,
            "score":      sc,
            "rating":     _rating(sc),
            "feedback":   _feedback(metric, value, lo, hi),
        })
    pd.DataFrame(score_records).to_csv(scores_csv, index=False)

    # 4. Build self-contained HTML report
    build_report(results_csv, scores_csv, report_html)

    return {
        "analysis_id":    analysis_id,
        "overall_score":  overall,
        "contact_time_sec": metrics.get("contact_time_sec"),
        "scores":         score_records,
        "report_url":     f"/report/{analysis_id}",
    }
