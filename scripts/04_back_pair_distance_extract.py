# -*- coding: cp1254 -*-

import cv2
import glob
import math
from pathlib import Path

import numpy as np
import pandas as pd

DATASET_NAME = "BackOnly_Test_02"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRAME_FOLDER = PROJECT_ROOT / "datasets" / DATASET_NAME
OUTPUT_FOLDER = PROJECT_ROOT / "outputs" / DATASET_NAME

OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

FPS = 60
BIT_DURATION_SECONDS = 0.1
FRAMES_PER_BIT = int(FPS * BIT_DURATION_SECONDS)

# Back face / green LEDs
LOWER_BACK = np.array([54, 83, 172])
UPPER_BACK = np.array([95, 147, 226])

MIN_AREA = 20
MAX_AREA = 6000

MIN_ASPECT_RATIO = 0.25
MAX_ASPECT_RATIO = 4.50

ON_AREA_THRESHOLD = 35

SHOW_PREVIEW = True
DISPLAY_SCALE = 0.5

CAMERA_VERTICAL_FOV_DEG = 60.0

frame_paths = sorted(glob.glob(str(FRAME_FOLDER / "*.png")))

if len(frame_paths) == 0:
    raise FileNotFoundError("No PNG files found. Check FRAME_FOLDER path.")

print("Total frame count:", len(frame_paths))
print("Duration at 60 FPS:", len(frame_paths) / FPS, "seconds")
print("Frames per bit:", FRAMES_PER_BIT)


