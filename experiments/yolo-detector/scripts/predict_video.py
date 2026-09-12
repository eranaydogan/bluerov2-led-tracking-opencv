import argparse
import math
from pathlib import Path

import cv2
import torch
from ultralytics import YOLO


CLASS_ID_BLUEROV2 = 0


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Run a fine-tuned YOLOv8 BlueROV2 detector on recorded "
            "simulation footage and extract image-space target observations."
        )
    )

    parser.add_argument(
        "--model",
        required=True,
        help="Path to the trained YOLO weights, e.g. best.pt",
    )
    parser.add_argument(
        "--source",
        required=True,
        help="Path to the input video.",
    )
    parser.add_argument(
        "--imgsz",
        type=int,
        default=640,
        help="YOLO inference image size.",
    )
    parser.add_argument(
        "--conf",
        type=float,
        default=0.60,
        help="Minimum detection confidence.",
    )
    parser.add_argument(
        "--iou",
        type=float,
        default=0.50,
        help="IoU threshold used by non-maximum suppression.",
    )
    parser.add_argument(
        "--device",
        default="0" if torch.cuda.is_available() else "cpu",
        help="Ultralytics inference device, e.g. 0 or cpu.",
    )
    parser.add_argument(
        "--delay-ms",
        type=int,
        default=1,
        help="Display delay between frames.",
    )
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the annotated output video.",
    )
    parser.add_argument(
        "--out",
        default="predicted_video.mp4",
        help="Output video path when --save is enabled.",
    )

    return parser.parse_args()


def select_best_detection(result, class_id=CLASS_ID_BLUEROV2):
    """Return the highest-confidence BlueROV2 bounding box."""

    best_detection = None
    best_confidence = -1.0

    for box in result.boxes:
        detected_class = int(box.cls.item())

        if detected_class != class_id:
            continue

        confidence = float(box.conf.item())

        if confidence > best_confidence:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())

            best_detection = {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2,
                "confidence": confidence,
            }

            best_confidence = confidence

    return best_detection


def compute_image_observation(detection, frame_width, frame_height):
    """
    Convert the selected bounding box into an image-space observation.

    The bounding-box center (u, v) provides the target position in the image.
    Normalized image-center errors are calculated in the same conceptual form
    later used by the project's visual-following perception pipeline.
    """

    u = (detection["x1"] + detection["x2"]) / 2.0
    v = (detection["y1"] + detection["y2"]) / 2.0

    image_center_u = frame_width / 2.0
    image_center_v = frame_height / 2.0

    error_u_px = u - image_center_u
    error_v_px = v - image_center_v

    radial_error_px = math.hypot(error_u_px, error_v_px)

    error_u_norm = error_u_px / max(image_center_u, 1.0)
    error_v_norm = error_v_px / max(image_center_v, 1.0)

    return {
        "u": u,
        "v": v,
        "error_u_px": error_u_px,
        "error_v_px": error_v_px,
        "radial_error_px": radial_error_px,
        "error_norm": (error_u_norm, error_v_norm),
    }


def main():
    args = parse_args()

    model_path = Path(args.model)
    source_path = Path(args.source)

    if not model_path.exists():
        raise FileNotFoundError(f"Model weights not found: {model_path}")

    if not source_path.exists():
        raise FileNotFoundError(f"Input video not found: {source_path}")

    model = YOLO(str(model_path))

    capture = cv2.VideoCapture(str(source_path))

    if not capture.isOpened():
        raise RuntimeError(f"Could not open video: {source_path}")

    frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0

    image_center = (
        int(frame_width / 2),
        int(frame_height / 2),
    )

    writer = None

    if args.save:
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")

        writer = cv2.VideoWriter(
            args.out,
            fourcc,
            fps,
            (frame_width, frame_height),
        )

    use_half_precision = (
        torch.cuda.is_available()
        and args.device != "cpu"
    )

    while True:
        success, frame = capture.read()

        if not success:
            break

        result = model.predict(
            frame,
            imgsz=args.imgsz,
            conf=args.conf,
            iou=args.iou,
            device=args.device,
            half=use_half_precision,
            verbose=False,
        )[0]

        detection = select_best_detection(result)

        output_frame = frame.copy()

        cv2.drawMarker(
            output_frame,
            image_center,
            (255, 255, 255),
            cv2.MARKER_CROSS,
            22,
            2,
        )

        if detection is not None:
            observation = compute_image_observation(
                detection,
                frame_width,
                frame_height,
            )

            x1 = detection["x1"]
            y1 = detection["y1"]
            x2 = detection["x2"]
            y2 = detection["y2"]
            confidence = detection["confidence"]

            u = observation["u"]
            v = observation["v"]
            error_u_norm, error_v_norm = observation["error_norm"]

            cv2.rectangle(
                output_frame,
                (x1, y1),
                (x2, y2),
                (0, 255, 0),
                2,
            )

            cv2.circle(
                output_frame,
                (int(u), int(v)),
                5,
                (0, 0, 255),
                -1,
            )

            cv2.line(
                output_frame,
                image_center,
                (int(u), int(v)),
                (0, 255, 255),
                2,
            )

            cv2.putText(
                output_frame,
                f"BlueROV2 {confidence:.2f}",
                (x1, max(20, y1 - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (0, 255, 0),
                2,
            )

            cv2.putText(
                output_frame,
                (
                    f"center=({u:.1f}, {v:.1f})  "
                    f"error_norm=({error_u_norm:+.3f}, "
                    f"{error_v_norm:+.3f})"
                ),
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.60,
                (240, 240, 240),
                2,
            )

        else:
            cv2.putText(
                output_frame,
                "BlueROV2 not detected",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 0, 255),
                2,
            )

        cv2.imshow(
            "BlueROV2 YOLOv8 Detection",
            output_frame,
        )

        if writer is not None:
            writer.write(output_frame)

        key = cv2.waitKey(args.delay_ms) & 0xFF

        if key == ord("q"):
            break

        if key == ord("s"):
            cv2.imwrite(
                "snapshot.png",
                output_frame,
            )

    capture.release()

    if writer is not None:
        writer.release()

    cv2.destroyAllWindows()

    if writer is not None:
        print(f"Annotated video saved to: {args.out}")
    else:
        print("Inference completed.")


if __name__ == "__main__":
    main()