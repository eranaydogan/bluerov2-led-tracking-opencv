import argparse
import json
from pathlib import Path

import cv2
import mss
import numpy as np


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--monitor", type=int, default=1)
    parser.add_argument("--scale", type=float, default=0.5)
    parser.add_argument("--output-json", default="outputs/screen_debug/capture_region.json")
    parser.add_argument("--output-png", default="outputs/screen_debug/full_monitor.png")
    args = parser.parse_args()

    out_json = Path(args.output_json)
    out_png = Path(args.output_png)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_png.parent.mkdir(parents=True, exist_ok=True)

    with mss.MSS() as sct:
        monitors = sct.monitors

        if args.monitor < 0 or args.monitor >= len(monitors):
            raise ValueError(f"Invalid monitor index {args.monitor}. Available: 0..{len(monitors)-1}")

        region = monitors[args.monitor]
        shot = sct.grab(region)

    frame_bgra = np.array(shot)
    frame = cv2.cvtColor(frame_bgra, cv2.COLOR_BGRA2BGR)

    cv2.imwrite(str(out_png), frame)

    h, w = frame.shape[:2]

    if args.scale <= 0:
        args.scale = 1.0

    preview_w = int(w * args.scale)
    preview_h = int(h * args.scale)

    preview = cv2.resize(frame, (preview_w, preview_h), interpolation=cv2.INTER_AREA)

    print("")
    print("Select the Unity Game View / camera image area.")
    print("Drag rectangle with mouse, then press ENTER or SPACE.")
    print("Press C to cancel.")
    print("")

    roi = cv2.selectROI("Select Game View ROI", preview, showCrosshair=True, fromCenter=False)
    cv2.destroyAllWindows()

    x, y, rw, rh = roi

    if rw <= 0 or rh <= 0:
        print("No ROI selected.")
        return

    left = int(x / args.scale)
    top = int(y / args.scale)
    width = int(rw / args.scale)
    height = int(rh / args.scale)

    capture_region = {
        "region_left": left,
        "region_top": top,
        "region_width": width,
        "region_height": height,
    }

    out_json.write_text(json.dumps(capture_region, indent=2), encoding="utf-8")

    print("")
    print("Selected capture region:")
    print(f"--region-left {left} --region-top {top} --region-width {width} --region-height {height}")
    print("")
    print(f"Saved screenshot : {out_png}")
    print(f"Saved region     : {out_json}")
    print("")


if __name__ == "__main__":
    main()
