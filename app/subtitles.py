"""Subtitle parsing, extraction, and frame rendering engine for MKV/MP4 and external subtitle files."""

from __future__ import annotations

import bisect
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleTrack:
    """Represents an embedded or external subtitle track."""

    stream_index: int
    title: str
    language: str
    codec: str
    is_external: bool = False
    file_path: Optional[str] = None

    def display_name(self) -> str:
        """User-friendly representation for GUI dropdowns."""
        if self.is_external:
            base = os.path.basename(self.file_path or "External Subtitle")
            return f"📂 {base}"
        lang_str = f" ({self.language})" if self.language and self.language != "und" else ""
        title_str = f": {self.title}" if self.title else ""
        return f"Track {self.stream_index}{lang_str}{title_str}"


@dataclass(frozen=True)
class SubtitleCue:
    """A timed subtitle text event."""

    start_sec: float
    end_sec: float
    text: str


def clean_subtitle_text(raw_text: str) -> str:
    """Strip formatting tags (HTML tags, ASS override tags like {\\an8}, {\\b1}) from subtitle text."""
    # Remove HTML style tags: <font...>, <b>, <i>, </u>, etc.
    text = re.sub(r"<[^>]+>", "", raw_text)
    # Remove ASS style override tags: {\an8}, {\pos(x,y)}, {\c&H...&}, etc.
    text = re.sub(r"\{[^}]*\}", "", text)
    # Replace escaped newlines or hard line breaks
    text = text.replace(r"\N", "\n").replace(r"\n", "\n")
    # Clean multiple spaces and trim
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    return "\n".join(lines)


def parse_srt_string(srt_content: str) -> List[SubtitleCue]:
    """Parse SRT formatted text into a sorted list of SubtitleCue objects."""
    cues: List[SubtitleCue] = []
    pattern = re.compile(
        r"(\d+)\s*\n(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*\n(.*?)(?=\n\n|\n\d+\s*\n|\Z)",
        re.DOTALL,
    )

    for match in pattern.finditer(srt_content):
        try:
            h1, m1, s1, ms1 = map(int, match.group(2, 3, 4, 5))
            h2, m2, s2, ms2 = map(int, match.group(6, 7, 8, 9))
            start_sec = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000.0
            end_sec = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000.0
            raw_text = match.group(10)
            cleaned = clean_subtitle_text(raw_text)
            if cleaned:
                cues.append(SubtitleCue(start_sec=start_sec, end_sec=end_sec, text=cleaned))
        except Exception as e:
            logger.debug(f"Skipping malformed SRT cue: {e}")

    cues.sort(key=lambda c: c.start_sec)
    return cues


