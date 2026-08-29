"""Video Processing & Pacing Engine.

Features:
- PlaybackState enum and PlayerSignals (Qt signals).
- VideoPlayerWorker executing in a dedicated QThread with monotonic clock pacing,
  hybrid sleep (>2ms OS sleep, sub-ms spin loop), dynamic drift compensation (>50ms lag),
  aspect-ratio preserving frame transformation, seamless looping, and virtual camera streaming.
- VideoPlayerController high-level thread-safe facade for application and UI interaction.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Union

import cv2
import numpy as np
from PySide6.QtCore import QCoreApplication, QObject, QThread, QUrl, Qt, Signal, Slot
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

from app.config import AppConfig, FPSPreset, ResolutionPreset
from app.utils import VideoMetadata, probe_video_metadata, transform_frame

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

logger = logging.getLogger(__name__)


class PlaybackState(str, Enum):
    """Playback state machine states."""

    UNLOADED = "unloaded"
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    SEEKING = "seeking"
    COMPLETED = "completed"
    ERROR = "error"


class PlayerSignals(QObject):
    """Qt Signals emitted during video playback and virtual camera streaming."""

    frame_ready = Signal(object, int)  # (frame_rgb: np.ndarray, frame_idx: int)
    position_changed = Signal(
        int, int, float, float
    )  # (current_frame: int, total_frames: int, current_sec: float, total_sec: float)
    state_changed = Signal(object)  # (state: PlaybackState)
    vcam_status_changed = Signal(
        bool, str, str
    )  # (is_active: bool, device_name: str, error_message: str)
    error_occurred = Signal(str, str)  # (error_type: str, error_message: str)
    media_loaded = Signal(object)  # (metadata: VideoMetadata)


class VideoPlayerWorker(QObject):
    """Background worker object handling video decoding, transformation, and pacing.

    Executes in a dedicated QThread with zero UI thread blocking.
    """

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        vcam_backend: Optional[IVirtualCamera] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or AppConfig()
        self.signals = PlayerSignals()

        # Thread synchronization
        self._lock = threading.RLock()
        self._is_running: bool = True
        self._state: PlaybackState = PlaybackState.UNLOADED

        # Media & decoding state
        self._video_path: Optional[str] = None
        self._cap: Optional[cv2.VideoCapture] = None
        self._metadata: Optional[VideoMetadata] = None
        self._current_frame_idx: int = 0
        self._total_frames: int = 0
        self._source_fps: float = 30.0
        self._source_width: int = 0
        self._source_height: int = 0

        # Runtime overrides
        self._target_width: Optional[int] = self._config.custom_width
        self._target_height: Optional[int] = self._config.custom_height
        self._target_fps: Optional[float] = self._config.custom_fps
        self._loop: bool = self._config.loop_playback
        self._use_mock_camera: bool = self._config.use_mock_camera
        self._flip_horizontal: bool = self._config.flip_horizontal

        # Virtual camera & frame canvas buffer
        self._custom_vcam_backend: Optional[IVirtualCamera] = vcam_backend
        self._vcam: Optional[IVirtualCamera] = None
        self._canvas_buffer: Optional[np.ndarray] = None


    # -----------------------------------------------------------------------
    # State Accessors
    # -----------------------------------------------------------------------

    def get_state(self) -> PlaybackState:
        """Return the current playback state."""
        with self._lock:
            return self._state

    def is_playing(self) -> bool:
        """Check if currently in PLAYING state."""
        with self._lock:
            return self._state == PlaybackState.PLAYING

    def get_metadata(self) -> Optional[VideoMetadata]:
        """Return metadata of the loaded video."""
        with self._lock:
            return self._metadata

    def get_current_frame_idx(self) -> int:
        """Return current frame index."""
        with self._lock:
            return self._current_frame_idx

    def get_total_frames(self) -> int:
        """Return total frame count."""
        with self._lock:
            return self._total_frames

    def _effective_dimensions(self) -> Tuple[int, int]:
        """Compute effective target (width, height)."""
        if (
            self._vcam is not None
            and self._vcam.is_active()
            and self._vcam.width > 0
            and self._vcam.height > 0
        ):
            return (self._vcam.width, self._vcam.height)
        if self._target_width is not None and self._target_height is not None:
            return (self._target_width, self._target_height)
        src_dim = (
            (self._source_width, self._source_height)
            if self._source_width > 0 and self._source_height > 0
            else None
        )
        return self._config.get_output_dimensions(source_dim=src_dim)

    def _effective_fps(self) -> float:
        """Compute effective target FPS."""
        if (
            self._vcam is not None
            and self._vcam.is_active()
            and self._vcam.fps > 0
        ):
            return float(self._vcam.fps)
        if self._target_fps is not None and self._target_fps > 0:
            return float(self._target_fps)
        return self._config.get_output_fps(source_fps=self._source_fps)

    # -----------------------------------------------------------------------
    # Media Loading
    # -----------------------------------------------------------------------

    @Slot(str)
    def load_video(self, file_path: Union[str, Path]) -> bool:
        """Load and probe a video file, initializing VideoCapture."""
        with self._lock:
            if not file_path:
                self._state = PlaybackState.UNLOADED
                self.signals.error_occurred.emit(
                    "FileNotFoundError", "Video file path cannot be empty."
                )
                self.signals.state_changed.emit(PlaybackState.UNLOADED)
                return False

            path_str = str(file_path)
            path_obj = Path(path_str)
            if not path_obj.is_file():
                self._state = PlaybackState.UNLOADED
                self.signals.error_occurred.emit(
                    "FileNotFoundError", f"File does not exist: {path_str}"
                )
                self.signals.state_changed.emit(PlaybackState.UNLOADED)
                return False

            metadata = probe_video_metadata(path_str)
            if not metadata.is_valid:
                self._state = PlaybackState.ERROR
                err_msg = metadata.error_message or "Failed to decode video header."
                self.signals.error_occurred.emit("InvalidVideoError", err_msg)
                self.signals.state_changed.emit(PlaybackState.ERROR)
                return False

            # Release previous capture if open
            if self._cap is not None:
                self._cap.release()
                self._cap = None

            cap = cv2.VideoCapture(path_str)
            if not cap.isOpened():
                self._state = PlaybackState.ERROR
                self.signals.error_occurred.emit(
                    "OpenCVError", f"OpenCV failed to open video capture: {path_str}"
                )
                self.signals.state_changed.emit(PlaybackState.ERROR)
                return False

            self._cap = cap
            self._video_path = path_str
            self._metadata = metadata
            self._total_frames = metadata.frame_count
            self._source_fps = metadata.fps if metadata.fps > 0 else 30.0
            self._source_width = metadata.width
            self._source_height = metadata.height
            self._current_frame_idx = 0

            # Update configuration video path
            self._config.video_path = path_str

            # Allocate or resize canvas buffer
            target_w, target_h = self._effective_dimensions()
            self._canvas_buffer = np.zeros((target_h, target_w, 3), dtype=np.uint8)

            # Read frame 0 for preview poster
            ret, frame_bgr = self._cap.read()
            if ret and frame_bgr is not None:
                transformed = transform_frame(
                    frame_bgr,
                    target_w,
                    target_h,
                    out_canvas=self._canvas_buffer,
                    flip_horizontal=self._flip_horizontal,
                )
                self.signals.frame_ready.emit(transformed, 0)
                # Rewind back to frame 0
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)


            self._state = PlaybackState.STOPPED
            self.signals.media_loaded.emit(metadata)
            total_sec = (
                self._total_frames / self._source_fps
                if self._source_fps > 0
                else 0.0
            )
            self.signals.position_changed.emit(0, self._total_frames, 0.0, total_sec)
            self.signals.state_changed.emit(PlaybackState.STOPPED)
            return True

    # -----------------------------------------------------------------------
    # Playback Controls
    # -----------------------------------------------------------------------

    @Slot()
    def play(self) -> None:
        """Start or resume playback on the dedicated worker thread."""
        with self._lock:
            if self._cap is None or self._state in (
                PlaybackState.UNLOADED,
                PlaybackState.ERROR,
            ):
                return

            if self._state == PlaybackState.PLAYING:
                return

            if self._state == PlaybackState.COMPLETED:
                # Rewind to start on replay
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self._current_frame_idx = 0

            self._state = PlaybackState.PLAYING
            self.signals.state_changed.emit(PlaybackState.PLAYING)

        # Run playback loop on worker thread
        self._run_playback_loop()

    def request_pause(self) -> None:
        """Thread-safe flag update for pausing."""
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                self._state = PlaybackState.PAUSED

    @Slot()
    def pause(self) -> None:
        """Pause playback."""
        with self._lock:
            if self._state == PlaybackState.PLAYING:
                self._state = PlaybackState.PAUSED
                self.signals.state_changed.emit(PlaybackState.PAUSED)

    def request_stop(self) -> None:
        """Thread-safe flag update for stopping."""
        with self._lock:
            self._state = PlaybackState.STOPPED
            self._current_frame_idx = 0

    @Slot()
    def stop(self) -> None:
        """Stop playback and rewind to frame 0."""
        with self._lock:
            self._state = PlaybackState.STOPPED
            self._current_frame_idx = 0

            if self._cap is not None and self._cap.isOpened():
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                ret, frame_bgr = self._cap.read()
                if ret and frame_bgr is not None:
                    target_w, target_h = self._effective_dimensions()
                    transformed = transform_frame(
                        frame_bgr,
                        target_w,
                        target_h,
                        out_canvas=self._canvas_buffer,
                    )
                    self.signals.frame_ready.emit(transformed, 0)
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

            total_sec = (
                self._total_frames / self._source_fps
                if self._source_fps > 0
                else 0.0
            )
            self.signals.position_changed.emit(0, self._total_frames, 0.0, total_sec)
            self.signals.state_changed.emit(PlaybackState.STOPPED)

    @Slot(int)
    def seek(self, frame_idx: int) -> None:
        """Seek to a specific frame index with clamping and preview update."""
        with self._lock:
            if self._cap is None or self._total_frames <= 0:
                return

            target_idx = max(0, min(int(frame_idx), self._total_frames - 1))
            self._current_frame_idx = target_idx
            self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)

            ret, frame_bgr = self._cap.read()
            if ret and frame_bgr is not None:
                target_w, target_h = self._effective_dimensions()
                transformed = transform_frame(
                    frame_bgr,
                    target_w,
                    target_h,
                    out_canvas=self._canvas_buffer,
                    flip_horizontal=self._flip_horizontal,
                )
                self.signals.frame_ready.emit(transformed, target_idx)

                if self._vcam is not None and self._vcam.is_active():
                    try:
                        self._vcam.send(transformed)
                    except Exception as e:
                        logger.warning(f"Error sending seek frame to vcam: {e}")

                # If not playing, keep pointer at target_idx
                if self._state != PlaybackState.PLAYING:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)

            cur_sec = (
                target_idx / self._source_fps if self._source_fps > 0 else 0.0
            )
            total_sec = (
                self._total_frames / self._source_fps
                if self._source_fps > 0
                else 0.0
            )
            self.signals.position_changed.emit(
                target_idx, self._total_frames, cur_sec, total_sec
            )

    @Slot(bool)
    def set_flip_horizontal(self, flip: bool) -> None:
        """Set horizontal flip (mirror) state dynamically."""
        with self._lock:
            self._flip_horizontal = bool(flip)
            self._config.flip_horizontal = self._flip_horizontal

            # If stopped or paused, re-render current frame immediately with new flip state
            if (
                self._cap is not None
                and self._cap.isOpened()
                and self._state != PlaybackState.PLAYING
            ):
                target_idx = self._current_frame_idx
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)
                ret, frame_bgr = self._cap.read()
                if ret and frame_bgr is not None:
                    target_w, target_h = self._effective_dimensions()
                    transformed = transform_frame(
                        frame_bgr,
                        target_w,
                        target_h,
                        out_canvas=self._canvas_buffer,
                        flip_horizontal=self._flip_horizontal,
                    )
                    self.signals.frame_ready.emit(transformed, target_idx)
                    if self._vcam is not None and self._vcam.is_active():
                        try:
                            self._vcam.send(transformed)
                        except Exception:
                            pass
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, target_idx)

    @Slot(bool)
    def set_loop(self, loop: bool) -> None:
        """Set continuous loop playback behavior."""
        with self._lock:
            self._loop = bool(loop)
            self._config.loop_playback = self._loop


    @Slot(int, int)
    def set_target_resolution(self, width: int, height: int) -> None:
        """Set target output resolution dynamically."""
        if width <= 0 or height <= 0:
            raise ValueError(
                f"Resolution dimensions must be positive integers: ({width}, {height})"
            )
        with self._lock:
            self._target_width = int(width)
            self._target_height = int(height)
            self._config.custom_width = self._target_width
            self._config.custom_height = self._target_height
            self._canvas_buffer = np.zeros(
                (self._target_height, self._target_width, 3), dtype=np.uint8
            )

            # If virtual camera is active and dimensions differ, re-open
            if (
                self._vcam is not None
                and self._vcam.is_active()
                and (self._vcam.width != width or self._vcam.height != height)
            ):
                dev = self._vcam.device
                fps = self._effective_fps()
                try:
                    self._vcam.open(width=width, height=height, fps=fps, device=dev)
                    self.signals.vcam_status_changed.emit(
                        True, self._vcam.get_device_name(), ""
                    )
                except Exception as e:
                    self.signals.vcam_status_changed.emit(
                        False, dev or "", str(e)
                    )
                    self.signals.error_occurred.emit(type(e).__name__, str(e))

    @Slot(float)
    def set_target_fps(self, fps: float) -> None:
        """Set target playback frame rate dynamically."""
        if fps <= 0:
            raise ValueError(f"FPS must be positive number: {fps}")
        with self._lock:
            self._target_fps = float(fps)
            self._config.custom_fps = self._target_fps

            # If virtual camera is active and fps differs, re-open if needed
            if (
                self._vcam is not None
                and self._vcam.is_active()
                and abs(self._vcam.fps - fps) > 0.1
            ):
                w, h = self._effective_dimensions()
                dev = self._vcam.device
                try:
                    self._vcam.open(width=w, height=h, fps=fps, device=dev)
                    self.signals.vcam_status_changed.emit(
                        True, self._vcam.get_device_name(), ""
                    )
                except Exception as e:
                    self.signals.vcam_status_changed.emit(
                        False, dev or "", str(e)
                    )
                    self.signals.error_occurred.emit(type(e).__name__, str(e))

    # -----------------------------------------------------------------------
    # Virtual Camera Controls
    # -----------------------------------------------------------------------

    @Slot(str, int, int, float)
    def start_virtual_camera(
        self,
        device: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
    ) -> bool:
        """Start streaming output frames to the virtual camera backend."""
        with self._lock:
            if width is not None and width > 0 and height is not None and height > 0:
                self._target_width = int(width)
                self._target_height = int(height)
            if fps is not None and fps > 0:
                self._target_fps = float(fps)

            eff_w = width if width is not None and width > 0 else self._effective_dimensions()[0]
            eff_h = height if height is not None and height > 0 else self._effective_dimensions()[1]
            eff_fps = fps if fps is not None and fps > 0 else self._effective_fps()

            if self._vcam is not None and self._vcam.is_active():
                self._vcam.close()

            if self._custom_vcam_backend is not None:
                self._vcam = self._custom_vcam_backend
            else:
                self._vcam = get_virtual_camera_backend(
                    force_mock=self._use_mock_camera, device=device
                )

            try:
                self._vcam.open(
                    width=eff_w, height=eff_h, fps=eff_fps, device=device
                )
                self._canvas_buffer = np.zeros((eff_h, eff_w, 3), dtype=np.uint8)
                dev_name = self._vcam.get_device_name()
                self.signals.vcam_status_changed.emit(True, dev_name, "")
                logger.info(f"Virtual camera started: {dev_name} ({eff_w}x{eff_h} @ {eff_fps} FPS)")
                return True
            except Exception as e:
                self._vcam = None
                dev_str = device or ""
                self.signals.vcam_status_changed.emit(False, dev_str, str(e))
                self.signals.error_occurred.emit(type(e).__name__, str(e))
                logger.error(f"Failed to start virtual camera: {e}")
                raise

    @Slot()
    def stop_virtual_camera(self) -> None:
        """Stop virtual camera streaming and release system device node."""
        with self._lock:
            if self._vcam is not None:
                dev_name = self._vcam.get_device_name()
                try:
                    self._vcam.close()
                except Exception as e:
                    logger.warning(f"Error closing virtual camera: {e}")
                finally:
                    self.signals.vcam_status_changed.emit(False, dev_name, "")
                    self._vcam = None
                    logger.info("Virtual camera stopped.")

    # -----------------------------------------------------------------------
    # Pacing Loop Implementation
    # -----------------------------------------------------------------------

    def _run_playback_loop(self) -> None:
        """Monotonic clock anchor pacing loop with dynamic drift compensation & hybrid sleep."""
        anchor_time = time.perf_counter()
        anchor_frame_idx = self._current_frame_idx

        while self._is_running:
            # Process pending Qt events on this worker thread
            QCoreApplication.processEvents()

            with self._lock:
                if self._state != PlaybackState.PLAYING or not self._is_running:
                    break
                if self._cap is None or not self._cap.isOpened():
                    break

                target_fps = self._effective_fps()
                frame_duration = 1.0 / target_fps if target_fps > 0 else 1.0 / 30.0
                target_w, target_h = self._effective_dimensions()
                loop_enabled = self._loop

            # Calculate target time for current frame
            relative_frame = self._current_frame_idx - anchor_frame_idx
            target_time = anchor_time + (relative_frame * frame_duration)
            now = time.perf_counter()

            # Dynamic drift compensation (>50ms lag)
            if (now - target_time) > 0.050 or (target_time - now) > 5.0:
                anchor_time = now
                anchor_frame_idx = self._current_frame_idx
                target_time = now

            # Hybrid sleep (>2ms OS sleep, sub-ms spin loop)
            remaining = target_time - time.perf_counter()
            if remaining > 0.002:
                time.sleep(remaining - 0.001)
            while time.perf_counter() < target_time:
                pass

            # Re-check state after sleep
            with self._lock:
                if self._state != PlaybackState.PLAYING or not self._is_running:
                    break

                ret, frame_bgr = self._cap.read()
                if not ret or frame_bgr is None:
                    # End of stream reached
                    if loop_enabled:
                        self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        self._current_frame_idx = 0
                        anchor_time = time.perf_counter()
                        anchor_frame_idx = 0
                        continue
                    else:
                        self._state = PlaybackState.COMPLETED
                        total_sec = (
                            self._total_frames / self._source_fps
                            if self._source_fps > 0
                            else 0.0
                        )
                        self.signals.position_changed.emit(
                            self._total_frames,
                            self._total_frames,
                            total_sec,
                            total_sec,
                        )
                        self.signals.state_changed.emit(PlaybackState.COMPLETED)
                        break

                cur_idx = self._current_frame_idx
                self._current_frame_idx += 1

                # Frame transformation
                if (
                    self._canvas_buffer is None
                    or self._canvas_buffer.shape != (target_h, target_w, 3)
                ):
                    self._canvas_buffer = np.zeros(
                        (target_h, target_w, 3), dtype=np.uint8
                    )

                transformed = transform_frame(
                    frame_bgr,
                    target_w,
                    target_h,
                    out_canvas=self._canvas_buffer,
                    flip_horizontal=self._flip_horizontal,
                )


                # Dispatch frame to virtual camera if active
                if self._vcam is not None and self._vcam.is_active():
                    try:
                        self._vcam.send(transformed)
                    except Exception as e:
                        dev = self._vcam.get_device_name() if self._vcam else ""
                        self.signals.vcam_status_changed.emit(False, dev, str(e))
                        self.signals.error_occurred.emit(type(e).__name__, str(e))

            # Emit frame and progress signals outside lock
            self.signals.frame_ready.emit(transformed, cur_idx)
            cur_sec = (
                cur_idx / self._source_fps if self._source_fps > 0 else 0.0
            )
            total_sec = (
                self._total_frames / self._source_fps
                if self._source_fps > 0
                else 0.0
            )
            self.signals.position_changed.emit(
                cur_idx, self._total_frames, cur_sec, total_sec
            )

    # -----------------------------------------------------------------------
    # Teardown & Cleanup
    # -----------------------------------------------------------------------

    @Slot()
    def cleanup(self) -> None:
        """Release all resources, close camera, and release video capture."""
        with self._lock:
            self._is_running = False
            self._state = PlaybackState.STOPPED

            if self._vcam is not None:
                try:
                    self._vcam.close()
                except Exception as e:
                    logger.warning(f"Error closing vcam in cleanup: {e}")
                finally:
                    self._vcam = None

            if self._cap is not None:
                try:
                    self._cap.release()
                except Exception as e:
                    logger.warning(f"Error releasing cap in cleanup: {e}")
                finally:
                    self._cap = None


class VideoPlayerController(QObject):
    """High-level thread-safe facade managing VideoPlayerWorker and its dedicated QThread."""

    # Public signals forwarded from worker
    frame_ready = Signal(object, int)
    position_changed = Signal(int, int, float, float)
    state_changed = Signal(object)
    vcam_status_changed = Signal(bool, str, str)
    error_occurred = Signal(str, str)
    media_loaded = Signal(object)

    # Internal signals for invoking worker slots across threads
    _sig_load_video = Signal(str)
    _sig_play = Signal()
    _sig_pause = Signal()
    _sig_stop = Signal()
    _sig_seek = Signal(int)
    _sig_set_loop = Signal(bool)
    _sig_set_flip = Signal(bool)
    _sig_set_resolution = Signal(int, int)
    _sig_set_fps = Signal(float)
    _sig_start_vcam = Signal(str, int, int, float)
    _sig_stop_vcam = Signal()
    _sig_cleanup = Signal()

    def __init__(
        self,
        config: Optional[AppConfig] = None,
        use_mock_camera: bool = False,
        vcam_backend: Optional[IVirtualCamera] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config or AppConfig(use_mock_camera=use_mock_camera)
        if use_mock_camera:
            self._config.use_mock_camera = True
        self._vcam_backend = vcam_backend

        # Dedicated worker thread
        self._thread = QThread()
        self._worker = VideoPlayerWorker(
            config=self._config,
            vcam_backend=self._vcam_backend,
        )
        self._worker.moveToThread(self._thread)

        # Audio playback engine
        self._audio_output = QAudioOutput(self)
        self._audio_player = QMediaPlayer(self)
        self._audio_player.setAudioOutput(self._audio_output)
        self._audio_output.setVolume(self._config.volume / 100.0)
        self._audio_output.setMuted(not self._config.audio_enabled)

        # Forward worker signals to controller signals
        self._worker.signals.frame_ready.connect(self.frame_ready)
        self._worker.signals.position_changed.connect(self.position_changed)
        self._worker.signals.state_changed.connect(self.state_changed)
        self._worker.signals.state_changed.connect(self._on_worker_state_changed)
        self._worker.signals.vcam_status_changed.connect(self.vcam_status_changed)
        self._worker.signals.error_occurred.connect(self.error_occurred)
        self._worker.signals.media_loaded.connect(self.media_loaded)

        # Connect internal cross-thread signals to worker slots
        self._sig_load_video.connect(
            self._worker.load_video, Qt.ConnectionType.QueuedConnection
        )
        self._sig_play.connect(
            self._worker.play, Qt.ConnectionType.QueuedConnection
        )
        self._sig_pause.connect(
            self._worker.pause, Qt.ConnectionType.QueuedConnection
        )
        self._sig_stop.connect(
            self._worker.stop, Qt.ConnectionType.QueuedConnection
        )
        self._sig_seek.connect(
            self._worker.seek, Qt.ConnectionType.QueuedConnection
        )
        self._sig_set_loop.connect(
            self._worker.set_loop, Qt.ConnectionType.QueuedConnection
        )
        self._sig_set_flip.connect(
            self._worker.set_flip_horizontal, Qt.ConnectionType.QueuedConnection
        )
        self._sig_set_resolution.connect(
            self._worker.set_target_resolution, Qt.ConnectionType.QueuedConnection
        )
        self._sig_set_fps.connect(
            self._worker.set_target_fps, Qt.ConnectionType.QueuedConnection
        )
        self._sig_stop_vcam.connect(
            self._worker.stop_virtual_camera, Qt.ConnectionType.QueuedConnection
        )
        self._sig_cleanup.connect(
            self._worker.cleanup, Qt.ConnectionType.QueuedConnection
        )

        self._thread.start()

    def _on_worker_state_changed(self, state: PlaybackState) -> None:
        """Synchronize audio playback engine with video worker state transitions."""
        if state == PlaybackState.PLAYING:
            if (
                self._config.audio_enabled
                and self._audio_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
            ):
                self._audio_player.play()
        elif state in (PlaybackState.PAUSED, PlaybackState.STOPPED, PlaybackState.COMPLETED):
            self._audio_player.pause()


    # -----------------------------------------------------------------------
    # Public Properties
    # -----------------------------------------------------------------------

    @property
    def config(self) -> AppConfig:
        """Application configuration."""
        return self._config

    @property
    def worker(self) -> VideoPlayerWorker:
        """Direct reference to the worker object."""
        return self._worker

    @property
    def signals(self) -> PlayerSignals:
        """Direct reference to player signals."""
        return self._worker.signals

    # -----------------------------------------------------------------------
    # Public API Methods
    # -----------------------------------------------------------------------

    def get_state(self) -> PlaybackState:
        """Return the current playback state."""
        return self._worker.get_state()

    def is_playing(self) -> bool:
        """Check if video is currently playing."""
        return self._worker.is_playing()

    def get_metadata(self) -> Optional[VideoMetadata]:
        """Return metadata of the loaded video."""
        return self._worker.get_metadata()

    def get_current_frame_idx(self) -> int:
        """Return current playback frame index."""
        return self._worker.get_current_frame_idx()

    def get_total_frames(self) -> int:
        """Return total frame count."""
        return self._worker.get_total_frames()

    def load_video(self, file_path: Union[str, Path]) -> bool:
        """Load a video file. Returns True if successfully probed and opened."""
        if not file_path:
            self._worker._state = PlaybackState.UNLOADED
            self.error_occurred.emit(
                "FileNotFoundError", "Video file path is empty."
            )
            self.state_changed.emit(PlaybackState.UNLOADED)
            return False

        path_str = str(file_path)
        if not Path(path_str).is_file():
            self._worker._state = PlaybackState.UNLOADED
            self.error_occurred.emit(
                "FileNotFoundError", f"File does not exist: {path_str}"
            )
            self.state_changed.emit(PlaybackState.UNLOADED)
            return False

        success = self._worker.load_video(path_str)
        if success:
            try:
                self._audio_player.setSource(QUrl.fromLocalFile(path_str))
            except Exception as e:
                logger.warning(f"Failed to load audio track: {e}")
        return success

    def play(self) -> None:
        """Start or resume video playback."""
        if self.get_state() in (PlaybackState.UNLOADED, PlaybackState.ERROR):
            return
        self._sig_play.emit()
        if (
            self._config.audio_enabled
            and self._audio_player.playbackState() != QMediaPlayer.PlaybackState.PlayingState
        ):
            try:
                self._audio_player.play()
            except Exception:
                pass

    def pause(self) -> None:
        """Pause video playback."""
        self._worker.request_pause()
        self._worker.pause()
        try:
            self._audio_player.pause()
        except Exception:
            pass

    def stop(self) -> None:
        """Stop video playback and reset position."""
        self._worker.request_stop()
        self._worker.stop()
        try:
            self._audio_player.stop()
            self._audio_player.setPosition(0)
        except Exception:
            pass

    def seek(self, frame_idx: int) -> None:
        """Seek playback position to the given frame index."""
        self._worker.seek(frame_idx)
        meta = self.get_metadata()
        if meta and meta.fps > 0:
            sec = frame_idx / meta.fps
            try:
                self._audio_player.setPosition(int(round(sec * 1000)))
            except Exception:
                pass

    def set_flip_horizontal(self, flip: bool) -> None:
        """Set horizontal flip (mirror) state."""
        self._config.flip_horizontal = bool(flip)
        self._sig_set_flip.emit(self._config.flip_horizontal)

    def set_audio_enabled(self, enabled: bool) -> None:
        """Enable or mute audio streaming."""
        self._config.audio_enabled = bool(enabled)
        self._audio_output.setMuted(not self._config.audio_enabled)
        if not self._config.audio_enabled:
            self._audio_player.pause()
        elif self.is_playing():
            self._audio_player.play()

    def set_volume(self, volume: int) -> None:
        """Set audio output volume (0-100)."""
        self._config.volume = max(0, min(100, int(volume)))
        self._audio_output.setVolume(self._config.volume / 100.0)

    def set_loop(self, loop: bool) -> None:
        """Enable or disable loop playback."""
        self._worker.set_loop(loop)
        self._config.loop_playback = bool(loop)

    def set_target_resolution(self, width: int, height: int) -> None:
        """Set output dimensions for scaling and transformation."""
        self._worker.set_target_resolution(width, height)

    def set_target_fps(self, fps: float) -> None:
        """Set target frame rate for pacing loop."""
        self._worker.set_target_fps(fps)

    def start_virtual_camera(
        self,
        device: Optional[str] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        fps: Optional[float] = None,
    ) -> bool:
        """Start the virtual camera device feed."""
        return self._worker.start_virtual_camera(
            device=device, width=width, height=height, fps=fps
        )

    def stop_virtual_camera(self) -> None:
        """Stop the virtual camera device feed."""
        self._worker.stop_virtual_camera()

    def cleanup(self) -> None:
        """Safely terminate the worker and its dedicated QThread."""
        try:
            self._audio_player.stop()
        except Exception:
            pass
        self._worker.cleanup()
        if self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(2000)

    def __del__(self) -> None:
        """Ensure thread cleanup on garbage collection."""
        try:
            self.cleanup()
        except Exception:
            pass

