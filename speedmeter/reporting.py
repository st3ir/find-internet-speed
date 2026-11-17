"""Rendering of a :class:`~speedmeter.models.MeasurementReport`.

Renderers are interchangeable implementations of :class:`ReportRenderer`, so a
new output format is a new class here and nothing else changes.
"""

from __future__ import annotations

import json
from typing import Protocol

from .formatting import (
    DECIMAL_STEP,
    format_bit_rate,
    format_byte_rate,
    format_duration,
    format_size,
)
from .models import MeasurementReport, RequestSample

_LABEL_WIDTH = 21


class ReportRenderer(Protocol):
    """Turns a report into text ready to be printed."""

    def render(self, report: MeasurementReport) -> str: ...


class TextReportRenderer:
    """Aligned key/value block for a human reader."""

    def render(self, report: MeasurementReport) -> str:
        rows = (
            ("URL", report.url),
            ("Requests", str(report.request_count)),
            (
                "Total downloaded",
                f"{format_size(report.total_bytes)} ({report.total_bytes} bytes)",
            ),
            ("Total request time", format_duration(report.total_duration)),
            ("Average per request", format_duration(report.average_duration)),
            (
                "Fastest / slowest",
                f"{format_duration(report.fastest_duration)} / "
                f"{format_duration(report.slowest_duration)}",
            ),
            (
                "Download speed",
                f"{format_bit_rate(report.speed_bits_per_second)} "
                f"({format_byte_rate(report.speed_bytes_per_second)})",
            ),
        )
        return "\n".join(f"{label:<{_LABEL_WIDTH}}{value}" for label, value in rows)


class JsonReportRenderer:
    """Machine-readable output; unit is part of every key name."""

    def __init__(self, indent: int | None = 2) -> None:
        self._indent = indent

    def render(self, report: MeasurementReport) -> str:
        megabits = DECIMAL_STEP**2
        mebibytes = 1024**2
        payload = {
            "url": report.url,
            "requests": report.request_count,
            "total_bytes": report.total_bytes,
            "total_seconds": report.total_duration,
            "average_seconds": report.average_duration,
            "average_bytes": report.average_bytes,
            "fastest_seconds": report.fastest_duration,
            "slowest_seconds": report.slowest_duration,
            "speed_mbit_per_second": report.speed_bits_per_second / megabits,
            "speed_mib_per_second": report.speed_bytes_per_second / mebibytes,
            "samples": [
                {"bytes": sample.bytes_downloaded, "seconds": sample.duration}
                for sample in report.samples
            ],
        }
        return json.dumps(payload, indent=self._indent, ensure_ascii=False)


def format_progress(index: int, total: int, sample: RequestSample) -> str:
    """One line of live progress, e.g. ``[ 3/10] 5.00 MiB in 842 ms -> 49.8 Mbit/s``."""
    width = len(str(total))
    return (
        f"[{index:>{width}}/{total}] "
        f"{format_size(sample.bytes_downloaded)} in {format_duration(sample.duration)}"
        f" -> {format_bit_rate(sample.speed_bits_per_second)}"
    )
