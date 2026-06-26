"""
analyse_swing.py
----------------
Computes biomechanical metrics from MediaPipe pose landmarks.
No MediaPipe or OpenCV required at import time — reads the pre-extracted
data/pose_data.csv produced by extract_pose.py.

    python analyse_swing.py      # → data/swing_results.csv
"""

import math
import os
import sys

import pandas as pd

# ── Inputs / outputs ──────────────────────────────────────────────────────────

POSE_FILE    = os.path.join("data", "pose_data.csv")
RESULTS_FILE = os.path.join("data", "swing_results.csv")

# ── MediaPipe landmark indices ────────────────────────────────────────────────

LM = {
    "LEFT_SHOULDER":  11,
    "RIGHT_SHOULDER": 12,
    "LEFT_ELBOW":     13,
    "RIGHT_ELBOW":    14,
    "LEFT_WRIST":     15,
    "RIGHT_WRIST":    16,
    "LEFT_HIP":       23,
    "RIGHT_HIP":      24,
    "LEFT_KNEE":      25,
    "RIGHT_KNEE":     26,
    "LEFT_ANKLE":     27,
    "RIGHT_ANKLE":    28,
}


# ── Geometry helpers ──────────────────────────────────────────────────────────

def compute_angle(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    """
    Interior angle at point B formed by A–B–C, in degrees [0, 180].
    Uses the arccos of the normalised dot product of vectors BA and BC.
    """
    bax, bay = a[0] - b[0], a[1] - b[1]
    bcx, bcy = c[0] - b[0], c[1] - b[1]
    dot  = bax * bcx + bay * bcy
    mag_ba = math.hypot(bax, bay)
    mag_bc = math.hypot(bcx, bcy)
    if mag_ba < 1e-9 or mag_bc < 1e-9:
        return 0.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


def _xy(row: pd.Series, idx: int) -> tuple[float, float]:
    """Return (x, y) for landmark index idx from a pose row."""
    return float(row[f"x_{idx}"]), float(row[f"y_{idx}"])


# ── Contact frame detection ───────────────────────────────────────────────────

def detect_contact_frame(
    df: pd.DataFrame,
    wrist_landmark: int = 16,
    smooth_window: int = 5,
) -> int:
    """
    Return the frame index of estimated racket contact using peak wrist velocity
    as a proxy. Velocity = per-frame Euclidean distance moved by the wrist in
    normalised image coordinates, smoothed with a rolling mean.
    """
    xs = df[f"x_{wrist_landmark}"].values
    ys = df[f"y_{wrist_landmark}"].values
    dx = [0.0] + [xs[i] - xs[i-1] for i in range(1, len(xs))]
    dy = [0.0] + [ys[i] - ys[i-1] for i in range(1, len(ys))]
    velocity = pd.Series([math.hypot(x, y) for x, y in zip(dx, dy)])
    smoothed = velocity.rolling(smooth_window, center=True, min_periods=1).mean()
    return int(smoothed.idxmax())


# ── Metric computation ────────────────────────────────────────────────────────

def compute_metrics(
    df: pd.DataFrame,
    contact_frame: int,
    handedness: str = "right",
) -> dict:
    """
    Compute biomechanical metrics at the contact frame.

    handedness: "right" or "left" (selects dominant-arm landmark indices).
    Returns a dict of metric_name → float value in natural units.
    """
    if handedness == "right":
        shoulder = LM["RIGHT_SHOULDER"]
        elbow    = LM["RIGHT_ELBOW"]
        wrist    = LM["RIGHT_WRIST"]
        hip_dom  = LM["RIGHT_HIP"]
        hip_off  = LM["LEFT_HIP"]
        knee     = LM["RIGHT_KNEE"]
        ankle    = LM["RIGHT_ANKLE"]
        sh_dom   = LM["RIGHT_SHOULDER"]
        sh_off   = LM["LEFT_SHOULDER"]
    else:
        shoulder = LM["LEFT_SHOULDER"]
        elbow    = LM["LEFT_ELBOW"]
        wrist    = LM["LEFT_WRIST"]
        hip_dom  = LM["LEFT_HIP"]
        hip_off  = LM["RIGHT_HIP"]
        knee     = LM["LEFT_KNEE"]
        ankle    = LM["LEFT_ANKLE"]
        sh_dom   = LM["LEFT_SHOULDER"]
        sh_off   = LM["RIGHT_SHOULDER"]

    row = df.iloc[contact_frame]
    fps = df.attrs.get("fps", 30.0)

    # 1. Elbow angle (shoulder, elbow, wrist)
    elbow_angle = compute_angle(_xy(row, shoulder), _xy(row, elbow), _xy(row, wrist))

    # 2. Shoulder line angle from horizontal
    sx_dom, sy_dom = _xy(row, sh_dom)
    sx_off, sy_off = _xy(row, sh_off)
    shoulder_angle = math.degrees(math.atan2(sy_dom - sy_off, sx_dom - sx_off))

    # 3. Hip line angle from horizontal
    hx_dom, hy_dom = _xy(row, hip_dom)
    hx_off, hy_off = _xy(row, hip_off)
    hip_angle = math.degrees(math.atan2(hy_dom - hy_off, hx_dom - hx_off))

    # 4. Kinetic chain separation
    shoulder_hip_diff = shoulder_angle - hip_angle

    # 5. Knee bend (hip, knee, ankle)
    knee_bend = compute_angle(_xy(row, hip_dom), _xy(row, knee), _xy(row, ankle))

    # 6. Wrist height relative to shoulder
    _, y_sh = _xy(row, shoulder)
    _, y_wr = _xy(row, wrist)
    y_hip_mid = (float(row[f"y_{hip_dom}"]) + float(row[f"y_{hip_off}"])) / 2
    torso_height = abs(y_sh - y_hip_mid) or 1e-9
    # y increases downward in image coords; positive ratio = wrist below shoulder
    # (wrist below shoulder → y_wr > y_sh)
    wrist_height_ratio = (y_wr - y_sh) / torso_height

    # 7. Body lean (torso midline from vertical)
    sh_mid_x = (sx_dom + sx_off) / 2
    sh_mid_y = (sy_dom + sy_off) / 2
    hip_mid_x = (hx_dom + hx_off) / 2
    hip_mid_y = (hy_dom + hy_off) / 2
    # atan2 with flipped y-axis (image coords, y down)
    body_lean = math.degrees(math.atan2(sh_mid_x - hip_mid_x, hip_mid_y - sh_mid_y))

    # 8. Timing
    contact_time = contact_frame / fps
    swing_tempo  = contact_frame / max(len(df) - 1, 1)

    return {
        "contact_frame":        contact_frame,
        "contact_time_sec":     round(contact_time, 3),
        "elbow_angle_deg":      round(elbow_angle, 2),
        "shoulder_angle_deg":   round(shoulder_angle, 2),
        "hip_angle_deg":        round(hip_angle, 2),
        "shoulder_hip_diff_deg":round(shoulder_hip_diff, 2),
        "knee_bend_deg":        round(knee_bend, 2),
        "wrist_height_ratio":   round(wrist_height_ratio, 4),
        "body_lean_deg":        round(body_lean, 2),
        "swing_tempo_frac":     round(swing_tempo, 4),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not os.path.exists(POSE_FILE):
        print(f"Error: {POSE_FILE} not found. Run extract_pose.py first.", file=sys.stderr)
        sys.exit(1)

    df = pd.read_csv(POSE_FILE)
    df.attrs["fps"] = 30.0  # default; extract_pose.py can embed this if needed

    contact = detect_contact_frame(df)
    metrics = compute_metrics(df, contact)

    results_df = pd.DataFrame([metrics])
    os.makedirs("data", exist_ok=True)
    results_df.to_csv(RESULTS_FILE, index=False)

    print(f"Contact frame: {contact} ({metrics['contact_time_sec']:.2f}s)")
    for k, v in metrics.items():
        print(f"  {k:30s}  {v}")
    print(f"\nResults saved to {RESULTS_FILE}")


if __name__ == "__main__":
    main()
