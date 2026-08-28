# Virtual Webcam

A Python desktop application built with PySide6 that streams local video files into an OS-level virtual camera (`v4l2loopback`). Any Linux application (Discord, OBS Studio, Chrome, Zoom, etc.) can discover and select it as a physical webcam.

## Features

- **Desktop GUI**: Clean PySide6 interface with file browser, drag-and-drop, interactive seek bar, and live preview.
- **Controls**: Play, Pause, Stop, Seek, Loop toggle, resolution selector (480p to 1440p), and FPS selector (15 to 60 FPS).
- **Smooth Playback**: Background worker thread with monotonic sub-millisecond pacing loop and aspect-ratio preserving letterbox scaling.
- **Linux Virtual Camera**: Native `v4l2loopback` integration with `exclusive_caps=1` for Discord compatibility.
- **Demo / Mock Mode**: Includes built-in test pattern generator and in-memory mock mode for zero-setup testing.

## Prerequisites (Linux)

Virtual webcams require the `v4l2loopback` kernel module:

### Ubuntu / Debian
```bash
sudo apt update && sudo apt install -y v4l2loopback-dkms
```

### Arch Linux / Manjaro
```bash
sudo pacman -S --needed v4l2loopback-dkms linux-headers
```

### Fedora
```bash
sudo dnf install -y v4l2loopback
```

### Load the Kernel Module
Load `v4l2loopback` with `exclusive_caps=1` (required for Discord/Chromium detection):
```bash
sudo modprobe v4l2loopback devices=1 video_nr=10 card_label="VirtualCam" exclusive_caps=1
```

## Quick Start

### 1. Setup Environment
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Run the App
```bash
./launch.sh
```
Or start directly with Python:
```bash
python -m app.main
```

### 3. (Optional) Install Desktop Shortcut
To launch from your system's application menu:
```bash
./install_desktop_shortcut.sh
```

## Discord Setup

1. Start the Virtual Webcam app, load a video, and click **Start Virtual Camera**.
2. Restart Discord (`Ctrl+R` or relaunch).
3. Go to **Settings** → **Voice & Video** → **Video Settings**.
4. Select **VirtualCam** (or `/dev/video10`).
5. Set **Video Background** to **None** (if background blur is enabled, Discord blurs non-human video feeds).

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Space` | Play / Pause |
| `S` / `Esc` | Stop |
| `Ctrl + O` | Open file dialog |
| `L` | Toggle Loop |
| `P` | Toggle Preview |
| `C` | Start / Stop Virtual Camera |
| `←` / `→` | Seek ±5 seconds |
| `F1` | Help & Setup Guide |

## CLI Options

| Option | Description |
|---|---|
| `-v, --video <path>` | Path to video file to load |
| `--demo` | Generate and load animated test video |
| `-r, --resolution <res>` | Output resolution (`original`, `480p`, `720p`, `1080p`, `1440p`) |
| `-f, --fps <fps>` | Output frame rate (`source`, `15`, `24`, `30`, `60`) |
| `-d, --device <dev>` | Specific V4L2 device node (e.g. `/dev/video10`) |
| `--mock` | Run with simulated in-memory camera (no driver required) |
| `--start-vcam` | Automatically start virtual camera on launch |
| `--autoplay` | Automatically start playback on launch |

## License

MIT
