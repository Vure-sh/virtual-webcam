"""Aspect ratio letterbox/pillarbox geometry, frame transformations, media probing, and formatters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

import cv2
import numpy as np


@dataclass(frozen=True)
class LetterboxGeometry:
    """Calculated geometry for aspect-ratio preserving frame letterboxing/pillarboxing."""

    target_width: int
    target_height: int
    scaled_width: int
    scaled_height: int
    pad_left: int
    pad_top: int
    scale_factor: float

    @property
    def pad_right(self) -> int:
        """Right padding in pixels."""
        return max(0, self.target_width - self.scaled_width - self.pad_left)

    @property
    def pad_bottom(self) -> int:
        """Bottom padding in pixels."""
        return max(0, self.target_height - self.scaled_height - self.pad_top)


def calculate_letterbox_geometry(
    src_w: int, src_h: int, dst_w: int, dst_h: int
) -> LetterboxGeometry:
    """Calculate exact scaling and padding to fit source into destination preserving aspect ratio.

    Args:
        src_w: Source video width (> 0)
        src_h: Source video height (> 0)
        dst_w: Target output width (> 0)
        dst_h: Target output height (> 0)

    Returns:
        LetterboxGeometry with scaled dimensions and padding offsets.

    Raises:
        ValueError: If any input dimension is non-positive.
    """
    if src_w <= 0 or src_h <= 0 or dst_w <= 0 or dst_h <= 0:
        raise ValueError(
            f"Dimensions must be positive integers. Got src=({src_w}, {src_h}), dst=({dst_w}, {dst_h})"
        )

    scale_w = dst_w / float(src_w)
    scale_h = dst_h / float(src_h)
    scale_factor = min(scale_w, scale_h)

    # Scale while strictly constraining within target dimensions
    scaled_w = max(1, min(dst_w, int(round(src_w * scale_factor))))
    scaled_h = max(1, min(dst_h, int(round(src_h * scale_factor))))

    # Symmetric padding (center on canvas)
    pad_left = (dst_w - scaled_w) // 2
    pad_top = (dst_h - scaled_h) // 2

    return LetterboxGeometry(
        target_width=dst_w,
        target_height=dst_h,
        scaled_width=scaled_w,
        scaled_height=scaled_h,
        pad_left=pad_left,
        pad_top=pad_top,
        scale_factor=scale_factor,
    )


def transform_frame(
    frame_bgr: np.ndarray,
    target_w: int,
    target_h: int,
    out_canvas: Optional[np.ndarray] = None,
    flip_horizontal: bool = False,
) -> np.ndarray:
    """Transform an input frame (BGR/gray) into a letterboxed RGB output frame on canvas.

    Converts color space from BGR to RGB, resizes with optimal interpolation
    (cv2.INTER_AREA for downscaling, cv2.INTER_CUBIC for upscaling), optionally flips horizontally,
    and centers the scaled frame onto a black canvas buffer.

    Args:
        frame_bgr: Input frame (numpy uint8 array with 2 or 3 dimensions).
        target_w: Destination width (> 0).
        target_h: Destination height (> 0).
        out_canvas: Optional preallocated uint8 array of shape (target_h, target_w, 3) for zero-copy reuse.
        flip_horizontal: If True, mirror the frame horizontally.

    Returns:
        RGB uint8 numpy array of shape (target_h, target_w, 3).

    Raises:
        ValueError: If input frame is invalid or target dimensions are non-positive.
    """
    if not isinstance(frame_bgr, np.ndarray):
        raise ValueError(f"frame_bgr must be a numpy.ndarray, got {type(frame_bgr)}")
    if frame_bgr.size == 0 or frame_bgr.ndim < 2:
        raise ValueError("frame_bgr must be a non-empty 2D or 3D array")
    if target_w <= 0 or target_h <= 0:
        raise ValueError(
            f"Target dimensions must be positive integers, got ({target_w}, {target_h})"
        )

    src_h, src_w = frame_bgr.shape[:2]

    # Convert color to RGB
    if frame_bgr.ndim == 2:
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2RGB)
    elif frame_bgr.shape[2] == 4:
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGRA2RGB)
    elif frame_bgr.shape[2] == 3:
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    else:
        raise ValueError(f"Unsupported number of frame channels: {frame_bgr.shape[2]}")

    geom = calculate_letterbox_geometry(src_w, src_h, target_w, target_h)

    # Perform resizing with optimal interpolation for maximum sharpness
    if geom.scaled_width == src_w and geom.scaled_height == src_h:
        scaled_frame = rgb_frame
    else:
        interpolation = (
            cv2.INTER_AREA if geom.scale_factor < 1.0 else cv2.INTER_CUBIC
        )
        scaled_frame = cv2.resize(
            rgb_frame,
            (geom.scaled_width, geom.scaled_height),
            interpolation=interpolation,
        )

    if flip_horizontal:
        scaled_frame = cv2.flip(scaled_frame, 1)

    # Canvas buffer management
    if (
        out_canvas is not None
        and isinstance(out_canvas, np.ndarray)
        and out_canvas.shape == (target_h, target_w, 3)
        and out_canvas.dtype == np.uint8
    ):
        canvas = out_canvas
        canvas.fill(0)
    else:
        canvas = np.zeros((target_h, target_w, 3), dtype=np.uint8)

    # Blit resized content centered on canvas
    y_start = geom.pad_top
    y_end = geom.pad_top + geom.scaled_height
    x_start = geom.pad_left
    x_end = geom.pad_left + geom.scaled_width

    canvas[y_start:y_end, x_start:x_end] = scaled_frame
    return canvas



@dataclass(frozen=True)
class VideoMetadata:
    """Probed metadata for a video file."""

    file_path: str
    width: int
    height: int
    fps: float
    frame_count: int
    duration_sec: float
    codec: str
    is_valid: bool = True
    error_message: Optional[str] = None

    @property
    def total_frames(self) -> int:
        """Alias for frame_count."""
        return self.frame_count

    @property
    def resolution_str(self) -> str:
        """Formatted resolution string (e.g., '1920x1080')."""
        return f"{self.width}x{self.height}"

    @property
    def duration_formatted(self) -> str:
        """Formatted duration string (e.g., '01:23')."""
        return format_timestamp(self.duration_sec)


def probe_video_metadata(file_path: Union[str, Path]) -> VideoMetadata:
    """Probe video file metadata using OpenCV VideoCapture.

    Args:
        file_path: Path to local video file.

    Returns:
        VideoMetadata containing probed width, height, fps, frame_count, duration, and codec.
    """
    path_obj = Path(file_path)
    if not path_obj.is_file():
        return VideoMetadata(
            file_path=str(file_path),
            width=0,
            height=0,
            fps=0.0,
            frame_count=0,
            duration_sec=0.0,
            codec="",
            is_valid=False,
            error_message=f"File does not exist: {file_path}",
        )

    cap = cv2.VideoCapture(str(path_obj))
    try:
        if not cap.isOpened():
            return VideoMetadata(
                file_path=str(file_path),
                width=0,
                height=0,
                fps=0.0,
                frame_count=0,
                duration_sec=0.0,
                codec="",
                is_valid=False,
                error_message=f"Could not open video file with OpenCV: {file_path}",
            )

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        raw_fps = cap.get(cv2.CAP_PROP_FPS)
        fps = (
            float(raw_fps)
            if (raw_fps is not None and raw_fps > 0 and not math.isnan(raw_fps))
            else 30.0
        )
        raw_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        frame_count = int(raw_count) if raw_count and raw_count > 0 else 0

        fourcc_int = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec_chars = [chr((fourcc_int >> (8 * i)) & 0xFF) for i in range(4)]
        codec = "".join(codec_chars).strip()

        duration_sec = (frame_count / fps) if (fps > 0 and frame_count > 0) else 0.0

        if width <= 0 or height <= 0:
            return VideoMetadata(
                file_path=str(file_path),
                width=width,
                height=height,
                fps=fps,
                frame_count=frame_count,
                duration_sec=duration_sec,
                codec=codec,
                is_valid=False,
                error_message="Video file has invalid or zero dimensions.",
            )

        return VideoMetadata(
            file_path=str(file_path),
            width=width,
            height=height,
            fps=fps,
            frame_count=frame_count,
            duration_sec=duration_sec,
            codec=codec,
            is_valid=True,
            error_message=None,
        )
    finally:
        cap.release()


def format_timestamp(seconds: float, force_hours: bool = False) -> str:
    """Format seconds into a timestamp string 'MM:SS' or 'HH:MM:SS'.

    Args:
        seconds: Elapsed or duration time in seconds.
        force_hours: If True, always format as 'HH:MM:SS'.

    Returns:
        Formatted timestamp string (e.g., '01:23' or '01:23:45').
    """
    if seconds < 0:
        prefix = "-"
        seconds = abs(seconds)
    else:
        prefix = ""

    total_seconds = int(round(seconds))
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    secs = total_seconds % 60

    if hours > 0 or force_hours:
        return f"{prefix}{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{prefix}{minutes:02d}:{secs:02d}"


def generate_sample_video(
    output_path: Union[str, Path],
    width: int = 1280,
    height: int = 720,
    fps: int = 30,
    duration_sec: int = 8,
) -> str:
    """Generate an animated test pattern MP4 video for instant testing.

    Includes animated gradient colors, bouncing orb, frame counter, and timestamp.

    Args:
        output_path: Destination video file path.
        width: Video width in pixels (default: 1280).
        height: Video height in pixels (default: 720).
        fps: Frames per second (default: 30).
        duration_sec: Total duration in seconds (default: 8).

    Returns:
        Absolute string path of the generated video file.
    """
    out_path = Path(output_path).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, float(fps), (width, height))
    if not writer.isOpened():
        # Fallback to avc1 or MJPG if mp4v is unavailable
        fourcc = cv2.VideoWriter_fourcc(*"MJPG")
        out_path = out_path.with_suffix(".avi")
        writer = cv2.VideoWriter(str(out_path), fourcc, float(fps), (width, height))

    total_frames = int(fps * duration_sec)
    ball_radius = max(15, min(width, height) // 16)
    
    try:
        for f in range(total_frames):
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            t = f / float(fps)

            # Animated gradient background
            hue_offset = int((t * 30.0) % 180)
            y_indices = np.linspace(0, 180, height, endpoint=False, dtype=np.uint8)
            hsv = np.zeros((height, width, 3), dtype=np.uint8)
            hsv[:, :, 0] = (y_indices[:, None] + hue_offset) % 180
            hsv[:, :, 1] = 160
            hsv[:, :, 2] = 45
            bg_bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
            frame[:] = bg_bgr

            # Grid pattern overlay
            for gx in range(0, width, 80):
                cv2.line(frame, (gx, 0), (gx, height), (60, 60, 70), 1)
            for gy in range(0, height, 80):
                cv2.line(frame, (0, gy), (width, gy), (60, 60, 70), 1)

            # Bouncing ball physics
            period_x = 3.5
            period_y = 2.1
            norm_x = (math.sin(2.0 * math.pi * t / period_x) + 1.0) / 2.0
            norm_y = (math.cos(2.0 * math.pi * t / period_y) + 1.0) / 2.0
            bx = int(ball_radius + norm_x * (width - 2 * ball_radius))
            by = int(ball_radius + norm_y * (height - 2 * ball_radius))

            # Ball glow & body
            cv2.circle(frame, (bx, by), ball_radius + 6, (40, 180, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (bx, by), ball_radius, (255, 255, 255), -1, cv2.LINE_AA)
            cv2.circle(frame, (bx - ball_radius // 3, by - ball_radius // 3), ball_radius // 4, (200, 240, 255), -1, cv2.LINE_AA)

            # Header card
            cv2.rectangle(frame, (width // 2 - 260, 20), (width // 2 + 260, 85), (20, 24, 32), -1)
            cv2.rectangle(frame, (width // 2 - 260, 20), (width // 2 + 260, 85), (0, 200, 255), 2)
            cv2.putText(
                frame,
                "VIRTUAL WEBCAM TEST PATTERN",
                (width // 2 - 240, 60),
                cv2.FONT_HERSHEY_DUPLEX,
                0.9,
                (255, 255, 255),
                2,
                cv2.LINE_AA,
            )

            # Status footer
            cur_time_str = format_timestamp(t)
            tot_time_str = format_timestamp(duration_sec)
            stats_str = f"Frame: {f+1:04d}/{total_frames}  |  Time: {cur_time_str}/{tot_time_str}  |  {width}x{height} @ {fps}fps"
            cv2.rectangle(frame, (30, height - 60), (width - 30, height - 20), (15, 17, 22), -1)
            cv2.putText(
                frame,
                stats_str,
                (45, height - 32),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.65,
                (100, 230, 150),
                2,
                cv2.LINE_AA,
            )

            writer.write(frame)
    finally:
        writer.release()

    return str(out_path)

