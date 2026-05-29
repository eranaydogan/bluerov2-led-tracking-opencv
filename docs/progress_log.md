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
