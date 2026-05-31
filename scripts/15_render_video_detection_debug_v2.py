import argparse
import importlib.util
import sys
from pathlib import Path

import cv2


def load_sender_v2_module():
    script_path = Path(__file__).resolve().parent / "13_live_back_video_sender_v2.py"

    if not script_path.exists():
        raise FileNotFoundError(f"Could not find sender V2 script: {script_path}")

    spec = importlib.util.spec_from_file_location("sender_v2", script_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["sender_v2"] = module
    spec.loader.exec_module(module)
    return module


def draw_text_block(frame, lines, x=20, y=32, color=(255, 255, 255)):
    yy = y

    for line in lines:
        cv2.putText(
            frame,
            str(line),
            (x, yy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            (0, 0, 0),
            4,
            cv2.LINE_AA,
        )
        cv2.putText(
            frame,
            str(line),
            (x, yy),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.62,
            color,
            2,
            cv2.LINE_AA,
        )
        yy += 28


def fmt(value, ndigits=3):
    if value is None:
        return "None"

    try:
        return f"{float(value):.{ndigits}f}"
    except (TypeError, ValueError):
        return str(value)


def draw_overlay(frame, frame_id, candidates, pair, pair_score, packet, raw_detection):
    out = frame.copy()
    h, w = out.shape[:2]

    center = (w // 2, h // 2)

    # Image center
    cv2.drawMarker(
        out,
        center,
        (255, 255, 255),
        markerType=cv2.MARKER_CROSS,
        markerSize=28,
        thickness=2,
    )

    # Draw all candidates
    for i, c in enumerate(candidates):
        x, y, bw, bh = c["x"], c["y"], c["w"], c["h"]

        # orange/yellow candidate boxes
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

    # Draw selected pair
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
        f"frame={frame_id}",
        f"valid={valid} held={held} reason={reason}",
        f"raw_reason={raw_detection.get('reason')}",
        f"candidate_count={len(candidates)} bit={raw_detection.get('bit')}",
        f"err_x={fmt(err_x)} err_y={fmt(err_y)}",
        f"px_dist={fmt(packet.get('pixel_distance'))}",
        f"est_dist={fmt(packet.get('estimated_distance'))}",
        f"dist_conf={fmt(packet.get('distance_confidence'))}",
        f"pair_score={fmt(pair_score)}",
        f"held_age_s={fmt(packet.get('held_age_s'))}",
    ]

    draw_text_block(out, lines, x=20, y=32, color=status_color)

    # Small legend
    legend_lines = [
        "orange: all candidates",
        "green: selected V2 pair",
        "cyan line: image center to pair midpoint",
    ]
    draw_text_block(out, legend_lines, x=20, y=h - 85, color=(255, 255, 255))

    return out


def main():
    sender_v2 = load_sender_v2_module()

    parser = argparse.ArgumentParser()

    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)

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

    parser.add_argument("--max-frames", type=int, default=None)

    args = parser.parse_args()

    video_path = Path(args.video)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    source_fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    if source_fps <= 0:
        source_fps = 60.0

    model_a, model_b = sender_v2.load_distance_model(args.distance_model_json)

    lower_back = sender_v2.parse_hsv(args.hsv_lower)
    upper_back = sender_v2.parse_hsv(args.hsv_upper)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(output_path), fourcc, source_fps, (width, height))

    if not writer.isOpened():
        raise RuntimeError(f"Could not open output video writer: {output_path}")

    print("=== Render Video Detection Debug Overlay V2 ===")
    print(f"video                         : {video_path}")
    print(f"output                        : {output_path}")
    print(f"source_fps                    : {source_fps}")
    print(f"frame_count                   : {frame_count}")
    print(f"resolution                    : {width}x{height}")
    print(f"allow_more_than_two_candidates: {args.allow_more_than_two_candidates}")
    print(f"pair_strategy                 : {args.pair_strategy}")
    print(f"distance_model                : estimated_distance = {model_a} / pixel_distance + {model_b}")
    print("")

    previous_valid_packet = None
    last_valid_video_time = None

    frame_id = 0

    while True:
        ret, frame = cap.read()

        if not ret:
            break

        if args.max_frames is not None and frame_id >= args.max_frames:
            break

        video_time = frame_id / source_fps

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
            packet["dataset"] = output_path.stem
            packet["frame"] = frame_id
            packet["held_observation"] = False
            packet["held_age_s"] = 0.0

            previous_valid_packet = dict(packet)
            last_valid_video_time = video_time

        else:
            reason = raw_detection.get("reason", "INVALID")
            allowed_hold = sender_v2.get_hold_seconds_for_reason(reason, args)

            can_hold = (
                previous_valid_packet is not None
                and last_valid_video_time is not None
                and (video_time - last_valid_video_time) <= allowed_hold
            )

            if can_hold:
                packet = dict(previous_valid_packet)
                packet["frame"] = frame_id
                packet["held_observation"] = True
                packet["held_age_s"] = video_time - last_valid_video_time
                packet["reason"] = "HELD_DURING_" + reason
            else:
                packet = sender_v2.make_invalid_packet(
                    dataset=output_path.stem,
                    frame_id=frame_id,
                    detection=raw_detection,
                )

        overlay = draw_overlay(
            frame=frame,
            frame_id=frame_id,
            candidates=candidates,
            pair=pair,
            pair_score=pair_score,
            packet=packet,
            raw_detection=raw_detection,
        )

        writer.write(overlay)

        if frame_id % 60 == 0:
            print(
                f"frame={frame_id} "
                f"valid={packet.get('valid')} "
                f"held={packet.get('held_observation')} "
                f"reason={packet.get('reason')} "
                f"raw_reason={raw_detection.get('reason')} "
                f"count={len(candidates)} "
                f"err={packet.get('error_norm')} "
                f"dist={packet.get('estimated_distance')} "
                f"score={pair_score}"
            )

        frame_id += 1

    cap.release()
    writer.release()

    print("")
    print(f"Finished. frames_written={frame_id}")
    print(f"Output saved: {output_path}")


if __name__ == "__main__":
    main()
