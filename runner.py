from __future__ import annotations

import math
import threading
import time
from typing import cast

import cv2

from detector import Detector
from recorder import Frame, Recorder
from shower import Shower

DEFAULT_MAX_DEVICES = 10


class Runner:
    def __init__(
        self,
        detecter: Detector,
        recorder: Recorder,
        shower: Shower,
        default_max_devices: int = DEFAULT_MAX_DEVICES,
    ) -> None:
        self.detecter: Detector = detecter
        self.recorder: Recorder = recorder
        self.shower: Shower = shower
        self.default_max_devices: int = default_max_devices

    def run(self, max_devices: int | None = None, mask: set[int] | None = None) -> int:
        backend = self.detecter.choose_backend()
        effective_max_devices = (
            max_devices if max_devices is not None else self.default_max_devices
        )
        detected_ids = self.detecter.detect_cameras(effective_max_devices, backend)

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

        workers = [
            threading.Thread(
                target=self._camera_worker,
                args=(index, stop_event, frames, lock, backend),
                name=f"Camera-{index}",
                daemon=True,
            )
            for index in camera_ids
        ]

        for worker in workers:
            worker.start()

        rows, cols = self.shower.grid_shape(len(camera_ids))
        context = self.recorder.recording_context

        try:
            while not stop_event.is_set():
                with lock:
                    composite = self.shower.compose(camera_ids, frames, rows, cols)

                if context.flag.is_set():
                    self.shower.annotate_recording(composite)

                key = self.shower.show(composite)
                if key in (27, ord("q"), ord("Q")):
                    if context.flag.is_set():
                        self.recorder.stop_session()
                    stop_event.set()
                    break
                if key in (ord("r"), ord("R")):
                    if not context.flag.is_set():
                        session = time.strftime("%Y%m%d_%H%M%S")
                        self.recorder.start_session(session)
                        print(f"Recording started: session {session}")
                    else:
                        print("Recording already active.")
                if key in (ord("s"), ord("S")):
                    if context.flag.is_set():
                        self.recorder.stop_session()
                        print("Recording stopped.")
                    else:
                        print("Recording is not running.")
        except KeyboardInterrupt:
            stop_event.set()
        finally:
            if context.flag.is_set():
                self.recorder.stop_session()
            for worker in workers:
                worker.join(timeout=1.0)
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
