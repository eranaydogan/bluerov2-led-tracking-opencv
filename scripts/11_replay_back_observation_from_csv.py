import argparse
import csv
import json
import math
import socket
import time
from pathlib import Path


DEFAULT_FACE_ID = "BACK"
DEFAULT_PATTERN = "11001100"


def parse_bool(value):
    if value is None:
        return False

    if isinstance(value, bool):
        return value

    text = str(value).strip().lower()

    return text in ["1", "true", "yes", "y", "on"]


def parse_float(value, default=None):
    if value is None:
        return default

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null"]:
        return default

    try:
        return float(text)
    except ValueError:
        return default


def parse_int(value, default=None):
    if value is None:
        return default

    text = str(value).strip()

    if text == "" or text.lower() in ["nan", "none", "null"]:
        return default

    try:
        return int(float(text))
    except ValueError:
        return default


def load_json_if_exists(path):
    path = Path(path)

    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_distance_model(path):
    """
    Expected model:
        estimated_distance = A / pixel_distance + B

    The exact JSON keys may differ, so this function tries several likely names.
    """
    data = load_json_if_exists(path)

    candidates_a = [
        "A",
        "a",
        "coef_A",
        "coefficient_A",
        "model_A",
        "fitted_A",
    ]

    candidates_b = [
        "B",
        "b",
        "coef_B",
        "coefficient_B",
        "model_B",
        "fitted_B",
    ]

    a = None
    b = None

    for key in candidates_a:
        if key in data:
            a = parse_float(data.get(key))
            break

    for key in candidates_b:
        if key in data:
            b = parse_float(data.get(key))
            break

    # Try nested formats if they exist.
    if a is None or b is None:
        for container_key in ["model", "parameters", "fit", "distance_model"]:
            container = data.get(container_key)

            if isinstance(container, dict):
                if a is None:
                    for key in candidates_a:
                        if key in container:
                            a = parse_float(container.get(key))
                            break

                if b is None:
                    for key in candidates_b:
                        if key in container:
                            b = parse_float(container.get(key))
                            break

    # Known current fitted model from calibration report.
    if a is None:
        a = 168.628584

    if b is None:
        b = 0.609526

    return float(a), float(b), data


def estimate_distance_from_pixel_distance(pixel_distance, model_a, model_b):
    if pixel_distance is None or pixel_distance <= 0:
        return None

    return model_a / pixel_distance + model_b


def distance_confidence_from_pixel_distance(pixel_distance, valid_geometry):
    """
    Simple initial heuristic.

    BackOnly_Test_04 around 74 px should be high confidence.
    Far range around 37 px should be lower.
    """
    if not valid_geometry:
        return 0.0

    if pixel_distance is None:
        return 0.0

    if pixel_distance >= 70:
        return 1.0

    if pixel_distance >= 50:
        return 0.85

    if pixel_distance >= 35:
        return 0.65

    return 0.40


def load_pattern_metrics(path):
    data = load_json_if_exists(path)

    pattern_accuracy = (
        parse_float(data.get("global_accuracy"))
        or parse_float(data.get("pattern_accuracy"))
        or parse_float(data.get("local_score"))
        or 1.0
    )

    bit_error_count = (
        parse_int(data.get("bit_error_count"))
        if data.get("bit_error_count") is not None
        else 0
    )

    bit_error_rate = (
        parse_float(data.get("bit_error_rate"))
        if data.get("bit_error_rate") is not None
        else 0.0
    )

    pattern = (
        data.get("expected_pattern")
        or data.get("pattern")
        or data.get("target_pattern")
        or DEFAULT_PATTERN
    )

    return {
        "pattern": pattern,
        "pattern_accuracy": float(pattern_accuracy),
        "bit_error_count": int(bit_error_count),
        "bit_error_rate": float(bit_error_rate),
        "raw": data,
    }


