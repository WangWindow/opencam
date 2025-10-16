from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MAX_DEVICES = 10
DEFAULT_MASK: set[int] = {0}


@dataclass
class ArgsResult:
    exit_code: int | None
    max_devices: int
    mask: set[int]


class ArgsParser:
    """Parse command line flags controlling device count and masking."""

    def __init__(
        self,
        default_max_devices: int = DEFAULT_MAX_DEVICES,
        default_mask: set[int] | None = DEFAULT_MASK,
    ) -> None:
        self.default_max_devices: int = default_max_devices
        self.default_mask: set[int] = set(default_mask or set())

    def parse(self, argv: list[str]) -> ArgsResult:
        """Interpret ``argv`` and return the desired runtime configuration."""

        args = list(argv[1:] if len(argv) > 0 else [])
        max_devices = self.default_max_devices
        mask = set(self.default_mask)
        positional_consumed = False

        args_iter = iter(args)
        for token in args_iter:
            if token in {"-h", "--help"}:
                self._print_usage()
                return ArgsResult(exit_code=0, max_devices=max_devices, mask=mask)
            if token in {"-m", "--max-devices"}:
                try:
                    value = next(args_iter)
                except StopIteration:
                    print("Missing value for --max-devices")
                    return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)
                parsed = self._parse_positive_int(value, "max-devices")
                if parsed is None:
                    return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)
                max_devices = parsed
                continue
            if token in {"-k", "--mask"}:
                try:
                    value = next(args_iter)
                except StopIteration:
                    print("Missing value for --mask")
                    return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)
                parsed_mask = self._parse_mask(value)
                if parsed_mask is None:
                    return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)
                mask = parsed_mask
                continue
            if token.startswith("-"):
                print(f"Unknown option: {token}")
                self._print_usage()
                return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)

            if positional_consumed:
                print("Unexpected positional argument:", token)
                self._print_usage()
                return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)

            parsed = self._parse_positive_int(token, "max-devices")
            if parsed is None:
                return ArgsResult(exit_code=1, max_devices=max_devices, mask=mask)
            max_devices = parsed
            positional_consumed = True

        return ArgsResult(exit_code=None, max_devices=max_devices, mask=mask)

    def _parse_positive_int(
        self, value: str, label: str, *, allow_zero: bool = False
    ) -> int | None:
        try:
            parsed = int(value)
        except ValueError:
            print(f"{label} must be an integer")
            return None
        if parsed < 0 or (parsed == 0 and not allow_zero):
            comparison = (
                "greater than or equal to 0" if allow_zero else "greater than 0"
            )
            print(f"{label} must be {comparison}")
            return None
        return parsed

    def _parse_mask(self, value: str) -> set[int] | None:
        parts = [segment.strip() for segment in value.split(",") if segment.strip()]
        if not parts:
            return set()

        mask: set[int] = set()
        for part in parts:
            parsed = self._parse_positive_int(part, "mask", allow_zero=True)
            if parsed is None:
                return None
            mask.add(parsed)
        return mask

    def _print_usage(self) -> None:
        print("Usage: python main.py [max_devices] [--max-devices N] [--mask 1,2,3]")
