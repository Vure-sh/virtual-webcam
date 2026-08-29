"""PySide6 Desktop GUI & UI Components for Virtual Webcam.

Components:
- VideoPreviewWidget: Aspect-ratio preserving QPainter viewport with live preview toggle.
- FileSelectorWidget: File browse dialog, drag-and-drop support, metadata badges.
- PlaybackControlWidget: Play/Pause/Stop, click-to-seek timeline slider, loop toggle.
- SettingsWidget: Resolution & FPS dropdowns, device selector, VCam toggle, status LEDs.
- MainWindow: Top-level modern window assembling all components and integrating VideoPlayerController.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt, QTimer, Signal, Slot
from PySide6.QtGui import (
    QAction,
    QBrush,
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QIcon,
    QImage,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QSpacerItem,
    QSplitter,
    QStatusBar,
    QStyle,
    QStyleOptionSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from app.config import AppConfig, FPSPreset, ResolutionPreset
from app.player import PlaybackState, VideoPlayerController
from app.utils import VideoMetadata, format_timestamp, generate_sample_video
from app.virtual_camera import PyVirtualCamBackend


logger = logging.getLogger(__name__)

# Supported drag & drop video extensions
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".webm"}

# Modern Dark Theme Stylesheet
DARK_STYLESHEET = """
QMainWindow, QWidget#CentralWidget {
    background-color: #121316;
    color: #e4e4e7;
    font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
    font-size: 13px;
}

QGroupBox {
    background-color: #1a1b20;
    border: 1px solid #2d3139;
    border-radius: 8px;
    margin-top: 24px;
    padding: 14px 10px 10px 10px;
    font-weight: bold;
    color: #93c5fd;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    top: 6px;
    padding: 0 4px;
}

QPushButton {
    background-color: #272a34;
    color: #f4f4f5;
    border: 1px solid #3b4252;
    border-radius: 6px;
    padding: 6px 14px;
    font-weight: 500;
    min-height: 20px;
}

QPushButton:hover {
    background-color: #353b49;
    border-color: #4c566a;
}

QPushButton:pressed {
    background-color: #20242c;
}

QPushButton:disabled {
    background-color: #181a1f;
    color: #5c6370;
    border-color: #23272e;
}

QPushButton#PrimaryButton {
    background-color: #2563eb;
    color: #ffffff;
    border: 1px solid #3b82f6;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background-color: #1d4ed8;
    border-color: #60a5fa;
}

QPushButton#PrimaryButton:pressed {
    background-color: #1e40af;
}

QPushButton#PrimaryButton:disabled {
    background-color: #1e293b;
    color: #64748b;
    border-color: #334155;
}

QPushButton#DangerButton {
    background-color: #dc2626;
    color: #ffffff;
    border: 1px solid #ef4444;
    font-weight: 600;
}

QPushButton#DangerButton:hover {
    background-color: #b91c1c;
}

QLineEdit {
    background-color: #1e2129;
    color: #f4f4f5;
    border: 1px solid #353b49;
    border-radius: 6px;
    padding: 6px 10px;
    selection-background-color: #3b82f6;
}

QLineEdit:focus {
    border-color: #60a5fa;
}

QComboBox {
    background-color: #1e2129;
    color: #f4f4f5;
    border: 1px solid #353b49;
    border-radius: 6px;
    padding: 5px 10px;
    min-height: 22px;
}

QComboBox:hover {
    border-color: #4c566a;
}

QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 24px;
    border-left: 1px solid #353b49;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}

QComboBox QAbstractItemView {
    background-color: #1e2129;
    color: #f4f4f5;
    border: 1px solid #353b49;
    selection-background-color: #2563eb;
    selection-color: #ffffff;
    outline: none;
}

QCheckBox {
    color: #e4e4e7;
    spacing: 8px;
    font-size: 13px;
}

QCheckBox::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #4c566a;
    border-radius: 4px;
    background-color: #1e2129;
}

QCheckBox::indicator:checked {
    background-color: #2563eb;
    border-color: #3b82f6;
}

QSlider::groove:horizontal {
    height: 6px;
    background-color: #272a34;
    border-radius: 3px;
}

QSlider::sub-page:horizontal {
    background-color: #3b82f6;
    border-radius: 3px;
}

QSlider::handle:horizontal {
    background-color: #f4f4f5;
    border: 2px solid #3b82f6;
    width: 14px;
    height: 14px;
    margin-top: -4px;
    margin-bottom: -4px;
    border-radius: 7px;
}

QSlider::handle:horizontal:hover {
    background-color: #ffffff;
    border-color: #60a5fa;
    transform: scale(1.1);
}

QSlider::handle:horizontal:disabled {
    background-color: #4c566a;
    border-color: #2d3139;
}

QStatusBar {
    background-color: #16181d;
    color: #94a3b8;
    border-top: 1px solid #23272e;
    font-size: 12px;
}

QLabel#Badge {
    background-color: #20242c;
    color: #cbd5e1;
    border: 1px solid #353b49;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: 600;
}

QLabel#StatusActive {
    background-color: #064e3b;
    color: #6ee7b7;
    border: 1px solid #059669;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: bold;
}

QLabel#StatusInactive {
    background-color: #272a34;
    color: #94a3b8;
    border: 1px solid #3b4252;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: bold;
}

QLabel#StatusError {
    background-color: #7f1d1d;
    color: #fca5a5;
    border: 1px solid #dc2626;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 11px;
    font-weight: bold;
}