def read_rows(csv_path):
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = []

    with csv_path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(row)

    rows.sort(key=lambda r: parse_int(r.get("frame"), 0))

    return rows


def row_to_packet(
    row,
    dataset,
    model_a,
    model_b,
    pattern_metrics,
    image_width_default=None,
    image_height_default=None,
    send_invalid=False,
):
    frame = parse_int(row.get("frame"), 0)

    bit = parse_int(row.get("bit"), 0)
    pair_found = parse_bool(row.get("pair_found"))
    candidate_count = parse_int(row.get("candidate_count"), 0)

    pixel_distance = parse_float(row.get("pixel_distance"))

    error_x = parse_float(row.get("error_x"))
    error_y = parse_float(row.get("error_y"))

    ray_x = parse_float(row.get("ray_x"))
    ray_y = parse_float(row.get("ray_y"))
    ray_z = parse_float(row.get("ray_z"))

    mid_x = parse_float(row.get("mid_x"))
    mid_y = parse_float(row.get("mid_y"))

    led1_x = parse_float(row.get("led1_x"))
    led1_y = parse_float(row.get("led1_y"))
    led2_x = parse_float(row.get("led2_x"))
    led2_y = parse_float(row.get("led2_y"))

    image_width = parse_int(row.get("image_width"), image_width_default)
    image_height = parse_int(row.get("image_height"), image_height_default)

    valid_geometry = (
        bit == 1
        and pair_found
        and candidate_count == 2
        and pixel_distance is not None
        and pixel_distance > 0
        and error_x is not None
        and error_y is not None
    )

    estimated_distance = estimate_distance_from_pixel_distance(
        pixel_distance,
        model_a,
        model_b
    )

    distance_confidence = distance_confidence_from_pixel_distance(
        pixel_distance,
        valid_geometry
    )

    valid = (
        valid_geometry
        and pattern_metrics["pattern_accuracy"] >= 0.95
        and distance_confidence >= 0.60
    )

    if not valid and not send_invalid:
        return None

    if not valid:
        return {
            "dataset": dataset,
            "frame": frame,
            "valid": False,
            "face_id": None,
            "pattern": pattern_metrics["pattern"],
            "pattern_accuracy": pattern_metrics["pattern_accuracy"],
            "bit_error_count": pattern_metrics["bit_error_count"],
            "bit_error_rate": pattern_metrics["bit_error_rate"],
            "pair_found": bool(pair_found),
            "candidate_count": candidate_count,
            "led1_px": None,
            "led2_px": None,
            "midpoint_px": None,
            "error_norm": [0.0, 0.0],
            "ray_cam": None,
            "pixel_distance": None,
            "estimated_distance": None,
            "distance_confidence": 0.0,
            "image_size": [image_width, image_height],
        }

    return {
        "dataset": dataset,
        "frame": frame,
        "valid": True,
        "face_id": DEFAULT_FACE_ID,
        "pattern": pattern_metrics["pattern"],
        "pattern_accuracy": pattern_metrics["pattern_accuracy"],
        "bit_error_count": pattern_metrics["bit_error_count"],
        "bit_error_rate": pattern_metrics["bit_error_rate"],
        "pair_found": True,
        "candidate_count": candidate_count,
        "led1_px": [led1_x, led1_y],
        "led2_px": [led2_x, led2_y],
        "midpoint_px": [mid_x, mid_y],
        "error_norm": [error_x, error_y],
        "ray_cam": [ray_x, ray_y, ray_z],
        "pixel_distance": pixel_distance,
        "estimated_distance": estimated_distance,
        "distance_confidence": distance_confidence,
        "image_size": [image_width, image_height],
    }


def build_packets(
    dataset,
    rows,
    model_a,
    model_b,
    pattern_metrics,
    send_invalid=False,
):
    packets = []

    for row in rows:
        packet = row_to_packet(
            row=row,
            dataset=dataset,
            model_a=model_a,
            model_b=model_b,
            pattern_metrics=pattern_metrics,
            send_invalid=send_invalid,
        )

        if packet is not None:
            packets.append(packet)

    return packets


