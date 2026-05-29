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


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_FOLDER = PROJECT_ROOT / "outputs" / DATASET_NAME

csv_path = OUTPUT_FOLDER / "back_pair_results.csv"

if not csv_path.exists():
    raise FileNotFoundError(f"CSV not found: {csv_path}")


FPS = 60
BIT_DURATION_SECONDS = 0.1
FRAMES_PER_BIT = int(FPS * BIT_DURATION_SECONDS)

EXPECTED_PATTERN = "11001100"


def cyclic_shifts(pattern):
    shifts = []

    for i in range(len(pattern)):
        shifts.append(pattern[i:] + pattern[:i])

    return shifts


def best_pattern_window_match(decoded, expected):
    """
    Finds the best local 8-bit window match.

    This answers:
    'Can I find the expected pattern anywhere in the decoded sequence?'

    This was the old confidence metric.
    """
    expected_shifts = cyclic_shifts(expected)
    pattern_len = len(expected)

    best_score = -1
    best_shift = None
    best_start = None
    best_window = None

    if len(decoded) < pattern_len:
        return best_score, best_shift, best_start, best_window

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


def repeated_pattern_for_length(pattern, length):
    """
    Repeats a pattern until the requested length is reached.
    """
    if len(pattern) == 0:
        raise ValueError("Pattern length cannot be zero.")

    repeated = (pattern * ((length // len(pattern)) + 1))[:length]
    return repeated


def global_repeated_pattern_match(decoded, expected):
    """
    Finds the best global repeated-pattern alignment.

    This answers:
    'Across the whole decoded sequence, how well does it match
    the repeated expected pattern?'

    This is more useful than only checking one good 8-bit window.
    """
    expected_shifts = cyclic_shifts(expected)

    best_accuracy = -1
    best_shift = None
    best_expected_repeated = None
    best_error_positions = None

    for shift in expected_shifts:
        expected_repeated = repeated_pattern_for_length(shift, len(decoded))

        error_positions = [
            i for i, (a, b) in enumerate(zip(decoded, expected_repeated))
            if a != b
        ]

        bit_error_count = len(error_positions)

        if len(decoded) == 0:
            accuracy = 0
        else:
            accuracy = 1 - (bit_error_count / len(decoded))

        if accuracy > best_accuracy:
            best_accuracy = accuracy
            best_shift = shift
            best_expected_repeated = expected_repeated
            best_error_positions = error_positions

    bit_error_count = len(best_error_positions)

    if len(decoded) == 0:
        bit_error_rate = 1
    else:
        bit_error_rate = bit_error_count / len(decoded)

    return {
        "global_accuracy": best_accuracy,
        "bit_error_count": bit_error_count,
        "bit_error_rate": bit_error_rate,
        "best_global_shift": best_shift,
        "expected_repeated": best_expected_repeated,
        "error_positions": best_error_positions,
    }


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

window_score, window_shift, window_start, window = best_pattern_window_match(
    decoded_string,
    EXPECTED_PATTERN
)

global_match = global_repeated_pattern_match(
    decoded_string,
    EXPECTED_PATTERN
)

print("Dataset:", DATASET_NAME)
print("FPS:", FPS)
print("Bit duration:", BIT_DURATION_SECONDS)
print("Frames per bit:", FRAMES_PER_BIT)
print("Expected pattern:", EXPECTED_PATTERN)
print("Total frame count:", len(frame_bits))
print("Total decoded bit count:", len(decoded_bits))

print("\nDecoded bits:")
print(decoded_string)

print("\nBest local 8-bit pattern match:")
print("Local score:", window_score)
print("Best start index:", window_start)
print("Decoded window:", window)
print("Matched expected shift:", window_shift)

print("\nGlobal repeated-pattern match:")
print("Global accuracy:", global_match["global_accuracy"])
print("Bit error count:", global_match["bit_error_count"])
print("Bit error rate:", global_match["bit_error_rate"])
print("Best global shift:", global_match["best_global_shift"])

if global_match["bit_error_count"] > 0:
    print("First error positions:", global_match["error_positions"][:20])
else:
    print("First error positions: none")

if global_match["global_accuracy"] >= 0.95:
    print("\nResult: BACK pattern is globally reliable.")
elif global_match["global_accuracy"] >= 0.80:
    print("\nResult: BACK pattern is detected, but there are noticeable bit errors.")
else:
    print("\nResult: BACK pattern is NOT globally reliable.")


summary = {
    "dataset": DATASET_NAME,
    "fps": FPS,
    "bit_duration_seconds": BIT_DURATION_SECONDS,
    "frames_per_bit": FRAMES_PER_BIT,
    "expected_pattern": EXPECTED_PATTERN,
    "total_frame_count": len(frame_bits),
    "total_decoded_bit_count": len(decoded_bits),
    "decoded_bits": decoded_string,
    "local_best_score": window_score,
    "local_best_start_index": window_start,
    "local_decoded_window": window,
    "local_matched_expected_shift": window_shift,
    "global_accuracy": global_match["global_accuracy"],
    "bit_error_count": global_match["bit_error_count"],
    "bit_error_rate": global_match["bit_error_rate"],
    "best_global_shift": global_match["best_global_shift"],
    "error_positions": global_match["error_positions"],
}

summary_path = OUTPUT_FOLDER / "back_pattern_decode_summary.json"

with open(summary_path, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=4)

print("\nSummary JSON saved:", summary_path)