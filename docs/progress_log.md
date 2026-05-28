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
