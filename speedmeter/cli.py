"""Console interface: argument parsing, progress output, exit codes.

The only module that is allowed to touch ``sys.stdout``/``sys.stderr``.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import IO

from . import __version__
from .app import build_meter
from .config import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MAX_BYTES,
    DEFAULT_REQUEST_COUNT,
    DEFAULT_TIMEOUT_SECONDS,
    MeasurementConfig,
)
from .errors import SpeedMeterError
from .measurement import ProgressListener, SpeedMeter, ignore_progress
from .models import RequestSample
from .reporting import (
    JsonReportRenderer,
    ReportRenderer,
    TextReportRenderer,
    format_progress,
)

#: Injection point for tests: how a meter is obtained from a config.
MeterFactory = Callable[[MeasurementConfig], SpeedMeter]

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_INTERRUPTED = 130

_EPILOG = """\
units:
  speed    Mbit/s (10^6 bits per second) and, in brackets, MiB/s (2^20 bytes per second)
  volume   binary prefixes (1 KiB = 1024 B, 1 MiB = 1024 KiB) plus the exact byte count
  time     milliseconds below one second, otherwise seconds

Only https:// is accepted by default. Progress goes to stderr, the final
report to stdout, so `--json` output stays pipeable.
"""


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive integer, got {raw!r}")
    return value


def _positive_float(raw: str) -> float:
    value = float(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError(f"expected a positive number, got {raw!r}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="speedmeter",
        description=(
            "Download one URL several times in a row and report the average "
            "request time, the total volume and the download speed."
        ),
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="address to download, e.g. https://host/image.jpg")
    parser.add_argument(
        "-n",
        "--requests",
        type=_positive_int,
        default=DEFAULT_REQUEST_COUNT,
        metavar="N",
        help="number of sequential requests (default: %(default)s)",
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=_positive_float,
        default=DEFAULT_TIMEOUT_SECONDS,
        metavar="SECONDS",
        help="per-request timeout (default: %(default)s)",
    )
    parser.add_argument(
        "--chunk-size",
        type=_positive_int,
        default=DEFAULT_CHUNK_SIZE,
        metavar="BYTES",
        help="socket read size (default: %(default)s)",
    )
    parser.add_argument(
        "--max-bytes",
        type=_positive_int,
        default=DEFAULT_MAX_BYTES,
        metavar="BYTES",
        help="refuse a response larger than this (default: %(default)s)",
    )
    parser.add_argument(
        "--ca-bundle",
        metavar="PATH",
        help="PEM file with trust anchors (default: certifi or the system bundle)",
    )
    parser.add_argument(
        "--allow-plaintext-http",
        action="store_true",
        help="permit http:// as well (unencrypted; off by default)",
    )
    parser.add_argument(
        "--json", action="store_true", help="print the report as JSON instead of text"
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="do not print per-request progress"
    )
    parser.add_argument("--version", action="version", version=f"speedmeter {__version__}")
    return parser


@dataclass(frozen=True, slots=True)
class CliOptions:
    """Everything the command line asked for."""

    config: MeasurementConfig
    renderer: ReportRenderer
    show_progress: bool


def parse_args(argv: Sequence[str] | None = None) -> CliOptions:
    args = build_parser().parse_args(argv)
    config = MeasurementConfig(
        url=args.url,
        request_count=args.requests,
        timeout=args.timeout,
        chunk_size=args.chunk_size,
        max_bytes=args.max_bytes,
        allow_plaintext_http=args.allow_plaintext_http,
        ca_bundle=args.ca_bundle,
    )
    renderer = JsonReportRenderer() if args.json else TextReportRenderer()
    return CliOptions(config=config, renderer=renderer, show_progress=not args.quiet)


def _progress_listener(total: int, stream: IO[str]) -> ProgressListener:
    def listener(index: int, sample: RequestSample) -> None:
        print(format_progress(index, total, sample), file=stream, flush=True)

    return listener


def main(
    argv: Sequence[str] | None = None,
    *,
    meter_factory: MeterFactory = build_meter,
    stdout: IO[str] | None = None,
    stderr: IO[str] | None = None,
) -> int:
    """Run the measurement; return the process exit code."""
    out = stdout if stdout is not None else sys.stdout
    err = stderr if stderr is not None else sys.stderr

    options = parse_args(argv)
    listener = (
        _progress_listener(options.config.request_count, err)
        if options.show_progress
        else ignore_progress
    )

    try:
        report = meter_factory(options.config).measure(listener)
    except SpeedMeterError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_FAILURE
    except KeyboardInterrupt:
        print("interrupted", file=err)
        return EXIT_INTERRUPTED

    print(options.renderer.render(report), file=out)
    return EXIT_OK
