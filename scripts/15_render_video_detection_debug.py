import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np


DEFAULT_LOWER_BACK = [54, 83, 172]
DEFAULT_UPPER_BACK = [95, 147, 226]


def parse_hsv(text):
    parts = [int(x.strip()) for x in text.split(",")]
    if len(parts) != 3:
        raise ValueError("HSV value must be like '54,83,172'")
    return parts


def parse_float(value, default=None):
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_json_if_exists(path):
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_distance_model(path):
    data = load_json_if_exists(path)

    a = parse_float(data.get("A"))
    b = parse_float(data.get("B"))

    if a is None:
        a = 168.62858387416162
    if b is None:
        b = 0.6095263977622732

    return float(a), float(b)


def estimate_distance(pixel_distance, model_a, model_b):
    if pixel_distance is None or pixel_distance <= 0:
        return None
    return model_a / pixel_distance + model_b


def distance_confidence(pixel_distance):
    if pixel_distance is None or pixel_distance <= 0:
        return 0.0

    if pixel_distance >= 70:
        return 1.0
    if pixel_distance >= 50:
        return 0.85
    if pixel_distance >= 35:
        return 0.65
    return 0.40


def find_led_candidates(
    frame,
    lower_back,
    upper_back,
    min_area,
    max_area,
    min_aspect_ratio,
    max_aspect_ratio,
):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    lower = np.array(lower_back, dtype=np.uint8)
    upper = np.array(upper_back, dtype=np.uint8)

    mask = cv2.inRange(hsv, lower, upper)

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

        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        if h == 0:
            continue

        aspect_ratio = w / h

        if aspect_ratio < min_aspect_ratio or aspect_ratio > max_aspect_ratio:
            continue

        cx = x + w // 2
        cy = y + h // 2

        candidates.append({
            "x": int(x),
            "y": int(y),
            "w": int(w),
            "h": int(h),
            "cx": float(cx),
            "cy": float(cy),
            "area": float(area),
            "aspect_ratio": float(aspect_ratio),
        })

    candidates = sorted(candidates, key=lambda c: c["area"], reverse=True)
    return candidates, mask_clean


def select_pair(candidates, allow_more_than_two):
    if len(candidates) < 2:
        return None

    if not allow_more_than_two and len(candidates) != 2:
        return None

    # Current temporary strategy:
    # use two largest candidates.
    return candidates[0], candidates[1]


def compute_observation(
    frame,
    candidates,
    pair,
    model_a,
    model_b,
    on_area_threshold,
):
    h, w = frame.shape[:2]

    total_area = sum(c["area"] for c in candidates)
    bit = 1 if total_area > on_area_threshold else 0

    if bit != 1:
        return {
            "valid": False,
            "reason": "BIT_OFF",
            "bit": bit,
            "total_area": total_area,
        }

    if pair is None:
        if len(candidates) < 2:
            reason = "PAIR_NOT_FOUND"
        else:
            reason = "CANDIDATE_COUNT_NOT_2"

        return {
            "valid": False,
            "reason": reason,
            "bit": bit,
            "total_area": total_area,
        }

    c1, c2 = pair

    led1_x = c1["cx"]
    led1_y = c1["cy"]
    led2_x = c2["cx"]
    led2_y = c2["cy"]

    pixel_distance = math.sqrt((led1_x - led2_x) ** 2 + (led1_y - led2_y) ** 2)

    mid_x = (led1_x + led2_x) / 2.0
    mid_y = (led1_y + led2_y) / 2.0

    image_center_x = w / 2.0
    image_center_y = h / 2.0

    error_x = (mid_x - image_center_x) / image_center_x
    error_y = (image_center_y - mid_y) / image_center_y

    dist = estimate_distance(pixel_distance, model_a, model_b)
    conf = distance_confidence(pixel_distance)

    valid = conf >= 0.60 and pixel_distance >= 20.0

    if not valid:
        return {
            "valid": False,
            "reason": "LOW_CONFIDENCE",
            "bit": bit,
            "total_area": total_area,
            "pixel_distance": pixel_distance,
            "estimated_distance": dist,
            "distance_confidence": conf,
            "error_x": error_x,
            "error_y": error_y,
        }

    return {
        "valid": True,
        "reason": "OK",
        "bit": bit,
        "total_area": total_area,
        "pixel_distance": pixel_distance,
        "estimated_distance": dist,
        "distance_confidence": conf,
        "error_x": error_x,
        "error_y": error_y,
        "mid_x": mid_x,
        "mid_y": mid_y,
    }


