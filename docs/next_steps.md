# Next Steps

## Current Status

The project has passed the offline video-based vision-to-control integration stage.

The currently validated pipeline is:

```text
Unity recorded video
→ OpenCV video sender V2
→ UDP observation packet
→ Linux controller V2
→ MAVLink MANUAL_CONTROL
→ ArduSub / Gazebo BlueROV2 motion
→ STOP + DISARM safety
```

This means the system can now:

* process a recorded Unity MP4 video,
* detect the BACK LED pair,
* estimate image-center error and approximate distance,
* generate controller-ready UDP observation packets,
* receive those packets on Linux,
* smooth and limit control commands,
* send MAVLink `MANUAL_CONTROL` commands,
* move the Gazebo BlueROV2 in an armed test,
* stop and disarm safely at the end of the run.

Important limitation:

This is still **offline video-based integration**, not true live closed-loop tracking. The robot moves in Gazebo, but the input video does not change in response to that motion. True closed-loop behavior requires live Unity/Unreal render capture.

---

## 1. Preserve the Current Stable Milestone

Before adding new features, keep the current working state stable.

Already completed:

```text
scripts/11_replay_back_observation_from_csv.py
scripts/12_live_back_png_sequence_sender.py
scripts/13_live_back_video_sender.py
scripts/13_live_back_video_sender_v2.py
scripts/14_analyze_video_observation_log.py
scripts/15_render_video_detection_debug.py
```

Control-side completed in the separate Linux repository:

```text
scripts/06_live_udp_to_mavlink_controller.py
scripts/07_manual_control_threshold_test.py
```

The current milestone should be documented as:

```text
Offline video → OpenCV observation → UDP → smoothed MAVLink control → Gazebo motion
```

---

## 2. Record a Cleaner Dynamic Unity Dataset

The first dynamic video, `BackOnly_Dynamic_Test_01.mp4`, was useful as a stress test because it included motion, blink frames, candidate-count changes and temporary occlusion. However, it is not ideal for clean control evaluation.

Create a cleaner video dataset:

```text
BackOnly_Dynamic_Clean_01.mp4
```

Recording requirements:

* fixed camera,
* BACK face visible,
* no fish or object occlusion,
* stable lighting,
* no motion blur for the first clean test,
* 1920x1080 resolution,
* 60 FPS,
* slow and controlled robot movement,
* both left and right image-error signs,
* distance should go both above and below the desired following distance.

Suggested motion sequence:

```text
0–3 s     stay centered and still
3–6 s     move right in the image
6–9 s     move left in the image
9–12 s    move away from camera
12–15 s   move closer than the desired distance
15–18 s   mild yaw right/left
18–20 s   return near center and stop
```

---

## 3. Separate Tracking Tests from Blink/Pattern Tests

Blinking LEDs are useful for face identification, but they make continuous tracking harder because fully OFF frames create temporary target loss.

Therefore, create two versions of the clean dynamic video.

### 3.1 Constant-ON tracking video

```text
BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4
```

Purpose:

* test pure LED tracking,
* test midpoint stability,
* test distance estimation,
* test controller smoothing,
* test forward/yaw control without blink-induced target loss.

LED behavior:

```text
BACK LEDs always ON
```

This should be the first clean control evaluation video.

### 3.2 Blink-pattern robustness video

```text
BackOnly_Dynamic_Clean_01_BLINK.mp4
```

Purpose:

* test `11001100` pattern robustness,
* test `BIT_OFF` handling,
* test `held_observation`,
* test reason-based hold behavior,
* test transition between `TRACK`, `INVALID_DECAY`, and `INVALID_STOP`.

LED behavior:

```text
BACK LEDs use pattern 11001100
```

This should be tested after the constant-ON video is stable.

---

## 4. Analyze Each New Video

For every new video, first run the V2 sender in offline log mode:

