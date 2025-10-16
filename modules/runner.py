from __future__ import annotations

import math
import threading
import time
from typing import cast

import cv2

from .detector import Detector
from .recorder import Frame, Recorder
from .shower import Shower
from .task import Task, TaskExecutionError, TaskManager

DEFAULT_MAX_DEVICES = 10


class Runner:
    """
    Coordinate capture threads, UI updates, and recording control.
    """

    def __init__(
        self,
        detector: Detector,
        recorder: Recorder,
        shower: Shower,
        default_max_devices: int = DEFAULT_MAX_DEVICES,
    ) -> None:
        self.detector: Detector = detector
        self.recorder: Recorder = recorder
        self.shower: Shower = shower
        self.default_max_devices: int = default_max_devices

    def run(self, max_devices: int | None = None, mask: set[int] | None = None) -> int:
        """
        Spin up workers and process UI events until shutdown.
        """
        backend = self.detector.choose_backend()
        effective_max_devices = (
            max_devices if max_devices is not None else self.default_max_devices
        )
        detected_ids, active_backend = self.detector.detect_cameras(
            effective_max_devices, backend
        )

        mask_set = mask or set()
        if mask_set:
            masked_found = sorted(set(detected_ids) & mask_set)
            if masked_found:
                print(f"Skipping masked cameras: {masked_found}")
        camera_ids = [idx for idx in detected_ids if idx not in mask_set]

        if not camera_ids:
            if detected_ids:
                print("No cameras available after applying mask.")
            else:
                print("No cameras detected. Increase max-devices or check connections.")
            return 1

        frames: dict[int, Frame | None] = {index: None for index in camera_ids}
        lock = threading.Lock()
        stop_event = threading.Event()
        tasks = [
            Task(
                target=self._camera_worker,
                args=(index, stop_event, frames, lock, active_backend),
                name=f"Camera-{index}",
            )
            for index in camera_ids
        ]
        manager = TaskManager(tasks)

        rows, cols = self.shower.grid_shape(len(camera_ids))
        context = self.recorder.recording_context

        try:
            manager.start_all()
            while not stop_event.is_set():
                with lock:
                    composite = self.shower.compose(camera_ids, frames, rows, cols)

                if context.flag.is_set():
                    self.shower.annotate_recording(composite)

                key = self.shower.show(composite)
                if self._process_keypress(key):
                    stop_event.set()
                    break
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            stop_event.set()
            if context.flag.is_set():
                self.recorder.stop_session()
            manager.join_all(timeout=1.5)
            try:
                manager.raise_failures()
            except TaskExecutionError as exc:
                print(exc)
            self.recorder.shutdown()
            self.shower.close()

        return 0

    def _camera_worker(
        self,
        index: int,
        stop_event: threading.Event,
        frames: dict[int, Frame | None],
        lock: threading.Lock,
        backend: int,
    ) -> None:
        capture = cv2.VideoCapture(index, backend)
        if not capture.isOpened():
            with lock:
                frames[index] = None
            return

        with lock:
            frames[index] = None

        fps = capture.get(cv2.CAP_PROP_FPS)
        if not fps or math.isclose(fps, 0.0):
            fps = self.recorder.default_fps

        try:
            while not stop_event.is_set():
                grabbed, frame = capture.read()
                if not grabbed:
                    time.sleep(0.05)
                    continue

                frame_array = cast(Frame, frame)
                with lock:
                    frames[index] = frame_array

                self.recorder.handle_frame(index, frame_array, fps)
        finally:
            capture.release()
            self.recorder.finalize_camera(index, "shutdown")

    def _process_keypress(self, key: int) -> bool:
        if key in (-1, 255):
            return False

        context_flag = self.recorder.recording_context.flag

        if key in (27, ord("q"), ord("Q")):
            if context_flag.is_set():
                self.recorder.stop_session()
            return True

        if key in (ord("r"), ord("R")):
            if context_flag.is_set():
                print("Recording already active.")
                return False
            session = time.strftime("%Y%m%d_%H%M%S")
            self.recorder.start_session(session)
            print(f"Recording started: session {session}")
            return False

        if key in (ord("s"), ord("S")):
            if context_flag.is_set():
                self.recorder.stop_session()
                print("Recording stopped.")
            else:
                print("Recording is not running.")
            return False

        return False
