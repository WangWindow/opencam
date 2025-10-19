from __future__ import annotations

import cv2
from pathlib import Path
from dataclasses import dataclass
import time
import threading

from camera import CameraStream, backend_from_name
from logger import logger


def parse_device_mask(mask: str | None) -> list[int]:
    if not mask:
        return []
    ids: set[int] = set()
    parts = [p.strip() for p in mask.split(",") if p.strip()]
    for p in parts:
        if "-" in p:
            a, b = p.split("-", 1)
            try:
                start = int(a)
                end = int(b)
                if start <= end:
                    ids.update(range(start, end + 1))
                else:
                    ids.update(range(end, start + 1))
            except ValueError:
                continue
        else:
            try:
                ids.add(int(p))
            except ValueError:
                continue
    return sorted(ids)


def discover_devices(backend: str, max_devices: int, mask: str | None) -> list[int]:
    ids = parse_device_mask(mask)
    if ids:
        return ids
    # Fallback: scan from 0..max_devices-1
    found: list[int] = []
    backend_flag = backend_from_name(backend)
    for i in range(max(0, max_devices)):
        cap = cv2.VideoCapture(i, backend_flag)
        if cap and cap.isOpened():
            found.append(i)
            cap.release()
    return found


@dataclass
class AppConfig:
    width: int = 1920
    height: int = 1080
    fps: float = 30.0
    backend: str = "ANY"
    target_dir: Path = Path("outputs")
    output_type: str = "mp4"  # mp4/avi/mkv
    device_mask: str | None = None
    max_devices: int = 4
    # 摄像头状态周期日志间隔（秒）；0 表示禁用周期日志
    status_log_interval_sec: float = 0.0


class MultiCamApp:
    def __init__(self, cfg: AppConfig) -> None:
        self.cfg: AppConfig = cfg
        self.cams: list[CameraStream] = []
        self.recording_session_ts: str | None = None
        # UI 由上层 Qt 托管，这里不再维护自定义排布状态

    def setup(self) -> bool:
        ids = discover_devices(
            self.cfg.backend, self.cfg.max_devices, self.cfg.device_mask
        )
        if not ids:
            logger.error("No cameras found. Check device_mask or increase max_devices.")
            return False
        logger.info(f"Discovered cameras: {ids}")

        # 并行启动打开摄像头，避免慢设备阻塞整体启动
        open_threads: list[threading.Thread] = []
        for did in ids:
            cam = CameraStream(
                did,
                self.cfg.backend,
                self.cfg.width,
                self.cfg.height,
                self.cfg.fps,
                self.cfg.status_log_interval_sec,
            )
            # 先加入列表，未打开前会显示占位
            self.cams.append(cam)
            t = threading.Thread(target=cam.open, name=f"OpenCam-{did}", daemon=True)
            t.start()
            open_threads.append(t)

        logger.info(
            f"Launching {len(open_threads)} camera(s) in background... UI will appear immediately; slow devices will show when ready."
        )
        # 不再在此创建任何 OpenCV 窗口；UI 由上层框架（如 Qt）托管
        return True

    def _make_session_dir(self) -> Path:
        ts = time.strftime("%Y%m%d_%H%M%S")
        self.recording_session_ts = ts
        p = self.cfg.target_dir / ts
        p.mkdir(parents=True, exist_ok=True)
        return p

    def start_recording_all(self) -> None:
        session_dir = self._make_session_dir()
        for cam in self.cams:
            base_name = f"cam{cam.device_id}_{self.recording_session_ts}"
            cam.start_recording(session_dir / base_name, self.cfg.output_type)

    def stop_recording_all(self) -> None:
        for cam in self.cams:
            cam.stop_recording()
