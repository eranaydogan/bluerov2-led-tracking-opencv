# Next Steps

## 1. Distance Calibration

Record back-only datasets at known distances:

```text
BackOnly_1m
BackOnly_2m
BackOnly_3m
BackOnly_4m
BackOnly_5m
```

For each dataset:

1. Run `04_back_pair_distance_extract.py`
2. Run `05_back_pattern_decode.py`
3. Run `06_back_distance_analysis.py`
4. Record:

   * median pixel distance,
   * filtered mean,
   * standard deviation,
   * pattern score.

## 2. Build Calibration Table

Example:

| Real distance | Median pixel distance | Pattern score | Std |
| ------------- | --------------------: | ------------: | --: |
| 1 m           |                     ? |             ? |   ? |
| 2 m           |                     ? |             ? |   ? |
| 3 m           |                     ? |             ? |   ? |
| 4 m           |                     ? |             ? |   ? |
| 5 m           |                     ? |             ? |   ? |

## 3. Improve Pair Selection

Current temporary filter:

```python
candidate_count == 2
```

Future method:

* evaluate all candidate pairs,
* choose the most geometrically plausible pair,
* compare with previous valid distance,
* reject unstable or isolated false positives.

## 4. Extend to Other Faces

After the back face is stable, repeat the process for:

* front face,
* left face,
* right face.

## 5. Multi-Face Detection

After single-face tests are validated, enable all LED groups and test multi-pattern detection.
