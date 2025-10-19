from __future__ import annotations

import cv2
import time
from threading import Event, Thread, Lock
from pathlib import Path
import numpy as np
from loguru import logger
from numpy.typing import NDArray
from typing import cast


def backend_from_name(name: str) -> int:
    name_u = name.strip().upper()
    if name_u in ("ANY", "AUTO", "DEFAULT"):
        return cv2.CAP_ANY
    if name_u in ("MSMF", "CAP_MSMF"):
        return cv2.CAP_MSMF
    if name_u in ("DSHOW", "DIRECTSHOW", "CAP_DSHOW"):
        return cv2.CAP_DSHOW
    if name_u in ("V4L2", "CAP_V4L2"):
        return cv2.CAP_V4L2
    # Fallback
    return cv2.CAP_ANY


def map_output_fourcc(output_type: str) -> tuple[str, str]:
    ot = output_type.lower()
    if ot == "mp4":
        return "mp4v", ".mp4"
    if ot == "mkv":
        return "XVID", ".mkv"
    # default avi
    return "MJPG", ".avi"


class CameraStream:
    def __init__(
        self,
        device_id: int,
        backend_name: str = "ANY",
        width: int = 1920,
        height: int = 1080,
        fps: float = 30.0,
        status_log_interval_sec: float = 0.0,
    ) -> None:
        self.device_id: int = device_id
        self.backend_flag: int = backend_from_name(backend_name)
        self.width: int = int(width)
        self.height: int = int(height)
        self.fps: float = float(fps)
        self._status_log_interval: float = float(status_log_interval_sec)

        self.cap: cv2.VideoCapture | None = None
        self.writer: cv2.VideoWriter | None = None
        self.recording: Event = Event()
        self.running: Event = Event()

        self._frame_lock: Lock = Lock()
        self._frame: NDArray[np.uint8] | None = None
        # Frame sequence and FPS/status fields
        self._frame_seq: int = 0
        self._last_frame_time: float = 0.0
        self._fps_ema: float = 0.0
        self._ema_alpha: float = 0.2  # smoothing factor for FPS EMA
        self._last_frame_size: tuple[int, int] | None = None  # (w, h)
        self._writer_lock: Lock = Lock()
        self._last_log_time: float = 0.0
        self._frame_count: int = 0
        self._start_time: float = 0.0
        self._thread: Thread | None = None

        self._out_fourcc_str: str = "MJPG"
        self._out_ext: str = ".avi"
        # 录制统计
        self._rec_start_time: float = 0.0
        self._rec_frame_count: int = 0
        self._rec_output_path: Path | None = None
        self._rec_size: tuple[int, int] | None = None

    def open(self) -> bool:
        self.cap = cv2.VideoCapture(self.device_id, self.backend_flag)
        if not self.cap or not self.cap.isOpened():
            logger.error(f"Camera {self.device_id}: failed to open")
            return False

        # Configure capture for performance similar to demo
        _ = self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter.fourcc(*"MJPG"))
        _ = self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        _ = self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        _ = self.cap.set(cv2.CAP_PROP_FPS, self.fps)

        # 预热：读取少量帧帮助后端稳定，减少首帧延迟
        warm_reads = 3
        for _i in range(warm_reads):
            _ret, _frm = self.cap.read()

        backend_name = (
            self.cap.getBackendName()
            if hasattr(self.cap, "getBackendName")
            else str(self.backend_flag)
        )
        logger.info(
            f"Camera {self.device_id}: opened with backend={backend_name}, target={self.width}x{self.height}@{self.fps:.2f}"
        )

        self.running.set()
        self._start_time = time.time()
        self._last_log_time = self._start_time
        self._frame_count = 0
        self._thread = Thread(
            target=self._loop, name=f"CameraStream-{self.device_id}", daemon=True
        )
        self._thread.start()
        return True

    def start_recording(self, output_path: Path, output_type: str = "avi") -> None:
        fourcc_str, ext = map_output_fourcc(output_type)
        self._out_fourcc_str = fourcc_str
        self._out_ext = ext
        output_path = output_path.with_suffix(ext)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # If already recording, restart
        if self.recording.is_set():
            self.stop_recording()

        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if self.cap else self.width
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if self.cap else self.height
        fourcc = cv2.VideoWriter.fourcc(*fourcc_str)
        new_writer = cv2.VideoWriter(str(output_path), fourcc, self.fps, (w, h))
        if new_writer and new_writer.isOpened():
            with self._writer_lock:
                self.writer = new_writer
                # 初始化录制统计
                self._rec_start_time = time.time()
                self._rec_frame_count = 0
                self._rec_output_path = output_path
                self._rec_size = (w, h)
                # 录制开始时重置 FPS 估计，仅在录制期间计算
                with self._frame_lock:
                    self._fps_ema = 0.0
                    self._last_frame_time = 0.0
                self.recording.set()
            logger.info(
                f"Camera {self.device_id}: start recording -> {output_path.name} fourcc={fourcc_str} size={w}x{h}@{self.fps:.2f}"
            )
        else:
            logger.error(
                f"Camera {self.device_id}: failed to open VideoWriter at {output_path}"
            )
            try:
                if new_writer:
                    new_writer.release()
            finally:
                pass

    def stop_recording(self) -> None:
        # 先清除录制标志，阻止新的写入
        was_recording = self.recording.is_set()
        if was_recording:
            self.recording.clear()
        # 在写锁下安全释放 writer，避免与写入竞争
        with self._writer_lock:
            if self.writer:
                try:
                    self.writer.release()
                finally:
                    self.writer = None
        if was_recording:
            # 汇总并输出录制统计
            duration = (
                max(0.0, time.time() - self._rec_start_time)
                if self._rec_start_time > 0
                else 0.0
            )
            avg_fps = (self._rec_frame_count / duration) if duration > 0 else 0.0
            width, height = (
                self._rec_size if self._rec_size else (self.width, self.height)
            )
            file_name = (
                self._rec_output_path.name if self._rec_output_path else "<unknown>"
            )
            logger.info(
                (
                    f"Camera {self.device_id}: stop recording | file={file_name} "
                    f"frames={self._rec_frame_count} duration={duration:.2f}s avg_fps={avg_fps:.2f} "
                    f"size={width}x{height} fourcc={self._out_fourcc_str}"
                )
            )
            # 清理统计
            self._rec_start_time = 0.0
            self._rec_frame_count = 0
            self._rec_output_path = None
            self._rec_size = None

    def get_latest_frame_with_seq(self) -> tuple[int, NDArray[np.uint8] | None]:
        """Return (sequence, latest_frame_copy). Sequence increases when a new frame is captured."""
        with self._frame_lock:
            seq = self._frame_seq
            frm = None if self._frame is None else self._frame.copy()
            return seq, frm

    def _loop(self) -> None:
        assert self.cap is not None
        while self.running.is_set():
            ret, frame = self.cap.read()
            if not ret:
                logger.warning(
                    f"Camera {self.device_id}: failed to read frame; stopping"
                )
                break

            # OpenCV 默认返回 uint8 BGR
            frame_u8 = cast(NDArray[np.uint8], frame)
            with self._frame_lock:
                self._frame = frame_u8
                self._frame_seq += 1
                # update last frame size
                self._last_frame_size = (int(frame_u8.shape[1]), int(frame_u8.shape[0]))
                # 仅在录制期间计算 FPS（EMA），正常预览时不计算
                if self.recording.is_set():
                    now = time.time()
                    if self._last_frame_time > 0:
                        dt = max(1e-6, now - self._last_frame_time)
                        inst_fps = 1.0 / dt
                        a = self._ema_alpha
                        self._fps_ema = a * inst_fps + (1.0 - a) * self._fps_ema
                    self._last_frame_time = now

            self._frame_count += 1
            now = time.time()
            if (
                self._status_log_interval > 0
                and (now - self._last_log_time) >= self._status_log_interval
            ):
                height = int(frame_u8.shape[0])
                width = int(frame_u8.shape[1])
                elapsed = now - self._start_time
                fps = self._frame_count / elapsed if elapsed > 0 else 0
                backend_name = (
                    self.cap.getBackendName()
                    if hasattr(self.cap, "getBackendName")
                    else str(self.backend_flag)
                )
                logger.info(
                    f"Camera {self.device_id}: {width}x{height}, ~{fps:.2f} FPS | backend={backend_name}"
                )
                self._last_log_time = now
                self._frame_count = 0
                self._start_time = now

            if self.recording.is_set():
                with self._writer_lock:
                    if self.recording.is_set() and self.writer is not None:
                        try:
                            self.writer.write(frame_u8)
                            self._rec_frame_count += 1
                        except Exception as e:
                            logger.warning(
                                f"Camera {self.device_id}: writer.write failed ({e}); stopping recording"
                            )
                            # 发生异常时安全停止录制，避免线程崩溃
                            self.recording.clear()
                            try:
                                if self.writer:
                                    self.writer.release()
                            finally:
                                self.writer = None

        self.running.clear()

    def get_status(self) -> dict[str, object]:
        """Return a snapshot of current status for UI display.
        Keys: 'fps' (float), 'size' (tuple[int,int] | None), 'recording' (bool)
        """
        with self._frame_lock:
            rec = self.recording.is_set()
            fps = float(self._fps_ema) if rec else 0.0
            size = self._last_frame_size
        return {"fps": fps, "size": size, "recording": rec}

    def close(self) -> None:
        self.stop_recording()
        if self.cap:
            try:
                self.cap.release()
            finally:
                self.cap = None
        logger.info(f"Camera {self.device_id}: closed")
