"""Measurement results and the arithmetic over them.

Pure data + derived values: no I/O, no formatting, so the maths can be tested
on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

BITS_PER_BYTE = 8


@dataclass(frozen=True, slots=True)
class RequestSample:
    """One completed request: how much arrived and how long it took."""

    bytes_downloaded: int
    duration: float
    """Wall-clock seconds from "about to connect" to "body fully read"."""

    def __post_init__(self) -> None:
        if self.bytes_downloaded < 0:
            raise ValueError("bytes_downloaded must not be negative")
        if self.duration < 0:
            raise ValueError("duration must not be negative")

    @property
    def speed_bytes_per_second(self) -> float:
        return self.bytes_downloaded / self.duration if self.duration > 0 else 0.0

    @property
    def speed_bits_per_second(self) -> float:
        return self.speed_bytes_per_second * BITS_PER_BYTE


@dataclass(frozen=True, slots=True)
class MeasurementReport:
    """Aggregate of all samples of a single run."""

    url: str
    samples: tuple[RequestSample, ...]

    def __post_init__(self) -> None:
        if not self.samples:
            raise ValueError("a report needs at least one sample")

    @property
    def request_count(self) -> int:
        return len(self.samples)

    @property
    def total_bytes(self) -> int:
        return sum(sample.bytes_downloaded for sample in self.samples)

    @property
    def total_duration(self) -> float:
        """Total time spent on requests (the sum of the samples)."""
        return sum(sample.duration for sample in self.samples)

    @property
    def average_duration(self) -> float:
        return self.total_duration / self.request_count

    @property
    def average_bytes(self) -> float:
        return self.total_bytes / self.request_count

    @property
    def fastest_duration(self) -> float:
        return min(sample.duration for sample in self.samples)

    @property
    def slowest_duration(self) -> float:
        return max(sample.duration for sample in self.samples)

    @property
    def speed_bytes_per_second(self) -> float:
        """Throughput of the run: all bytes divided by all the time they took."""
        return self.total_bytes / self.total_duration if self.total_duration > 0 else 0.0

    @property
    def speed_bits_per_second(self) -> float:
        return self.speed_bytes_per_second * BITS_PER_BYTE
