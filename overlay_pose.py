"""
overlay_pose.py
---------------
Draws the MediaPipe pose skeleton onto the original video frames using the
pre-extracted data/pose_data.csv.  The contact frame (from data/swing_results.csv)
is highlighted in orange with an annotation banner.

    python overlay_pose.py <video_path> [output_path]

Example:
    python overlay_pose.py forehand.mp4
    python overlay_pose.py forehand.mp4 forehand_annotated.mp4
"""

import os
import sys

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd

# ── Inputs / outputs ──────────────────────────────────────────────────────────

POSE_FILE    = os.path.join("data", "pose_data.csv")
RESULTS_FILE = os.path.join("data", "swing_results.csv")

# ── Drawing constants ─────────────────────────────────────────────────────────

COLOR_BONE_NORMAL  = (0, 220, 100)    # green
COLOR_BONE_CONTACT = (0, 165, 255)    # orange
COLOR_JOINT        = (255, 255, 255)  # white
COLOR_CONTACT_FILL = (0, 120, 200)    # blue-orange fill on contact joints
BONE_THICKNESS     = 2
JOINT_RADIUS       = 5
MIN_VISIBILITY     = 0.5              # skip landmarks below this confidence

# Use MediaPipe's canonical connection list (pairs of landmark indices)
_POSE_CONNECTIONS = list(mp.solutions.pose.POSE_CONNECTIONS)


# ── Skeleton drawing ──────────────────────────────────────────────────────────

def draw_skeleton(
    frame: np.ndarray,
    row: pd.Series,
    is_contact: bool,
    frame_w: int,
    frame_h: int,
) -> None:
    """Draw pose skeleton in-place on frame using normalised landmark coords."""
    bone_color  = COLOR_BONE_CONTACT if is_contact else COLOR_BONE_NORMAL
    joint_color = COLOR_CONTACT_FILL if is_contact else COLOR_JOINT

    # Connections (lines)
    for (a, b) in _POSE_CONNECTIONS:
        vis_a = row.get(f"visibility_{a}", 0)
        vis_b = row.get(f"visibility_{b}", 0)
        if vis_a < MIN_VISIBILITY or vis_b < MIN_VISIBILITY:
            continue
        x1 = int(row[f"x_{a}"] * frame_w)
        y1 = int(row[f"y_{a}"] * frame_h)
        x2 = int(row[f"x_{b}"] * frame_w)
        y2 = int(row[f"y_{b}"] * frame_h)
        cv2.line(frame, (x1, y1), (x2, y2), bone_color, BONE_THICKNESS, cv2.LINE_AA)

    # Joints (circles)
    for i in range(33):
        vis = row.get(f"visibility_{i}", 0)
        if vis < MIN_VISIBILITY:
            continue
        x = int(row[f"x_{i}"] * frame_w)
        y = int(row[f"y_{i}"] * frame_h)
        cv2.circle(frame, (x, y), JOINT_RADIUS, joint_color, -1, cv2.LINE_AA)
        cv2.circle(frame, (x, y), JOINT_RADIUS, bone_color, 1, cv2.LINE_AA)


def _contact_banner(frame: np.ndarray, frame_w: int) -> None:
    """Overlay an 'CONTACT' banner at the top of the contact frame."""
    banner_h = 36
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (frame_w, banner_h), (0, 100, 200), -1)
    cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
    cv2.putText(
        frame, "  CONTACT FRAME",
        (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA,
    )


def _frame_counter(frame: np.ndarray, frame_idx: int, total: int, frame_h: int) -> None:
    text = f"Frame {frame_idx}/{total}"
    cv2.putText(
        frame, text,
        (8, frame_h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA,
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def overlay_pose(
    video_path: str,
    output_path: str | None = None,
    pose_csv: str = POSE_FILE,
    results_csv: str = RESULTS_FILE,
) -> str:
    """
    Annotate video_path with skeleton overlays; return path to output video.

    Frames without detected pose are passed through unchanged.
    The contact frame gets an orange skeleton + banner.
    """
    if not os.path.exists(pose_csv):
        raise FileNotFoundError(f"Pose data not found: {pose_csv}. Run extract_pose.py first.")

    # Load pose data indexed by frame_idx for O(1) lookup
    pose_df = pd.read_csv(pose_csv).set_index("frame_idx")

    # Load contact frame if available
    contact_frame: int | None = None
    if os.path.exists(results_csv):
        res = pd.read_csv(results_csv)
        if "contact_frame" in res.columns and len(res) > 0:
            contact_frame = int(res.iloc[0]["contact_frame"])

    # Open input video
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps    = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total  = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Default output path
    if output_path is None:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_annotated.mp4"

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out = cv2.VideoWriter(output_path, fourcc, fps, (frame_w, frame_h))

    frame_idx   = 0
    annotated   = 0
    skipped     = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        is_contact = (frame_idx == contact_frame)

        if frame_idx in pose_df.index:
            row = pose_df.loc[frame_idx]
            draw_skeleton(frame, row, is_contact, frame_w, frame_h)
            annotated += 1
        else:
            skipped += 1

        if is_contact:
            _contact_banner(frame, frame_w)

        _frame_counter(frame, frame_idx, total, frame_h)
        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()

    print(f"Annotated {annotated} frames, {skipped} without pose data.")
    if contact_frame is not None:
        print(f"Contact frame {contact_frame} highlighted in orange.")
    print(f"Saved → {output_path}")
    return output_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python overlay_pose.py <video_path> [output_path]", file=sys.stderr)
        sys.exit(1)

    video_path  = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    overlay_pose(video_path, output_path)


if __name__ == "__main__":
    main()
