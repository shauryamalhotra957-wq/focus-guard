# Focus Guard

Focus Guard is a local Windows app that watches for **sustained visible phone
use during a work session**. When the phone remains in use for the configured
delay, it plays your selected reminder song. Put the phone down and the audio
stops after the clear delay.

> A webcam cannot reliably identify Instagram Reels specifically. This first
> version detects a phone held near the primary person. It will also react to
> texting, videos, and other visible phone use.

## What is included

- Live webcam preview with phone detection boxes
- Six-second default dwell time to avoid instant false alarms
- Evidence smoothing for brief missed detections
- One reminder per continuous phone-use episode
- Automatic audio stop after the phone leaves view
- Cooldown, five-minute snooze, and manual dismissal
- Configurable confidence, camera, timing, volume, and ignored desk strip
- Local, in-memory processing: no frame recording or uploading

The commercial song is intentionally **not included**. Select a lawfully
obtained local MP3, OGG, or WAV copy of:

**KITSCHKRIEG feat. BLUMENGARTEN & SHIRIN DAVID – GUT GENUG**

## Quick start on Windows

1. Install **64-bit Python 3.11** from
   [python.org](https://www.python.org/downloads/). During installation, enable
   **Add python.exe to PATH**.
2. Double-click `setup_and_run.bat`.
3. In Focus Guard, click **Choose file** and select your song.
4. Put an unused phone in the shaded bottom desk zone.
5. Click **Start work session**.

The first start installs the Python packages and downloads the small
`yolo26n.pt` detection model. Later starts reuse them.

### Manual setup

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

## Tuning

- **Trigger after:** Increase this if legitimate brief phone pickups cause
  reminders. Start with 6–10 seconds.
- **Confidence:** Increase this if phone-shaped objects trigger the detector;
  lower it if your phone is often missed.
- **Ignore bottom:** Adjust the shaded strip so a phone lying on your desk is
  ignored, while a phone lifted for viewing is outside the strip.
- **Require phone near primary person:** Reduces background-person alerts.
  Disable it if the camera only sees your hands and the person detector fails.
- **Camera:** `0` is usually the built-in/default webcam. Try `1` for a second
  camera.

For best results, keep your upper body and the area where you hold the phone
visible, use front lighting, and avoid parking the phone beside your face.

## Privacy

Video frames are sent from OpenCV directly to the local YOLO model, displayed
in the preview, and discarded. The app does not implement video capture,
screenshots, face recognition, analytics, or uploads. On Windows,
`%LOCALAPPDATA%\Focus Guard\settings.json` stores only the controls and local
song path. Existing settings from the project directory are copied there on
the first run and left in place as a safe fallback.

The model weights download from Ultralytics on first use. Once the model and
packages are installed, detection itself runs locally.

## Tests

The timing policy has dependency-free tests:

```powershell
python -m unittest discover -s tests -v
```

Useful physical checks:

1. Show the phone for less than the trigger time: no alert.
2. Hold it up past the trigger time: exactly one alert.
3. Keep holding it: the song must not restart or overlap.
4. Put it down: audio stops after the clear delay.
5. Lift it again during cooldown: no alert.
6. Try a remote, wallet, mug, and a phone parked in the shaded desk strip.
7. Stop the session and confirm the webcam activity light turns off.

## Current limitations

- It detects visible phone-use behavior, not the app or content on the screen.
- Small, hidden, dark, or edge-of-frame phones can be missed.
- A mounted phone near your face can look like active use.
- Holding a phone for legitimate work can still trigger the reminder.
- Ultralytics/PyTorch is a relatively large first-time install.

Recognizing Reels specifically would need a separate phone-side integration or
a custom screen-content classifier trained on visible phone displays. Head-pose
or gaze estimation could be added later, but should be an optional signal
because glasses, low light, and side views make it unreliable.

## Technical notes

The app uses the current Ultralytics prediction/result APIs and resolves the
COCO `cell phone` class by name instead of assuming a numeric ID:

- [Ultralytics prediction mode](https://docs.ultralytics.com/modes/predict/)
- [Ultralytics results API](https://docs.ultralytics.com/reference/engine/results/)
- [pygame streamed music API](https://www.pygame.org/docs/ref/music.html)
