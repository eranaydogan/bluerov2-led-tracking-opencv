import argparse
import csv
import importlib.util
import json
import socket
import sys
import time
from pathlib import Path

import cv2
import mss
import numpy as np


def load_sender_v2_module():
    script_path = Path(__file__).resolve().parent / "13_live_back_video_sender_v2.py"

    if not script_path.exists():
        raise FileNotFoundError(f"Could not find sender V2 script: {script_path}")

    spec = importlib.util.spec_from_file_location("sender_v2", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sender_v2"] = module
    spec.loader.exec_module(module)
    return module


def build_capture_region(sct, args):
    monitors = sct.monitors

    if args.region_left is not None:
        required = [
            args.region_left,
            args.region_top,
            args.region_width,
            args.region_height,
        ]

        if any(v is None for v in required):
            raise ValueError(
                "If using manual region, provide all of: "
                "--region-left --region-top --region-width --region-height"
            )

        return {
            "left": int(args.region_left),
            "top": int(args.region_top),
            "width": int(args.region_width),
            "height": int(args.region_height),
        }

    if args.monitor < 0 or args.monitor >= len(monitors):
        raise ValueError(f"Invalid monitor index {args.monitor}. Available: 0..{len(monitors)-1}")

    return monitors[args.monitor]


def fmt(value, ndigits=3):
    if value is None:
        return "None"

    try:
        return f"{float(value):.{ndigits}f}"
    except (TypeError, ValueError):
        return str(value)


def draw_text_block(frame, lines, x=20, y=32, color=(255, 255, 255), scale=0.65):
    yy = y

    for line in lines:
        cv2.putText(
            frame,
            str(line),
            (x, yy),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            str(line),
            (x, yy),
            cv2.FONT_HERSHEY_SIMPLEX,
            scale,
            color,
            2,
            cv2.LINE_AA,
        )
        yy += int(30 * scale / 0.65)


def draw_overlay(frame, candidates, pair, pair_score, packet, raw_detection, fps_est, sent_total):
    out = frame.copy()
    h, w = out.shape[:2]

    center = (w // 2, h // 2)

    cv2.drawMarker(
        out,
        center,
        (255, 255, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=28,
        thickness=2,
    )

    # All candidates
    for i, c in enumerate(candidates):
        x, y, bw, bh = c["x"], c["y"], c["w"], c["h"]

        color = (0, 180, 255)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
        cv2.circle(out, (int(c["cx"]), int(c["cy"])), 4, color, -1)

        label = f"#{i} A={c['area']:.0f}"
        cv2.putText(
            out,
            label,
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            (0, 0, 0),
            3,
            cv2.LINE_AA,
        )
        cv2.putText(
            out,
            label,
            (x, max(20, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.45,
            color,
            1,
            cv2.LINE_AA,
        )

    # Selected pair
    if pair is not None:
        c1, c2 = pair

        for c in [c1, c2]:
            x, y, bw, bh = c["x"], c["y"], c["w"], c["h"]
            cv2.rectangle(out, (x, y), (x + bw, y + bh), (0, 255, 0), 3)
            cv2.circle(out, (int(c["cx"]), int(c["cy"])), 6, (0, 255, 0), -1)

        p1 = (int(c1["cx"]), int(c1["cy"]))
        p2 = (int(c2["cx"]), int(c2["cy"]))
        mid_x = int((c1["cx"] + c2["cx"]) / 2.0)
        mid_y = int((c1["cy"] + c2["cy"]) / 2.0)

        cv2.line(out, p1, p2, (0, 255, 0), 2)
        cv2.circle(out, (mid_x, mid_y), 7, (0, 255, 0), -1)
        cv2.line(out, center, (mid_x, mid_y), (255, 255, 0), 2)

    valid = packet.get("valid")
    held = packet.get("held_observation")
    reason = packet.get("reason")

    if valid and not held:
        status_color = (0, 255, 0)
    elif valid and held:
        status_color = (0, 255, 255)
    else:
        status_color = (0, 0, 255)

    err = packet.get("error_norm")
    if isinstance(err, list) and len(err) >= 2:
        err_x = err[0]
        err_y = err[1]
    else:
        err_x = None
        err_y = None

    lines = [
        f"valid={valid} held={held} reason={reason}",
        f"raw_reason={raw_detection.get('reason')}",
        f"candidate_count={len(candidates)} bit={raw_detection.get('bit')}",
        f"err_x={fmt(err_x)} err_y={fmt(err_y)}",
        f"px_dist={fmt(packet.get('pixel_distance'))}",
        f"est_dist={fmt(packet.get('estimated_distance'))}",
        f"dist_conf={fmt(packet.get('distance_confidence'))}",
        f"pair_score={fmt(pair_score)}",
        f"fps={fmt(fps_est, 1)} sent={sent_total}",
        "press q to quit",
    ]

    draw_text_block(out, lines, x=20, y=32, color=status_color)

    return out


def resize_for_preview(frame, scale):
    if scale == 1.0:
        return frame

    h, w = frame.shape[:2]
    new_w = max(1, int(w * scale))
    new_h = max(1, int(h * scale))

    return cv2.resize(frame, (new_w, new_h), interpolation=cv2.INTER_AREA)


def open_csv_log(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)

    f = log_path.open("w", encoding="utf-8", newline="")

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

    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()

    return f, writer


def main():
    sender_v2 = load_sender_v2_module()

    parser = argparse.ArgumentParser()

    parser.add_argument("--dataset", default="Unity_Live_Capture_01")

    parser.add_argument("--monitor", type=int, default=1)

    parser.add_argument("--region-left", type=int, default=None)
    parser.add_argument("--region-top", type=int, default=None)
    parser.add_argument("--region-width", type=int, default=None)
    parser.add_argument("--region-height", type=int, default=None)

    parser.add_argument("--ip", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5005)
    parser.add_argument("--skip-send", action="store_true")

    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--preview-scale", type=float, default=0.5)

    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--log-name", default="live_observation_log.csv")

    parser.add_argument("--distance-model-json", default="outputs/calibration/distance_model_summary.json")

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
    parser.add_argument("--pair-strategy", choices=["largest2", "best"], default="best")

    parser.add_argument("--hold-default", type=float, default=0.0)
    parser.add_argument("--hold-bit-off", type=float, default=0.60)
    parser.add_argument("--hold-low-confidence", type=float, default=0.25)
    parser.add_argument("--hold-candidate-count-not-2", type=float, default=0.35)
    parser.add_argument("--hold-pair-not-found", type=float, default=0.15)

    parser.add_argument("--count", type=int, default=None)

    args = parser.parse_args()

    period = 1.0 / args.rate

    output_dir = Path(args.outputs_dir) / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / args.log_name

    model_a, model_b = sender_v2.load_distance_model(args.distance_model_json)
    lower_back = sender_v2.parse_hsv(args.hsv_lower)
    upper_back = sender_v2.parse_hsv(args.hsv_upper)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    csv_file, csv_writer = open_csv_log(log_path)

    previous_valid_packet = None
    last_valid_time = None

    frame_id = 0
    seq = 0
    sent_total = 0

    last_print_time = 0.0
    last_fps_time = time.perf_counter()
    fps_counter = 0
    fps_est = 0.0

    with mss.MSS() as sct:
        region = build_capture_region(sct, args)

        print("=== Live Unity Window Sender ===")
        print(f"dataset                       : {args.dataset}")
        print(f"capture_region                : {region}")
        print(f"rate                          : {args.rate} Hz")
        print(f"udp_target                    : {args.ip}:{args.port}")
        print(f"skip_send                     : {args.skip_send}")
        print(f"preview                       : {args.preview}")
        print(f"allow_more_than_two_candidates: {args.allow_more_than_two_candidates}")
        print(f"pair_strategy                 : {args.pair_strategy}")
        print(f"distance_model                : estimated_distance = {model_a} / pixel_distance + {model_b}")
        print(f"log_path                      : {log_path}")
        print("")
        print("Press Ctrl+C in terminal or q in preview window to stop.")
        print("")

        try:
            while True:
                loop_start = time.perf_counter()
                now = time.time()

                screenshot = sct.grab(region)
                frame_bgra = np.array(screenshot)

                # MSS returns BGRA. OpenCV BGR needed.
                frame = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)

                image_height, image_width = frame.shape[:2]

                candidates = sender_v2.find_led_candidates(
                    frame=frame,
                    lower_back=lower_back,
                    upper_back=upper_back,
                    min_area=args.min_area,
                    max_area=args.max_area,
                    min_aspect_ratio=args.min_aspect_ratio,
                    max_aspect_ratio=args.max_aspect_ratio,
                )

                pair, pair_score = sender_v2.select_pair(
                    candidates=candidates,
                    allow_more_than_two_candidates=args.allow_more_than_two_candidates,
                    pair_strategy=args.pair_strategy,
                    previous_valid_packet=previous_valid_packet,
                    image_width=image_width,
                    image_height=image_height,
                )

                raw_detection = sender_v2.compute_observation(
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

                if raw_detection.get("valid"):
                    packet = dict(raw_detection)
                    packet["dataset"] = args.dataset
                    packet["frame"] = frame_id
                    packet["held_observation"] = False
                    packet["held_age_s"] = 0.0

                    previous_valid_packet = dict(packet)
                    last_valid_time = now

                else:
                    reason = raw_detection.get("reason", "INVALID")
                    allowed_hold = sender_v2.get_hold_seconds_for_reason(reason, args)

                    can_hold = (
                        previous_valid_packet is not None
                        and last_valid_time is not None
                        and (now - last_valid_time) <= allowed_hold
                    )

                    if can_hold:
                        packet = dict(previous_valid_packet)
                        packet["frame"] = frame_id
                        packet["held_observation"] = True
                        packet["held_age_s"] = now - last_valid_time
                        packet["reason"] = "HELD_DURING_" + reason
                    else:
                        packet = sender_v2.make_invalid_packet(
                            dataset=args.dataset,
                            frame_id=frame_id,
                            detection=raw_detection,
                        )

                packet = sender_v2.add_udp_fields(packet, seq)

                if not args.skip_send:
                    payload = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                    sock.sendto(payload, (args.ip, args.port))

                csv_writer.writerow(sender_v2.packet_to_log_row(packet))

                fps_counter += 1
                fps_now = time.perf_counter()

                if fps_now - last_fps_time >= 1.0:
                    fps_est = fps_counter / (fps_now - last_fps_time)
                    fps_counter = 0
                    last_fps_time = fps_now

                if args.preview:
                    overlay = draw_overlay(
                        frame=frame,
                        candidates=candidates,
                        pair=pair,
                        pair_score=pair_score,
                        packet=packet,
                        raw_detection=raw_detection,
                        fps_est=fps_est,
                        sent_total=sent_total,
                    )

                    preview = resize_for_preview(overlay, args.preview_scale)
                    cv2.imshow("Unity Live Detection Preview", preview)

                    key = cv2.waitKey(1) & 0xFF
                    if key == ord("q"):
                        print("Preview quit requested.")
                        break

                if time.time() - last_print_time >= 1.0:
                    last_print_time = time.time()

                    err = packet.get("error_norm")
                    if isinstance(err, list) and len(err) >= 2:
                        err_x = err[0]
                        err_y = err[1]
                    else:
                        err_x = None
                        err_y = None

                    print(
                        f"seq={seq} "
                        f"frame={frame_id} "
                        f"valid={packet.get('valid')} "
                        f"held={packet.get('held_observation')} "
                        f"reason={packet.get('reason')} "
                        f"count={packet.get('candidate_count')} "
                        f"err=({fmt(err_x)}, {fmt(err_y)}) "
                        f"dist={fmt(packet.get('estimated_distance'))} "
                        f"px={fmt(packet.get('pixel_distance'))} "
                        f"fps={fmt(fps_est, 1)}"
                    )

                seq += 1
                frame_id += 1
                sent_total += 1

                if args.count is not None and sent_total >= args.count:
                    break

                elapsed = time.perf_counter() - loop_start
                sleep_time = period - elapsed

                if sleep_time > 0:
                    time.sleep(sleep_time)

        except KeyboardInterrupt:
            print("")
            print("Stopped by user.")

        finally:
            csv_file.close()
            sock.close()

            if args.preview:
                cv2.destroyAllWindows()

            print("")
            print(f"Finished. sent_total={sent_total}")
            print(f"Log saved: {log_path}")


if __name__ == "__main__":
    main()
