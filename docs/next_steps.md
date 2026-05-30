```md
# Next Steps

## Current Status

The project has now passed the offline video-based integration stage.

Validated pipeline:

```text
Unity recorded video
→ OpenCV video detection
→ UDP observation packet
→ Linux controller
→ MAVLink MANUAL_CONTROL
→ ArduSub/Gazebo motion
→ STOP/DISARM safety

This is not yet a true live closed-loop tracking system because the input video is pre-recorded. The next major goal is to move from offline video to live Unity/Unreal render capture.

1. Analyze Video Observation Log

Create:

scripts/14_analyze_video_observation_log.py

Input:

outputs/BackOnly_Dynamic_Test_01/video_observation_log.csv

The script should compute:

total packet count,
valid packet count,
invalid packet count,
held observation count,
valid ratio,
invalid reason distribution,
candidate count distribution,
error_x min/max/mean,
estimated_distance min/max/mean,
pixel_distance min/max/mean.

This will show how stable the current video-based detector is.

2. Render Debug Overlay Video

Create:

scripts/15_render_video_detection_debug.py

Input:

datasets/videos/BackOnly_Dynamic_Test_01.mp4

Output:

outputs/BackOnly_Dynamic_Test_01/debug_overlay.mp4

The overlay should display:

all LED candidates,
selected LED pair,
pair midpoint,
image center,
normalized error,
estimated distance,
valid / held / invalid state,
invalid reason.

This is necessary to understand why frames become:

BIT_OFF
LOW_CONFIDENCE
CANDIDATE_COUNT_NOT_2
PAIR_NOT_FOUND
3. Improve Candidate Pair Selection

Current temporary rule:

candidate_count == 2

This works in controlled back-only PNG tests but is too strict for dynamic video and live scenes.

Future method:

Evaluate all possible candidate pairs.
Score each pair using:
area similarity,
vertical alignment,
plausible pixel distance,
temporal consistency,
distance continuity,
previous valid pair position.
Select the highest scoring pair.
Reject the frame if no pair is reliable enough.

This should reduce false invalid states caused by candidate_count > 2.

4. Improve Hold Logic

Current hold logic:

hold_seconds = 0.35

Future reason-based hold logic:

BIT_OFF                  → allow longer hold
LOW_CONFIDENCE           → allow short hold
CANDIDATE_COUNT_NOT_2    → allow short hold if previous pair was stable
PAIR_NOT_FOUND           → very short hold or STOP
long occlusion           → STOP

The goal is to reduce unnecessary TRACK → STOP → TRACK transitions while keeping safety.

5. Improve Linux Controller

Create a next controller version:

06_live_udp_to_mavlink_controller.py

New features:

yaw deadband,
forward deadband,
EMA command smoothing,
acceleration limiting,
confidence-based gain scaling,
CSV control log output,
explicit state machine.

Suggested state machine:

NO_PACKET
PACKET_TIMEOUT
INVALID
ALIGN_ONLY
TRACK
SEARCH
STOP

Initial behavior:

TRACK:
  valid=True, confidence high
  x and r active

ALIGN_ONLY:
  valid=True but distance confidence low
  only yaw active

INVALID:
  short invalid period
  STOP or short hold depending on reason

PACKET_TIMEOUT:
  STOP

SEARCH:
  optional low-speed yaw scan

STOP:
  neutral MANUAL_CONTROL
6. Record Cleaner Dynamic Unity Videos

The first dynamic video included a fish occlusion. This was useful as a stress test, but cleaner videos are needed for controlled evaluation.

Record:

BackOnly_Dynamic_Clean_01
BackOnly_Lateral_Right_Left_01
BackOnly_Distance_In_Out_01
BackOnly_Yaw_Test_01
BackOnly_Occlusion_Test_01

Each video should document:

camera setup,
leader start position,
movement sequence,
FPS,
resolution,
whether occlusion exists,
whether motion blur is enabled.
7. Move to Live Unity Render Capture

After video-based tests are stable, move to live input.

Possible script:

scripts/16_live_unity_window_sender.py

Target pipeline:

Unity live camera/render
→ OpenCV frame processing
→ UDP observation packet
→ Linux controller
→ MAVLink MANUAL_CONTROL
→ Gazebo/ArduSub motion

This will be the first real step toward closed-loop tracking.

8. Extend to Multi-Face Detection

After BACK-only tracking is stable, extend to:

FRONT
LEFT
RIGHT

Each face should have:

own color or HSV range,
own binary pattern,
own pair detector,
own pattern confidence,
own distance confidence.

For diagonal views, do not average all LEDs into one point.

Instead, generate per-face observations:

BACK observation
RIGHT observation
LEFT observation
FRONT observation

Then select:

primary_face
secondary_face

based on confidence.

9. Long-Term Goal

The long-term goal is true closed-loop simulation:

Gazebo/ArduSub follower motion
→ Unity/Unreal live camera view changes
→ OpenCV detects updated LED position
→ UDP observation updates
→ controller reduces error
→ follower aligns with and follows leader

Success criteria:

error_x approaches zero,
yaw command approaches zero,
estimated_distance approaches desired distance,
forward command approaches zero near target distance,
target loss triggers safe STOP or SEARCH,
exit always sends STOP and DISARM.

---
