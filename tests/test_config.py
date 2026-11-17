"""Config invariants."""

from __future__ import annotations

import unittest

from speedmeter.config import DEFAULT_REQUEST_COUNT, MeasurementConfig
from speedmeter.errors import ConfigError


class MeasurementConfigTest(unittest.TestCase):
    def test_defaults_match_the_assignment(self) -> None:
        config = MeasurementConfig(url="https://example.com/image.jpg")

        self.assertEqual(config.request_count, 10)
        self.assertEqual(DEFAULT_REQUEST_COUNT, 10)
        self.assertFalse(config.allow_plaintext_http)
        self.assertIsNone(config.ca_bundle)

    def test_is_immutable(self) -> None:
        config = MeasurementConfig(url="https://example.com/image.jpg")

        with self.assertRaises(AttributeError):
            config.request_count = 1  # type: ignore[misc]

    def test_rejects_empty_url(self) -> None:
        with self.assertRaises(ConfigError):
            MeasurementConfig(url="   ")

    def test_rejects_non_positive_numbers(self) -> None:
        cases = {
            "request_count": 0,
            "timeout": 0.0,
            "chunk_size": -1,
            "max_bytes": 0,
        }
        for field, value in cases.items():
            with self.subTest(field=field):
                with self.assertRaises(ConfigError) as caught:
                    MeasurementConfig(url="https://example.com", **{field: value})
                self.assertIn(field, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
