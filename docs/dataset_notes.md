# Dataset Notes

Large datasets are not committed to GitHub.

Datasets should be stored externally as ZIP files using Google Drive, OneDrive, or another file-sharing service. The folder structure should be preserved so that scripts can run without manual path changes.

The repository should contain only small placeholder files such as `.gitkeep`.

---

## Recommended Local Dataset Structure

```text
datasets/
├── BackOnly_Test_01/
├── BackOnly_Test_02/
├── BackOnly_Test_03/
├── BackOnly_Test_04/
├── BackOnly_Test_05/
├── BackOnly_Test_06/
└── videos/
    ├── BackOnly_Dynamic_Test_01.mp4
    ├── BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4
    └── BackOnly_Dynamic_Clean_01_BLINK.mp4
```

Generated outputs should be placed under:

```text
outputs/
├── BackOnly_Test_04/
├── BackOnly_Dynamic_Test_01_v2/
├── BackOnly_Dynamic_Clean_01_CONSTANT_ON_v2/
├── BackOnly_Dynamic_Clean_01_BLINK_v2/
└── calibration/
```

---

## Dataset Types

This project currently uses two main dataset types:

```text
1. PNG frame sequence datasets
2. MP4 video datasets
```

They are used for different purposes.

---

## 1. PNG Frame Sequence Datasets

PNG sequences are preferred for calibration and exact image-processing analysis.

Use PNG datasets for:

* HSV threshold tuning,
* exact LED color analysis,
* exact contour-area analysis,
* pattern decoding,
* distance calibration,
* pixel-distance statistics,
* frame-level debugging without video compression artifacts.

PNG is the most reliable format when exact LED shape, color, bloom and edge behavior matter.

Example datasets:

```text
BackOnly_Test_01
BackOnly_Test_02
BackOnly_Test_03
BackOnly_Test_04
BackOnly_Test_05
BackOnly_Test_06
```

Known calibration set:

| Dataset          | Approx. distance | Notes                 |
| ---------------- | ---------------: | --------------------- |
| BackOnly_Test_01 |             1.47 | Initial reference     |
| BackOnly_Test_02 |             2.00 | Stable                |
| BackOnly_Test_03 |             2.50 | Usable                |
| BackOnly_Test_04 |             3.00 | Clean fixed-axis test |
| BackOnly_Test_05 |             4.00 | Clean fixed-axis test |
| BackOnly_Test_06 |             5.00 | Far-range boundary    |

Current distance model:

```text
estimated_distance = 168.628584 / pixel_distance + 0.609526
```

This model was created from the current back-only calibration datasets and is intended as a first control-side range cue, not as final metric localization.

---

## 2. MP4 Video Datasets

MP4 videos are now used for integration and stress testing.

Earlier notes said MP4 should only be used for demonstration. That is no longer accurate. MP4 should not replace PNG for final calibration, but it is useful for:

* dynamic movement tests,
* video-based OpenCV processing,
* UDP observation streaming tests,
* Linux controller integration tests,
* stress testing with occlusion,
* validating `held_observation`,
* testing `TRACK`, `INVALID_DECAY`, and `INVALID_STOP`,
* demonstration and reporting.

Important warning:

MP4/H.264 compression may change:

* HSV values,
* LED edge sharpness,
* bloom shape,
* contour area,
* candidate count,
* pixel distance,
* distance confidence.

Therefore:

```text
PNG → calibration and exact algorithm development
MP4 → integration, dynamic behavior, stress test, demonstration
```

---

## Current Dynamic Video Dataset

### BackOnly_Dynamic_Test_01.mp4

Type:

```text
Unity Recorder Movie / H.264 MP4
```

Path:

```text
datasets/videos/BackOnly_Dynamic_Test_01.mp4
```

Video properties:

```text
Resolution: 1920x1080
FPS: 60.0
Frame count: 1201
Duration: 20.0167 s
```

Scene:

* fixed camera,
* BACK LEDs active,
* leader robot moved manually using Python UDP keyboard control,
* temporary occlusion by fish,
* dynamic right/left movement,
* distance change,
* yaw test.

