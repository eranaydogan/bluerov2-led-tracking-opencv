# Progress Log

## Milestone 1 — Back Face Controlled Test

### Goal

Detect the two green LEDs on the back face, decode the `11001100` pattern, and measure the pixel distance between the two LEDs.

### Unity Setup

* Active LEDs: back face only
* Pattern: `11001100`
* FPS: 60
* Bit duration: 0.1 s
* Frames per bit: 6
* Recording format: PNG sequence
* Frame count: 601

### OpenCV Results

Pattern decoding:

```text
Decoded bits:
110011001100110011001100...
Score: 1.0
Result: BACK pattern detected successfully
```

Distance analysis after filtering:

```text
Valid frames:
bit == 1
pair_found == 1
candidate_count == 2
pixel_distance not null

Filtered median pixel distance: 168 px
Filtered standard deviation: 0.61 px
```

### Conclusion

The controlled back-only test was successful.

The system can:

* detect the green back LEDs,
* decode the back pattern,
* find the two LED centers,
* calculate a stable pixel distance.

### Observed Issue

When `candidate_count > 2`, false positives or extra blobs may cause incorrect pair selection.

### Temporary Solution

For the first distance analysis, only frames with `candidate_count == 2` are used.

### Future Improvement

When more than two candidates are detected, all candidate pairs should be scored using:

* expected geometric distance,
* y-axis alignment,
* area similarity,
* previous valid distance,
* pattern consistency.



# Progress Report — Back LED Pattern Detection, Distance Calibration and Next Control Interface

## 1. Current Objective

The current development stage focuses on validating the back-face LED tracking pipeline before moving to the full multi-face tracking scenario.

The target robot has 8 LEDs in total:

* 2 LEDs on the front face
* 2 LEDs on the back face
* 2 LEDs on the left face
* 2 LEDs on the right face

Each face uses a unique binary LED pattern. The two LEDs on the same face blink with the same pattern and the same phase. This design allows the vision system to verify the visible face, calculate the midpoint of the LED pair, and estimate approximate distance from the pixel distance between the two LEDs.

The first controlled tests focus on the back face because the main following scenario assumes that the follower robot observes the rear side of the leader robot. The back LEDs are green and are currently easier to detect with HSV-based segmentation.

---

## 2. Implemented Pipeline

The current OpenCV pipeline consists of three main scripts:

### 2.1 Back Pair Distance Extraction

Script:

```text
04_back_pair_distance_extract.py
```

Main tasks:

* Read PNG frames from the selected dataset folder.
* Detect green back-face LED candidates.
* Extract LED centers for each frame.
* Determine whether the LEDs are ON or OFF.
* Compute the pixel distance between the two detected LEDs.
* Save frame-level results to:

```text
outputs/<DATASET_NAME>/back_pair_results.csv
```

Stored values include:

* frame index,
* detected candidate count,
* ON/OFF bit,
* pair_found flag,
* LED center coordinates,
* pixel distance between the two LEDs.

### 2.2 Back Pattern Decoding

Script:

```text
05_back_pattern_decode.py
```

Main tasks:

* Read the frame-level bit sequence from `back_pair_results.csv`.
* Group frames into bits using 6 frames per bit.
* Decode the repeated `11001100` back-face pattern.
* Compare the decoded bit sequence with the expected pattern.

### 2.3 Distance Analysis

Script:

```text
06_back_distance_analysis.py
```

Main tasks:

* Read pixel-distance values from `back_pair_results.csv`.
* Use only reliable frames:

```text
bit == 1
pair_found == 1
candidate_count == 2
pixel_distance is not null
```

* Compute raw and filtered distance statistics.
* Save filtered results to:

```text
outputs/<DATASET_NAME>/back_pair_distance_filtered.csv
```

---

## 3. Unity Timing Correction

At first, LED blinking was controlled with a coroutine and `WaitForSeconds(tickRate)`. This caused timing mismatch because the practical frame duration did not align exactly with the intended 60 FPS capture rate.