QFrame#ErrorBanner {
    background-color: #450a0a;
    border: 1px solid #dc2626;
    border-radius: 6px;
    padding: 6px;
}
"""


# ---------------------------------------------------------------------------
# Quick Help & Setup Guide Dialog
# ---------------------------------------------------------------------------


class QuickHelpDialog(QDialog):
    """User-friendly setup and help dialog with setup instructions, shortcuts, and troubleshooting."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Virtual Webcam — Quick Help & Setup Guide")
        self.resize(680, 480)
        self.setStyleSheet(DARK_STYLESHEET)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        tabs = QTabWidget()
        tabs.setStyleSheet("""
            QTabWidget::pane {
                border: 1px solid #2d3139;
                border-radius: 6px;
                background-color: #1a1b20;
                padding: 12px;
            }
            QTabBar::tab {
                background-color: #20242c;
                color: #94a3b8;
                padding: 8px 16px;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #2563eb;
                color: #ffffff;
                font-weight: bold;
            }
        """)

        # Tab 1: Quick Start
        tab_start = QWidget()
        l_start = QVBoxLayout(tab_start)
        l_start.setSpacing(10)
        lbl_start = QLabel(
            "<h2>🚀 3-Step Quick Start</h2>"
            "<ol style='line-height: 1.8; font-size: 13px; color: #e4e4e7;'>"
            "<li><b>Load a Video:</b> Click <code>📂 Open Video...</code>, drag-and-drop a file, or click <code>🎬 Generate Demo Video</code>.</li>"
            "<li><b>Start Virtual Camera:</b> Click the blue <code>Start Virtual Camera</code> button on the right sidebar.</li>"
            "<li><b>Use in Apps:</b> Open Discord, OBS, Zoom, or your browser and select <b>VirtualCam</b> (or /dev/video10) as your camera device.</li>"
            "</ol>"
            "<p style='color: #93c5fd; font-size: 13px;'>💡 <i>Tip: Play, pause, or loop your video at any time — the virtual camera feed streams in real time!</i></p>"
        )
        lbl_start.setWordWrap(True)
        lbl_start.setTextFormat(Qt.TextFormat.RichText)
        l_start.addWidget(lbl_start)
        l_start.addStretch(1)
        tabs.addTab(tab_start, "🚀 Quick Start")

        # Tab 2: Linux Setup (v4l2loopback)
        tab_setup = QWidget()
        l_setup = QVBoxLayout(tab_setup)
        l_setup.setSpacing(10)
        lbl_setup_desc = QLabel(
            "<h3>🐧 Linux Virtual Camera Device Setup</h3>"
            "<p style='color: #cbd5e1; font-size: 13px;'>"
            "On Linux, virtual webcams use the <code>v4l2loopback</code> kernel module. Run the command below in your terminal to create the virtual camera device:</p>"
        )
        lbl_setup_desc.setWordWrap(True)
        lbl_setup_desc.setTextFormat(Qt.TextFormat.RichText)
        l_setup.addWidget(lbl_setup_desc)

        cmd_frame = QFrame()
        cmd_frame.setStyleSheet("background-color: #121316; border: 1px solid #353b49; border-radius: 6px; padding: 8px;")
        cmd_layout = QHBoxLayout(cmd_frame)
        cmd_text = "sudo modprobe v4l2loopback devices=1 video_nr=10 card_label=\"VirtualCam\" exclusive_caps=1"
        lbl_cmd = QLabel(f"<code>{cmd_text}</code>")
        lbl_cmd.setStyleSheet("color: #6ee7b7; font-family: monospace; font-size: 12px; font-weight: bold;")
        lbl_cmd.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        cmd_layout.addWidget(lbl_cmd, stretch=1)

        btn_copy = QPushButton("📋 Copy")
        btn_copy.setMaximumWidth(80)
        btn_copy.clicked.connect(lambda: self._copy_to_clipboard(cmd_text, btn_copy))
        cmd_layout.addWidget(btn_copy)
        l_setup.addWidget(cmd_frame)

        lbl_dkms = QLabel(
            "<p style='color: #94a3b8; font-size: 12px;'>"
            "If not installed yet, install it via: <code>sudo apt install v4l2loopback-dkms</code> (Debian/Ubuntu) or <code>sudo pacman -S v4l2loopback-dkms</code> (Arch)."
            "</p>"
        )
        lbl_dkms.setWordWrap(True)
        lbl_dkms.setTextFormat(Qt.TextFormat.RichText)
        l_setup.addWidget(lbl_dkms)
        l_setup.addStretch(1)
        tabs.addTab(tab_setup, "🐧 Linux Setup")

        # Tab 3: Keyboard Shortcuts
        tab_keys = QWidget()
        l_keys = QVBoxLayout(tab_keys)
        lbl_keys = QLabel(
            "<h3>⌨️ Keyboard Shortcuts</h3>"
            "<table style='width: 100%; border-collapse: collapse; font-size: 13px; line-height: 1.8; color: #e4e4e7;'>"
            "<tr><td><b>Space</b></td><td>Play / Pause playback</td></tr>"
            "<tr><td><b>S / Esc</b></td><td>Stop playback</td></tr>"
            "<tr><td><b>Ctrl+O</b></td><td>Open video file dialog</td></tr>"
            "<tr><td><b>M</b></td><td>Toggle horizontal flip / mirror video</td></tr>"
            "<tr><td><b>T</b></td><td>Toggle subtitles overlay on/off</td></tr>"
            "<tr><td><b>L</b></td><td>Toggle loop playback</td></tr>"
            "<tr><td><b>P</b></td><td>Toggle live preview rendering</td></tr>"
            "<tr><td><b>C</b></td><td>Start / Stop Virtual Camera</td></tr>"
            "<tr><td><b>← / →</b></td><td>Seek backward / forward 5 seconds</td></tr>"
            "<tr><td><b>F1 / Ctrl+H</b></td><td>Open this Help & Setup Guide</td></tr>"
            "</table>"
        )
        lbl_keys.setWordWrap(True)
        lbl_keys.setTextFormat(Qt.TextFormat.RichText)
        l_keys.addWidget(lbl_keys)
        l_keys.addStretch(1)
        tabs.addTab(tab_keys, "⌨️ Shortcuts")

        # Tab 4: Audio Streaming to Discord
        tab_audio = QWidget()
        l_audio = QVBoxLayout(tab_audio)
        lbl_audio = QLabel(
            "<h3>🎙️ How to Stream Audio to Discord / Calls</h3>"
            "<ol style='line-height: 1.8; font-size: 13px; color: #cbd5e1;'>"
            "<li><b>Enable Sound & Boost Volume:</b> Check the <b>🔊 Sound</b> box. You can boost volume up to <b>200%</b> using the slider!</li>"
            "<li><b>Create Virtual Mic:</b> Click <code>🎙️ Setup Virtual Mic for Discord</code> on the sidebar (or run <code>./setup_virtual_mic.sh</code>).</li>"
            "<li><b>Select in Discord:</b> In Discord, go to <b>User Settings (⚙️) → Voice & Video → Input Device (Microphone)</b> and select <b>Virtual_Microphone</b>.</li>"
            "<li><b>IMPORTANT for Audio Clarity:</b> Under Discord's <i>Voice Processing</i>, turn <b>OFF</b> <code>Noise Suppression (Krisp)</code> and <code>Echo Cancellation</code> so Discord doesn't filter out video sound!</li>"
            "</ol>"
        )
        lbl_audio.setWordWrap(True)
        lbl_audio.setTextFormat(Qt.TextFormat.RichText)
        l_audio.addWidget(lbl_audio)
        l_audio.addStretch(1)
        tabs.addTab(tab_audio, "🎙️ Audio Setup")

        # Tab 5: Subtitles
        tab_subs = QWidget()
        l_subs = QVBoxLayout(tab_subs)
        lbl_subs = QLabel(
            "<h3>💬 Subtitle Support (MKV, MP4, SRT, ASS)</h3>"
            "<ul style='line-height: 1.8; font-size: 13px; color: #cbd5e1;'>"
            "<li><b>Embedded MKV Subtitles:</b> When loading an MKV or MP4 video, all subtitle tracks (English, Japanese, etc.) are automatically discovered and loaded!</li>"
            "<li><b>Track Selector:</b> Choose your preferred subtitle track in the right sidebar dropdown, or turn off with <code>Subtitles Off</code>.</li>"
            "<li><b>External Subtitles:</b> Click the 📂 button next to Subtitles to load external <code>.srt</code>, <code>.ass</code>, <code>.ssa</code>, or <code>.vtt</code> subtitle files.</li>"
            "<li><b>Burned into Virtual Stream:</b> Subtitles are rendered directly into the video frames with crisp high-contrast outlines so Discord viewers see them in real time!</li>"
            "</ul>"
        )
        lbl_subs.setWordWrap(True)
        lbl_subs.setTextFormat(Qt.TextFormat.RichText)
        l_subs.addWidget(lbl_subs)
        l_subs.addStretch(1)
        tabs.addTab(tab_subs, "💬 Subtitles")

        # Tab 6: Discord & Troubleshooting
        tab_discord = QWidget()
        l_discord = QVBoxLayout(tab_discord)
        lbl_discord = QLabel(
            "<h3>💡 Discord & App Tips</h3>"
            "<ul style='line-height: 1.7; font-size: 13px; color: #cbd5e1;'>"
            "<li><b>Mirrored Video:</b> Toggle the <b>🪞 Flip/Mirror</b> checkbox (or press <kbd>M</kbd>) to flip video horizontally. Note that Discord locally mirrors your own camera preview, but other people in the call see the unmirrored stream.</li>"
            "<li><b>Blurry Video:</b> Set Discord's <b>Video Background</b> to <b>None</b> (Discord's background blur filter blurs non-human video feeds).</li>"
            "<li><b>Discord Camera Detection:</b> Ensure <code>exclusive_caps=1</code> was included in the modprobe command. Restart Discord after loading the kernel module.</li>"
            "<li><b>WebRTC / Browsers:</b> Chrome and Firefox detect <code>VirtualCam</code> automatically in Google Meet, Zoom Web, etc.</li>"
            "</ul>"
        )
        lbl_discord.setWordWrap(True)
        lbl_discord.setTextFormat(Qt.TextFormat.RichText)
        l_discord.addWidget(lbl_discord)
        l_discord.addStretch(1)
        tabs.addTab(tab_discord, "💡 Discord Tips")



        layout.addWidget(tabs, stretch=1)

        # Close button
        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryButton")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignRight)

    def _copy_to_clipboard(self, text: str, button: QPushButton) -> None:
        """Copy command text to system clipboard and provide visual feedback."""
        cb = QApplication.clipboard()
        if cb is not None:
            cb.setText(text)
            button.setText("✓ Copied!")
            QTimer.singleShot(2000, lambda: button.setText("📋 Copy"))


# ---------------------------------------------------------------------------
# Custom Clickable & Scrubbable Slider
# ---------------------------------------------------------------------------


