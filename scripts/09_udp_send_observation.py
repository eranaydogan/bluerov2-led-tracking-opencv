# -*- coding: cp1254 -*-

import argparse
import json
import socket
import time
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Send a generated observation packet over UDP."
    )

    parser.add_argument(
        "--dataset",
        default="BackOnly_Test_04",
        help="Dataset name under outputs/, for example BackOnly_Test_04."
    )

    parser.add_argument(
        "--frame",
        type=int,
        default=None,
        help="Frame number of the packet file. If omitted, observation_packet_sample.json is used."
    )

    parser.add_argument(
        "--ip",
        default="127.0.0.1",
        help="Destination IP address. Use 127.0.0.1 for localhost test."
    )

    parser.add_argument(
        "--port",
        type=int,
        default=5005,
        help="Destination UDP port."
    )

    parser.add_argument(
        "--count",
        type=int,
        default=10,
        help="Number of packets to send."
    )

    parser.add_argument(
        "--rate",
        type=float,
        default=10.0,
        help="Send rate in Hz."
    )

    return parser.parse_args()


def load_packet(packet_path):
    if not packet_path.exists():
        raise FileNotFoundError(
            f"Packet file not found: {packet_path}\n"
            "Run 08_generate_observation_packet.py first."
        )

    with open(packet_path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    args = parse_args()

    project_root = Path(__file__).resolve().parents[1]
    output_folder = project_root / "outputs" / args.dataset

    if args.frame is None:
        packet_path = output_folder / "observation_packet_sample.json"
    else:
        packet_path = output_folder / f"observation_packet_frame_{args.frame}.json"

    packet = load_packet(packet_path)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    destination = (args.ip, args.port)

    if args.rate <= 0:
        interval = 0.0
    else:
        interval = 1.0 / args.rate

    print("UDP sender started.")
    print("Packet file:", packet_path)
    print("Destination:", destination)
    print("Count:", args.count)
    print("Rate:", args.rate, "Hz")

    for seq in range(args.count):
        packet_to_send = dict(packet)
        packet_to_send["udp_seq"] = seq
        packet_to_send["sent_time_unix"] = time.time()

        payload = json.dumps(packet_to_send).encode("utf-8")

        sock.sendto(payload, destination)

        print(
            f"Sent seq={seq}, bytes={len(payload)}, "
            f"valid={packet_to_send.get('valid')}, "
            f"frame={packet_to_send.get('frame')}, "
            f"error={packet_to_send.get('error_norm')}, "
            f"distance={packet_to_send.get('estimated_distance')}"
        )

        if interval > 0 and seq < args.count - 1:
            time.sleep(interval)

    sock.close()
    print("UDP sender finished.")


if __name__ == "__main__":
    main()
