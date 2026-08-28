"""Virtual Webcam application package."""

__version__ = "0.1.0"

from app.config import AppConfig, FPSPreset, ResolutionPreset
from app.utils import (
    LetterboxGeometry,
    VideoMetadata,
    calculate_letterbox_geometry,
    format_timestamp,
    probe_video_metadata,
    transform_frame,
)
from app.virtual_camera import (
    DeviceBusyError,
    DeviceNotFoundError,
    DevicePermissionError,
    IVirtualCamera,
    MockVirtualCamBackend,
    PyVirtualCamBackend,
    VirtualCameraError,
    get_virtual_camera_backend,
)

__all__ = [
    "AppConfig",
    "ResolutionPreset",
    "FPSPreset",
    "LetterboxGeometry",
    "VideoMetadata",
    "calculate_letterbox_geometry",
    "transform_frame",
    "probe_video_metadata",
    "format_timestamp",
    "VirtualCameraError",
    "DeviceNotFoundError",
    "DeviceBusyError",
    "DevicePermissionError",
    "IVirtualCamera",
    "PyVirtualCamBackend",
    "MockVirtualCamBackend",
    "get_virtual_camera_backend",
]
