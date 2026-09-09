import argparse
import json
import math
import re
import socket
import time
from pathlib import Path

import cv2
import numpy as np


DEFAULT_FACE_ID = "BACK"
DEFAULT_PATTERN = "11001100"

DEFAULT_LOWER_BACK = [54, 83, 172]
DEFAULT_UPPER_BACK = [95, 147, 226]

DEFAULT_MIN_AREA = 20.0
DEFAULT_MAX_AREA = 6000.0

DEFAULT_MIN_ASPECT_RATIO = 0.25
DEFAULT_MAX_ASPECT_RATIO = 4.50

DEFAULT_ON_AREA_THRESHOLD = 35.0

DEFAULT_CAMERA_VERTICAL_FOV_DEG = 60.0


def natural_key(path):
    text = str(path)
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", text)]


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
        a = 168.628584

    if b is None:
        b = 0.609526

    return float(a), float(b), data


def load_pattern_metrics(path):
    data = load_json_if_exists(path)

    pattern_accuracy = parse_float(data.get("global_accuracy"), 1.0)
    bit_error_rate = parse_float(data.get("bit_error_rate"), 0.0)

    bit_error_count_raw = data.get("bit_error_count", 0)

    try:
        bit_error_count = int(bit_error_count_raw)
    except (TypeError, ValueError):
        bit_error_count = 0

    pattern = data.get("expected_pattern", DEFAULT_PATTERN)

    return {
        "pattern": pattern,
        "pattern_accuracy": float(pattern_accuracy),
        "bit_error_count": int(bit_error_count),
        "bit_error_rate": float(bit_error_rate),
    }


def estimate_distance(pixel_distance, model_a, model_b):
    if pixel_distance is None or pixel_distance <= 0:
        return None

    return model_a / pixel_distance + model_b


def distance_confidence(pixel_distance, pattern_accuracy):
    if pixel_distance is None or pixel_distance <= 0:
        return 0.0

    if pixel_distance >= 70:
        pixel_conf = 1.0
    elif pixel_distance >= 50:
        pixel_conf = 0.85
    elif pixel_distance >= 35:
        pixel_conf = 0.65
    else:
        pixel_conf = 0.40

    return round(pixel_conf * pattern_accuracy, 3)


def find_led_candidates(hsv_frame, lower_back, upper_back, min_area, max_area, min_aspect_ratio, max_aspect_ratio):
    lower = np.array(lower_back, dtype=np.uint8)
    upper = np.array(upper_back, dtype=np.uint8)

    mask = cv2.inRange(hsv_frame, lower, upper)

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


def compute_ray(mid_x, mid_y, image_width, image_height, camera_vertical_fov_deg):
    image_center_x = image_width / 2.0
    image_center_y = image_height / 2.0

    vertical_fov_rad = math.radians(camera_vertical_fov_deg)

    fy = (image_height / 2.0) / math.tan(vertical_fov_rad / 2.0)
    fx = fy

    x_cam = (mid_x - image_center_x) / fx
    y_cam = (image_center_y - mid_y) / fy
    z_cam = 1.0

    norm = math.sqrt(x_cam ** 2 + y_cam ** 2 + z_cam ** 2)

    return [
        x_cam / norm,
        y_cam / norm,
        z_cam / norm,
    ]


