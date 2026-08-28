"""Virtual camera abstraction interface, Linux v4l2loopback pyvirtualcam backend, and mock backend."""

from __future__ import annotations

import glob
import logging
import os
import threading
import time
from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom Exception Hierarchy
# ---------------------------------------------------------------------------


class VirtualCameraError(Exception):
    """Base exception for virtual camera operations."""

    pass


class DeviceNotFoundError(VirtualCameraError):
    """Raised when the specified or default virtual camera device is not found."""

    pass


class DeviceBusyError(VirtualCameraError):
    """Raised when the virtual camera device is already open or held by another process."""

    pass


class DevicePermissionError(VirtualCameraError):
    """Raised when permissions are insufficient to open the virtual camera device."""

    pass


# ---------------------------------------------------------------------------
# Abstract Base Class Interface
# ---------------------------------------------------------------------------


class IVirtualCamera(ABC):
    """Abstract interface defining the lifecycle and frame delivery for virtual cameras."""

    def __init__(self) -> None:
        self._width: int = 0
        self._height: int = 0
        self._fps: float = 30.0
        self._device: Optional[str] = None
        self._is_active: bool = False

    @property
    def width(self) -> int:
        """Configured camera frame width in pixels."""
        return self._width

    @property
    def height(self) -> int:
        """Configured camera frame height in pixels."""
        return self._height

    @property
    def fps(self) -> float:
        """Configured camera frame rate in frames per second."""
        return self._fps

    @property
    def device(self) -> Optional[str]:
        """Configured or allocated device path (e.g. '/dev/video2')."""
        return self._device

    @abstractmethod
    def open(
        self,
        width: int,
        height: int,
        fps: float,
        device: Optional[str] = None,
    ) -> bool:
        """Open and initialize the virtual camera device.

        Args:
            width: Output frame width in pixels (> 0).
            height: Output frame height in pixels (> 0).
            fps: Frame rate (> 0).
            device: Optional specific device node path (e.g. '/dev/video2').

        Returns:
            True if camera was successfully opened.

        Raises:
            DeviceNotFoundError: If the device does not exist.
            DeviceBusyError: If the device is in use by another application.
            DevicePermissionError: If insufficient permissions to open the device.
            VirtualCameraError: On general initialization failure.
            ValueError: On invalid dimensions or FPS.
        """
        pass

    @abstractmethod
    def send(self, frame_rgb: np.ndarray) -> None:
        """Send a single RGB frame to the virtual camera.

        Args:
            frame_rgb: Numpy uint8 RGB array of shape (height, width, 3).

        Raises:
            VirtualCameraError: If the camera is not active or transmission fails.
            ValueError: If frame dimensions or color format do not match camera specs.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the camera device and release all system resources safely."""
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Check if the virtual camera is currently opened and active."""
        pass

    @abstractmethod
    def get_device_name(self) -> str:
        """Get the human-readable or path identifier for the virtual camera device."""
        pass

    def __enter__(self) -> IVirtualCamera:
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit, ensuring safe release of camera resources."""
        self.close()


# ---------------------------------------------------------------------------
# PyVirtualCam Backend (Production / Linux v4l2loopback)
# ---------------------------------------------------------------------------


