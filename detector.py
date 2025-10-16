from __future__ import annotations

import os

import cv2


class Detector:
    def choose_backend(self) -> int:
        if os.name == "nt":
            return cv2.CAP_DSHOW
        return cv2.CAP_ANY

    def detect_cameras(self, max_devices: int, backend: int) -> list[int]:
        available: list[int] = []
        for index in range(max_devices):
            capture = cv2.VideoCapture(index, backend)
            if capture.isOpened():
                available.append(index)
            capture.release()
        return available
