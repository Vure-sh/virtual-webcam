#!/usr/bin/env bash
# ==============================================================================
# Install Linux Desktop Launcher Shortcut for Virtual Webcam
# ==============================================================================

set -e
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_DIR="$HOME/.local/share/applications"
mkdir -p "$DESKTOP_DIR"

DESKTOP_FILE="$DESKTOP_DIR/virtual-webcam.desktop"

cat << DESKTOP_CONTENT > "$DESKTOP_FILE"
[Desktop Entry]
Version=1.0
Type=Application
Name=Virtual Webcam
Comment=Stream local videos into an OS-level virtual camera for Discord & OBS
Exec=$PROJECT_DIR/launch.sh
Path=$PROJECT_DIR
Icon=camera-video
Terminal=false
Categories=AudioVideo;Video;Utility;
Keywords=webcam;camera;virtual;video;discord;obs;stream;
DESKTOP_CONTENT

chmod +x "$DESKTOP_FILE"

echo "✓ Virtual Webcam desktop shortcut installed successfully to:"
echo "  $DESKTOP_FILE"
echo "You can now search for 'Virtual Webcam' in your application menu!"
