import argparse
import csv
from collections import Counter
from pathlib import Path


def parse_bool(value):
    if value is None:
        return False

    text = str(value).strip().lower()
    return text in ["true", "1", "yes", "y"]


def parse_float(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["none", "null", "nan"]:
        return None

    try:
        return float(text)
    except ValueError:
        return None


def parse_int(value):
    if value is None:
        return None

    text = str(value).strip()

    if text == "" or text.lower() in ["none", "null", "nan"]:
        return None

    try:
        return int(float(text))
    except ValueError:
        return None


def load_rows(path):
    rows = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            rows.append(row)

    return rows


def numeric_stats(values):
    clean = [v for v in values if v is not None]

    if not clean:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
        }

    return {
        "count": len(clean),
        "min": min(clean),
        "max": max(clean),
        "mean": sum(clean) / len(clean),
    }


def print_stats(name, values):
    s = numeric_stats(values)

    print(f"{name}:")
    print(f"  count : {s['count']}")

    if s["count"] == 0:
        print("  min   : None")
        print("  max   : None")
        print("  mean  : None")
        return

    print(f"  min   : {s['min']:.6f}")
    print(f"  max   : {s['max']:.6f}")
    print(f"  mean  : {s['mean']:.6f}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--csv",
        default="outputs/BackOnly_Dynamic_Test_01/video_observation_log.csv",
        help="Path to video_observation_log.csv"
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)

    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows = load_rows(csv_path)

    total = len(rows)

    valid_flags = [parse_bool(r.get("valid")) for r in rows]
    held_flags = [parse_bool(r.get("held_observation")) for r in rows]

    valid_count = sum(valid_flags)
    invalid_count = total - valid_count
    held_count = sum(held_flags)

    reason_counter = Counter((r.get("reason") or "UNKNOWN") for r in rows)
    face_counter = Counter((r.get("face_id") or "None") for r in rows)
    candidate_counter = Counter(parse_int(r.get("candidate_count")) for r in rows)

    error_x_values = [
        parse_float(r.get("error_x"))
        for r in rows
        if parse_bool(r.get("valid"))
    ]

    error_y_values = [
        parse_float(r.get("error_y"))
        for r in rows
        if parse_bool(r.get("valid"))
    ]

    pixel_distance_values = [
        parse_float(r.get("pixel_distance"))
        for r in rows
        if parse_bool(r.get("valid"))
    ]

    estimated_distance_values = [
        parse_float(r.get("estimated_distance"))
        for r in rows
        if parse_bool(r.get("valid"))
    ]

    distance_confidence_values = [
        parse_float(r.get("distance_confidence"))
        for r in rows
        if parse_bool(r.get("valid"))
    ]

    print("=== Video Observation Log Analysis ===")
    print(f"csv_path      : {csv_path}")
    print(f"total packets : {total}")
    print("")

    print("Packet state summary:")
    print(f"  valid_count   : {valid_count}")
    print(f"  invalid_count : {invalid_count}")
    print(f"  held_count    : {held_count}")

    if total > 0:
        print(f"  valid_ratio   : {valid_count / total:.3f}")
        print(f"  invalid_ratio : {invalid_count / total:.3f}")
        print(f"  held_ratio    : {held_count / total:.3f}")
    print("")

    print("Reason distribution:")
    for reason, count in reason_counter.most_common():
        ratio = count / total if total else 0.0
        print(f"  {reason:35s} {count:5d}  ({ratio:.3f})")
    print("")

    print("Face distribution:")
    for face, count in face_counter.most_common():
        ratio = count / total if total else 0.0
        print(f"  {face:10s} {count:5d}  ({ratio:.3f})")
    print("")

    print("Candidate count distribution:")
    for candidate_count, count in sorted(candidate_counter.items(), key=lambda x: (-1 if x[0] is None else x[0])):
        ratio = count / total if total else 0.0
        print(f"  {str(candidate_count):>5s} : {count:5d}  ({ratio:.3f})")
    print("")

    print_stats("error_x valid only", error_x_values)
    print("")
    print_stats("error_y valid only", error_y_values)
    print("")
    print_stats("pixel_distance valid only", pixel_distance_values)
    print("")
    print_stats("estimated_distance valid only", estimated_distance_values)
    print("")
    print_stats("distance_confidence valid only", distance_confidence_values)
    print("")

    print("Control interpretation hints:")

    if error_x_values:
        print(f"  error_x range: {min(error_x_values):.3f} to {max(error_x_values):.3f}")

        if min(error_x_values) < 0 and max(error_x_values) > 0:
            print("  OK: video contains both left and right image-error signs.")
        else:
            print("  WARNING: video does not clearly contain both left and right error signs.")

    if estimated_distance_values:
        print(f"  estimated_distance range: {min(estimated_distance_values):.3f} to {max(estimated_distance_values):.3f}")

        if min(estimated_distance_values) < 3.0 and max(estimated_distance_values) > 3.0:
            print("  OK: video crosses desired distance = 3.0.")
        else:
            print("  NOTE: video mostly stays on one side of desired distance = 3.0.")

    print("")
    print("Recommended next actions:")

    if invalid_count > valid_count:
        print("  - Invalid count is high. Improve detection or hold logic before live closed-loop tests.")

    if reason_counter.get("CANDIDATE_COUNT_NOT_2", 0) > 0:
        print("  - Add best-pair selection for candidate_count > 2.")

    if reason_counter.get("LOW_CONFIDENCE", 0) > 0:
        print("  - Check pixel-distance confidence thresholds and MP4 compression effects.")

    if reason_counter.get("BIT_OFF", 0) > 0:
        print("  - Reason-based hold can allow longer hold during BIT_OFF frames.")

    if held_count > 0:
        print("  - held_observation is active. Verify held duration is safe for control.")

    print("")


if __name__ == "__main__":
    main()
