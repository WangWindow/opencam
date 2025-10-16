from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ArgsResult:
    exit_code: int | None
    max_devices: int
    mask: set[int]


class ArgsParser:
    """
    Parse simple CLI arguments controlling device count and masking.
    """

    def __init__(
        self,
        default_max_devices: int,
        default_mask: set[int] | None = None,
    ) -> None:
        self.default_max_devices: int = default_max_devices
        self.default_mask: set[int] = set(default_mask or set())

    def parse(self, argv: list[str]) -> ArgsResult:
        """
        Interpret ``argv`` and return the desired runtime configuration.
        """
        if len(argv) > 2:
            print("Usage: python main.py [max_devices]")
            return ArgsResult(
                exit_code=1,
                max_devices=self.default_max_devices,
                mask=set(self.default_mask),
            )

        if len(argv) == 2:
            try:
                value = int(argv[1])
            except ValueError:
                print("max_devices must be an integer")
                return ArgsResult(
                    exit_code=1,
                    max_devices=self.default_max_devices,
                    mask=set(self.default_mask),
                )
            return ArgsResult(
                exit_code=None, max_devices=value, mask=set(self.default_mask)
            )

        return ArgsResult(
            exit_code=None,
            max_devices=self.default_max_devices,
            mask=set(self.default_mask),
        )
