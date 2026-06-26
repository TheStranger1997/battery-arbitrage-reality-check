"""
test_swing.py
-------------
Lightweight unit tests for the tennis swing analysis pipeline.
No video or downloaded data needed — every test uses synthetic landmark data.

    python test_swing.py        # exits 0 if all pass, 1 otherwise
"""

import sys
import math
import pandas as pd

import analyse_swing as sw
import score_swing as sc

EPS = 0.1
_failures = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f"  ({detail})" if detail and not condition else ""))
    if not condition:
        _failures.append(name)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pose_df(n_frames: int = 30, wrist_peak_frame: int = 15) -> pd.DataFrame:
    """
    Build a synthetic pose DataFrame with n_frames rows.
    The right wrist (landmark 16) moves fastest at wrist_peak_frame.
    All other landmarks are stationary at biomechanically plausible positions.
    """
    rows = []
    for i in range(n_frames):
        # Wrist x increases slowly except at peak_frame where it jumps
        wrist_x = 0.5 + i * 0.005
        if i == wrist_peak_frame:
            wrist_x += 0.15  # large jump → peak velocity here

        row = {f"x_{k}": 0.5 for k in range(33)}
        row.update({f"y_{k}": 0.5 for k in range(33)})
        row.update({f"z_{k}": 0.0 for k in range(33)})
        row.update({f"visibility_{k}": 1.0 for k in range(33)})
        row["frame_idx"]     = i
        row["timestamp_sec"] = i / 30.0

        # Plausible skeleton (right-handed player, side-on view)
        # Shoulders: left(11) left of right(12)
        row["x_11"] = 0.35; row["y_11"] = 0.35   # LEFT_SHOULDER
        row["x_12"] = 0.55; row["y_12"] = 0.35   # RIGHT_SHOULDER
        # Elbows
        row["x_13"] = 0.30; row["y_13"] = 0.50   # LEFT_ELBOW
        row["x_14"] = 0.70; row["y_14"] = 0.50   # RIGHT_ELBOW
        # Wrists
        row["x_15"] = 0.25; row["y_15"] = 0.60
        row["x_16"] = wrist_x; row["y_16"] = 0.55  # RIGHT_WRIST (moves)
        # Hips
        row["x_23"] = 0.38; row["y_23"] = 0.65   # LEFT_HIP
        row["x_24"] = 0.52; row["y_24"] = 0.65   # RIGHT_HIP
        # Knees
        row["x_25"] = 0.36; row["y_25"] = 0.80
        row["x_26"] = 0.54; row["y_26"] = 0.80   # RIGHT_KNEE
        # Ankles
        row["x_27"] = 0.34; row["y_27"] = 0.95
        row["x_28"] = 0.54; row["y_28"] = 0.95   # RIGHT_ANKLE
        rows.append(row)
    return pd.DataFrame(rows)


def _straight_arm_df() -> pd.DataFrame:
    """Pose where right shoulder, elbow, wrist are collinear (straight arm)."""
    df = _make_pose_df(n_frames=5, wrist_peak_frame=2)
    for i in range(5):
        df.at[i, "x_12"] = 0.3; df.at[i, "y_12"] = 0.4   # RIGHT_SHOULDER
        df.at[i, "x_14"] = 0.5; df.at[i, "y_14"] = 0.4   # RIGHT_ELBOW
        df.at[i, "x_16"] = 0.7; df.at[i, "y_16"] = 0.4   # RIGHT_WRIST (same y)
    return df


