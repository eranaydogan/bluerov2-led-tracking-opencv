# -*- coding: cp1254 -*-

import pandas as pd
from pathlib import Path

DATASET_NAME = "BackOnly_Test_01"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FOLDER = PROJECT_ROOT / "outputs" / DATASET_NAME

csv_path = OUTPUT_FOLDER / "back_pair_results.csv"

if not csv_path.exists():
    raise FileNotFoundError(f"CSV not found: {csv_path}")



FPS = 60
BIT_DURATION_SECONDS = 0.1
FRAMES_PER_BIT = int(FPS * BIT_DURATION_SECONDS)

EXPECTED_PATTERN = "11001100"



df = pd.read_csv(csv_path)

frame_bits = df["bit"].astype(int).tolist()

decoded_bits = []

for start in range(0, len(frame_bits), FRAMES_PER_BIT):
    group = frame_bits[start:start + FRAMES_PER_BIT]

    if len(group) < FRAMES_PER_BIT:
        break

    ones = sum(group)
    zeros = len(group) - ones

    decoded_bit = 1 if ones >= zeros else 0
    decoded_bits.append(decoded_bit)

decoded_string = "".join(str(b) for b in decoded_bits)


def cyclic_shifts(pattern):
    shifts = []
    for i in range(len(pattern)):
        shifts.append(pattern[i:] + pattern[:i])
    return shifts


def best_pattern_match(decoded, expected):
    expected_shifts = cyclic_shifts(expected)
    pattern_len = len(expected)

    best_score = -1
    best_shift = None
    best_start = None
    best_window = None

    for start in range(0, len(decoded) - pattern_len + 1):
        window = decoded[start:start + pattern_len]

        for shift in expected_shifts:
            matches = sum(1 for a, b in zip(window, shift) if a == b)
            score = matches / pattern_len

            if score > best_score:
                best_score = score
                best_shift = shift
                best_start = start
                best_window = window

    return best_score, best_shift, best_start, best_window


score, shift, start, window = best_pattern_match(decoded_string, EXPECTED_PATTERN)

print("FPS:", FPS)
print("Bit duration:", BIT_DURATION_SECONDS)
print("Frames per bit:", FRAMES_PER_BIT)
print("Expected pattern:", EXPECTED_PATTERN)
print("Total frame count:", len(frame_bits))
print("Total decoded bit count:", len(decoded_bits))

print("\nDecoded bits:")
print(decoded_string)

print("\nBest pattern match:")
print("Score:", score)
print("Best start index:", start)
print("Decoded window:", window)
print("Matched expected shift:", shift)

if score >= 0.75:
    print("\nResult: BACK pattern is detected with acceptable confidence.")
else:
    print("\nResult: BACK pattern is NOT confidently detected.")