class ClickableSlider(QSlider):

    """Horizontal QSlider that jumps immediately to click location for click-to-seek."""

    seek_position_changed = Signal(int)

    def __init__(
        self, orientation: Qt.Orientation = Qt.Orientation.Horizontal, parent: Optional[QWidget] = None
    ) -> None:
        super().__init__(orientation, parent)
        self.is_tracking_user: bool = False

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle direct mouse click to calculate exact slider position value."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_tracking_user = True
            opt = QStyleOptionSlider()
            self.initStyleOption(opt)
            slider_rect = self.style().subControlRect(
                QStyle.ComplexControl.CC_Slider, opt, QStyle.SubControl.SC_SliderGroove, self
            )

            if self.orientation() == Qt.Orientation.Horizontal:
                length = slider_rect.width()
                pos = event.position().x() - slider_rect.x()
            else:
                length = slider_rect.height()
                pos = event.position().y() - slider_rect.y()

            if length > 0:
                fraction = max(0.0, min(1.0, pos / length))
                new_val = int(round(self.minimum() + fraction * (self.maximum() - self.minimum())))
                self.setValue(new_val)
                self.seek_position_changed.emit(new_val)
            event.accept()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Clear user tracking on release."""
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_tracking_user = False
            self.seek_position_changed.emit(self.value())
        super().mouseReleaseEvent(event)


# ---------------------------------------------------------------------------
# 1. VideoPreviewWidget
# ---------------------------------------------------------------------------


class VideoPreviewWidget(QWidget):
    """High-performance QPainter viewport displaying incoming RGB frame buffers as QImage.

    Preserves aspect ratio when scaling to widget dimensions (centered with
    black letterbox/pillarbox bars). Includes placeholder text overlays and
    live preview enable/disable toggling.
    """

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

        self._current_image: Optional[QImage] = None
        self._current_frame_idx: int = 0
        self._live_preview_enabled: bool = True
        self._placeholder_text: str = "No Video Loaded\nDrag & drop or click Open Video to start"

    @Slot(object, int)
    def set_frame(self, frame_rgb: np.ndarray, frame_idx: int = 0) -> None:
        """Display an incoming RGB uint8 numpy array frame.

        Args:
            frame_rgb: Numpy uint8 RGB array (height, width, 3).
            frame_idx: Index of the frame being displayed.
        """
        if not self._live_preview_enabled:
            return

        if not isinstance(frame_rgb, np.ndarray) or frame_rgb.size == 0 or frame_rgb.ndim != 3:
            return

        h, w, c = frame_rgb.shape
        if c != 3 or frame_rgb.dtype != np.uint8:
            return

        bytes_per_line = 3 * w
        # QImage created and copied to ensure memory safety across threads
        qimg = QImage(frame_rgb.data, w, h, bytes_per_line, QImage.Format.Format_RGB888).copy()
        self._current_image = qimg
        self._current_frame_idx = int(frame_idx)
        self.update()

    @Slot()
    def clear_frame(self) -> None:
        """Clear current frame image and reset to placeholder view."""
        self._current_image = None
        self._current_frame_idx = 0
        self.update()

    def set_live_preview_enabled(self, enabled: bool) -> None:
        """Enable or disable live preview rendering to save UI CPU load."""
        self._live_preview_enabled = bool(enabled)
        self.update()

    def is_live_preview_enabled(self) -> bool:
        """Return whether live preview is active."""
        return self._live_preview_enabled

    def has_frame(self) -> bool:
        """Return True if a valid frame image is currently loaded."""
        return self._current_image is not None and not self._current_image.isNull()

    def set_placeholder_text(self, text: str) -> None:
        """Update placeholder text string."""
        self._placeholder_text = text
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        """High-performance QPainter draw routine preserving aspect ratio."""
        painter = QPainter(self)
        rect = self.rect()

        # Fill background with dark letterbox canvas
        painter.fillRect(rect, QColor("#0d0e11"))

        if not self._live_preview_enabled:
            # Live preview disabled overlay
            painter.setPen(QColor("#94a3b8"))
            font = painter.font()
            font.setPointSize(13)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                rect,
                Qt.AlignmentFlag.AlignCenter,
                "⚡ Live Preview Paused\n(Virtual Camera streaming continues in background)",
            )
        elif self._current_image is not None and not self._current_image.isNull():
            # Draw aspect-ratio preserved scaled image
            img_w = self._current_image.width()
            img_h = self._current_image.height()
            widget_w = rect.width()
            widget_h = rect.height()

            if img_w > 0 and img_h > 0 and widget_w > 0 and widget_h > 0:
                scale = min(widget_w / float(img_w), widget_h / float(img_h))
                draw_w = max(1, int(round(img_w * scale)))
                draw_h = max(1, int(round(img_h * scale)))
                draw_x = (widget_w - draw_w) // 2
                draw_y = (widget_h - draw_h) // 2

                target_rect = QRect(draw_x, draw_y, draw_w, draw_h)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                painter.drawImage(target_rect, self._current_image)
        else:
            # Placeholder text
            painter.setPen(QColor("#64748b"))
            font = painter.font()
            font.setPointSize(12)
            painter.setFont(font)
            painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, self._placeholder_text)

        painter.end()


# ---------------------------------------------------------------------------
# 2. FileSelectorWidget
# ---------------------------------------------------------------------------


class FileSelectorWidget(QWidget):
    """File selection bar with browse button, file path label, metadata badges, and drag-and-drop."""

    file_selected = Signal(str)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(6)

        # Row 1: Open button, Demo button & Path display
        row1 = QHBoxLayout()
        row1.setSpacing(8)

        self.btn_open = QPushButton("📂 Open Video...")
        self.btn_open.setObjectName("PrimaryButton")
        self.btn_open.setToolTip("Browse and select a video file (MP4, MKV, AVI, MOV, WEBM)")
        self.btn_open.clicked.connect(self._on_browse_clicked)
        row1.addWidget(self.btn_open)

        self.btn_sample = QPushButton("🎬 Demo Video")
        self.btn_sample.setToolTip("Generate and immediately load an animated test pattern video")
        self.btn_sample.clicked.connect(self._on_generate_sample_clicked)
        row1.addWidget(self.btn_sample)

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        self.path_edit.setPlaceholderText("No video loaded. Click 'Open Video...', 'Demo Video', or drag & drop a file here")
        self.path_edit.setToolTip("Loaded video file path")
        row1.addWidget(self.path_edit, stretch=1)

        main_layout.addLayout(row1)

        # Row 2: Metadata badge strip
        row2 = QHBoxLayout()
        row2.setSpacing(8)

        lbl_info = QLabel("Metadata:")
        lbl_info.setStyleSheet("color: #64748b; font-size: 11px; font-weight: bold;")
        row2.addWidget(lbl_info)

        self.badge_resolution = QLabel("Res: --")
        self.badge_resolution.setObjectName("Badge")
        row2.addWidget(self.badge_resolution)

        self.badge_fps = QLabel("FPS: --")
        self.badge_fps.setObjectName("Badge")
        row2.addWidget(self.badge_fps)

        self.badge_codec = QLabel("Codec: --")
        self.badge_codec.setObjectName("Badge")
        row2.addWidget(self.badge_codec)

        self.badge_duration = QLabel("Duration: --")
        self.badge_duration.setObjectName("Badge")
        row2.addWidget(self.badge_duration)

        self.badge_frames = QLabel("Frames: --")
        self.badge_frames.setObjectName("Badge")
        row2.addWidget(self.badge_frames)

        row2.addStretch(1)
        main_layout.addLayout(row2)

    @property
    def file_label(self) -> QLineEdit:
        """Alias for path_edit."""
        return self.path_edit

    @property
    def metadata_label(self) -> QLabel:
        """Alias for badge_resolution."""
        return self.badge_resolution

    def _on_browse_clicked(self) -> None:
        """Open native file dialog to select video."""
        file_filter = (
            "Video Files (*.mp4 *.mkv *.avi *.mov *.webm);;"
            "MP4 Videos (*.mp4);;MKV Videos (*.mkv);;All Files (*)"
        )
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", "", file_filter
        )
        if file_path:
            self.set_file_path(file_path)
            self.file_selected.emit(file_path)

    def _on_generate_sample_clicked(self) -> None:
        """Generate and immediately load a test pattern video."""
        demo_path = Path.cwd() / "sample_test_video.mp4"
        try:
            generate_sample_video(demo_path, width=1280, height=720, fps=30, duration_sec=8)
            self.set_file_path(str(demo_path))
            self.file_selected.emit(str(demo_path))
        except Exception as e:
            logger.error(f"Failed to generate demo video: {e}")

    def set_file_path(self, path: str) -> None:
        """Update file path display."""
        self.path_edit.setText(str(path))


    def set_metadata(self, metadata: Optional[VideoMetadata]) -> None:
        """Update metadata badge strip."""
        if metadata is None or not metadata.is_valid:
            self.clear_metadata()
            return

        self.badge_resolution.setText(f"📺 {metadata.width}x{metadata.height}")
        self.badge_fps.setText(f"⚡ {metadata.fps:.2f} FPS")
        self.badge_codec.setText(f"🎞 {metadata.codec.upper() if metadata.codec else 'N/A'}")
        self.badge_duration.setText(f"⏱ {metadata.duration_formatted}")
        self.badge_frames.setText(f"🔢 {metadata.frame_count} frames")

    def clear_metadata(self) -> None:
        """Reset badges to empty placeholders."""
        self.badge_resolution.setText("Res: --")
        self.badge_fps.setText("FPS: --")
        self.badge_codec.setText("Codec: --")
        self.badge_duration.setText("Duration: --")
        self.badge_frames.setText("Frames: --")

    # -----------------------------------------------------------------------
    # Drag & Drop Support
    # -----------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Inspect drag mime data for acceptable video file extensions."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                suffix = Path(local_path).suffix.lower()
                if suffix in SUPPORTED_VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle dropped video file."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                suffix = Path(local_path).suffix.lower()
                if suffix in SUPPORTED_VIDEO_EXTENSIONS:
                    self.set_file_path(local_path)
                    self.file_selected.emit(local_path)
                    event.acceptProposedAction()
                    return
        event.ignore()


# ---------------------------------------------------------------------------
# 3. PlaybackControlWidget
# ---------------------------------------------------------------------------


class PlaybackControlWidget(QWidget):
    """Playback controls: Play/Pause/Stop, scrubbable seek slider, time label, loop, flip, preview, subtitles, and audio boost controls."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    seek_requested = Signal(int)
    loop_toggled = Signal(bool)
    preview_toggled = Signal(bool)
    flip_toggled = Signal(bool)
    subtitles_toggled = Signal(bool)
    audio_toggled = Signal(bool)
    volume_changed = Signal(int)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_state: PlaybackState = PlaybackState.UNLOADED
        self._total_frames: int = 0
        self._fps: float = 30.0
        self._is_seeking: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 6, 8, 8)
        main_layout.setSpacing(6)

        # Timeline Slider Row
        slider_layout = QHBoxLayout()
        slider_layout.setSpacing(8)

        self.slider = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.setEnabled(False)
        self.slider.sliderPressed.connect(self._on_slider_pressed)
        self.slider.sliderReleased.connect(self._on_slider_released)
        self.slider.sliderMoved.connect(self._on_slider_moved)
        self.slider.seek_position_changed.connect(self._on_seek_position_changed)
        slider_layout.addWidget(self.slider, stretch=1)

        self.lbl_time = QLabel("00:00 / 00:00")
        self.lbl_time.setMinimumWidth(90)
        self.lbl_time.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_time.setStyleSheet("color: #94a3b8; font-family: monospace; font-size: 12px; font-weight: bold;")
        slider_layout.addWidget(self.lbl_time)

        main_layout.addLayout(slider_layout)

        # Control Buttons Row
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        self.btn_play_pause = QPushButton("▶ Play")
        self.btn_play_pause.setObjectName("PrimaryButton")
        self.btn_play_pause.setEnabled(False)
        self.btn_play_pause.setMinimumWidth(85)
        self.btn_play_pause.clicked.connect(self._on_play_pause_clicked)
        controls_layout.addWidget(self.btn_play_pause)

        self.btn_stop = QPushButton("⏹ Stop")
        self.btn_stop.setEnabled(False)
        self.btn_stop.setMinimumWidth(75)
        self.btn_stop.clicked.connect(self._on_stop_clicked)
        controls_layout.addWidget(self.btn_stop)

        controls_layout.addSpacing(10)

        self.chk_loop = QCheckBox("🔁 Loop")
        self.chk_loop.setToolTip("Loop playback continuously (Hotkey: L)")
        self.chk_loop.setChecked(True)
        self.chk_loop.toggled.connect(self.loop_toggled.emit)
        controls_layout.addWidget(self.chk_loop)

        self.chk_flip = QCheckBox("🪞 Flip/Mirror")
        self.chk_flip.setToolTip("Mirror video horizontally (Hotkey: M)")
        self.chk_flip.setChecked(False)
        self.chk_flip.toggled.connect(self.flip_toggled.emit)
        controls_layout.addWidget(self.chk_flip)

        self.chk_subtitles = QCheckBox("💬 Subs")
        self.chk_subtitles.setToolTip("Toggle subtitle overlay on video frames (Hotkey: T)")
        self.chk_subtitles.setChecked(True)
        self.chk_subtitles.toggled.connect(self.subtitles_toggled.emit)
        controls_layout.addWidget(self.chk_subtitles)

        self.chk_preview = QCheckBox("👁 Preview")
        self.chk_preview.setToolTip("Toggle live video preview (Hotkey: P)")
        self.chk_preview.setChecked(True)
        self.chk_preview.toggled.connect(self.preview_toggled.emit)
        controls_layout.addWidget(self.chk_preview)

        controls_layout.addSpacing(10)

        # Audio controls (with up to 200% volume boost)
        self.chk_audio = QCheckBox("🔊 Sound")
        self.chk_audio.setToolTip("Enable/Mute audio playback")
        self.chk_audio.setChecked(True)
        self.chk_audio.toggled.connect(self._on_audio_toggled)
        controls_layout.addWidget(self.chk_audio)

        self.slider_volume = ClickableSlider(Qt.Orientation.Horizontal)
        self.slider_volume.setRange(0, 200)
        self.slider_volume.setValue(150)
        self.slider_volume.setMaximumWidth(80)
        self.slider_volume.setToolTip("Volume: 150% (Boosted)")
        self.slider_volume.valueChanged.connect(self._on_volume_slider_changed)
        controls_layout.addWidget(self.slider_volume)

        self.lbl_volume = QLabel("150%")
        self.lbl_volume.setStyleSheet("color: #94a3b8; font-size: 11px; font-weight: bold;")
        controls_layout.addWidget(self.lbl_volume)

        controls_layout.addStretch(1)
        main_layout.addLayout(controls_layout)

    def _on_audio_toggled(self, checked: bool) -> None:
        """Handle audio toggle."""
        self.slider_volume.setEnabled(checked)
        self.audio_toggled.emit(checked)

    def _on_volume_slider_changed(self, val: int) -> None:
        """Handle volume slider change with boost indicator."""
        boost_suffix = " (Boost)" if val > 100 else ""
        self.lbl_volume.setText(f"{val}%")
        self.slider_volume.setToolTip(f"Volume: {val}%{boost_suffix}")
        self.volume_changed.emit(val)

    @property
    def play_pause_btn(self) -> QPushButton:
        """Alias for btn_play_pause."""
        return self.btn_play_pause

    @property
    def stop_btn(self) -> QPushButton:
        """Alias for btn_stop."""
        return self.btn_stop

    @property
    def loop_checkbox(self) -> QCheckBox:
        """Alias for chk_loop."""
        return self.chk_loop

    @property
    def preview_checkbox(self) -> QCheckBox:
        """Alias for chk_preview."""
        return self.chk_preview

    @property
    def flip_checkbox(self) -> QCheckBox:
        """Alias for chk_flip."""
        return self.chk_flip

    @property
    def subtitles_checkbox(self) -> QCheckBox:
        """Alias for chk_subtitles."""
        return self.chk_subtitles

    @property
    def audio_checkbox(self) -> QCheckBox:
        """Alias for chk_audio."""
        return self.chk_audio

    @property
    def volume_slider(self) -> ClickableSlider:
        """Alias for slider_volume."""
        return self.slider_volume


    @property
    def timeline_slider(self) -> ClickableSlider:
        """Alias for slider."""
        return self.slider

    @property
    def slider_timeline(self) -> ClickableSlider:
        """Alias for slider."""
        return self.slider

    @property
    def current_time_label(self) -> QLabel:
        """Alias for lbl_time."""
        return self.lbl_time

    @property
    def total_time_label(self) -> QLabel:
        """Alias for lbl_time."""
        return self.lbl_time

    @property
    def lbl_current_time(self) -> QLabel:
        """Alias for lbl_time."""
        return self.lbl_time

    @property
    def lbl_total_time(self) -> QLabel:
        """Alias for lbl_time."""
        return self.lbl_time


    def _on_play_pause_clicked(self) -> None:
        """Handle click on Play/Pause toggle button."""
        if self._current_state == PlaybackState.PLAYING:
            self.pause_clicked.emit()
        else:
            self.play_clicked.emit()

    def _on_stop_clicked(self) -> None:
        """Handle click on Stop button."""
        self.stop_clicked.emit()

    def _on_slider_pressed(self) -> None:
        """User started scrubbing."""
        self._is_seeking = True

    def _on_slider_released(self) -> None:
        """User finished scrubbing."""
        self._is_seeking = False
        self.seek_requested.emit(self.slider.value())

    def _on_slider_moved(self, value: int) -> None:
        """User is dragging slider."""
        if self._total_frames > 0 and self._fps > 0:
            cur_sec = value / self._fps
            tot_sec = self._total_frames / self._fps
            self.lbl_time.setText(f"{format_timestamp(cur_sec)} / {format_timestamp(tot_sec)}")

    def _on_seek_position_changed(self, value: int) -> None:
        """Direct seek position clicked."""
        self.seek_requested.emit(value)

    @Slot(object)
    def set_playback_state(self, state: PlaybackState) -> None:
        """Update buttons and controls according to current playback state."""
        self._current_state = state

        if state == PlaybackState.PLAYING:
            self.btn_play_pause.setText("⏸ Pause")
            self.btn_play_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.slider.setEnabled(True)
        elif state in (PlaybackState.PAUSED, PlaybackState.STOPPED, PlaybackState.COMPLETED):
            self.btn_play_pause.setText("▶ Play")
            self.btn_play_pause.setEnabled(True)
            self.btn_stop.setEnabled(True)
            self.slider.setEnabled(True)
        elif state in (PlaybackState.UNLOADED, PlaybackState.ERROR):
            self.btn_play_pause.setText("▶ Play")
            self.btn_play_pause.setEnabled(False)
            self.btn_stop.setEnabled(False)
            self.slider.setEnabled(False)

    @Slot(int, int, float, float)
    def set_position(
        self, current_frame: int, total_frames: int, current_sec: float, total_sec: float
    ) -> None:
        """Update slider and time labels with current playback position."""
        self._total_frames = total_frames
        if total_sec > 0 and total_frames > 0:
            self._fps = total_frames / total_sec

        if total_frames > 0:
            self.slider.setRange(0, total_frames - 1)
            self.slider.setEnabled(True)
        else:
            self.slider.setRange(0, 0)
            self.slider.setEnabled(False)

        if not self._is_seeking and not self.slider.is_tracking_user:
            self.slider.setValue(max(0, min(current_frame, max(0, total_frames - 1))))

        self.lbl_time.setText(f"{format_timestamp(current_sec)} / {format_timestamp(total_sec)}")

    def set_controls_enabled(self, enabled: bool) -> None:
        """Enable or disable all playback buttons and sliders."""
        self.btn_play_pause.setEnabled(enabled)
        self.btn_stop.setEnabled(enabled)
        self.slider.setEnabled(enabled)

    def set_loop_checked(self, checked: bool) -> None:
        """Set loop checkbox state without triggering redundant events."""
        self.chk_loop.blockSignals(True)
        self.chk_loop.setChecked(bool(checked))
        self.chk_loop.blockSignals(False)

    def set_preview_checked(self, checked: bool) -> None:
        """Set live preview checkbox state."""
        self.chk_preview.blockSignals(True)
        self.chk_preview.setChecked(bool(checked))
        self.chk_preview.blockSignals(False)


