# virtual-webcam

A lightweight Linux desktop app that plays any local video file directly into an OS-level virtual webcam feed. External applications (Discord, OBS, Zoom, Chrome, Firefox) can capture and use it as a physical webcam.

Built with Python, PySide6, OpenCV, and `v4l2loopback`.

Showcase:

<img width="1920" height="1080" alt="showcasee" src="https://github.com/user-attachments/assets/e43ee1f9-2983-4cfd-8adb-f1ab80c1644f" />


---

## Features

- **Desktop GUI**: Clean PySide6 interface with file browser, drag-and-drop, and interactive seek bar.
- **MKV Subtitles & External Subs**: Automatically discovers and extracts embedded subtitles from `.mkv` and `.mp4` files (ASS, SSA, SRT). Also supports loading external `.srt`, `.ass`, `.vtt` files. Subtitles are rendered directly into the virtual camera stream.
- **Audio Streaming & Virtual Mic**: Streams audio from video files into Discord calls via a virtual microphone device with up to 200% volume amplification.
- **Mirror / Flip Video**: Real-time horizontal flip toggle (<kbd>M</kbd>) for Discord unmirroring.
- **Aspect Ratio Preserved**: Letterbox and pillarbox padding ensure video is never stretched or distorted.
- **Custom Res & FPS**: Switch output resolution (480p to 1440p) and frame rate on the fly.
- **Demo / Mock Mode**: Test the app immediately without kernel modules.

---

## Linux Setup (v4l2loopback)

Virtual webcams require the `v4l2loopback` kernel module:

### 1. Install the module

- **Arch / Manjaro**:
  ```bash
  sudo pacman -S --needed v4l2loopback-dkms linux-headers
  ```
- **Ubuntu / Debian**:
  ```bash
  sudo apt install v4l2loopback-dkms
  ```
- **Fedora**:
  ```bash
  sudo dnf install v4l2loopback
  ```

### 2. Load the driver

```bash
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1
```

> **Important**: The `exclusive_caps=1` flag is required for Discord and Chromium to discover the virtual camera device.

---

## Installation & Running

```bash
# Clone the repository
git clone https://github.com/Vure-sh/virtual-webcam.git
cd virtual-webcam

# Setup virtual environment & dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app
./launch.sh
```

---

## How to Use with Discord

### 1. Video Stream
1. Open **Virtual Webcam**, load your video file, and click **Start Virtual Camera**.
2. In Discord, go to **Settings → Voice & Video → Video Settings**.
3. Select **VirtualCam** as your camera device.
4. If your camera preview appears mirrored, press <kbd>M</kbd> or toggle **🪞 Flip/Mirror** in the app. *(Discord mirrors self-previews locally by default, but other call members see the unmirrored feed).*
5. If the video looks blurry, set Discord's **Video Background** to **None** (Discord's background blur filter treats non-human feeds as background).

### 2. Audio Stream (Streaming Sound into Call)
1. In the app, click **🎙️ Setup Virtual Mic for Discord** (or run `./setup_virtual_mic.sh`).
2. In Discord: Go to **Settings → Voice & Video → Input Device (Microphone)** and select **`Virtual_Microphone`**.
3. Use the in-app volume slider to boost audio up to **200%**.
4. **Important**: Under Discord's *Voice Processing*, turn **OFF** `Noise Suppression (Krisp)` and `Echo Cancellation` so Discord doesn't filter out video sound and background music.

### 3. Subtitles (MKV / ASS / SRT)
- When you load an `.mkv` file with embedded subtitles, the app automatically extracts and displays them.
- Choose different subtitle tracks from the **Subtitles** dropdown in the right sidebar.
- Press <kbd>T</kbd> or check/uncheck **💬 Subs** to toggle subtitles on/off.
- Click **📂** to load external `.srt`, `.ass`, or `.vtt` files.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| <kbd>Space</kbd> | Play / Pause playback |
| <kbd>S</kbd> / <kbd>Esc</kbd> | Stop playback |
| <kbd>Ctrl</kbd> + <kbd>O</kbd> | Open video file dialog |
| <kbd>M</kbd> | Toggle horizontal flip / mirror video |
| <kbd>T</kbd> | Toggle subtitles on / off |
| <kbd>L</kbd> | Toggle continuous loop |
| <kbd>P</kbd> | Toggle live preview |
| <kbd>C</kbd> | Start / Stop virtual camera streaming |
| <kbd>←</kbd> / <kbd>→</kbd> | Seek backward / forward 5 seconds |
| <kbd>F1</kbd> / <kbd>Ctrl</kbd> + <kbd>H</kbd> | Open in-app Help & Setup Guide |

---

## CLI Options

```bash
python -m app.main --video path/to/video.mkv --resolution 1080p --fps 30 --start-vcam --autoplay
```

| Option | Description |
|---|---|
| `-v, --video <path>` | Video file path to load on launch |
| `--mirror`, `--flip-h` | Start with video horizontally mirrored |
| `--no-subs` | Disable subtitle rendering |
| `--sub-file <path>` | External subtitle file to load on launch |
| `--no-audio` | Mute audio on launch |
| `-r, --resolution <preset>` | Resolution (`original`, `480p`, `720p`, `1080p`, `1440p`) |
| `-f, --fps <preset>` | Output FPS (`source`, `15`, `24`, `30`, `60`) |
| `-d, --device <node>` | Device node (default: `/dev/video10`) |
| `--mock` | Run in mock mode without kernel module |
| `--start-vcam` | Start streaming to virtual camera on launch |
| `--autoplay` | Start playback automatically on launch |

---

## License

MIT
