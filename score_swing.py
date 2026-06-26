"""
score_swing.py
--------------
Scores computed tennis swing metrics against ideal biomechanical ranges.
No MediaPipe or OpenCV required — pure pandas/math.

    python score_swing.py        # reads data/swing_results.csv → data/swing_scores.csv
"""

import math
import os
import pandas as pd

# ── Inputs / outputs ──────────────────────────────────────────────────────────

RESULTS_FILE = os.path.join("data", "swing_results.csv")
SCORES_FILE  = os.path.join("data", "swing_scores.csv")

# ── Ideal ranges ──────────────────────────────────────────────────────────────
# (ideal_low, ideal_high, unit, description)
# Ranges sourced from USTA coaching guidelines and Landlinger et al. (2010)
# "Kinematic differences of elite and high-performance tennis forehand drives."

IDEAL_RANGES: dict[str, tuple] = {
    "elbow_angle_deg":       (140, 170, "degrees", "right elbow at contact"),
    "shoulder_hip_diff_deg": (20,  45,  "degrees", "kinetic chain separation"),
    "knee_bend_deg":         (120, 150, "degrees", "right knee bend"),
    "wrist_height_ratio":    (0.2, 0.5, "ratio",   "wrist below shoulder"),
    "body_lean_deg":         (-10, 15,  "degrees", "forward body lean"),
}

# Per-metric coaching sentences: (below_range, within_range, above_range)
_FEEDBACK: dict[str, tuple[str, str, str]] = {
    "elbow_angle_deg": (
        "Arm too bent at contact — extend more through the ball for power.",
        "Good arm extension at contact.",
        "Arm nearly locked out — keep a slight bend to protect the elbow.",
    ),
    "shoulder_hip_diff_deg": (
        "Hips and shoulders rotating together — load the hips earlier and let shoulders follow.",
        "Good kinetic chain separation.",
        "Over-rotating shoulders before contact — hold the shoulder turn until hips clear.",
    ),
    "knee_bend_deg": (
        "Knees too deeply bent — you are sitting too low and losing explosive drive.",
        "Good knee bend for leg drive.",
        "Legs too straight — bend the knees more to load the ground reaction force.",
    ),
    "wrist_height_ratio": (
        "Contact point too high — let the ball drop into the strike zone.",
        "Good contact height.",
        "Contact point too low — move into the ball earlier or adjust your ready position.",
    ),
    "body_lean_deg": (
        "Falling back at contact — drive through the ball with forward weight transfer.",
        "Good body lean at contact.",
        "Leaning too far forward — stay balanced over your base.",
    ),
}

_RATINGS = [(90, "Excellent"), (70, "Good"), (50, "Fair"), (0, "Poor")]


# ── Core functions ────────────────────────────────────────────────────────────

def score_metric(
    value: float,
    ideal_low: float,
    ideal_high: float,
    tolerance: float = 0.25,
) -> float:
    """
    Score a single metric 0–100.

    100 if value is within [ideal_low, ideal_high].
    Decays linearly to 0 over one ideal-range-width outside the boundary,
    scaled by `tolerance` (0.25 = decays to ~0 at 4× range-width outside).
    """
    if ideal_low <= value <= ideal_high:
        return 100.0
    range_width = ideal_high - ideal_low
    if range_width == 0:
        return 100.0 if math.isclose(value, ideal_low) else 0.0
    if value < ideal_low:
        excess = ideal_low - value
    else:
        excess = value - ideal_high
    decay_width = range_width / tolerance
    score = 100.0 * max(0.0, 1.0 - excess / decay_width)
    return round(score, 2)


def score_all_metrics(results: dict) -> dict[str, float]:
    """Apply score_metric to every key in IDEAL_RANGES."""
    return {
        metric: score_metric(results[metric], lo, hi)
        for metric, (lo, hi, *_) in IDEAL_RANGES.items()
        if metric in results
    }


def overall_score(scores: dict[str, float]) -> float:
    """Equally-weighted mean of all individual scores."""
    if not scores:
        return 0.0
    return round(sum(scores.values()) / len(scores), 1)


def _rating(score: float) -> str:
    for threshold, label in _RATINGS:
        if score >= threshold:
            return label
    return "Poor"


def _feedback(metric: str, value: float, ideal_low: float, ideal_high: float) -> str:
    below, within, above = _FEEDBACK.get(metric, ("Below ideal.", "Within ideal.", "Above ideal."))
    if value < ideal_low:
        return below
    if value > ideal_high:
        return above
    return within


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    results_df = pd.read_csv(RESULTS_FILE)
    row = results_df.iloc[0].to_dict()

    records = []
    for metric, (lo, hi, unit, desc) in IDEAL_RANGES.items():
        if metric not in row:
            continue
        value = float(row[metric])
        sc = score_metric(value, lo, hi)
        records.append({
            "metric":     metric,
            "value":      round(value, 3),
            "ideal_low":  lo,
            "ideal_high": hi,
            "unit":       unit,
            "score":      sc,
            "rating":     _rating(sc),
            "feedback":   _feedback(metric, value, lo, hi),
        })

    scores_df = pd.DataFrame(records)
    os.makedirs("data", exist_ok=True)
    scores_df.to_csv(SCORES_FILE, index=False)

    total = overall_score({r["metric"]: r["score"] for r in records})
    print(f"Overall score: {total}/100")
    for r in records:
        print(f"  {r['metric']:30s}  {r['value']:7.2f}  →  {r['score']:5.1f}  [{r['rating']}]  {r['feedback']}")
    print(f"\nScores saved to {SCORES_FILE}")


if __name__ == "__main__":
    main()
