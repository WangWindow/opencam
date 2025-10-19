from __future__ import annotations

from loguru import logger
import sys
from pathlib import Path


def setup_logging(log_dir: str | Path | None = None, level: str = "INFO") -> None:
    """
    Configure loguru logger with console and optional file sink.

    - Console: colored, level from env/param.
    - File (optional): rotated daily and 50 MB, 10 backups.
    """
    logger.remove()
    logger.add(
        sys.stderr,
        level=level,
        colorize=True,
        format="<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )  # pyright: ignore[reportUnusedCallResult]

    if log_dir:
        p = Path(log_dir)
        p.mkdir(parents=True, exist_ok=True)
        logger.add(
            p / "opencamv.log",
            level=level,
            rotation="00:00",
            retention=10,
            enqueue=True,
            backtrace=False,
            diagnose=False,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {process} | {name}:{line} - {message}",
        )  # pyright: ignore[reportUnusedCallResult]


__all__ = ["logger", "setup_logging"]
