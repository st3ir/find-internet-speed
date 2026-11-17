"""Human-readable rendering of raw numbers.

One scaling helper, several thin wrappers over it -- adding a unit family is a
one-liner instead of another copy of the loop.
"""

from __future__ import annotations

BINARY_STEP = 1024
BINARY_UNITS = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")

DECIMAL_STEP = 1000
BIT_RATE_UNITS = ("bit/s", "kbit/s", "Mbit/s", "Gbit/s", "Tbit/s")


def scale(value: float, units: tuple[str, ...], step: int) -> tuple[float, str]:
    """Reduce ``value`` into the largest unit that keeps it >= 1."""
    magnitude = abs(value)
    for unit in units[:-1]:
        if magnitude < step:
            return value, unit
        value /= step
        magnitude /= step
    return value, units[-1]


def _format_scaled(value: float, units: tuple[str, ...], step: int) -> str:
    scaled, unit = scale(value, units, step)
    precision = 0 if unit == units[0] else 2
    return f"{scaled:.{precision}f} {unit}"


def format_size(num_bytes: float) -> str:
    """``52428800`` -> ``'50.00 MiB'``."""
    return _format_scaled(num_bytes, BINARY_UNITS, BINARY_STEP)


def format_byte_rate(bytes_per_second: float) -> str:
    """``5242880`` -> ``'5.00 MiB/s'``."""
    return f"{_format_scaled(bytes_per_second, BINARY_UNITS, BINARY_STEP)}/s"


def format_bit_rate(bits_per_second: float) -> str:
    """``41943040`` -> ``'41.94 Mbit/s'``."""
    return _format_scaled(bits_per_second, BIT_RATE_UNITS, DECIMAL_STEP)


def format_duration(seconds: float) -> str:
    """Sub-second values in milliseconds, anything longer in seconds."""
    if seconds < 1:
        return f"{seconds * 1000:.0f} ms"
    return f"{seconds:.2f} s"
