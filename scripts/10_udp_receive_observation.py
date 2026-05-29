# -*- coding: cp1254 -*-

import argparse
import json
import socket
import time


def parse_args():
    parser = argparse.ArgumentParser(
        description="Receive observation packets over UDP."
    )

    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/IP to bind. Use 0.0.0.0 to listen on all interfaces."
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5005,
        help="UDP port to listen on."
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="Socket timeout in seconds. Default is no timeout."
    )

    return parser.parse_args()


def main():
    args = parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))

    if args.timeout is not None:
        sock.settimeout(args.timeout)

    print("UDP receiver started.")
    print("Listening on:", (args.host, args.port))
    print("Press Ctrl+C to stop.\n")

    try:
        while True:
            data, address = sock.recvfrom(8192)
            receive_time = time.time()

            try:
                packet = json.loads(data.decode("utf-8"))
            except json.JSONDecodeError:
                print("Received invalid JSON from:", address)
                print("Raw data:", data)
                continue

            sent_time = packet.get("sent_time_unix")
            latency_ms = None

            if sent_time is not None:
                latency_ms = (receive_time - float(sent_time)) * 1000.0

            print("-" * 70)
            print("From:", address)
            print("udp_seq:", packet.get("udp_seq"))
            print("valid:", packet.get("valid"))
            print("dataset:", packet.get("dataset"))
            print("frame:", packet.get("frame"))
            print("face_id:", packet.get("face_id"))
            print("pattern_accuracy:", packet.get("pattern_accuracy"))
            print("bit_error_rate:", packet.get("bit_error_rate"))
            print("error_norm:", packet.get("error_norm"))
            print("ray_cam:", packet.get("ray_cam"))
            print("pixel_distance:", packet.get("pixel_distance"))
            print("estimated_distance:", packet.get("estimated_distance"))
            print("distance_confidence:", packet.get("distance_confidence"))

            if latency_ms is not None:
                print(f"latency_ms: {latency_ms:.3f}")

    except KeyboardInterrupt:
        print("\nReceiver stopped by user.")

    finally:
        sock.close()


if __name__ == "__main__":
    main()