# ── Tests ─────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Running swing analysis sanity tests...\n")

    # 1. compute_angle — right angle
    angle = sw.compute_angle((0, 0), (1, 0), (1, 1))
    check("compute_angle: right angle = 90°",
          abs(angle - 90.0) < EPS, f"got {angle:.2f}")

    # 2. compute_angle — collinear points → 180°
    angle = sw.compute_angle((0, 0), (1, 0), (2, 0))
    check("compute_angle: collinear = 180°",
          abs(angle - 180.0) < EPS, f"got {angle:.2f}")

    # 3. compute_angle — 45° angle
    # A=(1,0), B=(0,0), C=(1,1): BA=(1,0), BC=(1,1), dot=1, cos=1/√2 → 45°
    angle = sw.compute_angle((1, 0), (0, 0), (1, 1))
    check("compute_angle: 45° angle",
          abs(angle - 45.0) < EPS, f"got {angle:.2f}")

    # 4. score_metric — inside ideal range → 100
    s = sc.score_metric(155.0, 140, 170)
    check("score_metric: inside ideal → 100",
          abs(s - 100.0) < EPS, f"got {s}")

    # 5. score_metric — far outside range → 0
    s = sc.score_metric(5.0, 140, 170)
    check("score_metric: far outside → 0",
          s == 0.0, f"got {s}")

    # 6. score_metric — decreases monotonically as value moves away from ideal
    scores_below = [sc.score_metric(140 - d, 140, 170) for d in [0, 5, 10, 20, 50]]
    monotone = all(scores_below[i] >= scores_below[i+1] for i in range(len(scores_below)-1))
    check("score_metric: monotone decay below ideal",
          monotone, str(scores_below))

    # 7. detect_contact_frame — finds peak-velocity frame
    df = _make_pose_df(n_frames=30, wrist_peak_frame=15)
    contact = sw.detect_contact_frame(df, wrist_landmark=16, smooth_window=3)
    check("detect_contact_frame: finds wrist peak",
          abs(contact - 15) <= 2, f"expected ~15, got {contact}")

    # 8. detect_contact_frame — flat trajectory (no crash)
    flat_df = _make_pose_df(n_frames=10, wrist_peak_frame=99)  # no spike
    for i in range(10):
        flat_df.at[i, "x_16"] = 0.5  # static wrist
    try:
        _ = sw.detect_contact_frame(flat_df)
        check("detect_contact_frame: flat trajectory (no crash)", True)
    except Exception as e:
        check("detect_contact_frame: flat trajectory (no crash)", False, str(e))

    # 9. overall_score — equals mean of input scores
    scores = {"a": 80.0, "b": 60.0, "c": 100.0, "d": 40.0, "e": 70.0}
    expected = sum(scores.values()) / len(scores)
    got = sc.overall_score(scores)
    check("overall_score: equals mean of inputs",
          abs(got - expected) < EPS, f"expected {expected}, got {got}")

    # 10. compute_metrics — returns all required keys
    df = _make_pose_df(n_frames=30, wrist_peak_frame=15)
    required = {
        "contact_frame", "contact_time_sec", "elbow_angle_deg",
        "shoulder_angle_deg", "hip_angle_deg", "shoulder_hip_diff_deg",
        "knee_bend_deg", "wrist_height_ratio", "body_lean_deg", "swing_tempo_frac",
    }
    metrics = sw.compute_metrics(df, contact_frame=15)
    missing = required - set(metrics.keys())
    check("compute_metrics: returns all required keys",
          len(missing) == 0, f"missing: {missing}")

    # 11. Elbow angle ~180° for a straight arm
    straight_df = _straight_arm_df()
    metrics = sw.compute_metrics(straight_df, contact_frame=2)
    check("elbow_angle_deg ~180 for straight arm",
          abs(metrics["elbow_angle_deg"] - 180.0) < EPS,
          f"got {metrics['elbow_angle_deg']:.2f}")

    # 12. Wrist height ratio negative when wrist is above shoulder
    df = _make_pose_df(n_frames=5, wrist_peak_frame=2)
    for i in range(5):
        df.at[i, "y_12"] = 0.5   # RIGHT_SHOULDER lower in image
        df.at[i, "y_16"] = 0.2   # RIGHT_WRIST higher in image (smaller y = higher up)
    metrics = sw.compute_metrics(df, contact_frame=2)
    check("wrist_height_ratio < 0 when wrist is above shoulder",
          metrics["wrist_height_ratio"] < 0,
          f"got {metrics['wrist_height_ratio']:.4f}")

    # 13. score_all_metrics — all values in [0, 100]
    result_dict = {
        "elbow_angle_deg":       155.0,
        "shoulder_hip_diff_deg": 10.0,
        "knee_bend_deg":         160.0,
        "wrist_height_ratio":    0.3,
        "body_lean_deg":         5.0,
    }
    all_scores = sc.score_all_metrics(result_dict)
    in_range = all(0.0 <= v <= 100.0 for v in all_scores.values())
    check("score_all_metrics: all values in [0, 100]",
          in_range, str(all_scores))

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if _failures:
        print(f"FAILED: {len(_failures)} test(s): {', '.join(_failures)}")
        sys.exit(1)
    else:
        print(f"All 13 tests passed.")


if __name__ == "__main__":
    main()