The system was updated to use frame-based timing:

```text
FPS = 60
bit duration = 0.1 s
frames per bit = 6
```

For the back-face pattern:

```text
pBack = 11001100
```

This means:

```text
11 → 12 frames ON
00 → 12 frames OFF
```

After this correction, the pattern was decoded consistently.

---

## 4. Calibration Test Results

The following datasets were recorded using the back-only LED setup.

| Test name        | Approx. root distance | Pattern score | Median pixel distance | Filtered std | Notes                                            |
| ---------------- | --------------------: | ------------: | --------------------: | -----------: | ------------------------------------------------ |
| BackOnly_Test_01 |                  1.47 |           1.0 |              168.0 px |      0.61 px | Initial static reference                         |
| BackOnly_Test_02 |                  2.00 |           1.0 |              118.0 px |     0.002 px | Camera moved backward; Y/Z also changed slightly |
| BackOnly_Test_03 |                  2.50 |           1.0 |               92.0 px |      0.74 px | Camera moved backward; Y/Z also changed slightly |
| BackOnly_Test_04 |                  3.00 |           1.0 |              73.06 px |      0.82 px | Camera moved only along X; Y/Z fixed             |
| BackOnly_Test_05 |                  4.00 |           1.0 |               53.0 px |      0.67 px | Camera moved only along X; Y/Z fixed             |
| BackOnly_Test_06 |                  5.00 |           1.0 |               37.0 px |      2.24 px | Far-range boundary test                          |

The results show the expected inverse relationship:

```text
larger camera-target distance → smaller LED pixel distance
```

At around 5 Unity units, the LED pattern is still detectable, but the pixel-distance measurement becomes noisier because the LED pair appears much smaller in the image.

---

## 5. Key Findings

### 5.1 Back-face pattern detection works

The `11001100` pattern was repeatedly decoded with a best-window score of 1.0 across all tested distances.

### 5.2 Pixel distance can be used as a range cue

The measured pixel distance decreases consistently as the camera is moved farther away from the robot.

### 5.3 The far-range limit is starting to appear

At approximately 5 Unity units, the median pixel distance dropped to about 37 px and the filtered standard deviation increased to about 2.24 px. This indicates that the system still detects the LEDs but distance estimation becomes noisier.

### 5.4 Not every frame should be used for distance estimation

Only frames with reliable pair detection should be used. The current reliability filter is:

```text
bit == 1
pair_found == 1
candidate_count == 2
pixel_distance is not null
```

This significantly improves distance stability.

### 5.5 Best-window pattern score is not enough

The current pattern decoder can still find a perfect 8-bit window even if one or more errors occur elsewhere in the full decoded sequence. Therefore, global repeated-pattern accuracy, bit error count, and bit error rate should be added.

---

## 6. Data Needed for the Control Side

The next control interface should not only send a detected LED point. It should send a compact observation packet.

For the two-LED back-following case, the vision output should include:

```text
face_id
pattern_confidence
global_pattern_accuracy
pair_found
pair_midpoint_x
pair_midpoint_y
normalized_error_x
normalized_error_y
camera_ray_x
camera_ray_y
camera_ray_z
pixel_distance
estimated_distance
distance_confidence
frame_index
timestamp
valid_observation
```

The pair midpoint will be calculated as:

```text
mid_x = (led1_x + led2_x) / 2
mid_y = (led1_y + led2_y) / 2
```

The normalized screen error will be calculated relative to the image center:

```text
error_x = (mid_x - image_center_x) / image_center_x
error_y = (mid_y - image_center_y) / image_center_y
```

This output can later be sent from the Windows/OpenCV side to the Linux/control side through UDP.

---

## 7. Next Development Tasks

### Task 1 — Improve pattern validation

Update `05_back_pattern_decode.py` to compute:

* global repeated-pattern accuracy,
* bit error count,
* bit error rate,
* best shift over the entire decoded sequence.

This will allow the system to distinguish between “pattern was found somewhere” and “the whole decoded sequence is reliable.”