class PyVirtualCamBackend(IVirtualCamera):
    """Production virtual camera backend wrapping pyvirtualcam (v4l2loopback on Linux)."""

    def __init__(self) -> None:
        super().__init__()
        self._cam = None

    @classmethod
    def discover_devices(cls) -> List[str]:
        """Discover available video devices on the system (/dev/video*)."""
        devices = glob.glob("/dev/video*")

        def sort_key(path: str) -> int:
            base = os.path.basename(path).replace("video", "")
            return int(base) if base.isdigit() else 9999

        return sorted(devices, key=sort_key)

    @classmethod
    def list_devices(cls) -> List[str]:
        """Alias for discover_devices."""
        return cls.discover_devices()

    def _translate_error(
        self, err: Exception, device: Optional[str] = None
    ) -> VirtualCameraError:
        """Translate lower-level OS / pyvirtualcam exceptions to domain errors."""
        msg = str(err).lower()
        err_type = type(err).__name__

        if (
            isinstance(err, FileNotFoundError)
            or "no v4l2 loopback device found" in msg
            or "no such file" in msg
            or "cannot find" in msg
            or "not found" in msg
            or "does not exist" in msg
        ):
            dev_str = f" '{device}'" if device else ""
            return DeviceNotFoundError(
                f"Virtual camera device{dev_str} not found. Is v4l2loopback installed and loaded (modprobe v4l2loopback)? Details: {err}"
            )
        elif (
            isinstance(err, PermissionError)
            or "permission denied" in msg
            or "permission" in msg
            or "eacces" in msg
            or "eperm" in msg
        ):
            dev_str = f" '{device}'" if device else ""
            return DevicePermissionError(
                f"Permission denied accessing virtual camera device{dev_str}. Ensure user is in 'video' group (sudo usermod -aG video $USER). Details: {err}"
            )
        elif "busy" in msg or "ebusy" in msg or "device or resource busy" in msg:
            dev_str = f" '{device}'" if device else ""
            return DeviceBusyError(
                f"Virtual camera device{dev_str} is busy or held by another application. Details: {err}"
            )
        else:
            return VirtualCameraError(
                f"Virtual camera error ({err_type}): {err}"
            )

    def open(
        self,
        width: int,
        height: int,
        fps: float,
        device: Optional[str] = None,
    ) -> bool:
        """Open the pyvirtualcam device."""
        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError(
                f"Invalid camera parameters: width={width}, height={height}, fps={fps}. All must be positive."
            )

        if self.is_active():
            self.close()

        try:
            import pyvirtualcam
            from pyvirtualcam import PixelFormat

            cam_kwargs = {
                "width": int(width),
                "height": int(height),
                "fps": float(fps),
                "fmt": PixelFormat.RGB,
            }
            if device:
                cam_kwargs["device"] = device

            self._cam = pyvirtualcam.Camera(**cam_kwargs)
            self._width = int(width)
            self._height = int(height)
            self._fps = float(fps)
            self._device = device or getattr(self._cam, "device", "v4l2loopback")
            self._is_active = True
            logger.info(
                f"PyVirtualCam opened successfully: {self._device} ({self._width}x{self._height} @ {self._fps} FPS)"
            )
            return True

        except Exception as e:
            self._is_active = False
            self._cam = None
            translated = self._translate_error(e, device=device)
            logger.error(f"Failed to open PyVirtualCam: {translated}")
            raise translated from e

    def send(self, frame_rgb: np.ndarray) -> None:
        """Send an RGB frame to the pyvirtualcam device."""
        if not self.is_active() or self._cam is None:
            raise VirtualCameraError("Virtual camera is not active or has been closed.")

        if not isinstance(frame_rgb, np.ndarray):
            raise ValueError(f"frame_rgb must be a numpy.ndarray, got {type(frame_rgb)}")

        if frame_rgb.dtype != np.uint8:
            raise ValueError(f"frame_rgb must have uint8 dtype, got {frame_rgb.dtype}")

        expected_shape = (self._height, self._width, 3)
        if frame_rgb.shape != expected_shape:
            raise ValueError(
                f"Frame shape {frame_rgb.shape} does not match camera dimensions {expected_shape}"
            )

        try:
            self._cam.send(frame_rgb)
        except Exception as e:
            translated = self._translate_error(e, device=self._device)
            logger.error(f"Error sending frame to PyVirtualCam: {translated}")
            raise translated from e

    def close(self) -> None:
        """Close the pyvirtualcam device safely."""
        if self._cam is not None:
            try:
                self._cam.close()
            except Exception as e:
                logger.warning(f"Error during pyvirtualcam close: {e}")
            finally:
                self._cam = None
                self._is_active = False
                logger.info("PyVirtualCam closed.")
        else:
            self._is_active = False

    def is_active(self) -> bool:
        """Check if camera is currently open."""
        return self._is_active and (self._cam is not None)

    def get_device_name(self) -> str:
        """Return the device identifier."""
        return self._device or "pyvirtualcam"


