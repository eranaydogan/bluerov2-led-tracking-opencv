# -*- coding: cp1254 -*-

import json
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_FOLDER = PROJECT_ROOT / "outputs"
MODEL_OUTPUT_FOLDER = OUTPUT_FOLDER / "calibration"

MODEL_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)


# Current calibration points from back-only tests.
# distance_unit = camera-root distance in Unity units.
# median_px = filtered median pixel distance from 06_back_distance_analysis.py
CALIBRATION_POINTS = [
    {
        "test_name": "BackOnly_Test_01",
        "distance_unit": 1.47,
        "median_px": 168.0,
        "pattern_accuracy": 1.00,
        "filtered_std": 0.61,
        "notes": "Initial static reference",
    },
    {
        "test_name": "BackOnly_Test_02",
        "distance_unit": 2.00,
        "median_px": 118.0,
        "pattern_accuracy": 1.00,
        "filtered_std": 0.002,
        "notes": "Camera moved backward; Y/Z changed slightly",
    },
    {
        "test_name": "BackOnly_Test_03",
        "distance_unit": 2.50,
        "median_px": 92.00543462209176,
        "pattern_accuracy": 1.00,
        "filtered_std": 0.74,
        "notes": "Camera moved backward; Y/Z changed slightly",
    },
    {
        "test_name": "BackOnly_Test_04",
        "distance_unit": 3.00,
        "median_px": 73.06161783043132,
        "pattern_accuracy": 1.00,
        "filtered_std": 0.82,
        "notes": "Camera moved only along X axis; Y/Z fixed",
    },
    {
        "test_name": "BackOnly_Test_05",
        "distance_unit": 4.00,
        "median_px": 53.0,
        "pattern_accuracy": 1.00,
        "filtered_std": 0.67,
        "notes": "Camera moved only along X axis; Y/Z fixed",
    },
    {
        "test_name": "BackOnly_Test_06",
        "distance_unit": 5.00,
        "median_px": 37.0,
        "pattern_accuracy": 0.99,
        "filtered_std": 2.24,
        "notes": "Far-range boundary test",
    },
]


def fit_inverse_model(points):
    """
    Fits:

        distance = A * (1 / pixel_distance) + B

    This is a simple inverse-distance model.
    """
    px = np.array([p["median_px"] for p in points], dtype=float)
    distance = np.array([p["distance_unit"] for p in points], dtype=float)

    x = 1.0 / px

    # Linear least squares:
    # distance = A*x + B
    A, B = np.polyfit(x, distance, 1)

    return A, B


def estimate_distance(pixel_distance, A, B):
    if pixel_distance <= 0:
        return None

    return A * (1.0 / pixel_distance) + B


def evaluate_model(points, A, B):
    rows = []

    for p in points:
        predicted = estimate_distance(p["median_px"], A, B)
        error = p["distance_unit"] - predicted
        abs_error = abs(error)

        rows.append({
            "test_name": p["test_name"],
            "real_distance_unit": p["distance_unit"],
            "median_px": p["median_px"],
            "estimated_distance_unit": predicted,
            "error": error,
            "abs_error": abs_error,
            "pattern_accuracy": p["pattern_accuracy"],
            "filtered_std": p["filtered_std"],
            "notes": p["notes"],
        })

    df = pd.DataFrame(rows)

    mae = df["abs_error"].mean()
    rmse = np.sqrt((df["error"] ** 2).mean())

    return df, mae, rmse


def distance_confidence(pixel_distance, pattern_accuracy):
    """
    Simple heuristic confidence.

    The farther the robot is, the smaller the LED pair becomes.
    Below ~40 px, distance becomes noisier based on Test 06.
    """
    if pixel_distance <= 0:
        return 0.0

    if pixel_distance >= 70:
        pixel_conf = 1.0
    elif pixel_distance >= 50:
        pixel_conf = 0.85
    elif pixel_distance >= 35:
        pixel_conf = 0.65
    else:
        pixel_conf = 0.40

    return round(pixel_conf * pattern_accuracy, 3)


A, B = fit_inverse_model(CALIBRATION_POINTS)

df_eval, mae, rmse = evaluate_model(CALIBRATION_POINTS, A, B)

print("Distance model:")
print(f"estimated_distance = {A:.6f} / pixel_distance + {B:.6f}")

print("\nEvaluation:")
print(df_eval[[
    "test_name",
    "real_distance_unit",
    "median_px",
    "estimated_distance_unit",
    "error",
    "abs_error",
    "pattern_accuracy",
    "filtered_std",
]])

print("\nMean absolute error:", mae)
print("RMSE:", rmse)

# Example controller-side estimates
print("\nExample estimates:")
for px in [168, 118, 92, 73, 53, 37]:
    est = estimate_distance(px, A, B)
    conf = distance_confidence(px, 1.0)
    print(f"pixel_distance={px:>6} px -> estimated_distance={est:.3f} unit, confidence={conf}")


model_summary = {
    "model_type": "inverse_linear",
    "formula": "estimated_distance = A / pixel_distance + B",
    "A": A,
    "B": B,
    "mae": mae,
    "rmse": rmse,
    "calibration_points": CALIBRATION_POINTS,
}

summary_path = MODEL_OUTPUT_FOLDER / "distance_model_summary.json"
eval_csv_path = MODEL_OUTPUT_FOLDER / "distance_model_evaluation.csv"

with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(model_summary, f, indent=4)

df_eval.to_csv(eval_csv_path, index=False)

print("\nModel summary saved:", summary_path)
print("Evaluation CSV saved:", eval_csv_path)