### Task 2 — Add distance model

Create a simple script:

```text
07_distance_model.py
```

Purpose:

* read calibration results,
* fit or test a simple distance model,
* estimate distance from pixel distance.

Initial model:

```text
distance ≈ K / pixel_distance
```

Later, a fitted model or calibration lookup table can be used.

### Task 3 — Add midpoint and camera-ray outputs

Update `04_back_pair_distance_extract.py` to also save:

* LED pair midpoint,
* normalized image error,
* camera ray direction,
* observation confidence.

These outputs will be needed for the Linux-side controller.

### Task 4 — Prepare UDP observation packet

After the data fields are stable, define the observation packet to be sent to the control side.

Initial packet can be JSON for debugging. Later, it can be converted into a compact binary packet.

### Task 5 — Extend from back-only to multi-face detection

After the back-face case is stable, extend the logic to front, left, and right LED pairs.

For diagonal views where multiple faces may be visible, the system should generate per-face observations instead of forcing a single global center.

---

## 8. Current Status

The back-only tracking case is validated from approximately 1.5 to 5 Unity units.

The system can currently:

* detect the back LED pair,
* decode the back pattern,
* compute LED pair midpoint,
* measure pixel distance,
* use pixel distance as a range cue,
* identify the beginning of the far-range noise limit.

The next step is to convert the current detection output into a controller-ready observation format.



# Current Progress Report — Vision Output Preparation for Control Integration

## 1. Current Stage

The image-processing pipeline has moved from simple LED detection to controller-ready observation generation. The current focus is the back-face tracking case, where the follower robot observes the rear side of the leader robot.

The back face uses two green LEDs with the repeated binary pattern:

```text
11001100
```

The two LEDs on the same face blink with the same pattern and the same phase. This allows the system to detect the visible face, calculate the midpoint of the LED pair, estimate distance from LED pixel spacing, and generate image-center alignment errors for the control side.

## 2. Completed Work

### 2.1 Back LED Pair Detection

The script `04_back_pair_distance_extract.py` detects the two green back LEDs and saves frame-level results to:

```text
outputs/<DATASET_NAME>/back_pair_results.csv
```

The CSV now includes:

* LED candidate count
* ON/OFF bit value
* pair_found flag
* LED center coordinates
* pixel distance between the LEDs
* LED pair midpoint
* normalized image-center error
* camera ray direction
* image width and height

### 2.2 Global Pattern Accuracy

The script `05_back_pattern_decode.py` was extended beyond local pattern matching.

It now reports:

* local 8-bit best pattern score
* global repeated-pattern accuracy
* bit error count
* bit error rate
* best global pattern shift

This was necessary because a local score of 1.0 only proves that the expected pattern exists somewhere in the decoded sequence. The global accuracy shows whether the entire decoded bit sequence is reliable.

For the far-range test `BackOnly_Test_06`, the result was:

```text
Local score: 1.0
Global accuracy: 0.99
Bit error count: 1
Bit error rate: 0.01
```

This confirms that the pattern is still reliable at the far-range boundary, but small bit errors start to appear.

### 2.3 Distance Model

A first distance model was generated with `07_distance_model.py` using the current calibration tests.

The fitted model is:

```text
estimated_distance = 168.628584 / pixel_distance + 0.609526
```

Model evaluation:

```text
Mean absolute error: 0.116 unit
RMSE: 0.131 unit
```

This model is sufficient for the first control experiments, where the goal is not exact metric localization but relative following behavior.

### 2.4 Controller Observation Packet

The script `08_generate_observation_packet.py` generates a JSON observation packet from the processed CSV data.

Example output fields:

```json
{
  "valid": true,
  "face_id": "BACK",
  "pattern": "11001100",
  "pattern_accuracy": 1.0,
  "midpoint_px": [890.0, 556.0],
  "error_norm": [-0.0729, -0.0296],
  "ray_cam": [-0.0746, -0.0171, 0.9971],
  "pixel_distance": 74.027,
  "estimated_distance": 2.887,
  "distance_confidence": 1.0
}
```

