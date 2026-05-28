# Dataset Notes

Large PNG datasets are not committed to GitHub.

Datasets should be stored externally as ZIP files using Google Drive, OneDrive, or another file sharing service.

Recommended structure:

```text
Unity_LED_Dataset/
├── BackOnly_Test_01/
├── BackOnly_1m/
├── BackOnly_2m/
├── BackOnly_3m/
├── BackOnly_4m/
└── BackOnly_5m/
```

Each folder should contain PNG frames recorded from Unity Recorder.

Do not convert the PNG sequence to MP4 for algorithm testing. Video compression may change colors, edges, bloom, and HSV values.

MP4 can be used only for demonstration or presentation.
