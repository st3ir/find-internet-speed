"""Renderers."""

from __future__ import annotations

import json
import unittest

from speedmeter.models import MeasurementReport, RequestSample
from speedmeter.reporting import (
    JsonReportRenderer,
    TextReportRenderer,
    format_progress,
)

REPORT = MeasurementReport(
    url="https://example.com/image.jpg",
    samples=(
        RequestSample(bytes_downloaded=1_048_576, duration=0.5),
        RequestSample(bytes_downloaded=1_048_576, duration=1.5),
    ),
)


class TextReportRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.lines = TextReportRenderer().render(REPORT).splitlines()

    def test_shows_every_requested_figure(self) -> None:
        text = "\n".join(self.lines)

        self.assertIn("https://example.com/image.jpg", text)
        self.assertIn("Requests", text)
        self.assertIn("Average per request", text)
        self.assertIn("Download speed", text)

    def test_shows_volume_in_binary_units_and_raw_bytes(self) -> None:
        line = next(line for line in self.lines if line.startswith("Total downloaded"))

        self.assertIn("2.00 MiB", line)
        self.assertIn("2097152 bytes", line)

    def test_shows_speed_in_mbit_and_mib(self) -> None:
        line = next(line for line in self.lines if line.startswith("Download speed"))

        # 2 MiB over 2 s = 1 MiB/s = 8.389 Mbit/s
        self.assertIn("8.39 Mbit/s", line)
        self.assertIn("1.00 MiB/s", line)

    def test_average_request_time(self) -> None:
        line = next(line for line in self.lines if line.startswith("Average per request"))

        self.assertIn("1.00 s", line)


class JsonReportRendererTest(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(JsonReportRenderer().render(REPORT))

    def test_is_valid_json_with_documented_keys(self) -> None:
        self.assertEqual(self.payload["url"], "https://example.com/image.jpg")
        self.assertEqual(self.payload["requests"], 2)
        self.assertEqual(self.payload["total_bytes"], 2_097_152)
        self.assertEqual(self.payload["total_seconds"], 2.0)
        self.assertEqual(self.payload["average_seconds"], 1.0)
        self.assertAlmostEqual(self.payload["speed_mib_per_second"], 1.0)
        self.assertAlmostEqual(self.payload["speed_mbit_per_second"], 8.388608)

    def test_keeps_every_sample(self) -> None:
        self.assertEqual(
            self.payload["samples"],
            [
                {"bytes": 1_048_576, "seconds": 0.5},
                {"bytes": 1_048_576, "seconds": 1.5},
            ],
        )


class ProgressLineTest(unittest.TestCase):
    def test_is_aligned_and_complete(self) -> None:
        line = format_progress(3, 10, RequestSample(bytes_downloaded=1_048_576, duration=0.5))

        self.assertEqual(line, "[ 3/10] 1.00 MiB in 500 ms -> 16.78 Mbit/s")


if __name__ == "__main__":
    unittest.main()
