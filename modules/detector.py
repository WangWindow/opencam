from __future__ import annotations

import sys
from collections.abc import Iterable

import cv2


class Detector:
    """Probe camera indices while falling back across sensible backends."""

    def __init__(
        self,
        backend_preferences: Iterable[int] | None = None,
        failure_threshold: int | None = None,
    ) -> None:
        self._backend_preferences: tuple[int, ...] = (
            tuple(backend_preferences)
            if backend_preferences is not None
            else self._default_backends()
        )
        self._active_backend: int = self._backend_preferences[0]
        default_threshold = 1 if sys.platform == "win32" else 3
        self._failure_threshold: int = max(1, failure_threshold or default_threshold)

    def choose_backend(self) -> int:
        return self._backend_preferences[0]

    def active_backend(self) -> int:
        return self._active_backend

    def detect_cameras(self, max_devices: int, backend: int) -> tuple[list[int], int]:
        """Return detected indices and the backend that succeeded."""

        candidates = self._candidate_backends(backend)
        for candidate in candidates:
            available = self._probe_backend(candidate, max_devices)
            if available:
                if candidate != backend:
                    print(f"Switching backend to {self._backend_name(candidate)}")
                self._active_backend = candidate
                return available, candidate

        self._active_backend = candidates[-1]
        return [], self._active_backend

    def _probe_backend(self, backend: int, max_devices: int) -> list[int]:
        available: list[int] = []
        failures = 0
        for index in range(max_devices):
            capture = cv2.VideoCapture(index, backend)
            if capture.isOpened():
                available.append(index)
                failures = 0
            else:
                failures += 1
            capture.release()

            if failures >= self._failure_threshold and not available:
                break
        return available

    def _candidate_backends(self, backend: int) -> tuple[int, ...]:
        seen: set[int] = set()
        ordered: list[int] = []
        for candidate in (backend, *self._backend_preferences):
            if candidate in seen:
                continue
            ordered.append(candidate)
            seen.add(candidate)
        return tuple(ordered)

    def _default_backends(self) -> tuple[int, ...]:
        platform = sys.platform

        if platform == "win32":
            return (cv2.CAP_DSHOW, cv2.CAP_MSMF, cv2.CAP_ANY)

        if platform.startswith("linux"):
            return (cv2.CAP_V4L2, cv2.CAP_GSTREAMER, cv2.CAP_ANY)

        if platform == "darwin":
            return (cv2.CAP_AVFOUNDATION, cv2.CAP_ANY)

        return (cv2.CAP_ANY,)

    def _backend_name(self, backend: int) -> str:
        mapping = {
            cv2.CAP_DSHOW: "CAP_DSHOW",
            cv2.CAP_MSMF: "CAP_MSMF",
            cv2.CAP_ANY: "CAP_ANY",
            cv2.CAP_V4L2: "CAP_V4L2",
            cv2.CAP_GSTREAMER: "CAP_GSTREAMER",
            cv2.CAP_AVFOUNDATION: "CAP_AVFOUNDATION",
        }
        return mapping.get(backend, str(backend))
