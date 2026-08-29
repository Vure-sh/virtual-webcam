# virtual-webcam

A lightweight Linux desktop app that plays any local video file directly into a virtual webcam feed. Works out of the box with Discord, OBS, Zoom, and web browsers.

Built with Python, PySide6, OpenCV, and `v4l2loopback`.

---

## Why?

Discord and WebRTC browsers on Linux don't have an option to feed a local video file as a camera stream. This app handles the video decoding, pacing, and letterboxing, and outputs clean frames into a Linux virtual camera device (`/dev/video*`) that other apps detect as a real webcam.

## Features

- **Simple UI**: File picker, drag-and-drop, playback controls (Play, Pause, Stop, Seek, Loop), and a live preview.
- **Aspect Ratio Safe**: Keeps your video's original aspect ratio without stretching (adds clean letterboxing if needed).
- **Custom Res & FPS**: Switch output resolution (480p to 1440p) and frame rate on the fly.
- **Discord Ready**: Pre-configured with the flags Discord/Chromium need to detect the feed.
- **Demo Mode**: Includes a built-in test generator and mock camera mode so you can test it without setting up kernel modules first.

---

## Linux Setup (v4l2loopback)

Virtual webcams require the `v4l2loopback` kernel module.

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

> **Note on `exclusive_caps=1`**: Discord (and Chromium) will completely ignore the virtual camera if this flag is missing. It tells the driver to present only capture capabilities to user apps.

---

## Installation & Running

```bash
# Clone and enter the directory
git clone https://github.com/Vure-sh/virtual-webcam.git
cd virtual-webcam

# Setup virtualenv & install dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Run the app
./launch.sh
```

*(You can also run `./install_desktop_shortcut.sh` if you want to launch it from your Linux application menu.)*

---

## Using it with Discord

1. Open **Virtual Webcam**, pick a video (or hit **Demo Video**), and click **Start Virtual Camera**.
2. Relaunch Discord (or press `Ctrl + R` to refresh).
3. Head to **Settings → Voice & Video → Video Settings**.
4. Select **VirtualCam** as your camera.
5. **Important**: Turn off Discord's **Video Background** (set it to **None**). If blur is turned on, Discord won't detect a human face in the video and will blur the entire stream.

---

## Shortcuts

- `Space`: Play / Pause
- `S` or `Esc`: Stop
- `Ctrl + O`: Open video file
- `L`: Toggle loop
- `P`: Toggle preview
- `C`: Start / Stop virtual camera
- `←` / `→`: Seek ±5 seconds
- `F1`: Open in-app help guide

---

## CLI Flags

If you prefer running from the terminal without using the GUI dialogs:

```bash
python -m app.main --video path/to/video.mp4 --resolution 1080p --fps 30 --start-vcam --autoplay
```

| Flag | Description |
|---|---|
| `-v, --video <file>` | Path to video file |
| `--demo` | Generate and load a sample test video |
| `-r, --resolution <preset>` | Output resolution (`original`, `480p`, `720p`, `1080p`, `1440p`) |
| `-f, --fps <preset>` | Output FPS (`source`, `15`, `24`, `30`, `60`) |
| `-d, --device <dev>` | Device path (default: `/dev/video10`) |
| `--mock` | Run in test mode without kernel module |
| `--start-vcam` | Start virtual camera automatically |
| `--autoplay` | Start playback automatically |

---

## License

MIT
