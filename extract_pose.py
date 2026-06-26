"""
extract_pose.py
---------------
Extracts MediaPipe Pose landmarks from a video file frame by frame
and writes them to data/pose_data.csv.

    python extract_pose.py <video_path> [skip_frames]

Example:
    python extract_pose.py forehand.mp4
    python extract_pose.py forehand.mp4 2     # process every 2nd frame
"""

import os
import sys

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd

# ── Output ────────────────────────────────────────────────────────────────────

POSE_FILE = os.path.join("data", "pose_data.csv")

# ── Core functions ────────────────────────────────────────────────────────────

def _process_frame(frame_rgb: np.ndarray, pose) -> dict | None:
    """
    Run MediaPipe Pose on a single RGB frame.
    Returns a flat dict of {x_0..x_32, y_0..y_32, z_0..z_32, visibility_0..32}
    or None if no pose is detected.
    """
    result = pose.process(frame_rgb)
    if not result.pose_landmarks:
        return None
    row: dict = {}
    for idx, lm in enumerate(result.pose_landmarks.landmark):
        row[f"x_{idx}"]          = lm.x
        row[f"y_{idx}"]          = lm.y
        row[f"z_{idx}"]          = lm.z
        row[f"visibility_{idx}"] = lm.visibility
    return row


def extract_pose_landmarks(
    video_path: str,
    output_csv: str = POSE_FILE,
    skip_frames: int = 1,
) -> pd.DataFrame:
    """
    Extract MediaPipe Pose landmarks for every skip_frames-th frame.

    Returns a DataFrame where each row is one processed frame, columns are:
      frame_idx, timestamp_sec, x_0..x_32, y_0..y_32, z_0..z_32, visibility_0..32
    Rows where no pose was detected are dropped silently.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps        = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total      = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx  = 0
    rows       = []

    mp_pose = mp.solutions.pose
    with mp_pose.Pose(
        static_image_mode=False,
        model_complexity=1,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
    ) as pose:
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            if frame_idx % skip_frames == 0:
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                row = _process_frame(frame_rgb, pose)
                if row is not None:
                    row["frame_idx"]     = frame_idx
                    row["timestamp_sec"] = frame_idx / fps
                    rows.append(row)
            frame_idx += 1
            if frame_idx % 100 == 0:
                print(f"  Processed {frame_idx}/{total} frames...", flush=True)

    cap.release()

    if not rows:
        raise RuntimeError("No pose landmarks detected in any frame. Check video quality and camera angle.")

    # Reorder columns: metadata first, then landmarks
    df = pd.DataFrame(rows)
    meta_cols = ["frame_idx", "timestamp_sec"]
    lm_cols   = [c for c in df.columns if c not in meta_cols]
    df = df[meta_cols + sorted(lm_cols)]
    df.attrs["fps"] = fps

    os.makedirs(os.path.dirname(output_csv) or ".", exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Extracted {len(df)} frames from {os.path.basename(video_path)} → {output_csv}")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python extract_pose.py <video_path> [skip_frames]", file=sys.stderr)
        sys.exit(1)

    video_path  = sys.argv[1]
    skip_frames = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    extract_pose_landmarks(video_path, skip_frames=skip_frames)


if __name__ == "__main__":
    main()
