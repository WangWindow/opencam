from __future__ import annotations

import argparse
from pathlib import Path

from logger import setup_logging, logger
from app import AppConfig
from ui_qt import run_qt


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Multi-camera recorder using OpenCV")
    p.add_argument("--width", type=int, default=1920, help="Frame width per camera")  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--height",
        type=int,
        default=1080,
        help="Frame height per camera (also used for preview aspect if no frame yet)",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument("--fps", type=float, default=30.0, help="Target FPS per camera")  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--backend",
        type=str,
        default="ANY",
        choices=["ANY", "MSMF", "DSHOW", "V4L2"],
        help="OpenCV backend",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--target-dir",
        type=Path,
        default=Path("outputs"),
        help="Directory to store recordings",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--output-type",
        type=str,
        default="mp4",
        choices=["mp4", "avi", "mkv"],
        help="Container/codec preset (default mp4)",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--max-devices",
        type=int,
        default=4,
        help="Max devices to scan if no mask provided",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--device-mask",
        type=str,
        default=None,
        help="Device id mask, e.g. '0,2-3' (overrides scanning)",
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--log-dir", type=Path, default=None, help="Optional directory to write logs"
    )  # pyright: ignore[reportUnusedCallResult]
    p.add_argument("--log-level", type=str, default="INFO", help="Logging level")  # pyright: ignore[reportUnusedCallResult]
    p.add_argument(
        "--status-log-interval-sec",
        type=float,
        default=0.0,
        help="Interval (seconds) for periodic camera status logs; 0 disables",
    )  # pyright: ignore[reportUnusedCallResult]
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    setup_logging(args.log_dir, args.log_level)  # pyright: ignore[reportAny]

    cfg = AppConfig(
        width=args.width,  # pyright: ignore[reportAny]
        height=args.height,  # pyright: ignore[reportAny]
        fps=args.fps,  # pyright: ignore[reportAny]
        backend=args.backend,  # pyright: ignore[reportAny]
        target_dir=args.target_dir,  # pyright: ignore[reportAny]
        output_type=args.output_type,  # pyright: ignore[reportAny]
        device_mask=args.device_mask,  # pyright: ignore[reportAny]
        max_devices=args.max_devices,  # pyright: ignore[reportAny]
        status_log_interval_sec=args.status_log_interval_sec,  # pyright: ignore[reportAny]
    )

    # 统一使用 Qt UI 运行，避免 OpenCV 窗口阻塞与按键轮询
    try:
        return run_qt(cfg)
    except Exception:
        logger.exception("Qt UI failed to start")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