def process_frame(
    frame_path,
    model_a,
    model_b,
    pattern_metrics,
    lower_back,
    upper_back,
    min_area,
    max_area,
    min_aspect_ratio,
    max_aspect_ratio,
    on_area_threshold,
    camera_vertical_fov_deg,
    require_exactly_two_candidates,
):
    frame = cv2.imread(str(frame_path))

    if frame is None:
        return {
            "valid": False,
            "reason": "IMAGE_READ_FAILED",
            "image_size": None,
        }

    image_height, image_width = frame.shape[:2]
    image_center_x = image_width / 2.0
    image_center_y = image_height / 2.0

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    candidates, mask_clean = find_led_candidates(
        hsv_frame=hsv,
        lower_back=lower_back,
        upper_back=upper_back,
        min_area=min_area,
        max_area=max_area,
        min_aspect_ratio=min_aspect_ratio,
        max_aspect_ratio=max_aspect_ratio,
    )

    total_area = sum(c["area"] for c in candidates)
    bit = 1 if total_area > on_area_threshold else 0

    candidate_count = len(candidates)

    if bit != 1:
        return {
            "valid": False,
            "reason": "BIT_OFF",
            "bit": bit,
            "pair_found": False,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "image_size": [image_width, image_height],
        }

    if candidate_count < 2:
        return {
            "valid": False,
            "reason": "PAIR_NOT_FOUND",
            "bit": bit,
            "pair_found": False,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "image_size": [image_width, image_height],
        }

    if require_exactly_two_candidates and candidate_count != 2:
        return {
            "valid": False,
            "reason": "CANDIDATE_COUNT_NOT_2",
            "bit": bit,
            "pair_found": False,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "image_size": [image_width, image_height],
        }

    # Existing pipeline uses the two largest blobs.
    c1 = candidates[0]
    c2 = candidates[1]

    led1_x = c1["cx"]
    led1_y = c1["cy"]
    led2_x = c2["cx"]
    led2_y = c2["cy"]

    pixel_distance = math.sqrt(
        (led1_x - led2_x) ** 2 +
        (led1_y - led2_y) ** 2
    )

    mid_x = (led1_x + led2_x) / 2.0
    mid_y = (led1_y + led2_y) / 2.0

    error_x = (mid_x - image_center_x) / image_center_x
    error_y = (image_center_y - mid_y) / image_center_y

    ray_cam = compute_ray(
        mid_x=mid_x,
        mid_y=mid_y,
        image_width=image_width,
        image_height=image_height,
        camera_vertical_fov_deg=camera_vertical_fov_deg,
    )

    estimated_distance = estimate_distance(
        pixel_distance=pixel_distance,
        model_a=model_a,
        model_b=model_b,
    )

    dist_conf = distance_confidence(
        pixel_distance=pixel_distance,
        pattern_accuracy=pattern_metrics["pattern_accuracy"],
    )

    valid = (
        pattern_metrics["pattern_accuracy"] >= 0.95
        and dist_conf >= 0.60
        and pixel_distance >= 20.0
    )

    if not valid:
        return {
            "valid": False,
            "reason": "LOW_CONFIDENCE",
            "bit": bit,
            "pair_found": True,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "pixel_distance": pixel_distance,
            "distance_confidence": dist_conf,
            "image_size": [image_width, image_height],
        }

    return {
        "valid": True,
        "reason": "OK",
        "face_id": DEFAULT_FACE_ID,
        "pattern": pattern_metrics["pattern"],
        "pattern_accuracy": pattern_metrics["pattern_accuracy"],
        "bit_error_count": pattern_metrics["bit_error_count"],
        "bit_error_rate": pattern_metrics["bit_error_rate"],

        "bit": bit,
        "pair_found": True,
        "candidate_count": candidate_count,
        "total_area": total_area,

        "led1_px": [led1_x, led1_y],
        "led2_px": [led2_x, led2_y],
        "midpoint_px": [mid_x, mid_y],

        "error_norm": [error_x, error_y],
        "ray_cam": ray_cam,

        "pixel_distance": pixel_distance,
        "estimated_distance": estimated_distance,
        "distance_confidence": dist_conf,

        "image_size": [image_width, image_height],
    }


def make_invalid_packet(dataset, frame_id, detection):
    return {
        "dataset": dataset,
        "frame": frame_id,
        "valid": False,
        "face_id": None,
        "pattern": DEFAULT_PATTERN,
        "pattern_accuracy": 0.0,
        "bit_error_count": None,
        "bit_error_rate": 1.0,
        "bit": detection.get("bit"),
        "pair_found": False,
        "candidate_count": detection.get("candidate_count", 0),
        "total_area": detection.get("total_area", 0.0),
        "led1_px": None,
        "led2_px": None,
        "midpoint_px": None,
        "error_norm": [0.0, 0.0],
        "ray_cam": None,
        "pixel_distance": None,
        "estimated_distance": None,
        "distance_confidence": 0.0,
        "image_size": detection.get("image_size"),
        "held_observation": False,
        "reason": detection.get("reason", "INVALID"),
    }


