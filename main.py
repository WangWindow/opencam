from __future__ import annotations

import sys

from args_parser import ArgsParser
from detector import Detector
from recorder import Recorder
from runner import DEFAULT_MAX_DEVICES, Runner
from shower import Shower


def main(argv: list[str]) -> int:
    parser = ArgsParser(default_max_devices=DEFAULT_MAX_DEVICES, default_mask={0})
    result = parser.parse(argv)
    if result.exit_code is not None:
        return result.exit_code

    runner = Runner(
        detecter=Detector(),
        recorder=Recorder(),
        shower=Shower(),
        default_max_devices=DEFAULT_MAX_DEVICES,
    )
    return runner.run(max_devices=result.max_devices, mask=result.mask)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