The script now also supports selecting an observation near a requested frame:

```powershell
python .\scripts\08_generate_observation_packet.py BackOnly_Test_04 120
```

If the requested frame is not valid, the nearest valid frame is selected.

## 3. Calibration Results

| Test name        | Approx. distance | Pattern accuracy | Median pixel distance | Distance std | Notes                 |
| ---------------- | ---------------: | ---------------: | --------------------: | -----------: | --------------------- |
| BackOnly_Test_01 |             1.47 |             1.00 |                168 px |      0.61 px | Initial reference     |
| BackOnly_Test_02 |             2.00 |             1.00 |                118 px |     0.002 px | Stable                |
| BackOnly_Test_03 |             2.50 |             1.00 |                 92 px |      0.74 px | Usable                |
| BackOnly_Test_04 |             3.00 |             1.00 |              73.06 px |      0.82 px | Clean fixed-axis test |
| BackOnly_Test_05 |             4.00 |             1.00 |                 53 px |      0.67 px | Clean fixed-axis test |
| BackOnly_Test_06 |             5.00 |             0.99 |                 37 px |      2.24 px | Far-range boundary    |

The results show that the pixel distance between the two back LEDs decreases consistently as the camera-target distance increases.

## 4. Current Interpretation

The back-only tracking case is now usable as a controlled input source for the Linux-side controller.

The vision system can currently provide:

* visible face identity,
* pattern reliability,
* LED pair midpoint,
* image-center alignment error,
* camera ray direction,
* raw pixel distance,
* estimated distance,
* distance confidence.

## 5. Next Steps

The next development steps are:

1. Commit the current image-processing and observation-packet pipeline to GitHub.
2. Use the JSON packet format as the initial debugging payload.
3. Implement UDP transmission of the observation packet from Windows/OpenCV to the Linux controller.
4. Later convert JSON to a compact binary packet if latency or bandwidth becomes a problem.
5. Extend the method from the back-only case to multi-face views.
6. For diagonal views, generate one observation per visible face instead of averaging all LEDs into a single global point.


## UDP Observation Packet Localhost Test

### Goal

The goal of this step was to verify that the controller-ready JSON observation packet can be sent and received over UDP before integrating with the Linux-side controller.

### Test Setup

* Sender script: `09_udp_send_observation.py`
* Receiver script: `10_udp_receive_observation.py`
* Dataset: `BackOnly_Test_04`
* Selected frame: `120`
* Destination IP: `127.0.0.1`
* UDP port: `5005`
* Packet count: `10`
* Send rate: `10 Hz`

### Sent Observation

The transmitted packet contained the following key fields:

```text
valid: True
face_id: BACK
pattern_accuracy: 1.0
bit_error_rate: 0.0
error_norm: [-0.0729, -0.0287]
ray_cam: [-0.0746, -0.0165, 0.9971]
pixel_distance: 74.0068
estimated_distance: 2.8881
distance_confidence: 1.0
```

### Result

The receiver successfully received and parsed all 10 UDP packets.

The sequence numbers increased from `0` to `9`, and the received observation fields matched the sent JSON packet.

The localhost latency was approximately below 1 ms.

### Conclusion

The local UDP transmission test was successful. The JSON-based observation packet is now ready for Windows-to-Linux network testing before being connected to the actual controller.

Docs Update Patch — 2026-05-30
# Progress Report — Live UDP Observation Senders and Video-Based Control Integration

## 1. Current Stage

The project has moved from offline observation-packet generation to live-like UDP observation streaming and control-side MAVLink integration.

Previously, the OpenCV side could generate a single controller-ready JSON packet from processed CSV data. In the latest development stage, this was extended in three steps:

1. CSV replay UDP sender,
2. PNG sequence OpenCV UDP sender,
3. MP4 video OpenCV UDP sender.

The Linux-side controller was also tested with these observation streams using MAVLink `MANUAL_CONTROL`. Both arms-off and armed tests were completed successfully.

