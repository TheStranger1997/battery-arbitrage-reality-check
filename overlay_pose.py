"""
overlay_pose.py
---------------
Draws the MediaPipe skeleton onto original video frames using pre-extracted
data/pose_data.csv. The contact frame is highlighted in orange.

    python overlay_pose.py <video_path> [output_path]
"""

import os
import sys

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd

POSE_FILE    = os.path.join("data", "pose_data.csv")
RESULTS_FILE = os.path.join("data", "swing_results.csv")

COLOR_BONE_NORMAL  = (0, 220, 100)
COLOR_BONE_CONTACT = (0, 165, 255)
COLOR_JOINT        = (255, 255, 255)
COLOR_CONTACT_FILL = (0, 120, 200)
BONE_THICKNESS = 2
JOINT_RADIUS   = 5
MIN_VISIBILITY = 0.5
_POSE_CONNECTIONS = list(mp.solutions.pose.POSE_CONNECTIONS)


def draw_skeleton(frame, row, is_contact, frame_w, frame_h):
    bone_color  = COLOR_BONE_CONTACT if is_contact else COLOR_BONE_NORMAL
    joint_color = COLOR_CONTACT_FILL if is_contact else COLOR_JOINT
    for (a, b) in _POSE_CONNECTIONS:
        if row.get(f"visibility_{a}", 0) < MIN_VISIBILITY or row.get(f"visibility_{b}", 0) < MIN_VISIBILITY:
            continue
        cv2.line(frame,
                 (int(row[f"x_{a}"] * frame_w), int(row[f"y_{a}"] * frame_h)),
                 (int(row[f"x_{b}"] * frame_w), int(row[f"y_{b}"] * frame_h)),
                 bone_color, BONE_THICKNESS, cv2.LINE_AA)
    for i in range(33):
        if row.get(f"visibility_{i}", 0) < MIN_VISIBILITY:
            continue
        x, y = int(row[f"x_{i}"] * frame_w), int(row[f"y_{i}"] * frame_h)
        cv2.circle(frame, (x, y), JOINT_RADIUS, joint_color, -1, cv2.LINE_AA)
        cv2.circle(frame, (x, y), JOINT_RADIUS, bone_color, 1, cv2.LINE_AA)


def overlay_pose(video_path, output_path=None, pose_csv=POSE_FILE, results_csv=RESULTS_FILE):
    if not os.path.exists(pose_csv):
        raise FileNotFoundError(f"Pose data not found: {pose_csv}. Run extract_pose.py first.")

    pose_df = pd.read_csv(pose_csv).set_index("frame_idx")
    contact_frame = None
    if os.path.exists(results_csv):
        res = pd.read_csv(results_csv)
        if "contact_frame" in res.columns and len(res) > 0:
            contact_frame = int(res.iloc[0]["contact_frame"])

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"Cannot open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total   = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if output_path is None:
        base, _ = os.path.splitext(video_path)
        output_path = f"{base}_annotated.mp4"

    out = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (frame_w, frame_h))
    frame_idx = annotated = skipped = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        is_contact = (frame_idx == contact_frame)
        if frame_idx in pose_df.index:
            draw_skeleton(frame, pose_df.loc[frame_idx], is_contact, frame_w, frame_h)
            annotated += 1
        else:
            skipped += 1
        if is_contact:
            overlay = frame.copy()
            cv2.rectangle(overlay, (0, 0), (frame_w, 36), (0, 100, 200), -1)
            cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
            cv2.putText(frame, "  CONTACT FRAME", (8, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.putText(frame, f"Frame {frame_idx}/{total}", (8, frame_h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (160, 160, 160), 1, cv2.LINE_AA)
        out.write(frame)
        frame_idx += 1

    cap.release()
    out.release()
    print(f"Annotated {annotated} frames, {skipped} without pose data. Saved → {output_path}")
    return output_path


def main():
    if len(sys.argv) < 2:
        print("Usage: python overlay_pose.py <video_path> [output_path]", file=sys.stderr)
        sys.exit(1)
    overlay_pose(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)


if __name__ == "__main__":
    main()
