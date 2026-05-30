
```md
# Dataset Notes

Large datasets are not committed to GitHub.

Datasets should be stored externally as ZIP files using Google Drive, OneDrive, or another file sharing service.

Recommended structure:

```text
Unity_LED_Dataset/
├── BackOnly_Test_01/
├── BackOnly_Test_02/
├── BackOnly_Test_03/
├── BackOnly_Test_04/
├── BackOnly_Test_05/
├── BackOnly_Test_06/
└── videos/
    └── BackOnly_Dynamic_Test_01.mp4

Repository-local structure:

datasets/
├── BackOnly_Test_04/
└── videos/
    └── BackOnly_Dynamic_Test_01.mp4

Generated outputs:

outputs/
├── BackOnly_Test_04/
└── BackOnly_Dynamic_Test_01/
    └── video_observation_log.csv
PNG vs MP4 Usage
PNG sequence

PNG sequences are preferred for:

HSV calibration,
LED color analysis,
exact frame-level pattern decoding,
distance calibration,
pixel-distance statistics,
algorithm development without compression artifacts.

PNG should be used when exact color and blob shape are important.

MP4 video

MP4 videos can be used for:

video-based integration testing,
dynamic movement tests,
stress testing with occlusion,
checking OpenCV video processing,
checking UDP observation streaming,
checking Linux controller behavior with changing observations,
demonstration.

MP4 compression may change:

HSV values,
LED edges,
bloom shape,
contour area,
candidate count,
pixel distance.

Therefore, MP4 should not replace PNG for final calibration. However, MP4 is useful for integration and stress testing.

Current Dynamic Video Dataset
BackOnly_Dynamic_Test_01

Type:

Unity Recorder Movie / H.264 MP4

Path:

datasets/videos/BackOnly_Dynamic_Test_01.mp4

Properties:

Resolution: 1920x1080
FPS: 60.0
Frame count: 1201
Duration: 20.0167 s

Scene:

fixed camera,
BACK LEDs active,
leader robot moved manually using Python UDP keyboard control,
follower/control side not part of the video recording itself.

Movement sequence:

right movement,
left movement,
forward movement,
temporary fish occlusion,
return movement,
yaw right/left test,
stopped without reset.

Known notes:

Fish occlusion appears in the video.
Some frames produce BIT_OFF.
Some frames produce LOW_CONFIDENCE.
Some frames produce CANDIDATE_COUNT_NOT_2.
Some frames require held_observation.

This video is useful as an integration/stress-test dataset, not as a clean calibration dataset.

Git Policy

Do not commit large dataset files directly.

Recommended .gitignore entries:

datasets/**/*.png
datasets/**/*.mp4
outputs/**/*
!outputs/.gitkeep

If a small sample file is needed for documentation, place it under a dedicated sample folder and document why it is included.


---