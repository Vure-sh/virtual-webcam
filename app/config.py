"""Configuration models, resolution/FPS presets, and JSON serialization."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union


class ResolutionPreset(str, Enum):
    """Output resolution presets."""

    ORIGINAL = "original"
    P480 = "480p"
    P720 = "720p"
    P1080 = "1080p"
    P1440 = "1440p"

    @classmethod
    def from_string(cls, value: str) -> ResolutionPreset:
        """Parse string to ResolutionPreset (case-insensitive, handles aliases)."""
        if isinstance(value, cls):
            return value
        cleaned = str(value).strip().lower()
        alias_map = {
            "original": cls.ORIGINAL,
            "source": cls.ORIGINAL,
            "480p": cls.P480,
            "480": cls.P480,
            "sd": cls.P480,
            "720p": cls.P720,
            "720": cls.P720,
            "hd": cls.P720,
            "1080p": cls.P1080,
            "1080": cls.P1080,
            "fhd": cls.P1080,
            "fullhd": cls.P1080,
            "full_hd": cls.P1080,
            "1440p": cls.P1440,
            "1440": cls.P1440,
            "2k": cls.P1440,
            "qhd": cls.P1440,
        }
        if cleaned in alias_map:
            return alias_map[cleaned]
        for member in cls:
            if member.value.lower() == cleaned or member.name.lower() == cleaned:
                return member
        raise ValueError(
            f"Invalid resolution preset: '{value}'. Valid options: {[m.value for m in cls]}"
        )

    def to_dimensions(
        self, source_dim: Optional[Tuple[int, int]] = None
    ) -> Tuple[int, int]:
        """Convert preset to (width, height) pixel dimensions.

        Args:
            source_dim: Optional (source_width, source_height) from original video.

        Returns:
            Tuple of (width, height) in pixels.
        """
        if self == ResolutionPreset.ORIGINAL:
            if source_dim is not None and len(source_dim) == 2:
                w, h = int(source_dim[0]), int(source_dim[1])
                if w > 0 and h > 0:
                    return (w, h)
            return (1280, 720)
        elif self == ResolutionPreset.P480:
            return (854, 480)
        elif self == ResolutionPreset.P720:
            return (1280, 720)
        elif self == ResolutionPreset.P1080:
            return (1920, 1080)
        elif self == ResolutionPreset.P1440:
            return (2560, 1440)
        else:
            return (1280, 720)


class FPSPreset(str, Enum):
    """Target output frame rate presets."""

    SOURCE = "source"
    FPS_15 = "15"
    FPS_24 = "24"
    FPS_30 = "30"
    FPS_60 = "60"

    @classmethod
    def from_string(cls, value: Union[str, int, float]) -> FPSPreset:
        """Parse string or number to FPSPreset (case-insensitive, handles aliases)."""
        if isinstance(value, cls):
            return value
        cleaned = str(value).strip().lower().replace("fps", "").strip()
        alias_map = {
            "source": cls.SOURCE,
            "original": cls.SOURCE,
            "auto": cls.SOURCE,
            "15": cls.FPS_15,
            "15.0": cls.FPS_15,
            "24": cls.FPS_24,
            "24.0": cls.FPS_24,
            "23.976": cls.FPS_24,
            "30": cls.FPS_30,
            "30.0": cls.FPS_30,
            "29.97": cls.FPS_30,
            "60": cls.FPS_60,
            "60.0": cls.FPS_60,
            "59.94": cls.FPS_60,
        }
        if cleaned in alias_map:
            return alias_map[cleaned]
        for member in cls:
            if member.value.lower() == cleaned or member.name.lower() == cleaned:
                return member
        raise ValueError(
            f"Invalid FPS preset: '{value}'. Valid options: {[m.value for m in cls]}"
        )

    def to_fps(self, source_fps: Optional[float] = None) -> float:
        """Convert preset to numeric FPS value.

        Args:
            source_fps: Optional source video FPS.

        Returns:
            Target frame rate as float.
        """
        if self == FPSPreset.SOURCE:
            if source_fps is not None and float(source_fps) > 0:
                return float(source_fps)
            return 30.0
        elif self == FPSPreset.FPS_15:
            return 15.0
        elif self == FPSPreset.FPS_24:
            return 24.0
        elif self == FPSPreset.FPS_30:
            return 30.0
        elif self == FPSPreset.FPS_60:
            return 60.0
        else:
            return 30.0


@dataclass
class AppConfig:
    """Application configuration settings."""

    video_path: Optional[str] = None
    resolution_preset: ResolutionPreset = ResolutionPreset.P720
    fps_preset: FPSPreset = FPSPreset.SOURCE
    custom_width: Optional[int] = None
    custom_height: Optional[int] = None
    custom_fps: Optional[float] = None
    vcam_device: Optional[str] = None
    use_mock_camera: bool = False
    loop_playback: bool = True
    live_preview_enabled: bool = True
    flip_horizontal: bool = False
    audio_enabled: bool = True
    volume: int = 100

    def __post_init__(self) -> None:
        """Coerce and validate fields upon initialization."""
        if isinstance(self.resolution_preset, str) and not isinstance(
            self.resolution_preset, ResolutionPreset
        ):
            self.resolution_preset = ResolutionPreset.from_string(self.resolution_preset)
        if isinstance(self.fps_preset, (str, int, float)) and not isinstance(
            self.fps_preset, FPSPreset
        ):
            self.fps_preset = FPSPreset.from_string(self.fps_preset)
        self.validate()


    def validate(self) -> None:
        """Validate configuration values, raising ValueError on invalid entries."""
        if not isinstance(self.resolution_preset, ResolutionPreset):
            raise ValueError(
                f"resolution_preset must be a ResolutionPreset enum, got {type(self.resolution_preset)}"
            )
        if not isinstance(self.fps_preset, FPSPreset):
            raise ValueError(
                f"fps_preset must be a FPSPreset enum, got {type(self.fps_preset)}"
            )
        if self.custom_width is not None:
            if not isinstance(self.custom_width, int) or self.custom_width <= 0:
                raise ValueError(
                    f"custom_width must be a positive integer, got {self.custom_width}"
                )
            if self.custom_width > 7680:
                raise ValueError(f"custom_width exceeds 8K limit (7680): {self.custom_width}")
        if self.custom_height is not None:
            if not isinstance(self.custom_height, int) or self.custom_height <= 0:
                raise ValueError(
                    f"custom_height must be a positive integer, got {self.custom_height}"
                )
            if self.custom_height > 4320:
                raise ValueError(f"custom_height exceeds 8K limit (4320): {self.custom_height}")
        if self.custom_fps is not None:
            if not isinstance(self.custom_fps, (int, float)) or self.custom_fps <= 0:
                raise ValueError(
                    f"custom_fps must be a positive number, got {self.custom_fps}"
                )
            if self.custom_fps > 240.0:
                raise ValueError(f"custom_fps exceeds 240 FPS limit: {self.custom_fps}")
        if not isinstance(self.use_mock_camera, bool):
            raise ValueError("use_mock_camera must be a boolean")
        if not isinstance(self.loop_playback, bool):
            raise ValueError("loop_playback must be a boolean")
        if not isinstance(self.live_preview_enabled, bool):
            raise ValueError("live_preview_enabled must be a boolean")

    def get_output_dimensions(
        self, source_dim: Optional[Tuple[int, int]] = None
    ) -> Tuple[int, int]:
        """Compute effective output dimensions (custom overrides preset)."""
        if self.custom_width is not None and self.custom_height is not None:
            return (self.custom_width, self.custom_height)
        return self.resolution_preset.to_dimensions(source_dim)

    def get_output_fps(self, source_fps: Optional[float] = None) -> float:
        """Compute effective output FPS (custom overrides preset)."""
        if self.custom_fps is not None and self.custom_fps > 0:
            return float(self.custom_fps)
        return self.fps_preset.to_fps(source_fps)

    def to_dict(self) -> Dict[str, Any]:
        """Serialize configuration to a dictionary with string enum values."""
        return {
            "video_path": self.video_path,
            "resolution_preset": self.resolution_preset.value,
            "fps_preset": self.fps_preset.value,
            "custom_width": self.custom_width,
            "custom_height": self.custom_height,
            "custom_fps": self.custom_fps,
            "vcam_device": self.vcam_device,
            "use_mock_camera": self.use_mock_camera,
            "loop_playback": self.loop_playback,
            "live_preview_enabled": self.live_preview_enabled,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> AppConfig:
        """Construct AppConfig from a dictionary with robust key coercion."""
        if not isinstance(data, dict):
            raise ValueError(f"Expected dict for AppConfig.from_dict, got {type(data)}")

        res_raw = data.get("resolution_preset", ResolutionPreset.P720.value)
        resolution_preset = (
            ResolutionPreset.from_string(res_raw)
            if isinstance(res_raw, (str, ResolutionPreset))
            else ResolutionPreset.P720
        )

        fps_raw = data.get("fps_preset", FPSPreset.SOURCE.value)
        fps_preset = (
            FPSPreset.from_string(fps_raw)
            if isinstance(fps_raw, (str, int, float, FPSPreset))
            else FPSPreset.SOURCE
        )

        return cls(
            video_path=data.get("video_path"),
            resolution_preset=resolution_preset,
            fps_preset=fps_preset,
            custom_width=data.get("custom_width"),
            custom_height=data.get("custom_height"),
            custom_fps=(
                float(data["custom_fps"])
                if data.get("custom_fps") is not None
                else None
            ),
            vcam_device=data.get("vcam_device"),
            use_mock_camera=bool(data.get("use_mock_camera", False)),
            loop_playback=bool(data.get("loop_playback", True)),
            live_preview_enabled=bool(data.get("live_preview_enabled", True)),
        )

    def to_json(self, indent: Optional[int] = 2) -> str:
        """Serialize configuration to a formatted JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> AppConfig:
        """Deserialize configuration from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)

    def save_to_file(self, path: Union[str, Path]) -> None:
        """Save configuration to a JSON file."""
        target_path = Path(path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(self.to_json(indent=2))

    @classmethod
    def load_from_file(cls, path: Union[str, Path]) -> AppConfig:
        """Load configuration from a JSON file."""
        source_path = Path(path)
        if not source_path.is_file():
            raise FileNotFoundError(f"Configuration file not found: {source_path}")
        with open(source_path, "r", encoding="utf-8") as f:
            return cls.from_json(f.read())