class SubtitleManager:
    """Manages subtitle track discovery, extraction from MKV/MP4, and frame overlay rendering."""

    def __init__(self) -> None:
        self._tracks: List[SubtitleTrack] = []
        self._active_track: Optional[SubtitleTrack] = None
        self._cues: List[SubtitleCue] = []
        self._enabled: bool = True

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)

    def get_tracks(self) -> List[SubtitleTrack]:
        return list(self._tracks)

    def get_active_track(self) -> Optional[SubtitleTrack]:
        return self._active_track

    def clear(self) -> None:
        """Clear all loaded tracks and cues."""
        self._tracks.clear()
        self._active_track = None
        self._cues.clear()

    def discover_tracks(self, video_path: str) -> List[SubtitleTrack]:
        """Probe video file using ffprobe to list all embedded subtitle tracks."""
        self.clear()
        if not video_path or not Path(video_path).is_file():
            return []

        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "stream=index,codec_name,codec_type:stream_tags=language,title",
            "-of", "json",
            video_path,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
            if res.returncode != 0:
                logger.warning(f"ffprobe failed for {video_path}: {res.stderr}")
                return []
            data = json.loads(res.stdout)
            streams = data.get("streams", [])
            for s in streams:
                if s.get("codec_type") == "subtitle":
                    idx = int(s.get("index", 0))
                    codec = s.get("codec_name", "unknown")
                    tags = s.get("tags", {}) or {}
                    lang = tags.get("language", "und")
                    title = tags.get("title", "")
                    track = SubtitleTrack(
                        stream_index=idx,
                        title=title,
                        language=lang,
                        codec=codec,
                        is_external=False,
                    )
                    self._tracks.append(track)
            logger.info(f"Discovered {len(self._tracks)} subtitle tracks in {os.path.basename(video_path)}")
        except Exception as e:
            logger.warning(f"Error probing subtitles: {e}")

        # Check for matching sidecar subtitle files (.srt, .ass, .vtt) in same directory
        try:
            base_name = Path(video_path).stem
            parent_dir = Path(video_path).parent
            for ext in (".srt", ".ass", ".vtt", ".ssa"):
                sidecar = parent_dir / f"{base_name}{ext}"
                if sidecar.is_file():
                    ext_track = SubtitleTrack(
                        stream_index=len(self._tracks) + 1,
                        title=f"External {ext.upper()}",
                        language="und",
                        codec=ext.lstrip("."),
                        is_external=True,
                        file_path=str(sidecar),
                    )
                    self._tracks.append(ext_track)
        except Exception as e:
            logger.debug(f"Error checking sidecar subtitles: {e}")

        return list(self._tracks)

    def load_track(self, video_path: str, track: SubtitleTrack) -> bool:
        """Load and parse cues for the specified subtitle track."""
        self._cues.clear()
        self._active_track = track

        if track.is_external and track.file_path:
            return self.load_external_file(track.file_path)

        # Extract embedded track from MKV/MP4 via ffmpeg
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-map", f"0:{track.stream_index}",
            "-f", "srt",
            "-",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=10)
            if res.returncode != 0 and not res.stdout:
                logger.warning(f"ffmpeg failed to extract subtitle track {track.stream_index}: {res.stderr}")
                return False
            self._cues = parse_srt_string(res.stdout)
            logger.info(f"Loaded {len(self._cues)} subtitle cues from track {track.display_name()}")
            return len(self._cues) > 0
        except Exception as e:
            logger.warning(f"Error extracting subtitle track: {e}")
            return False

    def load_external_file(self, file_path: str) -> bool:
        """Parse external subtitle file (.srt, .vtt, etc.)."""
        self._cues.clear()
        path_obj = Path(file_path)
        if not path_obj.is_file():
            return False

        try:
            # If not already in tracks, add it
            if not any(t.file_path == file_path for t in self._tracks):
                track = SubtitleTrack(
                    stream_index=len(self._tracks) + 1,
                    title=path_obj.name,
                    language="und",
                    codec=path_obj.suffix.lstrip("."),
                    is_external=True,
                    file_path=str(path_obj),
                )
                self._tracks.append(track)
                self._active_track = track

            # If it's ASS/SSA or VTT, ffmpeg can convert cleanly to SRT format
            suffix = path_obj.suffix.lower()
            if suffix in (".ass", ".ssa", ".vtt"):
                cmd = ["ffmpeg", "-y", "-i", str(file_path), "-f", "srt", "-"]
                res = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=5)
                if res.returncode == 0 and res.stdout:
                    self._cues = parse_srt_string(res.stdout)
                    return len(self._cues) > 0

            # Default UTF-8 text parsing for .srt
            content = path_obj.read_text(encoding="utf-8", errors="replace")
            self._cues = parse_srt_string(content)
            logger.info(f"Loaded {len(self._cues)} cues from external file {path_obj.name}")
            return len(self._cues) > 0
        except Exception as e:
            logger.warning(f"Error reading external subtitle file: {e}")
            return False

    def get_cues_at(self, timestamp_sec: float) -> List[str]:
        """Return active subtitle text lines for the current playback time."""
        if not self._enabled or not self._cues:
            return []

        active_texts: List[str] = []
        for cue in self._cues:
            if cue.start_sec <= timestamp_sec <= cue.end_sec:
                active_texts.append(cue.text)
            elif cue.start_sec > timestamp_sec:
                break
        return active_texts

    def render(self, frame_rgb: np.ndarray, timestamp_sec: float) -> np.ndarray:
        """Render active subtitles directly onto the RGB video frame buffer."""
        if not self._enabled or not self._cues:
            return frame_rgb

        texts = self.get_cues_at(timestamp_sec)
        if not texts:
            return frame_rgb

        h, w = frame_rgb.shape[:2]
        if h <= 0 or w <= 0:
            return frame_rgb

        # Proportional font scaling based on 720p reference
        base_font_scale = max(0.5, (h / 720.0) * 0.85)
        outline_thickness = max(2, int(round(base_font_scale * 4.0)))
        inner_thickness = max(1, int(round(base_font_scale * 2.0)))
        font = cv2.FONT_HERSHEY_DUPLEX

        # Collect all lines to render
        all_lines: List[str] = []
        for text_block in texts:
            all_lines.extend(text_block.split("\n"))

        if not all_lines:
            return frame_rgb

        # Calculate text metrics
        line_heights: List[int] = []
        line_widths: List[int] = []
        line_baselines: List[int] = []

        for line in all_lines:
            (tw, th), bl = cv2.getTextSize(line, font, base_font_scale, outline_thickness)
            line_widths.append(tw)
            line_heights.append(th)
            line_baselines.append(bl)

        total_text_height = sum(line_heights) + int(len(all_lines) * 10 * base_font_scale)
        # Position at bottom with 7% margin
        bottom_margin = int(h * 0.07)
        y_cursor = h - bottom_margin - total_text_height

        for idx, line in enumerate(all_lines):
            tw = line_widths[idx]
            th = line_heights[idx]
            x = max(10, (w - tw) // 2)
            y = y_cursor + th

            # 1. Draw heavy black outline for high contrast
            cv2.putText(
                frame_rgb,
                line,
                (x, y),
                font,
                base_font_scale,
                (0, 0, 0),
                thickness=outline_thickness,
                lineType=cv2.LINE_AA,
            )

            # 2. Draw crisp white text
            cv2.putText(
                frame_rgb,
                line,
                (x, y),
                font,
                base_font_scale,
                (255, 255, 255),
                thickness=inner_thickness,
                lineType=cv2.LINE_AA,
            )

            y_cursor += th + int(10 * base_font_scale)

        return frame_rgb
