import argparse
import csv
import itertools
import json
import math
import socket
import time
from pathlib import Path

import cv2
import numpy as np


DEFAULT_FACE_ID = "BACK"
DEFAULT_PATTERN = "11001100"


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
        cv2.CHAIN_APPROX_SIMPLE,
    )

    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if area < min_area or area > max_area:
            continue

        x, y, w, h = cv2.boundingRect(cnt)

        if h <= 0:
            continue

        aspect_ratio = w / h

        if aspect_ratio < min_aspect_ratio or aspect_ratio > max_aspect_ratio:
            continue

        cx = x + w / 2.0
        cy = y + h / 2.0

        candidates.append(
            {
                "x": int(x),
                "y": int(y),
                "w": int(w),
                "h": int(h),
                "cx": float(cx),
                "cy": float(cy),
                "area": float(area),
                "aspect_ratio": float(aspect_ratio),
            }
        )

    candidates.sort(key=lambda c: c["area"], reverse=True)
    return candidates


def clamp01(value):
    return max(0.0, min(1.0, value))


def pair_pixel_distance(c1, c2):
    return math.sqrt((c1["cx"] - c2["cx"]) ** 2 + (c1["cy"] - c2["cy"]) ** 2)


def score_pair(c1, c2, previous_valid_packet, image_width, image_height):
    dist = pair_pixel_distance(c1, c2)

    if dist <= 0:
        return -1.0

    area_min = min(c1["area"], c2["area"])
    area_max = max(c1["area"], c2["area"])
    area_similarity = area_min / area_max if area_max > 0 else 0.0

    dy = abs(c1["cy"] - c2["cy"])
    y_alignment = 1.0 - clamp01(dy / max(1.0, dist * 0.75))

    # Back LED pair in our datasets usually falls inside this broad range.
    # This is not a hard rule; it only gives a soft preference.
    if 35.0 <= dist <= 180.0:
        distance_plausibility = 1.0
    elif 20.0 <= dist < 35.0:
        distance_plausibility = 0.55
    elif 180.0 < dist <= 260.0:
        distance_plausibility = 0.55
    else:
        distance_plausibility = 0.15

    continuity_distance = 0.5
    continuity_midpoint = 0.5

    if previous_valid_packet is not None:
        prev_px = previous_valid_packet.get("pixel_distance")
        prev_mid = previous_valid_packet.get("midpoint_px")

        if prev_px is not None and prev_px > 0:
            rel_diff = abs(dist - prev_px) / max(prev_px, 1.0)
            continuity_distance = math.exp(-2.0 * rel_diff)

        if isinstance(prev_mid, list) and len(prev_mid) >= 2:
            mid_x = (c1["cx"] + c2["cx"]) / 2.0
            mid_y = (c1["cy"] + c2["cy"]) / 2.0

            dmid = math.sqrt((mid_x - prev_mid[0]) ** 2 + (mid_y - prev_mid[1]) ** 2)
            diag = math.sqrt(image_width ** 2 + image_height ** 2)
            continuity_midpoint = math.exp(-8.0 * dmid / max(diag, 1.0))

    score = (
        0.30 * area_similarity
        + 0.25 * y_alignment
        + 0.20 * distance_plausibility
        + 0.15 * continuity_distance
        + 0.10 * continuity_midpoint
    )

    return score


def select_pair(
    candidates,
    allow_more_than_two_candidates,
    pair_strategy,
    previous_valid_packet,
    image_width,
    image_height,
):
    if len(candidates) < 2:
        return None, None

    if not allow_more_than_two_candidates and len(candidates) != 2:
        return None, None

    if len(candidates) == 2:
        return (candidates[0], candidates[1]), 1.0

    if pair_strategy == "largest2":
        return (candidates[0], candidates[1]), None

    best_pair = None
    best_score = -1.0

    for c1, c2 in itertools.combinations(candidates, 2):
        score = score_pair(
            c1=c1,
            c2=c2,
            previous_valid_packet=previous_valid_packet,
            image_width=image_width,
            image_height=image_height,
        )

        if score > best_score:
            best_score = score
            best_pair = (c1, c2)

    return best_pair, best_score