# ---------------------------------------------------------------------------
# Mock Virtual Camera Backend (In-Memory / Test Sink)
# ---------------------------------------------------------------------------


class MockVirtualCamBackend(IVirtualCamera):
    """In-memory mock virtual camera backend for testing and headless environments.

    Tracks frame counts, last frame data, dimensions, timestamps, and supports
    fault injection for error handling testing.
    """

    def __init__(
        self,
        simulate_busy: bool = False,
        simulate_permission_denied: bool = False,
        simulate_permission_error: bool = False,
        simulate_not_found: bool = False,
        simulate_send_failure: bool = False,
    ) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._frame_count: int = 0
        self._last_frame: Optional[np.ndarray] = None
        self._last_frame_shape: Optional[Tuple[int, ...]] = None
        self._last_frame_dtype: Optional[np.dtype] = None
        self._timestamps: List[float] = []

        # Fault injection simulation flags
        self.simulate_busy: bool = bool(simulate_busy)
        self.simulate_permission_denied: bool = bool(
            simulate_permission_denied or simulate_permission_error
        )
        self.simulate_not_found: bool = bool(simulate_not_found)
        self.simulate_send_failure: bool = bool(simulate_send_failure)

    @property
    def simulate_permission_error(self) -> bool:
        """Alias for simulate_permission_denied."""
        return self.simulate_permission_denied

    @simulate_permission_error.setter
    def simulate_permission_error(self, val: bool) -> None:
        self.simulate_permission_denied = bool(val)

    @property
    def _simulate_busy(self) -> bool:
        """Getter for simulate_busy with leading underscore."""
        return self.simulate_busy

    @_simulate_busy.setter
    def _simulate_busy(self, val: bool) -> None:
        self.simulate_busy = bool(val)

    @property
    def _simulate_permission_error(self) -> bool:
        """Getter for simulate_permission_error with leading underscore."""
        return self.simulate_permission_denied

    @_simulate_permission_error.setter
    def _simulate_permission_error(self, val: bool) -> None:
        self.simulate_permission_denied = bool(val)

    @property
    def _simulate_permission_denied(self) -> bool:
        """Getter for simulate_permission_denied with leading underscore."""
        return self.simulate_permission_denied

    @_simulate_permission_denied.setter
    def _simulate_permission_denied(self, val: bool) -> None:
        self.simulate_permission_denied = bool(val)

    @property
    def _simulate_device_missing(self) -> bool:
        """Getter for simulate_not_found (device missing alias)."""
        return self.simulate_not_found

    @_simulate_device_missing.setter
    def _simulate_device_missing(self, val: bool) -> None:
        self.simulate_not_found = bool(val)

    @property
    def _simulate_not_found(self) -> bool:
        """Getter for simulate_not_found with leading underscore."""
        return self.simulate_not_found

    @_simulate_not_found.setter
    def _simulate_not_found(self, val: bool) -> None:
        self.simulate_not_found = bool(val)

    @property
    def frame_count(self) -> int:
        """Total number of frames received."""
        with self._lock:
            return self._frame_count

    @property
    def frames_sent_count(self) -> int:
        """Alias for frame_count."""
        with self._lock:
            return self._frame_count

    @property
    def last_frame(self) -> Optional[np.ndarray]:
        """Copy of the most recent frame sent to the camera."""
        with self._lock:
            return self._last_frame.copy() if self._last_frame is not None else None

    @property
    def last_frame_data(self) -> Optional[np.ndarray]:
        """Direct reference or copy of the most recent frame sent to the camera."""
        with self._lock:
            return self._last_frame

    @property
    def last_frame_shape(self) -> Optional[Tuple[int, ...]]:
        """Shape of the most recent frame."""
        with self._lock:
            return self._last_frame_shape

    @property
    def last_frame_dtype(self) -> Optional[np.dtype]:
        """Dtype of the most recent frame."""
        with self._lock:
            return self._last_frame_dtype

    @property
    def timestamps(self) -> List[float]:
        """List of timestamps when frames were sent."""
        with self._lock:
            return list(self._timestamps)

    @property
    def frame_timestamps(self) -> List[float]:
        """Alias for timestamps."""
        return self.timestamps

    def open(
        self,
        width: int,
        height: int,
        fps: float,
        device: Optional[str] = None,
    ) -> bool:
        """Open the mock camera, simulating errors if configured."""
        if self.simulate_not_found:
            raise DeviceNotFoundError(
                f"Simulated error: Mock device '{device or 'MockCamera'}' not found."
            )
        if self.simulate_busy:
            raise DeviceBusyError(
                f"Simulated error: Mock device '{device or 'MockCamera'}' is busy."
            )
        if self.simulate_permission_denied:
            raise DevicePermissionError(
                f"Simulated error: Permission denied for mock device '{device or 'MockCamera'}'."
            )

        if width <= 0 or height <= 0 or fps <= 0:
            raise ValueError(
                f"Invalid camera parameters: width={width}, height={height}, fps={fps}. All must be positive."
            )

        with self._lock:
            if self._is_active:
                self._is_active = False

            self._width = int(width)
            self._height = int(height)
            self._fps = float(fps)
            self._device = device or "MockCamera"
            self._is_active = True
            self._frame_count = 0
            self._last_frame = None
            self._last_frame_shape = None
            self._last_frame_dtype = None
            self._timestamps.clear()
            return True

    def send(self, frame_rgb: np.ndarray) -> None:
        """Send a frame into the in-memory sink."""
        with self._lock:
            if not self._is_active:
                raise VirtualCameraError("Mock camera is not active or has been closed.")

            if self.simulate_send_failure:
                raise VirtualCameraError("Simulated frame transmission failure.")

            if not isinstance(frame_rgb, np.ndarray):
                raise ValueError(f"frame_rgb must be a numpy.ndarray, got {type(frame_rgb)}")

            if frame_rgb.dtype != np.uint8:
                raise ValueError(f"frame_rgb must have uint8 dtype, got {frame_rgb.dtype}")

            expected_shape = (self._height, self._width, 3)
            if frame_rgb.shape != expected_shape:
                raise ValueError(
                    f"Frame shape {frame_rgb.shape} does not match mock camera dimensions {expected_shape}"
                )

            self._frame_count += 1
            self._last_frame = frame_rgb.copy()
            self._last_frame_shape = frame_rgb.shape
            self._last_frame_dtype = frame_rgb.dtype
            self._timestamps.append(time.perf_counter())

    def close(self) -> None:
        """Close the mock camera."""
        with self._lock:
            self._is_active = False

    def is_active(self) -> bool:
        """Check if mock camera is active."""
        with self._lock:
            return self._is_active

    def get_device_name(self) -> str:
        """Return mock device name."""
        return self._device or "MockCamera"

    def reset(self) -> None:
        """Reset all recorded metrics and state."""
        with self._lock:
            self._frame_count = 0
            self._last_frame = None
            self._last_frame_shape = None
            self._last_frame_dtype = None
            self._timestamps.clear()
            self.simulate_busy = False
            self.simulate_permission_denied = False
            self.simulate_not_found = False
            self.simulate_send_failure = False


# ---------------------------------------------------------------------------
# Factory Function
# ---------------------------------------------------------------------------


def get_virtual_camera_backend(
    force_mock: bool = False, device: Optional[str] = None
) -> IVirtualCamera:
    """Instantiate and return the appropriate virtual camera backend.

    Args:
        force_mock: If True, returns a MockVirtualCamBackend.
        device: Optional device name or path.

    Returns:
        An instance implementing IVirtualCamera.
    """
    if force_mock:
        return MockVirtualCamBackend()
    return PyVirtualCamBackend()
