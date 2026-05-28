# -*- coding: cp1254 -*-

import pandas as pd
import os

FRAME_FOLDER = r"C:\Users\aydog\OneDrive\Desktop\OpenCV\Unity\SabitCamOn"

FPS = 60
BIT_DURATION_SECONDS = 0.1
FRAMES_PER_BIT = int(FPS * BIT_DURATION_SECONDS)

# Choose which signal to decode:
# "yellow_bit", "green_bit", "cyan_bit", "blue_bit", "combined_bit"
BIT_COLUMN = "combined_bit"

csv_path = os.path.join(FRAME_FOLDER, "led_detection_results.csv")

df = pd.read_csv(csv_path)

if BIT_COLUMN not in df.columns:
    raise ValueError(f"{BIT_COLUMN} column not found in CSV.")

frame_bits = df[BIT_COLUMN].astype(int).tolist()

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

print("FPS:", FPS)
print("Bit duration:", BIT_DURATION_SECONDS)
print("Frames per bit:", FRAMES_PER_BIT)
print("Decoded column:", BIT_COLUMN)
print("Total frame count:", len(frame_bits))
print("Total decoded bit count:", len(decoded_bits))
print("Decoded pattern:")
print(decoded_string)