Known notes:

* Useful as a stress-test dataset.
* Contains temporary occlusion.
* Contains `BIT_OFF` frames.
* Some frames produce `LOW_CONFIDENCE`.
* Some frames produce more than two candidates.
* Requires `held_observation` and best-pair logic for stable processing.
* Not ideal as a clean control-tuning dataset.

Recommended use:

```text
Use for robustness and stress testing, not for clean calibration.
```

---

## Planned Clean Dynamic Datasets

### BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4

Purpose:

* clean tracking test,
* controller smoothing test,
* midpoint stability test,
* distance-response test,
* no blink-induced target loss.

LED behavior:

```text
BACK LEDs always ON
```

Expected properties:

```text
Resolution: 1920x1080
FPS: 60
No occlusion
No motion blur for first test
Slow movement
Fixed camera
```

Recommended motion:

```text
0–3 s     centered and still
3–6 s     target moves right in image
6–9 s     target moves left in image
9–12 s    target moves away
12–15 s   target moves closer than desired distance
15–18 s   mild yaw right/left
18–20 s   return near center
```

### BackOnly_Dynamic_Clean_01_BLINK.mp4

Purpose:

* pattern robustness test,
* `BIT_OFF` handling test,
* reason-based hold test,
* `held_observation` validation.

LED behavior:

```text
BACK LEDs use 11001100 pattern
```

This video should be recorded after the constant-ON version.

---

## Output Files

Typical output files:

```text
outputs/<DATASET_NAME>/back_pair_results.csv
outputs/<DATASET_NAME>/back_pair_distance_filtered.csv
outputs/<DATASET_NAME>/back_pattern_decode_summary.json
outputs/<DATASET_NAME>/observation_packet_frame_120.json
outputs/<DATASET_NAME>/video_observation_log.csv
outputs/<DATASET_NAME>/video_observation_log_v2.csv
outputs/<DATASET_NAME>/debug_overlay.mp4
```

Recommended policy:

* Do not commit generated CSV, JSON and MP4 output files unless they are intentionally small examples.
* Keep generated outputs local.
* Use external storage for full datasets and videos.

---

## Git Ignore Policy

Recommended `.gitignore` entries:

```gitignore
# Datasets
datasets/**/*.png
datasets/**/*.mp4
datasets/**/*.avi
datasets/**/*.mov

# Generated outputs
outputs/**/*.csv
outputs/**/*.json
outputs/**/*.mp4
outputs/**/*.avi
outputs/**/*.mov

# Keep placeholder folders
!datasets/.gitkeep
!outputs/.gitkeep
```

If a small sample output is needed for documentation, place it in a dedicated sample folder and document why it is committed.

---

## Naming Convention

Use descriptive dataset names.

### Static calibration datasets

```text
BackOnly_Test_01
BackOnly_Test_02
BackOnly_Test_03
BackOnly_Test_04
BackOnly_Test_05
BackOnly_Test_06
```

### Known-distance datasets

```text
BackOnly_1m
BackOnly_2m
BackOnly_3m
BackOnly_4m
BackOnly_5m
```

### Dynamic video datasets

```text
BackOnly_Dynamic_Test_01
BackOnly_Dynamic_Clean_01_CONSTANT_ON
BackOnly_Dynamic_Clean_01_BLINK
BackOnly_Lateral_Right_Left_01
BackOnly_Distance_In_Out_01
BackOnly_Yaw_Test_01
BackOnly_Occlusion_Test_01
```

---

## Recommended Metadata for Each Dataset

For every dataset or video, record the following information in notes:

```text
Dataset name:
Recording date:
Source environment: Unity / Unreal
Input type: PNG sequence / MP4 video
Resolution:
FPS:
Frame count:
Duration:
Camera:
LED mode: constant ON / blink pattern
Active face:
Pattern:
Motion sequence:
Approximate distance range:
Occlusion: yes/no
Motion blur: yes/no
Lighting notes:
Known issues:
Recommended use:
```

This metadata will make future comparison between Unity, Unreal, PNG, MP4 and live-render tests much easier.

```
```
