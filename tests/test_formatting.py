"""Unit scaling and human-readable output."""

from __future__ import annotations

import unittest

from speedmeter.formatting import (
    format_bit_rate,
    format_byte_rate,
    format_duration,
    format_size,
    scale,
)


class ScaleTest(unittest.TestCase):
    def test_keeps_small_values_in_the_base_unit(self) -> None:
        self.assertEqual(scale(999, ("B", "KiB"), 1024), (999, "B"))

    def test_steps_up_and_stops_at_the_largest_unit(self) -> None:
        value, unit = scale(5 * 1024**5, ("B", "KiB", "MiB"), 1024)

        self.assertEqual(unit, "MiB")
        self.assertAlmostEqual(value, 5 * 1024**3)


class FormatTest(unittest.TestCase):
    def test_format_size(self) -> None:
        self.assertEqual(format_size(512), "512 B")
        self.assertEqual(format_size(1024), "1.00 KiB")
        self.assertEqual(format_size(52_428_800), "50.00 MiB")

    def test_format_bit_rate_is_decimal(self) -> None:
        self.assertEqual(format_bit_rate(999), "999 bit/s")
        self.assertEqual(format_bit_rate(1_500_000), "1.50 Mbit/s")
        self.assertEqual(format_bit_rate(2_500_000_000), "2.50 Gbit/s")

    def test_format_byte_rate_is_binary(self) -> None:
        self.assertEqual(format_byte_rate(1024), "1.00 KiB/s")
        self.assertEqual(format_byte_rate(5 * 1024**2), "5.00 MiB/s")

    def test_format_duration_switches_unit_at_one_second(self) -> None:
        self.assertEqual(format_duration(0.8425), "842 ms")
        self.assertEqual(format_duration(1.0), "1.00 s")
        self.assertEqual(format_duration(12.345), "12.35 s")


if __name__ == "__main__":
    unittest.main()
