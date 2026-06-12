import argparse
import csv
import importlib.util
import json
import socket
import sys
import time
from collections import deque
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
        cv2.putText(frame, str(line), (x, yy), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 4, cv2.LINE_AA)
        cv2.putText(frame, str(line), (x, yy), cv2.FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)
        yy += int(30 * scale / 0.65)


def draw_overlay(frame, candidates, pair, pair_score, packet, raw_detection, fps_est, sent_total,
                 red_pixel_count=0, red_on=0, pat_transitions=0, pat_fraction=0.0, pat_ready=False):
    out = frame.copy()
    h, w = out.shape[:2]
    center = (w // 2, h // 2)
    cv2.drawMarker(out, center, (255, 255, 255), markerType=cv2.MARKER_CROSS, markerSize=28, thickness=2)

    for i, c in enumerate(candidates):
        x, y, bw, bh = c["x"], c["y"], c["w"], c["h"]
        color = (0, 180, 255)
        cv2.rectangle(out, (x, y), (x + bw, y + bh), color, 2)
        cv2.circle(out, (int(c["cx"]), int(c["cy"])), 4, color, -1)
        label = f"#{i} A={c['area']:.0f}"
        cv2.putText(out, label, (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 0), 3, cv2.LINE_AA)
        cv2.putText(out, label, (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)

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

    # ---- KIRMIZI / PATERN gostergesi: SOL-ALT kose (yesil overlay'e dokunmaz) ----
    ready_txt = "READY" if pat_ready else "wait"
    red_label = (f"RED px={red_pixel_count} on={red_on} | "
                 f"gecis={pat_transitions} oran=%{pat_fraction*100:.0f} [{ready_txt}]")
    rx, ry = 20, h - 25
    (tw, th), _ = cv2.getTextSize(red_label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
    cv2.rectangle(out, (rx - 8, ry - th - 10), (rx + tw + 8, ry + 8), (0, 0, 0), -1)
    box_color = (0, 255, 255) if red_on else (255, 200, 0)
    cv2.putText(out, red_label, (rx, ry), cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2, cv2.LINE_AA)

    return out


def resize_for_preview(frame, scale):
    if scale == 1.0:
        return frame
    h, w = frame.shape[:2]
    return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)


def open_csv_log(log_path):
    log_path.parent.mkdir(parents=True, exist_ok=True)
    f = log_path.open("w", encoding="utf-8", newline="")
    fieldnames = [
        "udp_seq", "frame", "valid", "held_observation", "held_age_s", "reason",
        "face_id", "bit", "candidate_count", "total_area", "error_x", "error_y",
        "pixel_distance", "estimated_distance", "distance_confidence", "pair_score",
    ]
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    return f, writer


def parse_hsv_triplet(text):
    parts = [int(p.strip()) for p in text.split(",")]
    if len(parts) != 3:
        raise ValueError("HSV must be 'H,S,V'")
    return np.array(parts, dtype=np.uint8)


def count_red_pixels(frame_bgr, lo1, hi1, lo2, hi2):
    """Iki kirmizi aralik (HSV ~0 ve ~180) birlestirilir, kirmizi piksel sayilir.
    Yesil takibe DOKUNMAZ; ayni frame'i bagimsiz isler."""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    mask1 = cv2.inRange(hsv, lo1, hi1)
    mask2 = cv2.inRange(hsv, lo2, hi2)
    mask = cv2.bitwise_or(mask1, mask2)
    return int(cv2.countNonZero(mask)), mask


def analyze_red_pattern(red_window, window_sec, min_transitions, frac_lo, frac_hi):
    """PATERN DECODE -- emergency 'yanip sonen' kirmizi mi?

    red_window: deque of (timestamp, red_on)  -- zaman tabanli, FPS'ten bagimsiz.
    Karar = (1) pencere yeterince dolu (>= window_sec*0.9),
            (2) yeterli GECIS var (yanip soniyor: min_transitions),
            (3) on-orani DENGELI (frac_lo..frac_hi): ne hep-acik ne hep-kapali.

    Emergency  -> duzenli yanip soner -> cok gecis + dengeli oran -> TRUE.
    Sabit kirmizi (varil takili) -> oran ~1.0, gecis az -> FALSE.
    Kisa/seyrek ziplama (varil/balik) -> gecis az -> FALSE.

    Doner: (is_emergency, transitions, fraction, ready)
    """
    n = len(red_window)
    if n < 2:
        return False, 0, 0.0, False

    span = red_window[-1][0] - red_window[0][0]
    ready = span >= (window_sec * 0.9)

    # gecis sayisi
    transitions = 0
    prev = red_window[0][1]
    for _, on in list(red_window)[1:]:
        if on != prev:
            transitions += 1
            prev = on

    on_count = sum(on for _, on in red_window)
    fraction = on_count / n

    is_emergency = (
        ready
        and transitions >= min_transitions
        and (frac_lo <= fraction <= frac_hi)
    )
    return is_emergency, transitions, fraction, ready


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

    # ---- KIRMIZI (emergency) HSV araliklari (iki uc: ~0 ve ~180) ----
    parser.add_argument("--red-hsv1-lower", default="0,120,90")
    parser.add_argument("--red-hsv1-upper", default="10,255,255")
    parser.add_argument("--red-hsv2-lower", default="170,120,90")
    parser.add_argument("--red-hsv2-upper", default="180,255,255")

    # ---- KIRMIZI ASAMA 3: PATERN DECODE + ASCEND tetigi ----
    # Emergency = duzenli yanip sonen kirmizi. Sabit kirmizi (varil) ya da
    # seyrek ziplama (balik) REDDEDILIR. Periyottan bagimsiz (gecis+oran tabanli),
    # bu yuzden Unity/OpenCV FPS degisse de calisir.
    parser.add_argument("--red-pixel-threshold", type=float, default=1500.0,
                        help="Bir karede 'kirmizi var' esigi (varil~600-850, emergency~6000).")
    parser.add_argument("--pattern-window-sec", type=float, default=10.0,
                        help="Patern decode penceresi (saniye). ~3 periyot gozlemler. FPS bagimsiz.")
    parser.add_argument("--pattern-min-transitions", type=int, default=3,
                        help="Pencerede en az bu kadar yuksek<->dusuk gecisi (yanip sonme kaniti).")
    parser.add_argument("--pattern-frac-lo", type=float, default=0.45,
                        help="On-oraninin alt siniri. Altinda: cogu kapali -> emergency degil.")
    parser.add_argument("--pattern-frac-hi", type=float, default=0.92,
                        help="On-oraninin ust siniri. Ustunde: neredeyse hep acik (sabit kirmizi) -> REDDET.")
    parser.add_argument("--ascend-ip", default="127.0.0.1",
                        help="ASCEND sinyali hedefi (Unity makinesi). Yesil --ip'den AYRI.")
    parser.add_argument("--ascend-port", type=int, default=5014)
    parser.add_argument("--ascend-message", default="ASCEND")
    parser.add_argument("--ascend-repeat", type=int, default=5,
                        help="UDP kaybina karsi ASCEND'i kac kez yolla.")
    parser.add_argument("--red-log-name", default="red_detection_log.csv",
                        help="Kirmizi olcum/patern analizi icin AYRI csv (yesil log'a dokunmaz).")
    parser.add_argument("--no-ascend", action="store_true",
                        help="Tetigi devre disi birak (sadece olcum+csv+patern analizi, ASCEND yollanmaz).")

    args = parser.parse_args()

    period = 1.0 / args.rate

    output_dir = Path(args.outputs_dir) / args.dataset
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / args.log_name

    model_a, model_b = sender_v2.load_distance_model(args.distance_model_json)
    lower_back = sender_v2.parse_hsv(args.hsv_lower)
    upper_back = sender_v2.parse_hsv(args.hsv_upper)

    red_lo1 = parse_hsv_triplet(args.red_hsv1_lower)
    red_hi1 = parse_hsv_triplet(args.red_hsv1_upper)
    red_lo2 = parse_hsv_triplet(args.red_hsv2_lower)
    red_hi2 = parse_hsv_triplet(args.red_hsv2_upper)
    red_pixel_count = 0

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    ascend_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    csv_file, csv_writer = open_csv_log(log_path)

    # ---- KIRMIZI patern analizi icin AYRI csv (yesil log'a dokunmaz) ----
    red_log_path = output_dir / args.red_log_name
    red_csv_file = red_log_path.open("w", encoding="utf-8", newline="")
    red_csv_writer = csv.writer(red_csv_file)
    red_csv_writer.writerow(
        ["seq", "frame", "t_rel", "red_pixel_count", "red_on", "transitions", "fraction", "ready"]
    )

    # ---- PATERN DECODE: zaman-tabanli kayan pencere (FPS'ten bagimsiz) ----
    red_window = deque()  # her eleman: (timestamp, red_on)
    red_threshold = args.red_pixel_threshold
    pat_window_sec = args.pattern_window_sec
    pat_min_trans = args.pattern_min_transitions
    pat_frac_lo = args.pattern_frac_lo
    pat_frac_hi = args.pattern_frac_hi
    ascend_triggered = False
    run_start = time.perf_counter()

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

        print("=== Live Unity Window Sender (Stage 3: PATTERN DECODE + ascend) ===")
        print(f"dataset                       : {args.dataset}")
        print(f"capture_region                : {region}")
        print(f"rate                          : {args.rate} Hz")
        print(f"udp_target (green)            : {args.ip}:{args.port}")
        print(f"ascend_target (red)           : {args.ascend_ip}:{args.ascend_port}")
        print(f"red_threshold                 : {red_threshold} px")
        print(f"pattern window/min_trans/frac : {pat_window_sec}s / {pat_min_trans} / "
              f"{pat_frac_lo}-{pat_frac_hi}")
        print(f"no_ascend                     : {args.no_ascend}")
        print(f"green_log                     : {log_path}")
        print(f"red_log                       : {red_log_path}")
        print("")
        print("Press Ctrl+C in terminal or q in preview window to stop.")
        print("")

        try:
            while True:
                loop_start = time.perf_counter()
                now = time.time()

                screenshot = sct.grab(region)
                frame_bgra = np.array(screenshot)
                frame = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)

                image_height, image_width = frame.shape[:2]

                # ===== KIRMIZI OLCUM -- yesil takibe dokunmaz =====
                red_pixel_count, _red_mask = count_red_pixels(
                    frame, red_lo1, red_hi1, red_lo2, red_hi2
                )

                # ===== PATERN DECODE: zaman-tabanli pencere + analiz =====
                t_now = time.perf_counter()
                t_rel = t_now - run_start
                red_on = 1 if red_pixel_count >= red_threshold else 0

                red_window.append((t_now, red_on))
                while red_window and (t_now - red_window[0][0]) > pat_window_sec:
                    red_window.popleft()

                is_emergency, pat_trans, pat_frac, pat_ready = analyze_red_pattern(
                    red_window, pat_window_sec, pat_min_trans, pat_frac_lo, pat_frac_hi
                )

                if (not ascend_triggered) and (not args.no_ascend) and is_emergency:
                    ascend_triggered = True
                    print("")
                    print("=" * 64)
                    print(f">>> EMERGENCY PATERNI COZULDU (gecis={pat_trans} oran=%{pat_frac*100:.0f}) "
                          f"-- ASCEND GONDERILIYOR ({args.ascend_ip}:{args.ascend_port})")
                    print("=" * 64)
                    try:
                        for _ in range(args.ascend_repeat):
                            ascend_sock.sendto(args.ascend_message.encode("utf-8"),
                                               (args.ascend_ip, args.ascend_port))
                        time.sleep(0.2)  # paketlerin cikmasini bekle
                    except Exception as e:
                        print(f"[UYARI] ASCEND gonderilemedi: {e}")

                # ===== YESIL TAKIP (mevcut, dokunulmaz) =====
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

                # ---- KIRMIZI csv satiri (HER kare) -- patern analizi ham verisi ----
                red_csv_writer.writerow([
                    seq, frame_id, f"{t_rel:.4f}",
                    red_pixel_count, red_on, pat_trans, f"{pat_frac:.3f}", int(pat_ready),
                ])

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
                        red_pixel_count=red_pixel_count,
                        red_on=red_on,
                        pat_transitions=pat_trans,
                        pat_fraction=pat_frac,
                        pat_ready=pat_ready,
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
                        f"seq={seq} frame={frame_id} "
                        f"valid={packet.get('valid')} held={packet.get('held_observation')} "
                        f"reason={packet.get('reason')} count={packet.get('candidate_count')} "
                        f"err=({fmt(err_x)}, {fmt(err_y)}) dist={fmt(packet.get('estimated_distance'))} "
                        f"px={fmt(packet.get('pixel_distance'))} fps={fmt(fps_est, 1)}"
                    )
                    print(f"[PATERN] kirmizi_px={red_pixel_count} on={red_on} "
                          f"gecis={pat_trans} oran=%{pat_frac*100:.0f} "
                          f"hazir={'E' if pat_ready else 'H'} "
                          f"{'>>>EMERGENCY COZULDU<<<' if ascend_triggered else ''}")

                seq += 1
                frame_id += 1
                sent_total += 1

                # Patern cozuldu: ASCEND yollandi, gorev bitti -> script kapan
                if ascend_triggered:
                    print(">>> ASCEND gonderildi. Gorev tamam, script kapaniyor.")
                    break

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
            red_csv_file.close()
            sock.close()
            ascend_sock.close()
            if args.preview:
                cv2.destroyAllWindows()
            print("")
            print(f"Finished. sent_total={sent_total}")
            print(f"Green log saved: {log_path}")
            print(f"Red log saved  : {red_log_path}")


if __name__ == "__main__":
    main()