# ---------------------------------------------------------------------------
# 4. SettingsWidget
# ---------------------------------------------------------------------------


class SettingsWidget(QWidget):
    """Settings sidebar: Resolution/FPS dropdowns, Virtual Camera controls, Subtitles, status indicators."""

    resolution_changed = Signal(object)  # ResolutionPreset
    fps_changed = Signal(object)  # FPSPreset
    vcam_toggle_clicked = Signal()
    device_changed = Signal(str)
    refresh_devices_clicked = Signal()
    setup_virtual_mic_clicked = Signal()
    subtitle_track_selected = Signal(int)
    load_subs_clicked = Signal()
    help_clicked = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(260)
        self._is_vcam_active: bool = False
        self._init_ui()

    def _init_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(14)

        # Output Stream Configuration Group
        grp_stream = QGroupBox("Stream Settings")
        stream_layout = QGridLayout(grp_stream)
        stream_layout.setSpacing(8)
        stream_layout.setContentsMargins(10, 14, 10, 10)

        stream_layout.addWidget(QLabel("Resolution:"), 0, 0)
        self.combo_resolution = QComboBox()
        self.combo_resolution.setToolTip("Target stream resolution (aspect ratio is automatically preserved)")
        self.combo_resolution.addItem("Original (Source)", ResolutionPreset.ORIGINAL)
        self.combo_resolution.addItem("720p HD (1280x720)", ResolutionPreset.P720)
        self.combo_resolution.addItem("1080p FHD (1920x1080)", ResolutionPreset.P1080)
        self.combo_resolution.addItem("480p SD (854x480)", ResolutionPreset.P480)
        self.combo_resolution.addItem("1440p 2K (2560x1440)", ResolutionPreset.P1440)
        self.combo_resolution.setCurrentIndex(1)  # Default 720p
        self.combo_resolution.currentIndexChanged.connect(self._on_resolution_changed)
        stream_layout.addWidget(self.combo_resolution, 0, 1)

        stream_layout.addWidget(QLabel("Frame Rate:"), 1, 0)
        self.combo_fps = QComboBox()
        self.combo_fps.setToolTip("Target output frames-per-second streaming rate")
        self.combo_fps.addItem("Source FPS (Auto)", FPSPreset.SOURCE)
        self.combo_fps.addItem("15 FPS (Eco)", FPSPreset.FPS_15)
        self.combo_fps.addItem("24 FPS (Film)", FPSPreset.FPS_24)
        self.combo_fps.addItem("30 FPS (Standard)", FPSPreset.FPS_30)
        self.combo_fps.addItem("60 FPS (Smooth)", FPSPreset.FPS_60)
        self.combo_fps.setCurrentIndex(0)  # Default Source
        self.combo_fps.currentIndexChanged.connect(self._on_fps_changed)
        stream_layout.addWidget(self.combo_fps, 1, 1)

        main_layout.addWidget(grp_stream)

        # Subtitles Configuration Group
        grp_subs = QGroupBox("Subtitles (MKV / External)")
        subs_layout = QVBoxLayout(grp_subs)
        subs_layout.setSpacing(8)
        subs_layout.setContentsMargins(10, 14, 10, 10)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(6)
        self.combo_subtitles = QComboBox()
        self.combo_subtitles.setToolTip("Select subtitle track (embedded in MKV or external)")
        self.combo_subtitles.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_subtitles.addItem("Subtitles Off", -1)
        self.combo_subtitles.currentIndexChanged.connect(self._on_subtitle_changed)
        sub_row.addWidget(self.combo_subtitles, stretch=1)

        self.btn_load_subs = QPushButton("📂")
        self.btn_load_subs.setToolTip("Load external subtitle file (.srt, .ass, .vtt)")
        self.btn_load_subs.setMaximumWidth(36)
        self.btn_load_subs.clicked.connect(self.load_subs_clicked.emit)
        sub_row.addWidget(self.btn_load_subs)
        subs_layout.addLayout(sub_row)
        main_layout.addWidget(grp_subs)

        # Virtual Camera Device Group
        grp_vcam = QGroupBox("Virtual Camera Output")
        vcam_layout = QVBoxLayout(grp_vcam)
        vcam_layout.setSpacing(10)
        vcam_layout.setContentsMargins(10, 14, 10, 10)

        # Device selection row
        dev_row = QHBoxLayout()
        dev_row.setSpacing(6)
        self.combo_device = QComboBox()
        self.combo_device.setToolTip("Linux V4L2 virtual camera device node (/dev/video*)")
        self.combo_device.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.combo_device.currentIndexChanged.connect(self._on_device_changed)
        dev_row.addWidget(self.combo_device, stretch=1)

        self.btn_refresh = QPushButton("🔄")
        self.btn_refresh.setToolTip("Refresh video devices (/dev/video*)")
        self.btn_refresh.setMaximumWidth(36)
        self.btn_refresh.clicked.connect(self.refresh_devices_clicked.emit)
        dev_row.addWidget(self.btn_refresh)
        vcam_layout.addLayout(dev_row)

        # Start / Stop Toggle Button
        self.btn_vcam_toggle = QPushButton("Start Virtual Camera")
        self.btn_vcam_toggle.setObjectName("PrimaryButton")
        self.btn_vcam_toggle.setToolTip("Start streaming video frames to the virtual camera device (Hotkey: C)")
        self.btn_vcam_toggle.setMinimumHeight(32)
        self.btn_vcam_toggle.clicked.connect(self.vcam_toggle_clicked.emit)
        vcam_layout.addWidget(self.btn_vcam_toggle)

        # Status and Stats Rows
        stats_layout = QGridLayout()
        stats_layout.setSpacing(6)

        stats_layout.addWidget(QLabel("Status:"), 0, 0)
        self.lbl_vcam_status = QLabel("Inactive")
        self.lbl_vcam_status.setObjectName("StatusInactive")
        stats_layout.addWidget(self.lbl_vcam_status, 0, 1)

        stats_layout.addWidget(QLabel("Output FPS:"), 1, 0)
        self.lbl_stream_fps = QLabel("0.0 FPS")
        self.lbl_stream_fps.setStyleSheet("color: #e4e4e7; font-weight: bold;")
        stats_layout.addWidget(self.lbl_stream_fps, 1, 1)

        stats_layout.addWidget(QLabel("Streamed Frames:"), 2, 0)
        self.lbl_frame_count = QLabel("0")
        self.lbl_frame_count.setStyleSheet("color: #e4e4e7; font-weight: bold;")
        stats_layout.addWidget(self.lbl_frame_count, 2, 1)

        vcam_layout.addLayout(stats_layout)
        main_layout.addWidget(grp_vcam)

        # Virtual Mic & Audio Setup Button
        self.btn_virtual_mic = QPushButton("🎙️ Setup Virtual Mic for Discord")
        self.btn_virtual_mic.setToolTip("Create a virtual microphone device so Discord can stream audio from this video (PulseAudio/PipeWire)")
        self.btn_virtual_mic.clicked.connect(self.setup_virtual_mic_clicked.emit)
        main_layout.addWidget(self.btn_virtual_mic)

        # Quick Help Button
        self.btn_help = QPushButton("❓ Setup & Help Guide")
        self.btn_help.setToolTip("Open setup guide, Linux commands, shortcuts, and Discord tips (Hotkey: F1)")
        self.btn_help.clicked.connect(self.help_clicked.emit)
        main_layout.addWidget(self.btn_help)

        main_layout.addStretch(1)

    def _on_subtitle_changed(self, index: int) -> None:
        """Emit selected subtitle track index."""
        track_idx = self.combo_subtitles.itemData(index)
        if track_idx is not None:
            self.subtitle_track_selected.emit(int(track_idx))

    def set_subtitle_tracks(self, tracks: list, active: Optional[object] = None) -> None:
        """Update subtitle track dropdown."""
        self.combo_subtitles.blockSignals(True)
        self.combo_subtitles.clear()
        self.combo_subtitles.addItem("Subtitles Off", -1)
        active_index = 0
        for i, track in enumerate(tracks):
            self.combo_subtitles.addItem(track.display_name(), i)
            if active is not None and (
                track == active
                or getattr(track, "stream_index", None) == getattr(active, "stream_index", None)
            ):
                active_index = i + 1
        if tracks and active_index == 0:
            active_index = 1
        self.combo_subtitles.setCurrentIndex(active_index)
        self.combo_subtitles.blockSignals(False)




    def _on_resolution_changed(self, index: int) -> None:
        """Emit selected ResolutionPreset."""
        data = self.combo_resolution.itemData(index)
        if data is not None:
            try:
                preset = ResolutionPreset.from_string(data)
                self.resolution_changed.emit(preset)
            except ValueError:
                pass

    def _on_fps_changed(self, index: int) -> None:
        """Emit selected FPSPreset."""
        data = self.combo_fps.itemData(index)
        if data is not None:
            try:
                preset = FPSPreset.from_string(data)
                self.fps_changed.emit(preset)
            except ValueError:
                pass

    def _on_device_changed(self, index: int) -> None:
        """Emit selected device string."""
        dev = self.combo_device.currentText()
        self.device_changed.emit(dev)

    def set_devices(self, devices: List[str], selected: Optional[str] = None) -> None:
        """Populate device combobox."""
        self.combo_device.blockSignals(True)
        self.combo_device.clear()

        if not devices:
            self.combo_device.addItem("Auto Detect (v4l2loopback)")
        else:
            for dev in devices:
                self.combo_device.addItem(dev)

        if selected and selected in devices:
            self.combo_device.setCurrentText(selected)

        self.combo_device.blockSignals(False)

    def get_selected_device(self) -> Optional[str]:
        """Return selected device string or None."""
        text = self.combo_device.currentText()
        if "Auto Detect" in text or not text:
            return None
        return text

    def get_selected_resolution(self) -> ResolutionPreset:
        """Return selected resolution preset."""
        data = self.combo_resolution.currentData()
        try:
            return ResolutionPreset.from_string(data) if data is not None else ResolutionPreset.P720
        except ValueError:
            return ResolutionPreset.P720

    def get_selected_fps(self) -> FPSPreset:
        """Return selected FPS preset."""
        data = self.combo_fps.currentData()
        try:
            return FPSPreset.from_string(data) if data is not None else FPSPreset.SOURCE
        except ValueError:
            return FPSPreset.SOURCE

    def set_resolution_preset(self, preset: ResolutionPreset) -> None:
        """Select resolution preset in dropdown."""
        val = preset.value if isinstance(preset, ResolutionPreset) else str(preset)
        for i in range(self.combo_resolution.count()):
            if str(self.combo_resolution.itemData(i)) == str(val):
                self.combo_resolution.setCurrentIndex(i)
                break

    def set_fps_preset(self, preset: FPSPreset) -> None:
        """Select FPS preset in dropdown."""
        val = preset.value if isinstance(preset, FPSPreset) else str(preset)
        for i in range(self.combo_fps.count()):
            if str(self.combo_fps.itemData(i)) == str(val):
                self.combo_fps.setCurrentIndex(i)
                break

    @Slot(bool, str, str)
    def set_vcam_status(self, active: bool, device: str, error: str = "") -> None:
        """Update virtual camera status badge and toggle button state."""
        self._is_vcam_active = bool(active)

        if active:
            self.btn_vcam_toggle.setText("Stop Virtual Camera")
            self.btn_vcam_toggle.setObjectName("DangerButton")
            self.lbl_vcam_status.setText(f"Streaming ({device or 'Active'})")
            self.lbl_vcam_status.setObjectName("StatusActive")
        elif error:
            self.btn_vcam_toggle.setText("Start Virtual Camera")
            self.btn_vcam_toggle.setObjectName("PrimaryButton")
            self.lbl_vcam_status.setText("Error")
            self.lbl_vcam_status.setObjectName("StatusError")
            self.lbl_vcam_status.setToolTip(error)
        else:
            self.btn_vcam_toggle.setText("Start Virtual Camera")
            self.btn_vcam_toggle.setObjectName("PrimaryButton")
            self.lbl_vcam_status.setText("Inactive")
            self.lbl_vcam_status.setObjectName("StatusInactive")
            self.lbl_vcam_status.setToolTip("")

        # Re-apply stylesheet to update selector-based styling
        self.btn_vcam_toggle.style().unpolish(self.btn_vcam_toggle)
        self.btn_vcam_toggle.style().polish(self.btn_vcam_toggle)
        self.lbl_vcam_status.style().unpolish(self.lbl_vcam_status)
        self.lbl_vcam_status.style().polish(self.lbl_vcam_status)

    @Slot(float, int)
    def update_stream_stats(self, fps: float, frame_count: int) -> None:
        """Update stream FPS and frame count displays."""
        self.lbl_stream_fps.setText(f"{fps:.1f} FPS")
        self.lbl_frame_count.setText(f"{frame_count:,}")