def send_packets(sock, packets, ip, port, rate, loop, max_count=None):
    period = 1.0 / rate
    seq = 0
    sent_total = 0

    print(f"Sending UDP packets to {ip}:{port}")
    print(f"rate={rate} Hz, loop={loop}, packet_count={len(packets)}")
    print("Press Ctrl+C to stop.")
    print("")

    try:
        while True:
            for packet in packets:
                packet = dict(packet)
                packet["udp_seq"] = seq
                packet["sent_time_unix"] = time.time()

                data = json.dumps(packet, separators=(",", ":")).encode("utf-8")
                sock.sendto(data, (ip, port))

                if seq % max(1, int(rate)) == 0:
                    print(
                        f"seq={seq} "
                        f"frame={packet.get('frame')} "
                        f"valid={packet.get('valid')} "
                        f"face={packet.get('face_id')} "
                        f"err={packet.get('error_norm')} "
                        f"dist={packet.get('estimated_distance')} "
                        f"px={packet.get('pixel_distance')}"
                    )

                seq += 1
                sent_total += 1

                if max_count is not None and sent_total >= max_count:
                    print("")
                    print(f"Finished. sent_total={sent_total}")
                    return

                time.sleep(period)

            if not loop:
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
    parser.add_argument("--rate", type=float, default=20.0)
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--count", type=int, default=None)

    parser.add_argument("--send-invalid", action="store_true")

    parser.add_argument("--outputs-dir", default="outputs")
    parser.add_argument("--csv-name", default="back_pair_results.csv")
    parser.add_argument("--pattern-json-name", default="back_pattern_decode_summary.json")
    parser.add_argument("--distance-model-json", default="outputs/calibration/distance_model_summary.json")

    args = parser.parse_args()

    root = Path(".")
    dataset_dir = root / args.outputs_dir / args.dataset

    csv_path = dataset_dir / args.csv_name
    pattern_json_path = dataset_dir / args.pattern_json_name
    distance_model_path = root / args.distance_model_json

    print("=== Replay BACK observation packets from CSV ===")
    print(f"dataset              : {args.dataset}")
    print(f"csv_path             : {csv_path}")
    print(f"pattern_json_path    : {pattern_json_path}")
    print(f"distance_model_path  : {distance_model_path}")
    print(f"send_invalid         : {args.send_invalid}")
    print("")

    rows = read_rows(csv_path)
    pattern_metrics = load_pattern_metrics(pattern_json_path)
    model_a, model_b, model_raw = load_distance_model(distance_model_path)

    print(f"Loaded rows          : {len(rows)}")
    print(f"Pattern              : {pattern_metrics['pattern']}")
    print(f"Pattern accuracy     : {pattern_metrics['pattern_accuracy']}")
    print(f"Bit error rate       : {pattern_metrics['bit_error_rate']}")
    print(f"Distance model       : estimated_distance = {model_a} / pixel_distance + {model_b}")
    print("")

    packets = build_packets(
        dataset=args.dataset,
        rows=rows,
        model_a=model_a,
        model_b=model_b,
        pattern_metrics=pattern_metrics,
        send_invalid=args.send_invalid,
    )

    if not packets:
        raise RuntimeError("No packets were generated. Check CSV filters or use --send-invalid.")

    valid_count = sum(1 for p in packets if p.get("valid"))
    invalid_count = len(packets) - valid_count

    print(f"Generated packets    : {len(packets)}")
    print(f"Valid packets        : {valid_count}")
    print(f"Invalid packets      : {invalid_count}")
    print("")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    send_packets(
        sock=sock,
        packets=packets,
        ip=args.ip,
        port=args.port,
        rate=args.rate,
        loop=args.loop,
        max_count=args.count,
    )


if __name__ == "__main__":
    main()
