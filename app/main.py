"""Application Entry Point & CLI Bootstrap for Virtual Webcam Desktop Application."""

from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import List, Optional

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.config import AppConfig, FPSPreset, ResolutionPreset
from app.gui import DARK_STYLESHEET, MainWindow
from app.player import VideoPlayerController

logger = logging.getLogger("virtual_webcam")


def setup_logging(verbose: bool = False) -> None:
    """Configure root logger format and verbosity level."""
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%H:%M:%S",
    )


def build_arg_parser() -> argparse.ArgumentParser:
    """Construct CLI argument parser for application launcher."""
    parser = argparse.ArgumentParser(
        prog="virtual-webcam",
        description="Stream local video files into an OS-level virtual camera feed (v4l2loopback).",
    )

    parser.add_argument(
        "--video",
        "-v",
        type=str,
        default=None,
        help="Path to local video file to automatically load on startup.",
    )
    parser.add_argument(
        "--resolution",
        "-r",
        type=str,
        default="720p",
        help="Target output resolution preset (original, 480p, 720p, 1080p, 1440p). Default: 720p.",
    )
    parser.add_argument(
        "--fps",
        "-f",
        type=str,
        default="source",
        help="Target output FPS preset (source, 15, 24, 30, 60). Default: source.",
    )
    parser.add_argument(
        "--device",
        "-d",
        type=str,
        default=None,
        help="Virtual camera device node path (e.g. /dev/video2). Default: auto-detect.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        default=False,
        help="Force in-memory mock virtual camera backend (useful for testing or environments without v4l2loopback).",
    )
    parser.add_argument(
        "--offscreen",
        action="store_true",
        default=False,
        help="Run Qt application with QT_QPA_PLATFORM=offscreen for headless testing.",
    )
    parser.add_argument(
        "--autoplay",
        action="store_true",
        default=False,
        help="Automatically start playback after loading video.",
    )
    parser.add_argument(
        "--start-vcam",
        action="store_true",
        default=False,
        help="Automatically start streaming to virtual camera device on launch.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose debug logging output.",
    )
    parser.add_argument(
        "--demo",
        "--sample-video",
        action="store_true",
        default=False,
        help="Generate and load an animated test pattern video automatically.",
    )
    parser.add_argument(
        "--mirror",
        "--flip-h",
        dest="mirror",
        action="store_true",
        default=False,
        help="Mirror/flip video horizontally on startup.",
    )
    parser.add_argument(
        "--no-audio",
        "--mute",
        dest="no_audio",
        action="store_true",
        default=False,
        help="Mute/disable audio playback on startup.",
    )
    parser.add_argument(
        "--no-subs",
        "--no-subtitles",
        dest="no_subs",
        action="store_true",
        default=False,
        help="Disable subtitle rendering on startup.",
    )
    parser.add_argument(
        "--sub-file",
        "--subtitle-file",
        dest="sub_file",
        type=str,
        default=None,
        help="Path to external subtitle file (.srt, .ass, .vtt) to load on startup.",
    )

    return parser


def parse_args_to_config(argv: Optional[List[str]] = None) -> Tuple[AppConfig, argparse.Namespace]:
    """Parse CLI arguments and map them to AppConfig instance."""
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if args.offscreen:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"

    # Coerce resolution and FPS presets
    resolution_preset = ResolutionPreset.from_string(args.resolution)
    fps_preset = FPSPreset.from_string(args.fps)

    config = AppConfig(
        video_path=args.video,
        resolution_preset=resolution_preset,
        fps_preset=fps_preset,
        vcam_device=args.device,
        use_mock_camera=bool(args.mock),
        loop_playback=True,
        live_preview_enabled=True,
        flip_horizontal=bool(getattr(args, "mirror", False)),
        audio_enabled=not bool(getattr(args, "no_audio", False)),
        subtitles_enabled=not bool(getattr(args, "no_subs", False)),
    )

    return config, args




def main(argv: Optional[List[str]] = None) -> int:
    """Bootstrap and run PySide6 application event loop."""
    config, args = parse_args_to_config(argv)
    setup_logging(verbose=args.verbose)

    # Initialize QApplication (or reuse existing instance in test harnesses)
    app = QApplication.instance()
    is_external_app = app is not None
    if app is None:
        app = QApplication(sys.argv[:1] if argv is None else [sys.argv[0]])

    app.setApplicationName("VirtualWebcam")
    app.setOrganizationName("VirtualWebcamApp")
    app.setStyleSheet(DARK_STYLESHEET)

    # Allow clean Ctrl+C / SIGINT termination in terminal
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    sigint_timer = QTimer()
    sigint_timer.setInterval(200)
    sigint_timer.timeout.connect(lambda: None)  # Wake up Python interpreter for signal handling
    sigint_timer.start()

    # Create controller and window
    controller = VideoPlayerController(config=config, use_mock_camera=config.use_mock_camera)
    window = MainWindow(config=config, controller=controller)

    # Auto-generate and load demo video if requested
    if getattr(args, "demo", False) and not args.video:
        from app.utils import generate_sample_video
        sample_path = Path.cwd() / "sample_test_video.mp4"
        if not sample_path.exists():
            generate_sample_video(sample_path, width=1280, height=720, fps=30, duration_sec=8)
        args.video = str(sample_path)

    # Auto-load video if provided
    if args.video and Path(args.video).is_file():
        window.load_video(args.video)


    # Auto-start virtual camera if requested
    if args.start_vcam:
        window.settings_widget.vcam_toggle_clicked.emit()

    # Auto-play if requested
    if args.autoplay and args.video:
        controller.play()

    if not args.offscreen and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        window.show()

    # Execute main loop if we created QApplication
    exit_code = 0
    if not is_external_app:
        exit_code = app.exec()
        controller.cleanup()
    else:
        if args.offscreen:
            controller.cleanup()

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