This stage validates the following full integration chain:

```text
Unity recorded video
→ OpenCV frame processing
→ UDP observation packet
→ Linux controller
→ MAVLink MANUAL_CONTROL
→ ArduSub/Gazebo BlueROV2 motion
→ STOP
→ DISARM

This is still not a true live closed-loop tracking test because the video is pre-recorded. However, it is a major integration milestone because image-derived observations are now driving the simulated vehicle through the control pipeline.

2. Added Scripts
2.1 CSV Replay UDP Sender

Script:

scripts/11_replay_back_observation_from_csv.py

Purpose:

read outputs/<DATASET_NAME>/back_pair_results.csv,
read pattern summary JSON,
read distance model summary JSON,
reconstruct controller-ready BACK observation packets,
send packets over UDP to the Linux controller.

Example command:

python .\scripts\11_replay_back_observation_from_csv.py `
  --dataset BackOnly_Test_04 `
  --ip 192.168.137.228 `
  --port 5005 `
  --rate 20 `
  --loop

Result:

Windows-to-Linux UDP observation stream was verified.
Linux controller stayed in TRACK when valid packets arrived.
Packet age stayed low.
No packet timeout occurred during normal streaming.
The controller generated changing commands from frame-sequence data.
2.2 PNG Sequence OpenCV UDP Sender

Script:

scripts/12_live_back_png_sequence_sender.py

Purpose:

read PNG frames directly from datasets/<DATASET_NAME>/,
detect the BACK LED pair using OpenCV,
apply HSV thresholding and contour filtering,
compute:
LED pair midpoint,
normalized image error,
camera ray,
LED pixel distance,
estimated distance,
distance confidence,
send one observation packet per processed frame over UDP.

Example command:

python .\scripts\12_live_back_png_sequence_sender.py `
  --dataset BackOnly_Test_04 `
  --ip 192.168.137.228 `
  --port 5005 `
  --rate 20 `
  --loop

Main parameters:

LOWER_BACK = [54, 83, 172]
UPPER_BACK = [95, 147, 226]

min_area = 20
max_area = 6000

min_aspect_ratio = 0.25
max_aspect_ratio = 4.50

on_area_threshold = 35
camera_vertical_fov_deg = 60

Important addition:

held_observation

This field is used when the LED pair is temporarily missing due to blink OFF frames or short detection gaps. Instead of immediately dropping to invalid, the sender can briefly reuse the last valid observation.

Result:

PNG frames are processed directly by OpenCV.
CSV dependency was removed for this stage.
UDP observation packets are generated from image data.
Linux controller successfully received and used the stream.
Both arms-off and armed tests were completed successfully with 05_udp_to_mavlink_controller_safe.py.
2.3 Video-Based BACK Observation Sender

Script:

scripts/13_live_back_video_sender.py

Purpose:

read an MP4 video using OpenCV,
process the video frame by frame,
downsample a 60 FPS video to a 20 Hz observation stream,
detect BACK LED candidates,
generate UDP observation packets,
save a CSV log for later analysis.

Input video:

datasets/videos/BackOnly_Dynamic_Test_01.mp4

Example command:

python .\scripts\13_live_back_video_sender.py `
  --video .\datasets\videos\BackOnly_Dynamic_Test_01.mp4 `
  --dataset BackOnly_Dynamic_Test_01 `
  --ip 192.168.137.228 `
  --port 5005 `
  --rate 20 `
  --loop

Video properties:

Frame count: 1201
FPS: 60.0
Duration: 20.0167 s

Since the output stream rate was 20 Hz, the sender used:

frame_step = 3

The script produced:

outputs/BackOnly_Dynamic_Test_01/video_observation_log.csv

Observed states included:

valid=True
held_observation=True
BIT_OFF
LOW_CONFIDENCE
CANDIDATE_COUNT_NOT_2
PAIR_NOT_FOUND

This confirms that the video sender can handle both valid detections and temporary invalid/occluded frames.

3. Unity Recording Pipeline Updates

Unity was used to record a dynamic leader-robot video for offline video-based integration testing.

3.1 GazeboDataReceiver Update

The Unity GazeboDataReceiver script was updated to support two modes:

1. Absolute Gazebo pose mode
2. Keyboard relative recording mode

For dataset recording, the new mode was used:

keyboardRelativeMode = true

In this mode, the Python keyboard sender transmits relative x, y, z, yaw offsets. The receiver no longer subtracts pythonOrigin from the incoming packet. This prevents the leader object from jumping to an unintended position when the keyboard sender starts.

Important Unity receiver settings:

Force Unity Start Pose = true
Use Local Transform = true
Keyboard Relative Mode = true

Forced Unity Start Position:
X = -124.123
Y = -125.322
Z = 940.1
3.2 Keyboard Pose Sender

A Python keyboard sender was used to move the leader robot during video recording.

Controls:

W/S → forward/back
A/D → left/right
R/F → up/down
Q/E → yaw left/right
Shift → faster
X → reset
ESC → quit

The sender transmits a 9-float binary UDP packet to Unity:

x
y
z
roll
pitch
yaw
timestamp
seq
senderDt

Unity listens on:

127.0.0.1:5007
3.3 Unity Recorder Settings

The dynamic video was recorded using Unity Recorder.

Settings:

Recorder Type: Movie
Source: Targeted Camera
Camera: TaggedCamera
Tag: CVRecorderCamera
Resolution: 1920x1080
Playback: Constant
Target FPS: 60
Cap FPS: enabled
Codec: H.264 MP4
Encoding Quality: High
Include Audio: disabled
Accumulation / Motion Blur: disabled

Output:

datasets/videos/BackOnly_Dynamic_Test_01.mp4

The video contains:

right movement,
left movement,
forward movement,
temporary occlusion by fish,
return movement,
yaw right/left test,
final stop without reset.
4. Linux Control Integration

The Linux control side uses:

scripts/05_udp_to_mavlink_controller_safe.py

This script:

connects to MAVLink at udpin:127.0.0.1:14551,
listens for UDP observation packets at 0.0.0.0:5005,
parses JSON observation packets,
checks validity and confidence,
computes x and r commands,
sends MANUAL_CONTROL to ArduSub,
sends STOP on invalid observation or timeout,
sends STOP and DISARM at the end of the test.

Initial control mapping:

x = k_forward * (estimated_distance - desired_distance)
r = k_yaw * error_norm[0]
z = 500
y = 0

Current desired distance:

desired_distance = 3.0

Vertical control is currently disabled:

z = 500 fixed
5. Video-Based Arms-Off Test

First, the video sender was tested with the Linux controller without arming the vehicle.

Command:

python scripts/05_udp_to_mavlink_controller_safe.py \
  --runtime 30 \
  --packet-timeout 1.0 \
  --k-forward 100 \
  --k-yaw 120 \
  --max-x 120 \
  --max-r 120

Result:

UDP packets were received.
state=TRACK appeared when valid BACK observations arrived.
state=INVALID appeared when detection was not valid.
valid=True packets generated control commands.
valid=False packets generated STOP commands:
cmd=(0,0,500,0)

Example observations:

error_x > 0 → r > 0
error_x < 0 → r < 0
estimated_distance > 3.0 → x > 0

The reduced gains prevented overly aggressive commands.

6. Video-Based Armed Test

After the arms-off test, a short armed test was performed.

Linux command:

python scripts/05_udp_to_mavlink_controller_safe.py \
  --runtime 10 \
  --packet-timeout 1.0 \
  --arm \
  --k-forward 100 \
  --k-yaw 120 \
  --max-x 120 \
  --max-r 120

Windows video sender:

python .\scripts\13_live_back_video_sender.py `
  --video .\datasets\videos\BackOnly_Dynamic_Test_01.mp4 `
  --dataset BackOnly_Dynamic_Test_01 `
  --ip 192.168.137.228 `
  --port 5005 `
  --rate 20 `
  --loop

Observed result:

Vehicle is ARMED
state=TRACK
HB armed=True
valid=True → command generated
valid=False → STOP command generated
Sending STOP before exit
Vehicle is DISARMED
Controller finished safely

This confirms that the video-based OpenCV observation stream can drive the ArduSub/Gazebo vehicle through MAVLink in an armed test, while still exiting safely.

7. Current Technical Status

The system has now been validated up to:

Unity recorded video
→ OpenCV video detection
→ UDP observation stream
→ Linux controller
→ MAVLink MANUAL_CONTROL
→ ArduSub/Gazebo motion
→ STOP/DISARM safety

Completed:

static observation packet generation,
localhost UDP packet test,
Windows-to-Linux UDP observation transmission,
CSV replay sender,
PNG sequence OpenCV sender,
MP4 video OpenCV sender,
Linux UDP-to-MAVLink safe controller test,
arms-off video integration test,
armed video integration test with reduced gains.

Important limitation:

This is still an offline video-based test. It is not yet a true live closed-loop tracking test because the video image does not change in response to the follower robot’s motion.

8. Known Limitations
8.1 Frequent INVALID states

The dynamic video test produced several invalid conditions:

BIT_OFF
LOW_CONFIDENCE
CANDIDATE_COUNT_NOT_2
PAIR_NOT_FOUND

This creates a safe but discontinuous behavior:

TRACK → STOP → TRACK → STOP

This is acceptable for safety, but it should be improved for smoother tracking.

8.2 Candidate selection is still simple

Current logic often expects:

candidate_count == 2

This is safe in controlled tests but can fail in video when:

reflections appear,
LED blobs split,
fish or other objects occlude the LEDs,
more than two green candidates appear.

Future solution:

evaluate all possible candidate pairs,
score by geometry,
score by area similarity,
score by previous valid distance,
score by temporal consistency.
8.3 MP4 compression can affect HSV values

MP4/H.264 compression can slightly change colors and edges.

For strict algorithm calibration, PNG sequences are still preferred. MP4 is useful for integration/stress tests and demonstration, especially when testing video processing and temporary occlusions.

8.4 Distance model may need refinement for dynamic videos

The current distance model was fitted using static calibration datasets. In dynamic MP4 recordings, compression, motion, and slight camera/scene differences may change pixel-distance values.

Future work should compare:

PNG-based distance estimates,
MP4-based distance estimates,
Unity ground-truth positions,
LED world positions.
9. Next Development Tasks
9.1 Analyze video observation log

Create:

scripts/14_analyze_video_observation_log.py

Input:

outputs/BackOnly_Dynamic_Test_01/video_observation_log.csv

Metrics:

valid / invalid ratio,
held observation ratio,
reason distribution,
error_x min/max/mean,
estimated_distance min/max/mean,
pixel_distance min/max/mean,
candidate count distribution.
9.2 Render debug overlay video

Create:

scripts/15_render_video_detection_debug.py

Overlay should show:

LED candidate boxes,
selected LED pair,
midpoint,
image center,
error_norm,
estimated_distance,
valid / held / invalid,
invalid reason.

This will help diagnose why CANDIDATE_COUNT_NOT_2, LOW_CONFIDENCE, or PAIR_NOT_FOUND occurred.

9.3 Improve candidate pair selection

Replace the strict candidate_count == 2 assumption with pair scoring.

Candidate pair score can use:

LED area similarity,
vertical alignment,
distance continuity from previous frame,
reasonable pixel-distance range,
temporal stability,
pattern consistency.
9.4 Improve hold logic

Current hold logic uses a fixed duration:

hold_seconds = 0.35

Future hold should depend on reason:

BIT_OFF → longer hold allowed
LOW_CONFIDENCE → short hold
CANDIDATE_COUNT_NOT_2 → short hold if previous observation is stable
PAIR_NOT_FOUND → very short hold or STOP
long occlusion → STOP
9.5 Improve Linux controller

Future controller script:

06_live_udp_to_mavlink_controller.py

Possible additions:

yaw deadband,
forward deadband,
EMA command smoothing,
acceleration limiting,
confidence-based gain scaling,
explicit state machine:
TRACK
ALIGN_ONLY
INVALID
PACKET_TIMEOUT
STOP
SEARCH
9.6 Move to live Unity/Unreal render

The next major step is to replace offline MP4 input with live image capture.

Possible script:

scripts/16_live_unity_window_sender.py

Target future pipeline:

Unity or Unreal live render
→ OpenCV frame processing
→ UDP observation packet
→ Linux MAVLink controller
→ Gazebo/ArduSub follower motion

This will be the first real step toward closed-loop tracking.


Progress Update — Clean Constant-ON Video and Controller V2 Validation
Summary

A new clean dynamic Unity video was recorded using the BACK LEDs in constant-ON mode:

BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4

The purpose of this dataset was to separate pure tracking/control behavior from blink-pattern related target loss. Unlike the previous blink-pattern video, the BACK LEDs were kept continuously visible so that midpoint tracking, distance estimation, and controller smoothing could be evaluated more clearly.

A new Unity LED mode was added to RovLeds.cs:

forceBackConstantOn = true

When this mode is enabled:

frontLEDs → OFF
backLEDs  → constant ON
leftLEDs  → OFF
rightLEDs → OFF

This allows clean BACK-only tracking tests without binary blink interruption.

Video Dataset

Recorded video:

datasets/videos/BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4

Video properties:

Resolution : 1920x1080
FPS        : 60.0
Frames     : 1201
Duration   : 20.0167 s

Approximate movement sequence:

1. Initial centered position
2. Movement to the right in the image
3. Movement to the left in the image
4. Forward and backward movement while on the left side
5. Yaw right / yaw left motion
6. Final recentering near the image center
OpenCV Sender V2 Analysis

The video was processed using:

scripts/13_live_back_video_sender_v2.py

with:

allow_more_than_two_candidates = true
pair_strategy = best
detection_rate = every video frame
send_rate = 20 Hz

The generated observation log was analyzed using:

scripts/14_analyze_video_observation_log.py

Main results:

total packets : 401
valid_count   : 342
invalid_count : 59
held_count    : 56

valid_ratio   : 0.853
invalid_ratio : 0.147
held_ratio    : 0.140

This satisfies the clean-video target:

valid_ratio   ≥ 0.85
invalid_ratio ≤ 0.15

The video also contains both horizontal error signs and crosses the desired distance:

error_x range              : -0.7885 to +0.5979
estimated_distance range   : 2.1356 to 5.4275
desired controller distance: 3.0

Therefore, this video is suitable for controller-side testing because it can produce both yaw directions and both forward/backward distance-control behavior.

Debug Overlay V2

A new V2-compatible debug overlay script was added:

scripts/15_render_video_detection_debug_v2.py

This script reuses the same pair-selection logic as 13_live_back_video_sender_v2.py, so the green selected LED pair shown in the overlay matches the pair used by the UDP sender.

Generated overlay:

outputs/BackOnly_Dynamic_Clean_01_CONSTANT_ON_v2/debug_overlay_v2.mp4

Visual inspection results:

- The selected green pair corresponds to the correct BACK LED pair.
- When extra orange candidates appear, the V2 best-pair logic usually keeps the correct pair.
- At far-left / far-distance regions, detection can temporarily break.
- The midpoint line is visually consistent with the detected LED pair.
- The sign of error_x is correct:
  target right in image → error_x positive
  target left in image  → error_x negative
- Final frames show the target moving back toward the image center.

Known issue:

Even in constant-ON mode, some frames are classified as BIT_OFF or PAIR_NOT_FOUND. This does not mean the LEDs physically turned off; it means the HSV mask failed to extract enough valid LED area in those frames. This mostly happens when the robot is far away, near the edge of the image, or during difficult yaw/angle conditions.