def compute_observation(
    frame,
    candidates,
    pair,
    pair_score,
    model_a,
    model_b,
    pattern_accuracy,
    on_area_threshold,
    min_pixel_distance,
    min_distance_confidence,
):
    image_height, image_width = frame.shape[:2]
    image_center_x = image_width / 2.0
    image_center_y = image_height / 2.0

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

    if pair is None:
        reason = "PAIR_NOT_FOUND" if candidate_count < 2 else "CANDIDATE_COUNT_NOT_2"

        return {
            "valid": False,
            "reason": reason,
            "bit": bit,
            "pair_found": False,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "image_size": [image_width, image_height],
        }

    c1, c2 = pair

    led1_x = c1["cx"]
    led1_y = c1["cy"]
    led2_x = c2["cx"]
    led2_y = c2["cy"]

    pixel_distance = pair_pixel_distance(c1, c2)

    mid_x = (led1_x + led2_x) / 2.0
    mid_y = (led1_y + led2_y) / 2.0

    error_x = (mid_x - image_center_x) / image_center_x
    error_y = (image_center_y - mid_y) / image_center_y

    estimated_distance = estimate_distance(
        pixel_distance=pixel_distance,
        model_a=model_a,
        model_b=model_b,
    )

    dist_conf = distance_confidence(
        pixel_distance=pixel_distance,
        pattern_accuracy=pattern_accuracy,
    )

    valid = (
        pattern_accuracy >= 0.95
        and dist_conf >= min_distance_confidence
        and pixel_distance >= min_pixel_distance
    )

    if not valid:
        return {
            "valid": False,
            "reason": "LOW_CONFIDENCE",
            "bit": bit,
            "pair_found": True,
            "candidate_count": candidate_count,
            "total_area": total_area,
            "led1_px": [led1_x, led1_y],
            "led2_px": [led2_x, led2_y],
            "midpoint_px": [mid_x, mid_y],
            "error_norm": [error_x, error_y],
            "pixel_distance": pixel_distance,
            "estimated_distance": estimated_distance,
            "distance_confidence": dist_conf,
            "pair_score": pair_score,
            "image_size": [image_width, image_height],
        }

    return {
        "valid": True,
        "reason": "OK",
        "face_id": DEFAULT_FACE_ID,
        "pattern": DEFAULT_PATTERN,
        "pattern_accuracy": pattern_accuracy,
        "bit_error_count": 0,
        "bit_error_rate": 0.0,
        "bit": bit,
        "pair_found": True,
        "candidate_count": candidate_count,
        "total_area": total_area,
        "led1_px": [led1_x, led1_y],
        "led2_px": [led2_x, led2_y],
        "midpoint_px": [mid_x, mid_y],
        "error_norm": [error_x, error_y],
        "ray_cam": None,
        "pixel_distance": pixel_distance,
        "estimated_distance": estimated_distance,
        "distance_confidence": dist_conf,
        "pair_score": pair_score,
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
        "pair_score": None,
        "image_size": detection.get("image_size"),
        "held_observation": False,
        "held_age_s": None,
        "reason": detection.get("reason", "INVALID"),
    }


def get_hold_seconds_for_reason(reason, args):
    if reason == "BIT_OFF":
        return args.hold_bit_off

    if reason == "LOW_CONFIDENCE":
        return args.hold_low_confidence

    if reason == "CANDIDATE_COUNT_NOT_2":
        return args.hold_candidate_count_not_2

    if reason == "PAIR_NOT_FOUND":
        return args.hold_pair_not_found

    return args.hold_default


def packet_to_log_row(packet):
    err = packet.get("error_norm")

    if isinstance(err, list) and len(err) >= 2:
        error_x = err[0]
        error_y = err[1]
    else:
        error_x = None
        error_y = None

    return {
        "udp_seq": packet.get("udp_seq"),
        "frame": packet.get("frame"),
        "valid": packet.get("valid"),
        "held_observation": packet.get("held_observation"),
        "held_age_s": packet.get("held_age_s"),
        "reason": packet.get("reason"),
        "face_id": packet.get("face_id"),
        "bit": packet.get("bit"),
        "candidate_count": packet.get("candidate_count"),
        "total_area": packet.get("total_area"),
        "error_x": error_x,
        "error_y": error_y,
        "pixel_distance": packet.get("pixel_distance"),
        "estimated_distance": packet.get("estimated_distance"),
        "distance_confidence": packet.get("distance_confidence"),
        "pair_score": packet.get("pair_score"),
    }