# ---------------------------------------------------------------------------
# 5. MainWindow
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    """Main application window assembling TopBar, Preview Viewport, Settings Sidebar, and Controls."""

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        controller: Optional[VideoPlayerController] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Virtual Webcam - PySide6")
        self.resize(1024, 720)
        self.setMinimumSize(800, 540)
        self.setStyleSheet(DARK_STYLESHEET)
        self.setAcceptDrops(True)

        self._config = config or AppConfig()
        self._controller = controller or VideoPlayerController(config=self._config)

        # Performance stats tracking
        self._rendered_frames_count: int = 0
        self._last_fps_calc_time: float = 0.0
        self._frames_since_last_calc: int = 0
        self._current_rendered_fps: float = 0.0

        self._init_ui()
        self._bind_signals()
        self.refresh_devices()

        # Apply initial config selections
        self.settings_widget.set_resolution_preset(self._config.resolution_preset)
        self.settings_widget.set_fps_preset(self._config.fps_preset)
        self.playback_controls.set_loop_checked(self._config.loop_playback)
        self.playback_controls.set_preview_checked(self._config.live_preview_enabled)
        self.preview_widget.set_live_preview_enabled(self._config.live_preview_enabled)

        # If config already contains a video_path, load it
        if self._config.video_path:
            self.load_video(self._config.video_path)

    def _init_ui(self) -> None:
        """Construct window layout and child widgets."""
        central_widget = QWidget(self)
        central_widget.setObjectName("CentralWidget")
        self.setCentralWidget(central_widget)

        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(8)

        # Non-blocking Error Banner with Help Action
        self.error_banner = QFrame()
        self.error_banner.setObjectName("ErrorBanner")
        self.error_banner.setVisible(False)
        banner_layout = QHBoxLayout(self.error_banner)
        banner_layout.setContentsMargins(10, 6, 10, 6)
        banner_layout.setSpacing(8)

        self.lbl_error_message = QLabel()
        self.lbl_error_message.setStyleSheet("color: #fca5a5; font-weight: 500;")
        banner_layout.addWidget(self.lbl_error_message, stretch=1)

        self.btn_banner_help = QPushButton("💡 Setup Guide / Fix")
        self.btn_banner_help.setObjectName("PrimaryButton")
        self.btn_banner_help.setMaximumHeight(26)
        self.btn_banner_help.clicked.connect(self.show_help_dialog)
        banner_layout.addWidget(self.btn_banner_help)

        btn_dismiss_error = QPushButton("✕")
        btn_dismiss_error.setMaximumWidth(28)
        btn_dismiss_error.setStyleSheet("background: transparent; border: none; color: #fca5a5; font-size: 14px;")
        btn_dismiss_error.clicked.connect(lambda: self.error_banner.setVisible(False))
        banner_layout.addWidget(btn_dismiss_error)
        root_layout.addWidget(self.error_banner)


        # Top Bar: File Selector
        self.file_selector = FileSelectorWidget(self)
        root_layout.addWidget(self.file_selector)

        # Center Splitter: Video Preview (Left) + Settings (Right)
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)

        self.preview_widget = VideoPreviewWidget(self)
        self.splitter.addWidget(self.preview_widget)

        self.settings_widget = SettingsWidget(self)
        self.splitter.addWidget(self.settings_widget)
        self.splitter.setStretchFactor(0, 4)
        self.splitter.setStretchFactor(1, 1)

        root_layout.addWidget(self.splitter, stretch=1)

        # Bottom Bar: Playback Controls
        self.playback_controls = PlaybackControlWidget(self)
        root_layout.addWidget(self.playback_controls)

        # Status Bar
        self.status_bar = QStatusBar(self)
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Select a video file to begin.")

    def _bind_signals(self) -> None:
        """Connect UI components to controller slots and worker signals."""
        # File selector -> controller
        self.file_selector.file_selected.connect(self.load_video)

        # Playback controls -> controller & UI update
        self.playback_controls.play_clicked.connect(self._on_play_clicked)
        self.playback_controls.pause_clicked.connect(self._on_pause_clicked)
        self.playback_controls.stop_clicked.connect(self._on_stop_clicked)
        self.playback_controls.seek_requested.connect(self._controller.seek)
        self.playback_controls.loop_toggled.connect(self._controller.set_loop)
        self.playback_controls.flip_toggled.connect(self._controller.set_flip_horizontal)
        self.playback_controls.subtitles_toggled.connect(self._controller.set_subtitles_enabled)
        self.playback_controls.audio_toggled.connect(self._controller.set_audio_enabled)
        self.playback_controls.volume_changed.connect(self._controller.set_volume)
        self.playback_controls.preview_toggled.connect(self._on_preview_toggled)

        # Settings -> controller
        self.settings_widget.resolution_changed.connect(self._on_resolution_changed)
        self.settings_widget.fps_changed.connect(self._on_fps_changed)
        self.settings_widget.subtitle_track_selected.connect(self._controller.select_subtitle_track)
        self.settings_widget.load_subs_clicked.connect(self._on_load_external_subs)
        self.settings_widget.vcam_toggle_clicked.connect(self._on_vcam_toggle_clicked)
        self.settings_widget.refresh_devices_clicked.connect(self.refresh_devices)
        self.settings_widget.setup_virtual_mic_clicked.connect(self._on_setup_virtual_mic)
        self.settings_widget.help_clicked.connect(self.show_help_dialog)

        # Controller -> UI
        self._controller.frame_ready.connect(self._on_frame_ready)
        self._controller.position_changed.connect(self.playback_controls.set_position)
        self._controller.state_changed.connect(self._on_state_changed)
        self._controller.media_loaded.connect(self._on_media_loaded)
        self._controller.subtitles_discovered.connect(self._on_subtitles_discovered)
        self._controller.subtitle_track_changed.connect(self._on_subtitle_track_changed)
        self._controller.vcam_status_changed.connect(self._on_vcam_status_changed)
        self._controller.error_occurred.connect(self.show_error)


    # -----------------------------------------------------------------------
    # Public Controller Delegation
    # -----------------------------------------------------------------------

    @property
    def controller(self) -> VideoPlayerController:
        """Direct reference to player controller facade."""
        return self._controller

    @Slot(str)
    def load_video(self, file_path: str) -> bool:
        """Load a video file into controller and UI."""
        self.error_banner.setVisible(False)
        self.file_selector.set_file_path(file_path)
        success = self._controller.load_video(file_path)
        if success:
            self.status_bar.showMessage(f"Loaded: {os.path.basename(file_path)}")
        return success

    @Slot()
    def refresh_devices(self) -> None:
        """Scan system for available video devices (/dev/video*)."""
        devices = PyVirtualCamBackend.discover_devices()
        selected = self.settings_widget.get_selected_device()
        self.settings_widget.set_devices(devices, selected=selected)
        logger.info(f"Discovered video devices: {devices}")

    # -----------------------------------------------------------------------
    # Internal Slots & Event Handlers
    # -----------------------------------------------------------------------

    @Slot()
    def _on_play_clicked(self) -> None:
        """Handle Play button click."""
        self._controller.play()

    @Slot()
    def _on_pause_clicked(self) -> None:
        """Handle Pause button click."""
        self._controller.pause()
        self.playback_controls.set_playback_state(PlaybackState.PAUSED)
        self.status_bar.showMessage("Paused.")

    @Slot()
    def _on_stop_clicked(self) -> None:
        """Handle Stop button click."""
        self._controller.stop()
        self.playback_controls.set_playback_state(PlaybackState.STOPPED)
        self.status_bar.showMessage("Stopped.")

    @Slot(object, int)
    def _on_frame_ready(self, frame_rgb: np.ndarray, frame_idx: int) -> None:
        """Handle incoming decoded and transformed frame."""
        self.preview_widget.set_frame(frame_rgb, frame_idx)

        # Track rendering FPS and total frame counter
        self._rendered_frames_count += 1
        self._frames_since_last_calc += 1

        import time

        now = time.perf_counter()
        if self._last_fps_calc_time == 0.0:
            self._last_fps_calc_time = now
        elif (now - self._last_fps_calc_time) >= 0.5:
            elapsed = now - self._last_fps_calc_time
            self._current_rendered_fps = self._frames_since_last_calc / elapsed
            self._frames_since_last_calc = 0
            self._last_fps_calc_time = now
            self.settings_widget.update_stream_stats(
                self._current_rendered_fps, self._rendered_frames_count
            )

    @Slot(object)
    def _on_state_changed(self, state: PlaybackState) -> None:
        """Update playback controls and status bar on state transition."""
        self.playback_controls.set_playback_state(state)
        state_labels = {
            PlaybackState.UNLOADED: "Ready. No video loaded.",
            PlaybackState.STOPPED: "Stopped.",
            PlaybackState.PLAYING: "Playing...",
            PlaybackState.PAUSED: "Paused.",
            PlaybackState.COMPLETED: "Playback finished.",
            PlaybackState.ERROR: "Playback Error.",
        }
        msg = state_labels.get(state, f"State: {state.value}")
        self.status_bar.showMessage(msg)

    @Slot(object)
    def _on_media_loaded(self, metadata: VideoMetadata) -> None:
        """Update file selector badges and settings based on loaded video."""
        self.file_selector.set_metadata(metadata)
        self.playback_controls.set_controls_enabled(True)
        self.playback_controls.set_playback_state(PlaybackState.STOPPED)

        # Apply source dimensions to target resolution if PRESET is ORIGINAL
        if self._config.resolution_preset == ResolutionPreset.ORIGINAL:
            w, h = self._config.get_output_dimensions((metadata.width, metadata.height))
            self._controller.set_target_resolution(w, h)

    @Slot(bool, str, str)
    def _on_vcam_status_changed(self, active: bool, device: str, error: str) -> None:
        """Update settings widget and status bar on virtual camera state change."""
        self.settings_widget.set_vcam_status(active, device, error)
        if active:
            self.status_bar.showMessage(f"Virtual camera active on {device or 'default device'}")
        elif error:
            self.status_bar.showMessage(f"Virtual camera error: {error}")
            self.show_error("VirtualCameraError", error)
        else:
            self.status_bar.showMessage("Virtual camera stopped.")

    @Slot(object)
    def _on_resolution_changed(self, preset: ResolutionPreset) -> None:
        """Handle resolution dropdown change."""
        self._config.resolution_preset = preset
        meta = self._controller.get_metadata()
        src_dim = (meta.width, meta.height) if meta else None
        target_w, target_h = self._config.get_output_dimensions(src_dim)
        self._controller.set_target_resolution(target_w, target_h)
        logger.info(f"Target resolution changed to {target_w}x{target_h} ({preset.value})")

    @Slot(object)
    def _on_fps_changed(self, preset: FPSPreset) -> None:
        """Handle FPS dropdown change."""
        self._config.fps_preset = preset
        meta = self._controller.get_metadata()
        src_fps = meta.fps if meta else None
        target_fps = self._config.get_output_fps(src_fps)
        self._controller.set_target_fps(target_fps)
        logger.info(f"Target FPS changed to {target_fps} ({preset.value})")

    @Slot()
    def _on_vcam_toggle_clicked(self) -> None:
        """Handle Start/Stop Virtual Camera button click."""
        if self.settings_widget._is_vcam_active:
            self._controller.stop_virtual_camera()
        else:
            meta = self._controller.get_metadata()
            src_dim = (meta.width, meta.height) if meta else None
            src_fps = meta.fps if meta else None

            w, h = self._config.get_output_dimensions(src_dim)
            fps = self._config.get_output_fps(src_fps)
            device = self.settings_widget.get_selected_device()

            try:
                self._controller.start_virtual_camera(
                    device=device, width=w, height=h, fps=fps
                )
            except Exception as e:
                self.show_error("VirtualCameraError", str(e))

    @Slot(bool)
    def _on_preview_toggled(self, enabled: bool) -> None:
        """Toggle live video preview widget rendering."""
        self._config.live_preview_enabled = bool(enabled)
        self.preview_widget.set_live_preview_enabled(enabled)

    @Slot(str, str)
    def show_error(self, error_type: str, message: str) -> None:
        """Display a non-blocking error banner with clear message."""
        self.lbl_error_message.setText(f"⚠️ [{error_type}] {message}")
        self.error_banner.setVisible(True)
        self.status_bar.showMessage(f"Error: {message}")
        logger.error(f"UI Error [{error_type}]: {message}")

    def show_critical_dialog(self, title: str, message: str) -> None:
        """Display a modal critical error dialog."""
        QMessageBox.critical(self, title, message)

    @Slot(list)
    def _on_subtitles_discovered(self, tracks: list) -> None:

        """Update subtitle track selection in settings sidebar."""
        active = self._controller.get_active_subtitle_track()
        self.settings_widget.set_subtitle_tracks(tracks, active=active)

    @Slot(object)
    def _on_subtitle_track_changed(self, track: Optional[object]) -> None:
        """Reflect active subtitle track changes in UI."""
        tracks = self._controller.get_subtitle_tracks()
        self.settings_widget.set_subtitle_tracks(tracks, active=track)

    @Slot()
    def _on_load_external_subs(self) -> None:
        """Open file dialog to browse for external subtitle files."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Subtitle File",
            "",
            "Subtitle Files (*.srt *.ass *.ssa *.vtt);;All Files (*)",
        )
        if file_path:
            success = self._controller.load_external_subtitles(file_path)
            if success:
                self.status_bar.showMessage(
                    f"Loaded subtitles: {os.path.basename(file_path)}", 6000
                )
            else:
                self.show_error("SubtitleError", f"Failed to load subtitle file: {file_path}")

    @Slot()
    def _on_setup_virtual_mic(self) -> None:
        """Create virtual microphone audio sink & source for Discord streaming."""
        import subprocess

        try:
            # Run setup_virtual_mic.sh if present, otherwise direct pactl commands
            script_path = Path(__file__).resolve().parent.parent / "setup_virtual_mic.sh"
            if script_path.is_file():
                subprocess.run([str(script_path)], capture_output=True, text=True, check=False)
            else:
                subprocess.run(
                    [
                        "pactl",
                        "load-module",
                        "module-null-sink",
                        "sink_name=VirtualMic",
                        "sink_properties=device.description=Virtual_Audio_Sink",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    [
                        "pactl",
                        "load-module",
                        "module-remap-source",
                        "master=VirtualMic.monitor",
                        "source_name=VirtualMic_Source",
                        "source_properties=device.description=Virtual_Microphone",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                subprocess.run(
                    ["pactl", "set-sink-volume", "VirtualMic", "150%"],
                    capture_output=True,
                    check=False,
                )

            self.status_bar.showMessage(
                "✓ Virtual Microphone source active! In Discord: Settings -> Voice & Video -> Input Device -> select 'Virtual_Microphone'.",
                12000,
            )
            self.show_help_dialog()
        except Exception as e:
            self.show_error("VirtualMicError", f"Failed to setup Virtual Microphone: {e}")

    @Slot()
    def show_help_dialog(self) -> None:
        """Open interactive setup and help guide dialog."""
        dialog = QuickHelpDialog(self)
        dialog.exec()

    def keyPressEvent(self, event) -> None:
        """Handle global keyboard shortcuts for user-friendly playback control."""
        key = event.key()
        mods = event.modifiers()

        if key == Qt.Key.Key_Space:
            if self._controller.get_state() == PlaybackState.PLAYING:
                self._on_pause_clicked()
            else:
                self._on_play_clicked()
            event.accept()
        elif key in (Qt.Key.Key_S, Qt.Key.Key_Escape):
            self._on_stop_clicked()
            event.accept()
        elif key == Qt.Key.Key_M and not (mods & Qt.KeyboardModifier.ControlModifier):
            new_val = not self.playback_controls.chk_flip.isChecked()
            self.playback_controls.chk_flip.setChecked(new_val)
            self._controller.set_flip_horizontal(new_val)
            event.accept()
        elif key == Qt.Key.Key_T and not (mods & Qt.KeyboardModifier.ControlModifier):
            new_val = not self.playback_controls.chk_subtitles.isChecked()
            self.playback_controls.chk_subtitles.setChecked(new_val)
            self._controller.set_subtitles_enabled(new_val)
            event.accept()
        elif key == Qt.Key.Key_L and not (mods & Qt.KeyboardModifier.ControlModifier):
            new_val = not self.playback_controls.chk_loop.isChecked()
            self.playback_controls.set_loop_checked(new_val)
            self._controller.set_loop(new_val)
            event.accept()
        elif key == Qt.Key.Key_P and not (mods & Qt.KeyboardModifier.ControlModifier):
            new_val = not self.playback_controls.chk_preview.isChecked()
            self.playback_controls.set_preview_checked(new_val)
            self._on_preview_toggled(new_val)
            event.accept()
        elif key == Qt.Key.Key_C or (key == Qt.Key.Key_V and (mods & Qt.KeyboardModifier.ShiftModifier)):
            self._on_vcam_toggle_clicked()
            event.accept()
        elif key == Qt.Key.Key_Left:
            meta = self._controller.get_metadata()
            if meta and meta.duration_sec > 0:
                cur_frame = self.playback_controls.slider.value()
                fps = meta.fps if meta.fps > 0 else 30.0
                target_frame = max(0, int(cur_frame - 5 * fps))
                self._controller.seek(target_frame)
            event.accept()
        elif key == Qt.Key.Key_Right:
            meta = self._controller.get_metadata()
            if meta and meta.duration_sec > 0:
                cur_frame = self.playback_controls.slider.value()
                fps = meta.fps if meta.fps > 0 else 30.0
                total_frames = meta.frame_count
                target_frame = min(max(0, total_frames - 1), int(cur_frame + 5 * fps))
                self._controller.seek(target_frame)
            event.accept()
        elif key in (Qt.Key.Key_F1, Qt.Key.Key_H) and (key == Qt.Key.Key_F1 or (mods & Qt.KeyboardModifier.ControlModifier)):
            self.show_help_dialog()
            event.accept()
        elif key == Qt.Key.Key_O and (mods & Qt.KeyboardModifier.ControlModifier):
            self.file_selector._on_browse_clicked()
            event.accept()


        else:
            super().keyPressEvent(event)


    # -----------------------------------------------------------------------
    # Drag & Drop at Window Level
    # -----------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Inspect drag mime data for acceptable video file extensions."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                suffix = Path(local_path).suffix.lower()
                if suffix in SUPPORTED_VIDEO_EXTENSIONS:
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Handle dropped video file at window level."""
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                local_path = url.toLocalFile()
                suffix = Path(local_path).suffix.lower()
                if suffix in SUPPORTED_VIDEO_EXTENSIONS:
                    self.load_video(local_path)
                    event.acceptProposedAction()
                    return
        event.ignore()

    # -----------------------------------------------------------------------
    # Lifecycle & Teardown
    # -----------------------------------------------------------------------

    def closeEvent(self, event) -> None:
        """Clean resource teardown on window close."""
        logger.info("Closing MainWindow: cleaning up controller and virtual camera resources.")
        if self._controller is not None:
            self._controller.cleanup()
        event.accept()
