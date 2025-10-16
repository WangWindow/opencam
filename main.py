from __future__ import annotations

import sys

from modules import ArgsParser, Detector, Recorder, Runner, Shower


def main(argv: list[str]) -> int:
    """
    Entry point wiring concrete module implementations together.
    """
    result = ArgsParser().parse(argv)
    if result.exit_code is not None:
        return result.exit_code

    # Reuse the parsed device limit so batch runs can shrink or expand easily.
    runner = Runner(
        detector=Detector(),
        recorder=Recorder(),
        shower=Shower(),
        default_max_devices=result.max_devices,
    )
    return runner.run(mask=result.mask)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
