# -*- coding: cp1254 -*-

import cv2
import glob
from pathlib import Path

import numpy as np

DATASET_NAME = "BackOnly_Test_02"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRAME_FOLDER = PROJECT_ROOT / "datasets" / DATASET_NAME

frame_paths = sorted(glob.glob(str(FRAME_FOLDER / "*.png")))

if len(frame_paths) == 0:
    raise FileNotFoundError("PNG bulunamadi. FRAME_FOLDER yolunu kontrol et.")

# LED'in net gorundugu bir frame sec
frame_index = 80
frame_index = min(frame_index, len(frame_paths) - 1)

frame = cv2.imread(frame_paths[frame_index])

if frame is None:
    raise RuntimeError("Frame okunamadi.")

frame = cv2.resize(frame, None, fx=0.5, fy=0.5)
hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

def nothing(x):
    pass

cv2.namedWindow("HSV Tuner")

cv2.createTrackbar("H Min", "HSV Tuner", 20, 179, nothing)
cv2.createTrackbar("H Max", "HSV Tuner", 95, 179, nothing)
cv2.createTrackbar("S Min", "HSV Tuner", 80, 255, nothing)
cv2.createTrackbar("S Max", "HSV Tuner", 255, 255, nothing)
cv2.createTrackbar("V Min", "HSV Tuner", 150, 255, nothing)
cv2.createTrackbar("V Max", "HSV Tuner", 255, 255, nothing)

while True:
    h_min = cv2.getTrackbarPos("H Min", "HSV Tuner")
    h_max = cv2.getTrackbarPos("H Max", "HSV Tuner")
    s_min = cv2.getTrackbarPos("S Min", "HSV Tuner")
    s_max = cv2.getTrackbarPos("S Max", "HSV Tuner")
    v_min = cv2.getTrackbarPos("V Min", "HSV Tuner")
    v_max = cv2.getTrackbarPos("V Max", "HSV Tuner")

    lower = np.array([h_min, s_min, v_min])
    upper = np.array([h_max, s_max, v_max])

    mask = cv2.inRange(hsv, lower, upper)

    result = cv2.bitwise_and(frame, frame, mask=mask)

    cv2.imshow("Original", frame)
    cv2.imshow("Mask", mask)
    cv2.imshow("Result", result)

    key = cv2.waitKey(1)

    if key == ord("q"):
        break

print("Secilen HSV degerleri:")
print("LOWER_LED =", [h_min, s_min, v_min])
print("UPPER_LED =", [h_max, s_max, v_max])

cv2.destroyAllWindows()