```powershell
python .\scripts\13_live_back_video_sender_v2.py `
  --video .\datasets\videos\BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4 `
  --dataset BackOnly_Dynamic_Clean_01_CONSTANT_ON_v2 `
  --rate 20 `
  --skip-send `
  --no-realtime `
  --allow-more-than-two-candidates `
  --pair-strategy best
```

Then analyze the generated log:

```powershell
python .\scripts\14_analyze_video_observation_log.py `
  --csv .\outputs\BackOnly_Dynamic_Clean_01_CONSTANT_ON_v2\video_observation_log_v2.csv
```

Target metrics for a clean constant-ON video:

```text
valid_ratio   ≥ 0.85
invalid_ratio ≤ 0.15
held_ratio    should be low
CANDIDATE_COUNT_NOT_2 should be rare
LOW_CONFIDENCE should be rare
PAIR_NOT_FOUND should be rare
```

For blink-pattern videos, a higher `held_ratio` is acceptable because OFF frames are expected.

---

## 5. Generate Debug Overlay Videos

Before using a video for control tests, generate a debug overlay.

Example:

```powershell
python .\scripts\15_render_video_detection_debug.py `
  --video .\datasets\videos\BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4 `
  --output .\outputs\BackOnly_Dynamic_Clean_01_CONSTANT_ON_v2\debug_overlay.mp4 `
  --allow-more-than-two-candidates
```

Check visually:

* Are the selected green boxes really the two BACK LEDs?
* Does the midpoint move correctly when the robot moves left/right?
* Does `error_x` change sign correctly?
* Does `estimated_distance` decrease when the target gets closer?
* Does `estimated_distance` increase when the target moves away?
* Are false positives selected as LEDs?
* Does the selected LED pair remain stable during motion?

Only use the video for control tests after the overlay is visually reasonable.

---

## 6. Run Controller V2 Tests with Clean Videos

After the video log and overlay are acceptable, run Linux-side controller tests.

### 6.1 Arms-off test

Linux:

```bash
cd ~/bluerov2-led-control
source .venv/bin/activate

python scripts/06_live_udp_to_mavlink_controller.py \
  --runtime 20 \
  --packet-timeout 1.0 \
  --k-forward 100 \
  --k-yaw 120 \
  --max-x 120 \
  --max-r 120 \
  --yaw-deadband 0.04 \
  --forward-deadband 0.15 \
  --ema-alpha 0.35 \
  --max-delta-x-per-sec 240 \
  --max-delta-r-per-sec 260 \
  --invalid-decay-seconds 0.50 \
  --seq-jump-warning-threshold 10 \
  --log-csv logs/control_v2_clean_arms_off_01.csv
```

Windows:

```powershell
python .\scripts\13_live_back_video_sender_v2.py `
  --video .\datasets\videos\BackOnly_Dynamic_Clean_01_CONSTANT_ON.mp4 `
  --dataset BackOnly_Dynamic_Clean_01_CONSTANT_ON_live `
  --ip 192.168.137.228 `
  --port 5005 `
  --rate 20 `
  --loop `
  --allow-more-than-two-candidates `
  --pair-strategy best
```

### 6.2 Armed test

Only after the arms-off test is clean:

```bash
python scripts/06_live_udp_to_mavlink_controller.py \
  --runtime 12 \
  --packet-timeout 1.0 \
  --arm \
  --k-forward 100 \
  --k-yaw 120 \
  --max-x 120 \
  --max-r 120 \
  --yaw-deadband 0.04 \
  --forward-deadband 0.15 \
  --ema-alpha 0.35 \
  --max-delta-x-per-sec 240 \
  --max-delta-r-per-sec 260 \
  --invalid-decay-seconds 0.50 \
  --seq-jump-warning-threshold 10 \
  --log-csv logs/control_v2_clean_armed_01.csv
