import cv2
import glob
import os
import numpy as np

FRAME_FOLDER = r"C:\Users\aydog\OneDrive\Desktop\OpenCV\Unity\SabitCamArkadan"

FPS = 60

frame_paths = sorted(glob.glob(os.path.join(FRAME_FOLDER, "*.png")))

if len(frame_paths) == 0:
    raise FileNotFoundError("No PNG files found. Check FRAME_FOLDER path.")

print("Total frame count:", len(frame_paths))
print("Duration at 60 FPS:", len(frame_paths) / FPS, "seconds")


# ------------------------------------------------------------
# HSV masks
# OpenCV HSV ranges:
# H: 0-179
# S: 0-255
# V: 0-255
# ------------------------------------------------------------

# Bright yellow / white-yellow LED glow
LOWER_YELLOW = np.array([15, 45, 180])
UPPER_YELLOW = np.array([45, 220, 255])

# Bright green LED glow
LOWER_GREEN = np.array([54, 83, 172])
UPPER_GREEN = np.array([95, 147, 226])

# Bright cyan / turquoise LED glow
LOWER_CYAN = np.array([52, 0, 252])
UPPER_CYAN = np.array([107, 144, 255])

# Bright blue LED glow
LOWER_BLUE = np.array([110, 70, 220])
UPPER_BLUE = np.array([135, 255, 255])

# Area filters
MIN_AREA = 35
MAX_AREA = 6000

# Shape filters
MIN_ASPECT_RATIO = 0.25
MAX_ASPECT_RATIO = 4.50

# If there are too many candidates, keep strongest ones for debug display
MAX_DISPLAY_CANDIDATES = 8

# Optional ROI.
# Use this only if you want to process only part of the image.
USE_ROI = False
ROI_X = 0
ROI_Y = 0
ROI_W = 960
ROI_H = 1080


def merge_close_boxes(boxes, distance_threshold=18):
    """
    Merge boxes that are very close to each other.
    This helps when one physical LED is split into multiple small contours.
    boxes format: [x, y, w, h, area]
    """

    if len(boxes) == 0:
        return []

    merged = []
    used = [False] * len(boxes)

    for i in range(len(boxes)):
        if used[i]:
            continue

        x1, y1, w1, h1, a1 = boxes[i]
        group = [(x1, y1, w1, h1, a1)]
        used[i] = True

        cx1 = x1 + w1 / 2
        cy1 = y1 + h1 / 2

        changed = True

        while changed:
            changed = False

            for j in range(len(boxes)):
                if used[j]:
                    continue

                x2, y2, w2, h2, a2 = boxes[j]
                cx2 = x2 + w2 / 2
                cy2 = y2 + h2 / 2

                # Check distance to any box in current group
                should_merge = False

                for gx, gy, gw, gh, ga in group:
                    gcx = gx + gw / 2
                    gcy = gy + gh / 2

                    dist = np.sqrt((cx2 - gcx) ** 2 + (cy2 - gcy) ** 2)

                    if dist < distance_threshold:
                        should_merge = True
                        break

                if should_merge:
                    group.append((x2, y2, w2, h2, a2))
                    used[j] = True
                    changed = True

        min_x = min(g[0] for g in group)
        min_y = min(g[1] for g in group)
        max_x = max(g[0] + g[2] for g in group)
        max_y = max(g[1] + g[3] for g in group)
        total_area = sum(g[4] for g in group)

        merged.append([
            int(min_x),
            int(min_y),
            int(max_x - min_x),
            int(max_y - min_y),
            float(total_area)
        ])

    return merged


for frame_index, path in enumerate(frame_paths):
    frame = cv2.imread(path)

    if frame is None:
        print("Could not read:", path)
        continue

    original_frame = frame.copy()

    if USE_ROI:
        frame_proc = frame[ROI_Y:ROI_Y + ROI_H, ROI_X:ROI_X + ROI_W]
    else:
        frame_proc = frame

    hsv = cv2.cvtColor(frame_proc, cv2.COLOR_BGR2HSV)

    yellow_mask = cv2.inRange(hsv, LOWER_YELLOW, UPPER_YELLOW)
    green_mask = cv2.inRange(hsv, LOWER_GREEN, UPPER_GREEN)
    cyan_mask = cv2.inRange(hsv, LOWER_CYAN, UPPER_CYAN)
    blue_mask = cv2.inRange(hsv, LOWER_BLUE, UPPER_BLUE)

    mask = cv2.bitwise_or(yellow_mask, green_mask)
    mask = cv2.bitwise_or(mask, cyan_mask)
    mask = cv2.bitwise_or(mask, blue_mask)
    
    # Noise cleaning
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    mask_clean = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel_open)
    mask_clean = cv2.morphologyEx(mask_clean, cv2.MORPH_CLOSE, kernel_close)

    contours, _ = cv2.findContours(
        mask_clean,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    raw_boxes = []

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

        # Mean brightness test inside the candidate region
        candidate_mask = mask_clean[y:y + h, x:x + w]
        candidate_hsv = hsv[y:y + h, x:x + w]
        v_channel = candidate_hsv[:, :, 2]

        mean_v = cv2.mean(v_channel, mask=candidate_mask)[0]

        if mean_v < 170:
            continue

        raw_boxes.append([x, y, w, h, area])

    merged_boxes = merge_close_boxes(raw_boxes, distance_threshold=10)

    # Sort strongest candidates by area
    merged_boxes = sorted(merged_boxes, key=lambda b: b[4], reverse=True)

    display_boxes = merged_boxes[:MAX_DISPLAY_CANDIDATES]

    output = original_frame.copy()

    for idx, (x, y, w, h, area) in enumerate(display_boxes):
        if USE_ROI:
            x_draw = x + ROI_X
            y_draw = y + ROI_Y
        else:
            x_draw = x
            y_draw = y

        cx = x_draw + w // 2
        cy = y_draw + h // 2

        cv2.rectangle(output, (x_draw, y_draw), (x_draw + w, y_draw + h), (0, 255, 0), 2)
        cv2.circle(output, (cx, cy), 4, (0, 0, 255), -1)

        cv2.putText(
            output,
            f"ID:{idx} A:{int(area)}",
            (x_draw, y_draw - 5),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 255, 0),
            1
        )

    cv2.putText(
        output,
        f"Frame: {frame_index} | Raw: {len(raw_boxes)} | Merged: {len(merged_boxes)}",
        (30, 40),
        cv2.FONT_HERSHEY_SIMPLEX,
        1,
        (0, 255, 255),
        2
    )

    display_output = cv2.resize(output, None, fx=0.5, fy=0.5)
    display_mask = cv2.resize(mask_clean, None, fx=0.5, fy=0.5)

    cv2.imshow("LED Detection V2", display_output)
    cv2.imshow("LED Mask V2", display_mask)

    key = cv2.waitKey(int(1000 / FPS))

    if key == ord("q"):
        break

cv2.destroyAllWindows()