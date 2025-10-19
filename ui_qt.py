"""
Qt UI for OpenCamV with a scrollable, auto-column grid layout.
"""

from __future__ import annotations

import sys
from typing import override, cast

import cv2
import numpy as np
from numpy.typing import NDArray
from PySide6 import QtCore, QtGui, QtWidgets
from app import MultiCamApp, AppConfig
from camera import CameraStream
from logger import logger


def np_bgr_to_qimage(img: NDArray[np.uint8] | None) -> QtGui.QImage:
    """Convert BGR uint8 image (H, W, 3) to QImage (RGB)."""
    if img is None or img.size == 0:
        return QtGui.QImage()
    h, w, ch = img.shape
    assert ch == 3
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    bytes_per_line = ch * w
    return QtGui.QImage(
        rgb.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888
    )


class VideoWidget(QtWidgets.QLabel):
    """A QLabel-based widget to show frames efficiently."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding,
            QtWidgets.QSizePolicy.Policy.Expanding,
        )
        self.setMinimumSize(320, 180)
        self.setStyleSheet("background-color: #000;")

    def show_frame(self, frame: NDArray[np.uint8] | None) -> None:
        if frame is None:
            self.clear()
            return
        img = np_bgr_to_qimage(frame)
        pix = QtGui.QPixmap.fromImage(img)
        # Scale to fit, keep aspect ratio, smooth
        pix = pix.scaled(
            self.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatio,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(pix)

    @override
    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        # 保持简单；由定时器驱动的刷新会更新视图
        super().resizeEvent(e)


class CameraTile(QtWidgets.QWidget):
    """A camera tile with a title and a video view."""

    def __init__(
        self, cam: CameraStream, parent: QtWidgets.QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.cam: CameraStream = cam
        self.title: QtWidgets.QLabel = QtWidgets.QLabel(f"Camera {cam.device_id}")
        self.title.setStyleSheet("color: #ddd; padding: 4px;")
        # status label for resolution / fps / rec indicator
        self.status: QtWidgets.QLabel = QtWidgets.QLabel("—")
        self.status.setStyleSheet(
            "color: #aaa; padding: 0 4px 4px 4px; font-size: 12px;"
        )
        self.video: VideoWidget = VideoWidget()
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(6)
        lay.addWidget(self.title)
        lay.addWidget(self.status)
        lay.addWidget(self.video, 1)
        self.setMinimumWidth(320)
        self._last_seq: int = -1

    # FPS 不在 Qt 计算，Qt 仅显示 camera.get_status() 提供的数据

    def refresh(self) -> None:
        seq, frame = self.cam.get_latest_frame_with_seq()
        # 仅在出现新帧时才进行渲染与缩放，降低 CPU/GPU 压力
        if frame is not None and seq != self._last_seq:
            self._last_seq = seq
            self.video.show_frame(frame)
        # 从相机层获取状态（fps/size/recording）
        st = self.cam.get_status()
        # fps
        _fps_val = st.get("fps", 0.0)
        try:
            fps = (
                float(_fps_val)
                if isinstance(_fps_val, (int, float))
                else float(str(_fps_val))
            )
        except Exception:
            fps = 0.0
        # size
        _size_obj = st.get("size")
        w: int | None = None
        h: int | None = None
        if isinstance(_size_obj, tuple):
            tup = cast(tuple[object, ...], _size_obj)
            if len(tup) == 2 and isinstance(tup[0], int) and isinstance(tup[1], int):
                w = tup[0]
                h = tup[1]
        size_text = f"{w}x{h}" if (w is not None and h is not None) else "—"
        rec = bool(st.get("recording", False))
        parts = [size_text]
        if rec:
            parts.append(f"{fps:.1f} FPS")
        else:
            parts.append("— FPS")
        if rec:
            parts.append("REC")
        self.status.setText("  |  ".join(parts))
        if rec:
            self.status.setStyleSheet(
                "color: #e55; padding: 0 4px 4px 4px; font-weight: 600; font-size: 12px;"
            )
        else:
            self.status.setStyleSheet(
                "color: #aaa; padding: 0 4px 4px 4px; font-size: 12px;"
            )


class QtMultiCamApp(QtWidgets.QMainWindow):
    """Qt window with a scrollable grid of camera tiles. Columns auto-fit by width."""

    def __init__(self, core_app: MultiCamApp) -> None:
        super().__init__()
        self.core: MultiCamApp = core_app
        self.setWindowTitle("OpenCamV - MultiCam")
        self.resize(1200, 800)

        # Scroll area with container and grid layout
        self.scrollArea: QtWidgets.QScrollArea = QtWidgets.QScrollArea(self)
        self.scrollArea.setWidgetResizable(True)
        container: QtWidgets.QWidget = QtWidgets.QWidget()
        self.gridLayout: QtWidgets.QGridLayout = QtWidgets.QGridLayout(container)
        self.gridLayout.setContentsMargins(8, 8, 8, 8)
        self.gridLayout.setHorizontalSpacing(8)
        self.gridLayout.setVerticalSpacing(8)
        self.scrollArea.setWidget(container)
        self.setCentralWidget(self.scrollArea)
        # Create tiles for each camera
        self.tiles: list[CameraTile] = [CameraTile(cam, self) for cam in self.core.cams]
        self.card_min_w: int = 380
        self._relayout()

        # Timer to refresh frames
        self.timer: QtCore.QTimer = QtCore.QTimer(self)
        self.timer.setInterval(16)  # ~60 FPS
        _ = self.timer.timeout.connect(self._on_tick)  # type: ignore[arg-type]
        self.timer.start()

        # Shortcuts
        self._shortcut_r: QtGui.QShortcut = QtGui.QShortcut(
            QtGui.QKeySequence("R"), self
        )
        _ = self._shortcut_r.activated.connect(self._start_rec)  # type: ignore[arg-type]
        self._shortcut_s: QtGui.QShortcut = QtGui.QShortcut(
            QtGui.QKeySequence("S"), self
        )
        _ = self._shortcut_s.activated.connect(self._stop_rec)  # type: ignore[arg-type]
        self._shortcut_q: QtGui.QShortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Q"), self
        )
        _ = self._shortcut_q.activated.connect(self.close)  # type: ignore[arg-type]
        self._shortcut_esc: QtGui.QShortcut = QtGui.QShortcut(
            QtGui.QKeySequence("Esc"), self
        )
        _ = self._shortcut_esc.activated.connect(self.close)  # type: ignore[arg-type]

    def _on_tick(self) -> None:
        try:
            for t in self.tiles:
                t.refresh()
        except Exception as e:
            logger.exception(f"UI tick failed: {e}")

    def _start_rec(self) -> None:
        self.core.start_recording_all()

    def _stop_rec(self) -> None:
        self.core.stop_recording_all()

    def _relayout(self) -> None:
        # Clear grid
        while self.gridLayout.count():
            item = self.gridLayout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)
        # Compute columns by available width
        avail_w = self.scrollArea.viewport().width()
        cols = max(1, avail_w // self.card_min_w) if self.card_min_w > 0 else 1
        for i, tile in enumerate(self.tiles):
            r = i // cols
            c = i % cols
            self.gridLayout.addWidget(tile, r, c)

    @override
    def resizeEvent(self, e: QtGui.QResizeEvent) -> None:
        super().resizeEvent(e)
        self._relayout()

    @override
    def closeEvent(self, event: QtGui.QCloseEvent) -> None:
        try:
            self.timer.stop()
            self.core.stop_recording_all()
            for cam in self.core.cams:
                cam.close()
        finally:
            super().closeEvent(event)


def run_qt(cfg: AppConfig) -> int:
    core = MultiCamApp(cfg)
    if not core.setup():
        return 2
    app = QtWidgets.QApplication(sys.argv[:1])
    win = QtMultiCamApp(core)
    win.show()
    return app.exec()


if __name__ == "__main__":
    # Fallback run if executed directly
    default_cfg = AppConfig()
    raise SystemExit(run_qt(default_cfg))
