# -*- coding: cp1254 -*-

import cv2
import glob
from pathlib import Path

DATASET_NAME = "BackOnly_Test_01"

PROJECT_ROOT = Path(__file__).resolve().parents[1]

FRAME_FOLDER = PROJECT_ROOT / "datasets" / DATASET_NAME

FPS = 60

frame_paths = sorted(glob.glob(str(FRAME_FOLDER / "*.png")))

print("Total frame count:", len(frame_paths))
print("Duration at 60 FPS:", len(frame_paths) / FPS, "seconds")

if len(frame_paths) == 0:
    raise FileNotFoundError("Klasörde PNG bulunamadı. FRAME_FOLDER yolunu kontrol et.")

for i, path in enumerate(frame_paths):
    frame = cv2.imread(path)

    if frame is None:
        print("Okunamadı:", path)
        continue

    # Cok buyukse ekrana sigdirmak icin kucultelim
    display = cv2.resize(frame, None, fx=0.5, fy=0.5)

    cv2.putText(
        display,
        f"Frame: {i}/{len(frame_paths)-1}",
        (30, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2
    )

    cv2.imshow("Unity PNG Sequence Preview", display)

    # 60 FPS gibi oynatmaya calisir
    key = cv2.waitKey(int(1000 / FPS))

    if key == ord("q"):
        break

cv2.destroyAllWindows()
