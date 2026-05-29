# -*- coding: cp1254 -*-

import json
import sys
from pathlib import Path

import pandas as pd


DEFAULT_DATASET_NAME = "BackOnly_Test_04"

if len(sys.argv) > 1:
    DATASET_NAME = sys.argv[1]
else:
    DATASET_NAME = DEFAULT_DATASET_NAME

if len(sys.argv) > 2:
    TARGET_FRAME = int(sys.argv[2])
else:
    TARGET_FRAME = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FOLDER = PROJECT_ROOT / "outputs" / DATASET_NAME
CALIBRATION_FOLDER = PROJECT_ROOT / "outputs" / "calibration"

PAIR_CSV_PATH = OUTPUT_FOLDER / "back_pair_results.csv"
PATTERN_SUMMARY_PATH = OUTPUT_FOLDER / "back_pattern_decode_summary.json"
DISTANCE_MODEL_PATH = CALIBRATION_FOLDER / "distance_model_summary.json"

if not PAIR_CSV_PATH.exists():
    raise FileNotFoundError(f"Pair CSV not found: {PAIR_CSV_PATH}")

if not DISTANCE_MODEL_PATH.exists():
    raise FileNotFoundError(f"Distance model summary not found: {DISTANCE_MODEL_PATH}")


FACE_ID = "BACK"
EXPECTED_PATTERN = "11001100"

MIN_PATTERN_ACCURACY = 0.95
MIN_PIXEL_DISTANCE = 20.0


def load_json(path):
    if not path.exists():
        return None

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def estimate_distance(pixel_distance, model):
    if pixel_distance is None or pixel_distance <= 0:
        return None

    A = model["A"]
    B = model["B"]

    return A / pixel_distance + B


def distance_confidence(pixel_distance, pattern_accuracy):
    if pixel_distance is None or pixel_distance <= 0:
        return 0.0

    # Current heuristic from calibration tests:
    # >= 70 px: stable close/mid range
    # 50-70 px: still reliable
    # 35-50 px: usable but noisier
    # < 35 px: far/noisy range
    if pixel_distance >= 70:
        pixel_conf = 1.0
    elif pixel_distance >= 50:
        pixel_conf = 0.85
    elif pixel_distance >= 35:
        pixel_conf = 0.65
    else:
        pixel_conf = 0.40

    return round(pixel_conf * pattern_accuracy, 3)


def is_valid_row(row, pattern_accuracy):
    required_columns = [
        "bit",
        "pair_found",
        "candidate_count",
        "pixel_distance",
        "mid_x",
        "mid_y",
        "error_x",
        "error_y",
        "ray_x",
        "ray_y",
        "ray_z",
    ]

    for col in required_columns:
        if col not in row.index:
            return False

    if int(row["bit"]) != 1:
        return False

    if int(row["pair_found"]) != 1:
        return False

    # For the current back-only pipeline, only exactly two candidates are trusted.
    # This prevents false positives or split blobs from being selected as a wrong pair.
    if int(row["candidate_count"]) != 2:
        return False

    if pd.isna(row["pixel_distance"]):
        return False

    if float(row["pixel_distance"]) < MIN_PIXEL_DISTANCE:
        return False

    if pattern_accuracy < MIN_PATTERN_ACCURACY:
        return False

    return True


def select_observation_row(valid_df, target_frame):
    """
    If target_frame is None, select the first valid row.
    If target_frame is given, select the valid row closest to that frame.
    """
    if len(valid_df) == 0:
        return None, None

    if target_frame is None:
        selected = valid_df.iloc[0]
        selected_frame_delta = 0
        return selected, selected_frame_delta

    valid_df = valid_df.copy()
    valid_df["frame_delta"] = (valid_df["frame"] - target_frame).abs()

    selected = valid_df.sort_values(["frame_delta", "frame"]).iloc[0]
    selected_frame_delta = int(selected["frame_delta"])

    return selected, selected_frame_delta


df = pd.read_csv(PAIR_CSV_PATH)

pattern_summary = load_json(PATTERN_SUMMARY_PATH)

if pattern_summary is None:
    pattern_accuracy = 1.0
    bit_error_rate = 0.0
    bit_error_count = 0
else:
    pattern_accuracy = float(pattern_summary.get("global_accuracy", 0.0))
    bit_error_rate = float(pattern_summary.get("bit_error_rate", 1.0))
    bit_error_count = int(pattern_summary.get("bit_error_count", -1))

distance_model = load_json(DISTANCE_MODEL_PATH)

valid_mask = df.apply(lambda row: is_valid_row(row, pattern_accuracy), axis=1)
valid_df = df[valid_mask].copy()

selected_row, selected_frame_delta = select_observation_row(valid_df, TARGET_FRAME)

if selected_row is None:
    packet = {
        "dataset": DATASET_NAME,
        "requested_frame": TARGET_FRAME,
        "selected_frame_delta": None,
        "frame": None,
        "valid": False,
        "face_id": FACE_ID,
        "reason": "No valid observation row found.",
        "pattern": EXPECTED_PATTERN,
        "pattern_accuracy": pattern_accuracy,
        "bit_error_count": bit_error_count,
        "bit_error_rate": bit_error_rate,
    }
else:
    row = selected_row

    pixel_distance = float(row["pixel_distance"])
    estimated_distance = estimate_distance(pixel_distance, distance_model)
    dist_conf = distance_confidence(pixel_distance, pattern_accuracy)

    packet = {
        "dataset": DATASET_NAME,
        "requested_frame": TARGET_FRAME,
        "selected_frame_delta": selected_frame_delta,
        "frame": int(row["frame"]),
        "valid": True,

        "face_id": FACE_ID,
        "pattern": EXPECTED_PATTERN,
        "pattern_accuracy": pattern_accuracy,
        "bit_error_count": bit_error_count,
        "bit_error_rate": bit_error_rate,

        "pair_found": bool(row["pair_found"]),
        "candidate_count": int(row["candidate_count"]),

        "led1_px": [
            float(row["led1_x"]),
            float(row["led1_y"]),
        ],
        "led2_px": [
            float(row["led2_x"]),
            float(row["led2_y"]),
        ],

        "midpoint_px": [
            float(row["mid_x"]),
            float(row["mid_y"]),
        ],

        "error_norm": [
            float(row["error_x"]),
            float(row["error_y"]),
        ],

        "ray_cam": [
            float(row["ray_x"]),
            float(row["ray_y"]),
            float(row["ray_z"]),
        ],

        "pixel_distance": pixel_distance,
        "estimated_distance": estimated_distance,
        "distance_confidence": dist_conf,

        "image_size": [
            int(row["image_width"]),
            int(row["image_height"]),
        ],
    }


if TARGET_FRAME is None:
    packet_filename = "observation_packet_sample.json"
else:
    packet_filename = f"observation_packet_frame_{TARGET_FRAME}.json"

packet_path = OUTPUT_FOLDER / packet_filename

with open(packet_path, "w", encoding="utf-8") as f:
    json.dump(packet, f, indent=4)

print("Dataset:", DATASET_NAME)

if TARGET_FRAME is None:
    print("Requested frame: None, using first valid observation.")
else:
    print("Requested frame:", TARGET_FRAME)

print("Observation packet:")
print(json.dumps(packet, indent=4))

print("\nPacket saved:", packet_path)