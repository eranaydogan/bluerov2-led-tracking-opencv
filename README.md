# BlueROV2 LED-Based Visual Tracking & Perception

Computer-vision and perception pipeline for a BlueROV2 visual-following system.

The project detects LED markers attached to a leader robot, estimates target alignment and relative distance, and generates controller-ready observations that can be streamed over UDP to a separate Linux control system.

This repository contains the **vision / perception subsystem** of the TÜBİTAK 2209-A supported graduation project:

**BlueROV2 LED-Based Target Tracking System & Distributed Co-Simulation**

The corresponding control-side repository is:

➡️ [bluerov2-led-control](https://github.com/eranaydogan/bluerov2-led-control)

---

## Demo & Results

### 3D Mission Replay

![BlueROV2 3D mission replay](docs/media/mission_replay_3d.gif)

Logged leader and follower poses reconstructed as a 3D mission replay.
The visualization shows trajectory history, vehicle heading, relative separation,
depth, target distance, and the emergency ASCEND transition.

During the tracking phase:

- Mean leader–follower distance: **4.97 m**
- Maximum leader–follower distance: **5.74 m**

Tracking metrics exclude the emergency ASCEND phase because the follower
intentionally leaves the leader after the failsafe is triggered.

### Full Visual Tracking Demo

▶️ [Watch the full tracking demo](docs/media/full_tracking_demo.mp4)

The full simulation recording shows the follower maintaining visual tracking
of the leader while maneuvering through the Unity environment.

## System Overview

```text
Unity Game View / recorded visual input
                ↓
        Live screen capture / video
                ↓
        OpenCV image processing
                ↓
        LED candidate detection
                ↓
        LED pair selection
                ↓
   Target midpoint + image-center error
                ↓
      Relative distance estimation
                ↓
     Observation validation / hold logic
                ↓
        UDP observation packet
                ↓
       Linux control subsystem
                ↓
       MAVLink / ArduSub / Gazebo
```

The repository evolved from controlled PNG-sequence experiments into a live perception pipeline capable of capturing the Unity Game View, processing observations in real time, and transmitting them to the control subsystem.

---

## Main Capabilities

### LED-Based Target Detection

The current tracking configuration focuses on the **BACK face** of the leader BlueROV2.

The perception pipeline:

- extracts LED candidates using HSV-based segmentation,
- evaluates candidate geometry,
- selects the most plausible LED pair,
- calculates the pair midpoint,
- computes normalized image-center error,
- estimates relative distance from LED pixel spacing,
- assigns detection and distance confidence,
- maintains short-term observations during temporary detection loss.

The system also supports candidate-pair selection when more than two possible blobs are visible.

---

### Relative Distance Estimation

Distance is estimated from the apparent pixel spacing between the two LEDs.

The calibrated model is:

```text
estimated_distance = 168.628584 / pixel_distance + 0.609526
```

Calibration performance:

```text
Mean Absolute Error : 0.116
RMSE                : 0.131
```

The model is intended as a relative control cue rather than a high-precision metric localization system.

---

### Controller-Ready Observation Output

The perception side produces observations containing fields such as:

```text
valid
face_id
pattern_accuracy
distance_confidence
error_norm
pixel_distance
estimated_distance
held_observation
udp_seq
```

Example:

```json
{
  "valid": true,
  "face_id": "BACK",
  "pattern_accuracy": 1.0,
  "error_norm": [-0.0729, -0.0287],
  "pixel_distance": 74.0068,
  "estimated_distance": 2.8881,
  "distance_confidence": 1.0
}
```

The observation packet is streamed over UDP to the Linux-side controller.

---

## Live Unity Perception

The project currently supports live capture of the Unity Game View using `mss`.

Validated pipeline:

```text
Unity Game View
→ screen capture
→ OpenCV LED detection
→ LED pair selection
→ observation generation
→ UDP streaming
```

The live sender supports:

- configurable screen-capture regions,
- real-time OpenCV processing,
- LED candidate visualization,
- selected-pair visualization,
- normalized image error calculation,
- relative distance estimation,
- CSV logging,
- UDP transmission,
- temporary observation holding,
- configurable confidence thresholds.

The current main live script is:

```text
scripts/18_live_unity_window_sender.py
```

---

## Emergency LED Pattern Detection

The latest live perception stage also contains a separate **red emergency LED detector**.

This logic:

1. detects red pixels independently from the normal green tracking pipeline,
2. stores detections in a time-based sliding window,
3. evaluates ON/OFF transitions,
4. checks the active-time fraction,
5. distinguishes a flashing emergency signal from continuously visible red objects,
6. sends an `ASCEND` command over UDP when the emergency pattern is confirmed.

The emergency detection logic is intentionally separate from the primary tracking pipeline.

---

## Detection Performance

A clean constant-ON dynamic Unity video was evaluated using the V2 perception pipeline.

Results:

```text
Total observations : 401
Valid              : 342
Invalid            : 59
Held               : 56

Valid ratio        : 0.853
Invalid ratio      : 0.147
Held ratio         : 0.140
```

Observed target ranges included:

```text
Normalized horizontal error : -0.7885 to +0.5979
Estimated distance          : 2.1356 to 5.4275
```

This dataset provided both left/right image-error directions and distances above and below the desired following distance, making it suitable for controller testing.

---

## Development Progression

The perception pipeline was developed incrementally:

```text
PNG sequence experiments
        ↓
LED pair detection
        ↓
Temporal pattern analysis
        ↓
Distance calibration
        ↓
Static observation packet
        ↓
Local UDP test
        ↓
Windows → Linux UDP streaming
        ↓
PNG-sequence live sender
        ↓
MP4 video sender
        ↓
V2 pair-selection and hold logic
        ↓
Debug-overlay and log analysis
        ↓
Live Unity Game View capture
        ↓
Emergency LED pattern detection
```

---

## Main Scripts

| Script | Purpose |
|---|---|
| `01_preview_png_sequence.py` | Preview Unity-generated PNG sequences |
| `03_hsv_tuner.py` | Tune HSV thresholds for LED extraction |
| `04_back_pair_distance_extract.py` | Detect the BACK LED pair and extract geometric measurements |
| `05_back_pattern_decode.py` | Analyze temporal LED pattern consistency |
| `06_back_distance_analysis.py` | Analyze pixel-distance measurements |
| `07_distance_model.py` | Fit and evaluate the LED-spacing distance model |
| `08_generate_observation_packet.py` | Generate controller-ready observation packets |
| `09_udp_send_observation.py` | Test UDP observation transmission |
| `10_udp_receive_observation.py` | Test UDP observation reception |
| `11_replay_back_observation_from_csv.py` | Replay observations from processed CSV data |
| `12_live_back_png_sequence_sender.py` | Process PNG frames and stream observations over UDP |
| `13_live_back_video_sender.py` | Process recorded MP4 video |
| `13_live_back_video_sender_v2.py` | Improved video perception and pair-selection pipeline |
| `14_analyze_video_observation_log.py` | Analyze observation logs |
| `15_render_video_detection_debug.py` | Render detection-debug overlays |
| `15_render_video_detection_debug_v2.py` | V2-compatible debug visualization |
| `16_live_unity_window_sender.py` | Initial live Unity Game View capture |
| `17_select_capture_region.py` | Select the Unity screen-capture region |
| `18_live_unity_window_sender.py` | Current live perception sender with emergency pattern detection |

Older experimental scripts are preserved under:

```text
scripts/legacy/
```

---

## Repository Structure

```text
.
├── README.md
├── requirements.txt
├── .gitignore
│
├── scripts/
│   ├── 01_preview_png_sequence.py
│   ├── ...
│   ├── 18_live_unity_window_sender.py
│   └── legacy/
│
├── docs/
│   ├── calibration_log.md
│   ├── dataset_notes.md
│   ├── next_steps.md
│   ├── progress_log.md
│   └── project_task_board.md
│
├── unity/
│   └── RovLeds.cs
│
├── datasets/
│   └── .gitkeep
│
└── outputs/
    └── .gitkeep
```

Large datasets, videos and generated output files are intentionally excluded from the repository.

---

## Installation

Create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
pip install -r requirements.txt
```

Dependencies:

```text
opencv-python
numpy
pandas
mss
```

---

## Running the Live Unity Sender

First select or determine the Unity Game View capture region:

```powershell
python .\scripts\17_select_capture_region.py
```

Then run the live perception pipeline:

```powershell
python .\scripts\18_live_unity_window_sender.py `
  --region-left <LEFT> `
  --region-top <TOP> `
  --region-width <WIDTH> `
  --region-height <HEIGHT> `
  --ip <CONTROL_PC_IP> `
  --port 5005 `
  --rate 20 `
  --preview `
  --allow-more-than-two-candidates `
  --pair-strategy best `
  --min-distance-confidence 0.40
```

For perception-only testing without UDP output:

```powershell
python .\scripts\18_live_unity_window_sender.py `
  --region-left <LEFT> `
  --region-top <TOP> `
  --region-width <WIDTH> `
  --region-height <HEIGHT> `
  --preview `
  --skip-send
```

---

## Current Limitations

The current implementation still has several research and engineering limitations:

- BACK-face tracking is substantially more developed than multi-face tracking.
- Pixel-spacing distance estimation is affected by viewing angle and foreshortening.
- Distance estimates can become artificially large during strong yaw angles.
- HSV-based segmentation remains sensitive to lighting, reflections and target scale.
- Target loss can occur when the robot approaches the image boundary.
- Emergency LED thresholds are currently tuned for the simulation environment.
- Full multi-face FRONT / BACK / LEFT / RIGHT perception is not yet implemented.

These limitations are part of the ongoing development toward more robust visual following.

---

## Related Control Repository

The control subsystem is maintained separately:

### [BlueROV2 Visual Control & MAVLink Integration](https://github.com/eranaydogan/bluerov2-led-control)

It receives perception observations over UDP and handles:

- observation validation,
- forward and yaw control,
- command smoothing,
- rate limiting,
- MAVLink `MANUAL_CONTROL`,
- ArduSub SITL integration,
- Gazebo BlueROV2 motion,
- safe STOP and DISARM behavior.

Keeping perception and control in separate repositories reflects the distributed architecture used during development.

---

## Project Context

**Graduation Project**  
**Funded by TÜBİTAK 2209-A**  
**Role: Project Lead**

The broader project explores visual target tracking, distributed simulation and autonomous following for underwater robotic systems using BlueROV2.