def find_led_candidates(hsv_frame):
    mask = cv2.inRange(hsv_frame, LOWER_BACK, UPPER_BACK)

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel_close)

    contours, _ = cv2.findContours(
        mask_clean,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if area < MIN_AREA or area > MAX_AREA:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        if h == 0:
            continue

        aspect_ratio = w / h

        if aspect_ratio < MIN_ASPECT_RATIO or aspect_ratio > MAX_ASPECT_RATIO:
            continue

        cx = x + w // 2
        cy = y + h // 2

        candidates.append({
            "x": x,
            "y": y,
            "w": w,
            "h": h,
            "cx": cx,
            "cy": cy,
            "area": area
        })

    candidates = sorted(candidates, key=lambda c: c["area"], reverse=True)

    return candidates, mask_clean


records = []

for frame_index, path in enumerate(frame_paths):
    frame = cv2.imread(path)

    if frame is None:
        continue

    image_height, image_width = frame.shape[:2]
    image_center_x = image_width / 2.0
    image_center_y = image_height / 2.0

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)


    candidates, mask_clean = find_led_candidates(hsv)

    total_area = sum(c["area"] for c in candidates)
    bit = 1 if total_area > ON_AREA_THRESHOLD else 0

    pair_found = 0
    led1_x = None
    led1_y = None
    led2_x = None
    led2_y = None
    pixel_distance = None

    mid_x = None
    mid_y = None
    error_x = None
    error_y = None
    ray_x = None
    ray_y = None
    ray_z = None

    if len(candidates) >= 2:
        c1 = candidates[0]
        c2 = candidates[1]

        led1_x = c1["cx"]
        led1_y = c1["cy"]
        led2_x = c2["cx"]
        led2_y = c2["cy"]

        pixel_distance = math.sqrt((led1_x - led2_x) ** 2 + (led1_y - led2_y) ** 2)

        mid_x = (led1_x + led2_x) / 2.0
        mid_y = (led1_y + led2_y) / 2.0

        error_x = (mid_x - image_center_x) / image_center_x
        error_y = (image_center_y - mid_y) / image_center_y
        vertical_fov_rad = math.radians(CAMERA_VERTICAL_FOV_DEG)

        fy = (image_height / 2.0) / math.tan(vertical_fov_rad / 2.0)
        fx = fy

        x_cam = (mid_x - image_center_x) / fx
        y_cam = (image_center_y - mid_y) / fy
        z_cam = 1.0

        norm = math.sqrt(x_cam ** 2 + y_cam ** 2 + z_cam ** 2)

        ray_x = x_cam / norm
        ray_y = y_cam / norm
        ray_z = z_cam / norm

        pair_found = 1

    records.append({
        "frame": frame_index,
        "file": Path(path).name,
        "candidate_count": len(candidates),
        "total_area": total_area,
        "bit": bit,
        "pair_found": pair_found,
        "led1_x": led1_x,
        "led1_y": led1_y,
        "led2_x": led2_x,
        "led2_y": led2_y,
        "pixel_distance": pixel_distance,
        "mid_x": mid_x,
        "mid_y": mid_y,
        "error_x": error_x,
        "error_y": error_y,
        "ray_x": ray_x,
        "ray_y": ray_y,
        "ray_z": ray_z,
        "camera_vertical_fov_deg": CAMERA_VERTICAL_FOV_DEG,
        "image_width": image_width,
        "image_height": image_height
    })

    if SHOW_PREVIEW:
        output = frame.copy()

        for idx, c in enumerate(candidates[:5]):
            x, y, w, h = c["x"], c["y"], c["w"], c["h"]
            cx, cy = c["cx"], c["cy"]

            cv2.rectangle(output, (x, y), (x + w, y + h), (0, 255, 0), 2)
            cv2.circle(output, (cx, cy), 4, (0, 0, 255), -1)

            cv2.putText(
                output,
                f"ID:{idx} A:{int(c['area'])}",
                (x, y - 5),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 0),
                1
            )

        if pair_found:
            cv2.line(output, (led1_x, led1_y), (led2_x, led2_y), (255, 0, 0), 2)
            cv2.putText(
                output,
                f"d_px: {pixel_distance:.1f}",
                (30, 80),
                cv2.FONT_HERSHEY_SIMPLEX,
                1,
                (255, 0, 0),
                2
            )

            cv2.circle(output, (int(mid_x), int(mid_y)), 6, (255, 255, 255), -1)

            cv2.line(
                output,
                (int(image_center_x), int(image_center_y)),
                (int(mid_x), int(mid_y)),
                (0, 255, 255),
                2
            )

            cv2.putText(
                output,
                f"err_x:{error_x:.3f} err_y:{error_y:.3f}",
                (30, 120),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 255),
                2
            )
            cv2.putText(
                output,
                f"ray:[{ray_x:.3f},{ray_y:.3f},{ray_z:.3f}]",
                (30, 150),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 255),
                2
            )

        cv2.putText(
            output,
            f"Frame:{frame_index} Bit:{bit} Pair:{pair_found} Count:{len(candidates)}",
            (30, 40),
            cv2.FONT_HERSHEY_SIMPLEX,
            1,
            (0, 255, 255),
            2
        )

        display_output = cv2.resize(output, None, fx=DISPLAY_SCALE, fy=DISPLAY_SCALE)
        display_mask = cv2.resize(mask_clean, None, fx=DISPLAY_SCALE, fy=DISPLAY_SCALE)

        cv2.imshow("Back Pair Distance", display_output)
        cv2.imshow("Back Green Mask", display_mask)

        key = cv2.waitKey(int(1000 / FPS))

        if key == ord("q"):
            break

cv2.destroyAllWindows()

df = pd.DataFrame(records)

output_csv = OUTPUT_FOLDER / "back_pair_results.csv"
df.to_csv(output_csv, index=False)

print("CSV saved:", output_csv)
print("Total processed frames:", len(df))

valid_distances = df["pixel_distance"].dropna()

if len(valid_distances) > 0:
    print("Mean pixel distance:", valid_distances.mean())
    print("Min pixel distance:", valid_distances.min())
    print("Max pixel distance:", valid_distances.max())
else:
    print("No valid LED pair distance found.")

print("First 120 frame bits:")
print("".join(str(b) for b in df["bit"].astype(int).tolist()[:120]))
