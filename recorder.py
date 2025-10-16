from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

Frame = NDArray[np.uint8]


def _default_fourcc() -> int:
    return cast(int, getattr(cv2, "VideoWriter_fourcc")(*"mp4v"))


@dataclass
class RecordingContext:
    flag: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    session_id: str | None = None

    def set_session(self, session: str | None) -> None:
        with self.lock:
            self.session_id = session

    def get_session(self) -> str | None:
        with self.lock:
            return self.session_id


@dataclass
class CameraRecordingState:
    writer: cv2.VideoWriter | None = None
    active_session: str | None = None
    warned_writer_failure: bool = False
    video_path: Path | None = None
    record_start: float | None = None
    frame_written: int = 0
    frame_size_out: tuple[int, int] = (0, 0)


class Recorder:
    def __init__(
        self,
        record_dir: Path | None = None,
        fourcc: int | None = None,
        default_fps: float = 30.0,
    ) -> None:
        self.record_dir: Path = record_dir or Path("recordings")
        self.fourcc: int = fourcc if fourcc is not None else _default_fourcc()
        self.default_fps: float = default_fps
        self._lock: threading.Lock = threading.Lock()
        self._states: dict[int, CameraRecordingState] = {}
        self._context: RecordingContext = RecordingContext()

    @property
    def recording_context(self) -> RecordingContext:
        return self._context

    def start_session(self, session: str) -> None:
        self._context.set_session(session)
        self._context.flag.set()

    def stop_session(self) -> None:
        self._context.flag.clear()
        self._context.set_session(None)

    def handle_frame(self, index: int, frame: Frame, fps: float) -> None:
        with self._lock:
            state = self._states.setdefault(index, CameraRecordingState())
            if not self._context.flag.is_set():
                if state.writer is not None:
                    self._finish_recording(index, state, "stopped")
                return

            session = self._context.get_session()
            if not session:
                return

            if session != state.active_session:
                self._finish_recording(index, state, "saved")
                if not self._start_recording(index, state, session, frame, fps):
                    return

            writer = state.writer
            if writer is None:
                return

            state.frame_written += 1
        writer.write(frame)

    def finalize_camera(self, index: int, reason: str) -> None:
        with self._lock:
            state = self._states.get(index)
            if not state:
                return
            self._finish_recording(index, state, reason)

    def shutdown(self) -> None:
        with self._lock:
            for index, state in self._states.items():
                self._finish_recording(index, state, "shutdown")

    def _start_recording(
        self,
        index: int,
        state: CameraRecordingState,
        session: str,
        frame: Frame,
        fps: float,
    ) -> bool:
        self.record_dir.mkdir(parents=True, exist_ok=True)
        filename = f"cam{index}_{session}.mp4"
        path = self.record_dir / filename
        frame_size = (int(frame.shape[1]), int(frame.shape[0]))
        effective_fps = fps if fps and not math.isclose(fps, 0.0) else self.default_fps
        candidate = cv2.VideoWriter(str(path), self.fourcc, effective_fps, frame_size)

        if not candidate.isOpened():
            candidate.release()
            if not state.warned_writer_failure:
                print(f"Failed to start recorder for camera {index} at {path}")
                state.warned_writer_failure = True
            return False

        state.writer = candidate
        state.active_session = session
        state.video_path = path
        state.record_start = time.perf_counter()
        state.frame_written = 0
        state.frame_size_out = frame_size
        state.warned_writer_failure = False
        print(f"Recording camera {index} -> {path}")
        return True

    def _finish_recording(
        self,
        index: int,
        state: CameraRecordingState,
        reason: str,
    ) -> None:
        if state.writer is None:
            state.active_session = None
            state.video_path = None
            state.record_start = None
            state.frame_written = 0
            state.frame_size_out = (0, 0)
            return

        state.writer.release()
        duration = 0.0
        if state.record_start is not None:
            duration = time.perf_counter() - state.record_start
        width, height = state.frame_size_out
        fps_est = state.frame_written / duration if duration > 0 else 0.0
        name = state.video_path.name if state.video_path else "unknown"
        message = (
            "[Camera {idx}] {reason}: {name} | {width}x{height} | {frames} frames | "
            "{duration:.2f}s | ~{fps:.2f}fps"
        ).format(
            idx=index,
            reason=reason,
            name=name,
            width=width,
            height=height,
            frames=state.frame_written,
            duration=duration,
            fps=fps_est,
        )
        print(message)

        state.writer = None
        state.active_session = None
        state.video_path = None
        state.record_start = None
        state.frame_written = 0
        state.frame_size_out = (0, 0)
        state.warned_writer_failure = False
