"""Arithmetic over samples and reports."""

from __future__ import annotations

import unittest

from speedmeter.models import MeasurementReport, RequestSample


class RequestSampleTest(unittest.TestCase):
    def test_speed_is_bytes_over_seconds(self) -> None:
        sample = RequestSample(bytes_downloaded=2_000_000, duration=2.0)

        self.assertEqual(sample.speed_bytes_per_second, 1_000_000)
        self.assertEqual(sample.speed_bits_per_second, 8_000_000)

    def test_zero_duration_does_not_divide_by_zero(self) -> None:
        self.assertEqual(RequestSample(bytes_downloaded=10, duration=0.0).speed_bytes_per_second, 0.0)

    def test_rejects_negative_values(self) -> None:
        with self.assertRaises(ValueError):
            RequestSample(bytes_downloaded=-1, duration=1.0)
        with self.assertRaises(ValueError):
            RequestSample(bytes_downloaded=1, duration=-1.0)


class MeasurementReportTest(unittest.TestCase):
    def setUp(self) -> None:
        self.report = MeasurementReport(
            url="https://example.com/image.jpg",
            samples=(
                RequestSample(bytes_downloaded=1_000, duration=1.0),
                RequestSample(bytes_downloaded=1_000, duration=2.0),
                RequestSample(bytes_downloaded=1_000, duration=5.0),
            ),
        )

    def test_aggregates(self) -> None:
        self.assertEqual(self.report.request_count, 3)
        self.assertEqual(self.report.total_bytes, 3_000)
        self.assertEqual(self.report.total_duration, 8.0)
        self.assertEqual(self.report.average_bytes, 1_000)
        self.assertEqual(self.report.fastest_duration, 1.0)
        self.assertEqual(self.report.slowest_duration, 5.0)

    def test_average_duration(self) -> None:
        self.assertAlmostEqual(self.report.average_duration, 8.0 / 3)

    def test_speed_uses_total_volume_over_total_time(self) -> None:
        self.assertEqual(self.report.speed_bytes_per_second, 375.0)
        self.assertEqual(self.report.speed_bits_per_second, 3_000.0)

    def test_zero_total_duration_does_not_divide_by_zero(self) -> None:
        report = MeasurementReport(
            url="https://example.com",
            samples=(RequestSample(bytes_downloaded=10, duration=0.0),),
        )

        self.assertEqual(report.speed_bytes_per_second, 0.0)

    def test_needs_at_least_one_sample(self) -> None:
        with self.assertRaises(ValueError):
            MeasurementReport(url="https://example.com", samples=())


if __name__ == "__main__":
    unittest.main()
