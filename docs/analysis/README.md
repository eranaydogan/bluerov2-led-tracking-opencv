# Mission Trajectory Analysis

This directory contains the post-processing and visualization tools used to
analyze logged leader and follower motion from the BlueROV2 tracking simulation.

## Contents

- `path_analysis.py` — trajectory processing, metric calculation, static plots, and interactive 3D mission replay
- `path_analysis_dashboard.html` — interactive Plotly-based 3D mission visualization
- `leader_path_log.csv` — logged leader pose data
- `follower_path_log.csv` — logged follower pose data
- `gps_surface_log.csv` — surface-position log generated after the emergency ascent
- `path_analysis_1_top_view.png` — top-down X-Z trajectory comparison
- `path_analysis_2_depth_time.png` — depth profile over time
- `path_analysis_3_separation_time.png` — leader–follower separation over time
- `path_analysis_4_target_error_time.png` — follower horizontal error to the target

The pose logs contain timestamped position and yaw measurements:

```text
time_s, x, y, z, yaw

Position logs are converted from Unity units to meters during analysis.

Tracking-performance statistics are calculated separately from the emergency
ASCEND phase, since the follower intentionally leaves the leader once the
failsafe behavior is triggered.