```

Expected behavior:

```text
valid observation → smooth forward/yaw command
short invalid     → INVALID_DECAY
long invalid      → INVALID_STOP
test end          → STOP + DISARM
```

---

## 7. Add Control Log Analysis

Create a new control-side analysis script in the Linux repository:

```text
scripts/08_analyze_control_log.py
```

It should analyze controller CSV logs such as:

```text
logs/control_v2_armed_test_03.csv
```

Metrics to compute:

* time spent in `TRACK`,
* time spent in `INVALID_DECAY`,
* time spent in `INVALID_STOP`,
* average and maximum `target_x`,
* average and maximum `smooth_x`,
* average and maximum `target_r`,
* average and maximum `smooth_r`,
* command saturation ratio,
* number of STOP transitions,
* packet age statistics,
* held observation ratio.

This will make controller tuning more systematic.

---

## 8. Improve Candidate Pair Selection

The current V2 sender supports best-pair selection, but the scoring should be improved over time.

Current direction:

```text
candidate_count > 2
→ evaluate possible LED pairs
→ select most plausible pair
```

Future scoring criteria:

* area similarity,
* y-axis alignment,
* plausible pixel distance,
* previous midpoint continuity,
* previous pixel-distance continuity,
* temporal stability,
* motion consistency,
* pattern consistency.

This is especially important for cluttered scenes, reflections, multiple LED-like objects and diagonal views.

---

## 9. Improve LED Signaling Strategy

The current blink pattern can interrupt tracking when both LEDs are fully OFF.

Future options:

### Option A — Bright/dim modulation

```text
1 bit → bright LED
0 bit → dim LED
```

The LEDs never fully disappear, so tracking remains continuous.

### Option B — One tracking LED + one pattern LED

```text
LED 1 → always ON tracking beacon
LED 2 → binary pattern LED
```

This allows continuous tracking and pattern decoding at the same time.

### Option C — Constant-ON for control tuning, blink for robustness

Use:

```text
CONSTANT_ON video → controller and tracking tuning
BLINK video       → pattern and hold robustness testing
```

This is the recommended near-term approach.

---

## 10. Move to Live Unity Render / Window Capture

After clean offline video tests are stable, move to live image input.

Create:

```text
scripts/16_live_unity_window_sender.py
```

Target pipeline:

```text
Unity live Game View / render window
→ OpenCV frame capture
→ LED detection
→ UDP observation packet
→ Linux controller V2
→ MAVLink MANUAL_CONTROL
→ Gazebo BlueROV2 motion
```

This will be the first step toward true closed-loop tracking.

Success criteria for live closed-loop tracking:

* `error_x` approaches zero over time,
* yaw command decreases as the target becomes centered,
* estimated distance approaches the desired following distance,
* forward command decreases near the desired distance,
* target loss triggers safe decay/STOP behavior,
* test end always sends STOP + DISARM.

---

## 11. Extend to Multi-Face Detection

After BACK-only tracking is stable, extend detection to:

```text
FRONT
BACK
LEFT
RIGHT
```

Each face should have:

* own color or HSV profile,
* own temporal pattern,
* own geometric pair detector,
* own confidence score.

For diagonal views, do not average all visible LEDs into one global center.

Instead, generate per-face observations:

```text
BACK observation
RIGHT observation
LEFT observation
FRONT observation
```

Then select:

```text
primary_face
secondary_face
```

based on confidence and controller requirements.

---

## 12. Long-Term Goal

The long-term goal is full closed-loop simulation:

```text
Gazebo / ArduSub follower motion
→ Unity or Unreal live visual rendering
→ OpenCV LED detection
→ UDP observation update
→ Controller reduces image and distance error
→ Follower aligns with and follows leader
```

Final success criteria:

* stable target detection,
* stable face identification,
* reliable distance cue,
* smooth forward/yaw control,
* safe STOP on target loss,
* repeatable behavior in Unity and Unreal environments,
* extendable design for real underwater testing.

```
```