def add_udp_fields(packet, seq):
    packet["udp_seq"] = seq
    packet["sent_time_unix"] = time.time()
    return packet


def save_log(log_rows, log_path):
    if not log_rows:
        return

    fieldnames = [
        "udp_seq",
        "frame",
        "valid",
        "held_observation",
        "held_age_s",
        "reason",
        "face_id",
        "bit",
        "candidate_count",
        "total_area",
        "error_x",
        "error_y",
        "pixel_distance",
        "estimated_distance",
        "distance_confidence",
        "pair_score",
    ]

    with log_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)


def run(args):
    video_path = Path(args.video)

    if not video_path.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    if source_fps <= 0:
        source_fps = args.source_fps_fallback

    send_step = max(1, int(round(source_fps / args.rate)))

    model_a, model_b = load_distance_model(args.distance_model_json)

    lower_back = parse_hsv(args.hsv_lower)
    upper_back = parse_hsv(args.hsv_upper)

    output_dir = Path(args.outputs_dir) / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)

    log_path = output_dir / args.log_name

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print("=== Live BACK video UDP sender V2 ===")
    print(f"video                         : {video_path}")
    print(f"dataset                       : {args.dataset}")
    print(f"video_opened                  : {cap.isOpened()}")
    print(f"source_fps                    : {source_fps}")
    print(f"frame_count                   : {frame_count}")
    print(f"detection_rate                : every video frame")
    print(f"send_rate                     : {args.rate}")
    print(f"send_step                     : {send_step}")
    print(f"udp_target                    : {args.ip}:{args.port}")
    print(f"allow_more_than_two_candidates: {args.allow_more_than_two_candidates}")
    print(f"pair_strategy                 : {args.pair_strategy}")
    print(f"hold_bit_off                  : {args.hold_bit_off}")
    print(f"hold_low_confidence           : {args.hold_low_confidence}")
    print(f"hold_candidate_count_not_2    : {args.hold_candidate_count_not_2}")
    print(f"hold_pair_not_found           : {args.hold_pair_not_found}")
    print(f"distance_model                : estimated_distance = {model_a} / pixel_distance + {model_b}")
    print(f"log_path                      : {log_path}")
    print(f"realtime                      : {not args.no_realtime}")
    print("")

    seq = 0
    sent_total = 0
    log_rows = []

    last_valid_packet = None
    last_valid_video_time = None

    try:
        while True:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            frame_id = 0
            video_loop_start_wall = time.perf_counter()

            last_valid_packet = None
            last_valid_video_time = None

            while True:
                ret, frame = cap.read()

                if not ret:
                    break

                video_time = frame_id / source_fps

                image_height, image_width = frame.shape[:2]

                candidates = find_led_candidates(
                    frame=frame,
                    lower_back=lower_back,
                    upper_back=upper_back,
                    min_area=args.min_area,
                    max_area=args.max_area,
                    min_aspect_ratio=args.min_aspect_ratio,
                    max_aspect_ratio=args.max_aspect_ratio,
                )

                pair, pair_score = select_pair(
                    candidates=candidates,
                    allow_more_than_two_candidates=args.allow_more_than_two_candidates,
                    pair_strategy=args.pair_strategy,
                    previous_valid_packet=last_valid_packet,
                    image_width=image_width,
                    image_height=image_height,
                )

                detection = compute_observation(
                    frame=frame,
                    candidates=candidates,
                    pair=pair,
                    pair_score=pair_score,
                    model_a=model_a,
                    model_b=model_b,
                    pattern_accuracy=args.pattern_accuracy,
                    on_area_threshold=args.on_area_threshold,
                    min_pixel_distance=args.min_pixel_distance,
                    min_distance_confidence=args.min_distance_confidence,
                )

                if detection.get("valid"):
                    current_packet = dict(detection)
                    current_packet["dataset"] = args.dataset
                    current_packet["frame"] = frame_id
                    current_packet["held_observation"] = False
                    current_packet["held_age_s"] = 0.0

                    last_valid_packet = dict(current_packet)
                    last_valid_video_time = video_time

                else:
                    reason = detection.get("reason", "INVALID")
                    allowed_hold = get_hold_seconds_for_reason(reason, args)

                    can_hold = (
                        last_valid_packet is not None
                        and last_valid_video_time is not None
                        and (video_time - last_valid_video_time) <= allowed_hold
                    )

                    if can_hold:
                        current_packet = dict(last_valid_packet)
                        current_packet["frame"] = frame_id
                        current_packet["held_observation"] = True
                        current_packet["held_age_s"] = video_time - last_valid_video_time
                        current_packet["reason"] = "HELD_DURING_" + reason
                    else:
                        current_packet = make_invalid_packet(
                            dataset=args.dataset,
                            frame_id=frame_id,
                            detection=detection,
                        )

                should_send = (frame_id % send_step) == 0

                if should_send:
                    packet = add_udp_fields(dict(current_packet), seq)

                    if not args.skip_send:
                        payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                        sock.sendto(payload, (args.ip, args.port))

                    log_rows.append(packet_to_log_row(packet))

                    if seq % max(1, int(args.rate)) == 0:
                        print(
                            f"seq={seq} "
                            f"frame={packet.get('frame')} "
                            f"valid={packet.get('valid')} "
                            f"held={packet.get('held_observation')} "
                            f"reason={packet.get('reason')} "
                            f"count={packet.get('candidate_count')} "
                            f"err={packet.get('error_norm')} "
                            f"dist={packet.get('estimated_distance')} "
                            f"px={packet.get('pixel_distance')} "
                            f"score={packet.get('pair_score')}"
                        )

                    seq += 1
                    sent_total += 1

                    if args.count is not None and sent_total >= args.count:
                        break

                if not args.no_realtime:
                    target_wall = video_loop_start_wall + video_time
                    sleep_time = target_wall - time.perf_counter()

                    if sleep_time > 0:
                        time.sleep(sleep_time)

                frame_id += 1

            if args.count is not None and sent_total >= args.count:
                break

            if not args.loop:
                break

        save_log(log_rows, log_path)

        print("")
        print(f"Finished. sent_total={sent_total}")
        print(f"Log saved: {log_path}")

    except KeyboardInterrupt:
        print("")
        print(f"Stopped by user. sent_total={sent_total}")
        save_log(log_rows, log_path)
        print(f"Log saved: {log_path}")

    finally:
        cap.release()


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument("--video", required=True)
    parser.add_argument("--dataset", required=True)

    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--skip-send", action="store_true")

    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--log-name", default="video_observation_log_v2.csv")

    parser.add_argument("--distance-model-json", default="outputs/calibration/distance_model_summary.json")

    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--source-fps-fallback", type=float, default=60.0)

    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--count", type=int, default=None)
    parser.add_argument("--no-realtime", action="store_true")

    parser.add_argument("--hsv-lower", default="54,83,172")
    parser.add_argument("--hsv-upper", default="95,147,226")

    parser.add_argument("--min-area", type=float, default=20.0)
    parser.add_argument("--max-area", type=float, default=6000.0)

    parser.add_argument("--min-aspect-ratio", type=float, default=0.25)
    parser.add_argument("--max-aspect-ratio", type=float, default=4.50)

    parser.add_argument("--on-area-threshold", type=float, default=35.0)

    parser.add_argument("--pattern-accuracy", type=float, default=1.0)
    parser.add_argument("--min-pixel-distance", type=float, default=20.0)
    parser.add_argument("--min-distance-confidence", type=float, default=0.60)

    parser.add_argument("--allow-more-than-two-candidates", action="store_true")
    parser.add_argument(
        "--pair-strategy",
        choices=["largest2", "best"],
        default="best",
    )

    parser.add_argument("--hold-default", type=float, default=0.0)
    parser.add_argument("--hold-bit-off", type=float, default=0.60)
    parser.add_argument("--hold-low-confidence", type=float, default=0.25)
    parser.add_argument("--hold-candidate-count-not-2", type=float, default=0.35)
    parser.add_argument("--hold-pair-not-found", type=float, default=0.15)

    args = parser.parse_args()
    run(args)


if __name__ == "__main__":
    main()
