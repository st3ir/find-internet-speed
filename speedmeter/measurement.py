"""The measurement loop itself."""

from __future__ import annotations

import time
from collections.abc import Callable

from .config import MeasurementConfig
from .models import MeasurementReport, RequestSample
from .transport import Transport

#: Clock used for timing; injectable so tests do not have to sleep.
Clock = Callable[[], float]

#: Called after every completed request with its 1-based index and sample.
#: Keeps progress reporting (an I/O concern) out of the measurement loop.
ProgressListener = Callable[[int, RequestSample], None]


def ignore_progress(index: int, sample: RequestSample) -> None:
    """Default listener: do nothing."""


class SpeedMeter:
    """Performs ``config.request_count`` sequential downloads and times them.

    Depends on the :class:`~speedmeter.transport.Transport` protocol, so it
    knows nothing about sockets, TLS or urllib.
    """

    def __init__(
        self,
        transport: Transport,
        config: MeasurementConfig,
        clock: Clock = time.perf_counter,
    ) -> None:
        self._transport = transport
        self._config = config
        self._clock = clock

    def measure(self, listener: ProgressListener = ignore_progress) -> MeasurementReport:
        samples = []
        for index in range(1, self._config.request_count + 1):
            sample = self._measure_once()
            samples.append(sample)
            listener(index, sample)
        return MeasurementReport(url=self._config.url, samples=tuple(samples))

    def _measure_once(self) -> RequestSample:
        """One request, fully drained before the clock is stopped."""
        downloaded = 0
        started_at = self._clock()
        for chunk in self._transport.stream(
            self._config.url,
            timeout=self._config.timeout,
            chunk_size=self._config.chunk_size,
        ):
            downloaded += len(chunk)
        return RequestSample(
            bytes_downloaded=downloaded, duration=self._clock() - started_at
        )
