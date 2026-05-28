# -*- coding: cp1254 -*-

import cv2
import glob
import os
import numpy as np
import pandas as pd

FRAME_FOLDER = r"C:\Users\aydog\OneDrive\Desktop\OpenCV\Unity\SabitCamOn"

FPS = 60
BIT_DURATION_SECONDS = 0.1
FRAMES_PER_BIT = int(FPS * BIT_DURATION_SECONDS)

frame_paths = sorted(glob.glob(os.path.join(FRAME_FOLDER, "*.png")))

if len(frame_paths) == 0:
    raise FileNotFoundError("PNG bulunamadı. FRAME_FOLDER yolunu kontrol et.")


# HSV values from detection/tuner
LOWER_YELLOW = np.array([15, 45, 180])
UPPER_YELLOW = np.array([45, 220, 255])

LOWER_GREEN = np.array([54, 83, 172])
UPPER_GREEN = np.array([95, 147, 226])

LOWER_CYAN = np.array([52, 0, 252])
UPPER_CYAN = np.array([107, 144, 255])

LOWER_BLUE = np.array([110, 70, 220])
UPPER_BLUE = np.array([135, 255, 255])


MIN_AREA = 35
MAX_AREA = 6000

# Area threshold for deciding ON/OFF per color
YELLOW_ON_THRESHOLD = 35
GREEN_ON_THRESHOLD = 35
CYAN_ON_THRESHOLD = 35
BLUE_ON_THRESHOLD = 35

records = []


def get_mask_area_and_count(mask):
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel_close)

    contours, _ = cv2.findContours(
        mask_clean,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    total_area = 0
    count = 0
    centers = []

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if area < MIN_AREA or area > MAX_AREA:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        cx = x + w // 2
        cy = y + h // 2

        total_area += area
        count += 1
        centers.append((cx, cy))

    return total_area, count, centers


for frame_index, path in enumerate(frame_paths):
    frame = cv2.imread(path)

    if frame is None:
        continue

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    yellow_mask = cv2.inRange(hsv, LOWER_YELLOW, UPPER_YELLOW)
    green_mask = cv2.inRange(hsv, LOWER_GREEN, UPPER_GREEN)
    cyan_mask = cv2.inRange(hsv, LOWER_CYAN, UPPER_CYAN)
    blue_mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)

    yellow_area, yellow_count, yellow_centers = get_mask_area_and_count(yellow_mask)
    green_area, green_count, green_centers = get_mask_area_and_count(green_mask)
    cyan_area, cyan_count, cyan_centers = get_mask_area_and_count(cyan_mask)
    blue_area, blue_count, blue_centers = get_mask_area_and_count(blue_mask)

    yellow_bit = 1 if yellow_area > YELLOW_ON_THRESHOLD else 0
    green_bit = 1 if green_area > GREEN_ON_THRESHOLD else 0
    cyan_bit = 1 if cyan_area > CYAN_ON_THRESHOLD else 0
    blue_bit = 1 if blue_area > BLUE_ON_THRESHOLD else 0

    combined_bit = 1 if (yellow_bit or green_bit or cyan_bit or blue_bit) else 0

    records.append({
        "frame": frame_index,
        "file": os.path.basename(path),

        "yellow_area": yellow_area,
        "yellow_count": yellow_count,
        "yellow_bit": yellow_bit,

        "green_area": green_area,
        "green_count": green_count,
        "green_bit": green_bit,

        "cyan_area": cyan_area,
        "cyan_count": cyan_count,
        "cyan_bit": cyan_bit,

        "blue_area": blue_area,
        "blue_count": blue_count,
        "blue_bit": blue_bit,

        "combined_bit": combined_bit,
    })


df = pd.DataFrame(records)

output_csv = os.path.join(FRAME_FOLDER, "led_detection_results.csv")
df.to_csv(output_csv, index=False)

print("CSV kaydedildi:", output_csv)
print("Toplam frame:", len(df))
print("60 FPS kabul edilirse süre:", len(df) / FPS, "saniye")
print("Frames per bit:", FRAMES_PER_BIT)

print("\nİlk 120 frame combined bit:")
print("".join(str(b) for b in df["combined_bit"].astype(int).tolist()[:120]))

print("\nİlk 120 frame yellow bit:")
print("".join(str(b) for b in df["yellow_bit"].astype(int).tolist()[:120]))

print("\nİlk 120 frame green bit:")
print("".join(str(b) for b in df["green_bit"].astype(int).tolist()[:120]))

print("\nİlk 120 frame cyan bit:")
print("".join(str(b) for b in df["cyan_bit"].astype(int).tolist()[:120]))

print("\nİlk 120 frame blue bit:")
print("".join(str(b) for b in df["blue_bit"].astype(int).tolist()[:120]))