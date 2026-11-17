"""The measurement loop, with a stub transport and a fake clock."""

from __future__ import annotations

import unittest
from collections.abc import Iterator

from speedmeter.config import MeasurementConfig
from speedmeter.errors import DownloadError
from speedmeter.measurement import SpeedMeter
from speedmeter.models import RequestSample

URL = "https://example.com/image.jpg"


class FakeTransport:
    """Returns a fixed body and remembers how it was called."""

    def __init__(self, body: bytes = b"x" * 1000, error: Exception | None = None) -> None:
        self._body = body
        self._error = error
        self.calls: list[tuple[str, float, int]] = []

    def stream(self, url: str, *, timeout: float, chunk_size: int) -> Iterator[bytes]:
        self.calls.append((url, timeout, chunk_size))
        if self._error is not None:
            raise self._error
        for start in range(0, len(self._body), chunk_size):
            yield self._body[start : start + chunk_size]


class FakeClock:
    """Returns pre-programmed timestamps, one per call."""

    def __init__(self, ticks: list[float]) -> None:
        self._ticks = list(ticks)

    def __call__(self) -> float:
        if not self._ticks:
            raise AssertionError("clock called more often than expected")
        return self._ticks.pop(0)


def constant_clock(step: float) -> FakeClock:
    """Timestamps that make every request take exactly ``step`` seconds."""
    ticks: list[float] = []
    now = 0.0
    for _ in range(1000):
        ticks += [now, now + step]
        now += step
    return FakeClock(ticks)


class SpeedMeterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.config = MeasurementConfig(url=URL, timeout=7.0, chunk_size=256)

    def test_performs_exactly_ten_requests_by_default(self) -> None:
        transport = FakeTransport()
        meter = SpeedMeter(transport, self.config, clock=constant_clock(0.5))

        report = meter.measure()

        self.assertEqual(len(transport.calls), 10)
        self.assertEqual(report.request_count, 10)

    def test_counts_every_byte_of_every_response(self) -> None:
        transport = FakeTransport(body=b"x" * 1500)
        meter = SpeedMeter(transport, self.config, clock=constant_clock(0.5))

        report = meter.measure()

        self.assertEqual(report.total_bytes, 15_000)
        self.assertEqual({s.bytes_downloaded for s in report.samples}, {1500})

    def test_reports_average_time_and_speed(self) -> None:
        transport = FakeTransport(body=b"x" * 1000)
        meter = SpeedMeter(transport, self.config, clock=constant_clock(0.5))

        report = meter.measure()

        self.assertEqual(report.average_duration, 0.5)
        self.assertEqual(report.total_duration, 5.0)
        self.assertEqual(report.speed_bytes_per_second, 2000.0)  # 10 KB / 5 s

    def test_measures_each_request_separately(self) -> None:
        transport = FakeTransport()
        config = MeasurementConfig(url=URL, request_count=3)
        # start/end pairs: 1 s, 2 s and 4 s
        meter = SpeedMeter(transport, config, clock=FakeClock([0, 1, 1, 3, 3, 7]))

        report = meter.measure()

        self.assertEqual([s.duration for s in report.samples], [1, 2, 4])
        self.assertEqual(report.fastest_duration, 1)
        self.assertEqual(report.slowest_duration, 4)

    def test_forwards_the_configured_request_parameters(self) -> None:
        transport = FakeTransport()
        config = MeasurementConfig(url=URL, request_count=2, timeout=7.0, chunk_size=256)
        meter = SpeedMeter(transport, config, clock=constant_clock(0.1))

        meter.measure()

        self.assertEqual(transport.calls, [(URL, 7.0, 256)] * 2)

    def test_notifies_the_listener_after_every_request(self) -> None:
        transport = FakeTransport()
        config = MeasurementConfig(url=URL, request_count=4)
        meter = SpeedMeter(transport, config, clock=constant_clock(0.25))
        seen: list[tuple[int, RequestSample]] = []

        report = meter.measure(lambda index, sample: seen.append((index, sample)))

        self.assertEqual([index for index, _ in seen], [1, 2, 3, 4])
        self.assertEqual([sample for _, sample in seen], list(report.samples))

    def test_report_keeps_the_measured_url(self) -> None:
        meter = SpeedMeter(FakeTransport(), self.config, clock=constant_clock(0.5))

        self.assertEqual(meter.measure().url, URL)

    def test_a_failing_request_aborts_the_run(self) -> None:
        transport = FakeTransport(error=DownloadError("boom"))
        meter = SpeedMeter(transport, self.config, clock=constant_clock(0.5))

        with self.assertRaises(DownloadError):
            meter.measure()

        self.assertEqual(len(transport.calls), 1)


if __name__ == "__main__":
    unittest.main()
