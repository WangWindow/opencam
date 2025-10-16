from __future__ import annotations

import math
from typing import cast

import cv2
import numpy as np
from numpy.typing import NDArray

Frame = NDArray[np.uint8]


class Shower:
    """
    Compose tiled camera previews and handle on-screen overlays.
    """

    def __init__(
        self,
        window_title: str = "Multi-Camera",
        tile_size: tuple[int, int] = (640, 480),
    ) -> None:
        self.window_title: str = window_title
        self.tile_size: tuple[int, int] = tile_size

    def grid_shape(self, count: int) -> tuple[int, int]:
        cols = max(1, math.ceil(math.sqrt(count)))
        rows = math.ceil(count / cols)
        return rows, cols

    def compose(
        self,
        camera_ids: list[int],
        frames: dict[int, Frame | None],
        rows: int,
        cols: int,
    ) -> Frame:
        """
        Build a tiled mosaic covering the provided camera IDs.
        """
        tile_w, tile_h = self.tile_size
        blank: Frame = np.zeros((tile_h, tile_w, 3), dtype=np.uint8)
        tiles: list[Frame] = []

        for index in camera_ids:
            frame = frames.get(index)
            if frame is None:
                tile = blank.copy()
            else:
                tile = cast(Frame, cv2.resize(frame, (tile_w, tile_h)))

            _ = cv2.putText(
                tile,
                f"Cam {index}",
                (10, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                1.0,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )
            tiles.append(tile)

        while len(tiles) < rows * cols:
            tiles.append(blank.copy())

        grid_rows: list[Frame] = []
        for row_index in range(rows):
            start = row_index * cols
            end = start + cols
            row_strip = np.hstack(tiles[start:end])
            grid_rows.append(row_strip)

        return np.vstack(grid_rows)

    def annotate_recording(self, composite: Frame) -> None:
        _ = cv2.circle(composite, (30, 30), 12, (0, 0, 255), -1)
        _ = cv2.putText(
            composite,
            "REC",
            (50, 35),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.0,
            (0, 0, 255),
            2,
            cv2.LINE_AA,
        )

    def show(self, composite: Frame) -> int:
        cv2.imshow(self.window_title, composite)
        return cv2.waitKey(1)

    def close(self) -> None:
        cv2.destroyAllWindows()
