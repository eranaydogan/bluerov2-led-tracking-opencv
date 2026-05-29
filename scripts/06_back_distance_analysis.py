# -*- coding: cp1254 -*-

import pandas as pd
from pathlib import Path

DATASET_NAME = "BackOnly_Test_06"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FOLDER = PROJECT_ROOT / "outputs" / DATASET_NAME

csv_path = OUTPUT_FOLDER / "back_pair_results.csv"

if not csv_path.exists():
    raise FileNotFoundError(f"CSV not found: {csv_path}")

df = pd.read_csv(csv_path)

print("Total rows:", len(df))

# Only use frames where LEDs are ON and a pair was found
valid = df[
    (df["bit"] == 1) &
    (df["pair_found"] == 1) &
    (df["candidate_count"] == 2) &
    (df["pixel_distance"].notna())
].copy()

print("Valid ON + pair frames:", len(valid))

if len(valid) == 0:
    raise RuntimeError("No valid pixel distance data found.")

# Basic stats before filtering
print("\nRaw valid distance statistics:")
print("Mean:", valid["pixel_distance"].mean())
print("Median:", valid["pixel_distance"].median())
print("Min:", valid["pixel_distance"].min())
print("Max:", valid["pixel_distance"].max())
print("Std:", valid["pixel_distance"].std())

# IQR outlier filtering
q1 = valid["pixel_distance"].quantile(0.25)
q3 = valid["pixel_distance"].quantile(0.75)
iqr = q3 - q1

lower_bound = q1 - 1.5 * iqr
upper_bound = q3 + 1.5 * iqr

filtered = valid[
    (valid["pixel_distance"] >= lower_bound) &
    (valid["pixel_distance"] <= upper_bound)
].copy()

print("\nIQR filter bounds:")
print("Lower:", lower_bound)
print("Upper:", upper_bound)

print("\nFiltered distance statistics:")
print("Filtered frame count:", len(filtered))
print("Mean:", filtered["pixel_distance"].mean())
print("Median:", filtered["pixel_distance"].median())
print("Min:", filtered["pixel_distance"].min())
print("Max:", filtered["pixel_distance"].max())
print("Std:", filtered["pixel_distance"].std())

# Save cleaned result
output_csv = OUTPUT_FOLDER / "back_pair_distance_filtered.csv"
filtered.to_csv(output_csv, index=False)

print("\nFiltered CSV saved:", output_csv)

# Print a small sample
print("\nSample filtered rows:")
print(filtered[["frame", "bit", "pair_found", "candidate_count", "pixel_distance"]].head(20))
