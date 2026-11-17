"""Command line: parsing, output routing, exit codes."""

from __future__ import annotations

import contextlib
import io
import json
import unittest

from speedmeter.cli import EXIT_FAILURE, EXIT_INTERRUPTED, EXIT_OK, main, parse_args
from speedmeter.config import MeasurementConfig
from speedmeter.errors import DownloadError, InsecureUrlError
from speedmeter.measurement import ProgressListener, ignore_progress
from speedmeter.models import MeasurementReport, RequestSample
from speedmeter.reporting import JsonReportRenderer, TextReportRenderer

URL = "https://example.com/image.jpg"

REPORT = MeasurementReport(
    url=URL,
    samples=(
        RequestSample(bytes_downloaded=1_048_576, duration=0.5),
        RequestSample(bytes_downloaded=1_048_576, duration=1.5),
    ),
)


class StubMeter:
    """Replays a canned report (and the progress callbacks that go with it)."""

    def __init__(self, report: MeasurementReport = REPORT, error: Exception | None = None) -> None:
        self._report = report
        self._error = error

    def measure(self, listener: ProgressListener = ignore_progress) -> MeasurementReport:
        if self._error is not None:
            raise self._error
        for index, sample in enumerate(self._report.samples, start=1):
            listener(index, sample)
        return self._report


def run(argv: list[str], meter: StubMeter | None = None) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(
        argv,
        meter_factory=lambda config: meter or StubMeter(),
        stdout=out,
        stderr=err,
    )
    return code, out.getvalue(), err.getvalue()


@contextlib.contextmanager
def _silenced():
    """Keep argparse usage errors out of the test output."""
    with contextlib.redirect_stderr(io.StringIO()):
        yield


class ParseArgsTest(unittest.TestCase):
    def test_builds_a_config_from_the_defaults(self) -> None:
        options = parse_args([URL])

        self.assertEqual(
            options.config,
            MeasurementConfig(url=URL),
        )
        self.assertIsInstance(options.renderer, TextReportRenderer)
        self.assertTrue(options.show_progress)

    def test_every_flag_reaches_the_config(self) -> None:
        options = parse_args(
            [
                URL,
                "-n", "3",
                "-t", "2.5",
                "--chunk-size", "4096",
                "--max-bytes", "123456",
                "--allow-plaintext-http",
                "--ca-bundle", "/tmp/ca.pem",
                "--json",
                "--quiet",
            ]
        )

        self.assertEqual(
            options.config,
            MeasurementConfig(
                url=URL,
                request_count=3,
                timeout=2.5,
                chunk_size=4096,
                max_bytes=123_456,
                allow_plaintext_http=True,
                ca_bundle="/tmp/ca.pem",
            ),
        )
        self.assertIsInstance(options.renderer, JsonReportRenderer)
        self.assertFalse(options.show_progress)

    def test_rejects_a_non_positive_request_count(self) -> None:
        for argv in ([URL, "-n", "0"], [URL, "-n", "-5"], [URL, "-t", "0"]):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit) as caught, _silenced():
                    parse_args(argv)
                self.assertEqual(caught.exception.code, 2)

    def test_url_is_required(self) -> None:
        with self.assertRaises(SystemExit), _silenced():
            parse_args([])


class MainTest(unittest.TestCase):
    def test_prints_the_report_to_stdout_and_succeeds(self) -> None:
        code, out, _ = run([URL])

        self.assertEqual(code, EXIT_OK)
        self.assertIn("Download speed", out)
        self.assertIn("8.39 Mbit/s", out)

    def test_progress_goes_to_stderr_so_stdout_stays_pipeable(self) -> None:
        _, out, err = run([URL, "--json", "-n", "2"])

        self.assertEqual(json.loads(out)["requests"], 2)
        self.assertIn("[1/2]", err)
        self.assertIn("[2/2]", err)

    def test_quiet_suppresses_progress(self) -> None:
        _, out, err = run([URL, "--quiet"])

        self.assertEqual(err, "")
        self.assertIn("Download speed", out)

    def test_an_insecure_url_fails_with_a_message_and_no_report(self) -> None:
        code, out, err = run([URL], StubMeter(error=InsecureUrlError("nope")))

        self.assertEqual(code, EXIT_FAILURE)
        self.assertEqual(out, "")
        self.assertIn("error: nope", err)

    def test_a_network_failure_fails_cleanly(self) -> None:
        code, _, err = run([URL], StubMeter(error=DownloadError("host is down")))

        self.assertEqual(code, EXIT_FAILURE)
        self.assertIn("error: host is down", err)

    def test_ctrl_c_is_not_a_traceback(self) -> None:
        code, _, err = run([URL], StubMeter(error=KeyboardInterrupt()))

        self.assertEqual(code, EXIT_INTERRUPTED)
        self.assertIn("interrupted", err)

    def test_unexpected_errors_are_not_swallowed(self) -> None:
        with self.assertRaises(RuntimeError):
            run([URL], StubMeter(error=RuntimeError("bug")))


if __name__ == "__main__":
    unittest.main()