def packet_from_detection(dataset, frame_id, detection):
    packet = dict(detection)
    packet["dataset"] = dataset
    packet["frame"] = frame_id
    packet["held_observation"] = False
    return packet


def add_udp_fields(packet, seq):
    packet["udp_seq"] = seq
    packet["sent_time_unix"] = time.time()
    return packet


def frame_id_from_path(path, fallback):
    numbers = re.findall(r"\d+", path.stem)

    if not numbers:
        return fallback

    return int(numbers[-1])


def send_loop(args):
    dataset_dir = Path(args.datasets_dir) / args.dataset

    if not dataset_dir.exists():
        raise FileNotFoundError(f"Dataset directory not found: {dataset_dir}")

    frame_files = sorted(dataset_dir.glob(args.frame_glob), key=natural_key)

    if not frame_files:
        raise RuntimeError(f"No frames found under {dataset_dir} with glob {args.frame_glob}")

    if args.frame_step is None:
        frame_step = max(1, int(round(args.source_fps / args.rate)))
    else:
        frame_step = max(1, int(args.frame_step))

    selected_frames = frame_files[::frame_step]

    model_a, model_b, _ = load_distance_model(args.distance_model_json)

    pattern_json_path = Path(args.outputs_dir) / args.dataset / args.pattern_json_name
    pattern_metrics = load_pattern_metrics(pattern_json_path)

    lower_back = parse_hsv(args.hsv_lower)
    upper_back = parse_hsv(args.hsv_upper)

    require_exactly_two_candidates = not args.allow_more_than_two_candidates

    print("=== Live BACK PNG sequence UDP sender ===")
    print(f"dataset                    : {args.dataset}")
    print(f"dataset_dir                : {dataset_dir}")
    print(f"frame_glob                 : {args.frame_glob}")
    print(f"all_frames                 : {len(frame_files)}")
    print(f"frame_step                 : {frame_step}")
    print(f"selected_frames            : {len(selected_frames)}")
    print(f"source_fps                 : {args.source_fps}")
    print(f"send_rate                  : {args.rate}")
    print(f"udp_target                 : {args.ip}:{args.port}")
    print(f"lower_back                 : {lower_back}")
    print(f"upper_back                 : {upper_back}")
    print(f"min_area                   : {args.min_area}")
    print(f"max_area                   : {args.max_area}")
    print(f"min_aspect_ratio           : {args.min_aspect_ratio}")
    print(f"max_aspect_ratio           : {args.max_aspect_ratio}")
    print(f"on_area_threshold          : {args.on_area_threshold}")
    print(f"candidate_count_exactly_2  : {require_exactly_two_candidates}")
    print(f"camera_vertical_fov_deg    : {args.camera_vertical_fov_deg}")
    print(f"distance_model             : estimated_distance = {model_a} / pixel_distance + {model_b}")
    print(f"pattern_accuracy           : {pattern_metrics['pattern_accuracy']}")
    print(f"bit_error_rate             : {pattern_metrics['bit_error_rate']}")
    print(f"hold_seconds               : {args.hold_seconds}")
    print(f"send_invalid               : {args.send_invalid}")
    print("")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    seq = 0
    sent_total = 0

    period = 1.0 / args.rate

    last_valid_packet = None
    last_valid_time = None

    try:
        while True:
            for index, frame_path in enumerate(selected_frames):
                loop_start = time.time()

                frame_id = frame_id_from_path(frame_path, fallback=index * frame_step)

                detection = process_frame(
                    frame_path=frame_path,
                    model_a=model_a,
                    model_b=model_b,
                    pattern_metrics=pattern_metrics,
                    lower_back=lower_back,
                    upper_back=upper_back,
                    min_area=args.min_area,
                    max_area=args.max_area,
                    min_aspect_ratio=args.min_aspect_ratio,
                    max_aspect_ratio=args.max_aspect_ratio,
                    on_area_threshold=args.on_area_threshold,
                    camera_vertical_fov_deg=args.camera_vertical_fov_deg,
                    require_exactly_two_candidates=require_exactly_two_candidates,
                )

                now = time.time()

                if detection.get("valid"):
                    packet = packet_from_detection(
                        dataset=args.dataset,
                        frame_id=frame_id,
                        detection=detection,
                    )

                    last_valid_packet = dict(packet)
                    last_valid_time = now

                else:
                    if (
                        last_valid_packet is not None
                        and last_valid_time is not None
                        and (now - last_valid_time) <= args.hold_seconds
                    ):
                        packet = dict(last_valid_packet)
                        packet["frame"] = frame_id
                        packet["held_observation"] = True
                        packet["held_age_s"] = now - last_valid_time
                        packet["reason"] = "HELD_DURING_" + detection.get("reason", "INVALID")
                    else:
                        packet = make_invalid_packet(
                            dataset=args.dataset,
                            frame_id=frame_id,
                            detection=detection,
                        )

                        if not args.send_invalid:
                            elapsed = time.time() - loop_start

                            if elapsed < period:
                                time.sleep(period - elapsed)

                            continue

                packet = add_udp_fields(packet, seq)

                payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                sock.sendto(payload, (args.ip, args.port))

                if seq % max(1, int(args.rate)) == 0:
                    print(
                        f"seq={seq} "
                        f"frame={packet.get('frame')} "
                        f"valid={packet.get('valid')} "
                        f"held={packet.get('held_observation')} "
                        f"reason={packet.get('reason')} "
                        f"bit={packet.get('bit')} "
                        f"count={packet.get('candidate_count')} "
                        f"face={packet.get('face_id')} "
                        f"err={packet.get('error_norm')} "
                        f"dist={packet.get('estimated_distance')} "
                        f"px={packet.get('pixel_distance')}"
                    )

                seq += 1
                sent_total += 1

                if args.count is not None and sent_total >= args.count:
                    print("")
                    print(f"Finished. sent_total={sent_total}")
                    return

                elapsed = time.time() - loop_start

                if elapsed < period:
                    time.sleep(period - elapsed)

            if not args.loop:
                print("")
                print(f"Finished one pass. sent_total={sent_total}")
                return

    except KeyboardInterrupt:
        print("")
        print(f"Stopped by user. sent_total={sent_total}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--dataset", required=True)
    parser.add_argument("--ip", required=True)
    parser.add_argument("--port", type=int, default=5005)

    parser.add_argument("--datasets-dir", default="datasets")
    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--frame-glob", default="*.png")

    parser.add_argument("--pattern-json-name", default="back_pattern_decode_summary.json")
    parser.add_argument("--distance-model-json", default="outputs/calibration/distance_model_summary.json")

    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--source-fps", type=float, default=60.0)
    parser.add_argument("--frame-step", type=int, default=None)

    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--count", type=int, default=None)

    parser.add_argument("--hsv-lower", default="54,83,172")
    parser.add_argument("--hsv-upper", default="95,147,226")

    parser.add_argument("--min-area", type=float, default=20.0)
    parser.add_argument("--max-area", type=float, default=6000.0)

    parser.add_argument("--min-aspect-ratio", type=float, default=0.25)
    parser.add_argument("--max-aspect-ratio", type=float, default=4.50)

    parser.add_argument("--on-area-threshold", type=float, default=35.0)

    parser.add_argument("--camera-vertical-fov-deg", type=float, default=60.0)

    parser.add_argument("--hold-seconds", type=float, default=0.35)

    parser.add_argument("--send-invalid", action="store_true", default=True)

    parser.add_argument(
        "--allow-more-than-two-candidates",
        action="store_true",
        help="Use two largest blobs even if more than two candidates are found."
    )

    args = parser.parse_args()

    send_loop(args)


if __name__ == "__main__":
    main()