def draw_overlay(frame, frame_id, candidates, pair, obs):
    output = frame.copy()
    h, w = output.shape[:2]

    image_center = (w // 2, h // 2)

    cv2.drawMarker(
        output,
        image_center,
        (255, 255, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=24,
        thickness=2,
    )

    for i, c in enumerate(candidates):
        x, y, bw, bh = c["x"], c["y"], c["w"], c["h"]

        color = (0, 180, 255)
        thickness = 2

        cv2.rectangle(output, (x, y), (x + bw, y + bh), color, thickness)
        cv2.circle(output, (int(c["cx"]), int(c["cy"])), 4, color, -1)

        cv2.putText(
            output,
            f"#{i} A={c['area']:.0f}",
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    if pair is not None:
        c1, c2 = pair
        p1 = (int(c1["cx"]), int(c1["cy"]))
        p2 = (int(c2["cx"]), int(c2["cy"]))

        cv2.rectangle(
            output,
            (c1["x"], c1["y"]),
            (c1["x"] + c1["w"], c1["y"] + c1["h"]),
            (0, 255, 0),
            3,
        )

        cv2.rectangle(
            output,
            (c2["x"], c2["y"]),
            (c2["x"] + c2["w"], c2["y"] + c2["h"]),
            (0, 255, 0),
            3,
        )

        cv2.line(output, p1, p2, (0, 255, 0), 2)

        mid_x = int((c1["cx"] + c2["cx"]) / 2.0)
        mid_y = int((c1["cy"] + c2["cy"]) / 2.0)

        cv2.circle(output, (mid_x, mid_y), 6, (0, 255, 0), -1)
        cv2.line(output, image_center, (mid_x, mid_y), (255, 255, 0), 2)

    valid = obs.get("valid")
    reason = obs.get("reason")

    status_color = (0, 255, 0) if valid else (0, 0, 255)

    lines = [
        f"frame={frame_id}",
        f"valid={valid} reason={reason}",
        f"candidate_count={len(candidates)} bit={obs.get('bit')}",
        f"err=({obs.get('error_x')}, {obs.get('error_y')})",
        f"px_dist={obs.get('pixel_distance')}",
        f"est_dist={obs.get('estimated_distance')}",
        f"conf={obs.get('distance_confidence')}",
    ]

    y0 = 32
    for line in lines:
        cv2.putText(
            output,
            line,
            (20, y0),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            status_color,
            2,
            cv2.LINE_AA,
        )
        y0 += 28

    return output


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--video", required=True)
    parser.add_argument("--output", default="outputs/BackOnly_Dynamic_Test_01/debug_overlay.mp4")

    parser.add_argument("--distance-model-json", default="outputs/calibration/distance_model_summary.json")

    parser.add_argument("--hsv-lower", default="54,83,172")
    parser.add_argument("--hsv-upper", default="95,147,226")

    parser.add_argument("--min-area", type=float, default=20.0)
    parser.add_argument("--max-area", type=float, default=6000.0)
    parser.add_argument("--min-aspect-ratio", type=float, default=0.25)
    parser.add_argument("--max-aspect-ratio", type=float, default=4.50)
    parser.add_argument("--on-area-threshold", type=float, default=35.0)

    parser.add_argument("--allow-more-than-two-candidates", action="store_true")

    parser.add_argument("--max-frames", type=int, default=None)

    args = parser.parse_args()

    video_path = Path(args.video)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if fps <= 0:
        fps = 60.0

    model_a, model_b = load_distance_model(args.distance_model_json)

    lower_back = parse_hsv(args.hsv_lower)
    upper_back = parse_hsv(args.hsv_upper)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Could not open writer: {output_path}")

    print("=== Render Video Detection Debug Overlay ===")
    print(f"video                         : {video_path}")
    print(f"output                        : {output_path}")
    print(f"fps                           : {fps}")
    print(f"frame_count                   : {frame_count}")
    print(f"resolution                    : {width}x{height}")
    print(f"allow_more_than_two_candidates: {args.allow_more_than_two_candidates}")
    print("")

    frame_id = 0

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        if args.max_frames is not None and frame_id >= args.max_frames:
            break

        candidates, _ = find_led_candidates(
            frame=frame,
            lower_back=lower_back,
            upper_back=upper_back,
            min_area=args.min_area,
            max_area=args.max_area,
            min_aspect_ratio=args.min_aspect_ratio,
            max_aspect_ratio=args.max_aspect_ratio,
        )

        pair = select_pair(
            candidates=candidates,
            allow_more_than_two=args.allow_more_than_two_candidates,
        )

        obs = compute_observation(
            frame=frame,
            candidates=candidates,
            pair=pair,
            model_a=model_a,
            model_b=model_b,
            on_area_threshold=args.on_area_threshold,
        )

        overlay = draw_overlay(
            frame=frame,
            frame_id=frame_id,
            candidates=candidates,
            pair=pair,
            obs=obs,
        )

        writer.write(overlay)

        if frame_id % 60 == 0:
            print(
                f"frame={frame_id} "
                f"valid={obs.get('valid')} "
                f"reason={obs.get('reason')} "
                f"count={len(candidates)} "
                f"dist={obs.get('estimated_distance')}"
            )

        frame_id += 1

    cap.release()
    writer.release()

    print("")
    print(f"Finished. frames_written={frame_id}")
    print(f"Output saved: {output_path}")


if __name__ == "__main__":
    main()
