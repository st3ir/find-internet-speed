"""Sequential HTTP download-speed probe.

The package is split by responsibility:

* :mod:`speedmeter.security`    -- what we are allowed to connect to and how TLS is configured
* :mod:`speedmeter.transport`   -- how bytes are pulled off the wire
* :mod:`speedmeter.measurement` -- how the samples are collected
* :mod:`speedmeter.models`      -- what a sample/report is and the maths over it
* :mod:`speedmeter.reporting`   -- how a report is rendered
* :mod:`speedmeter.cli`         -- how a human talks to all of the above
"""

from __future__ import annotations

from .config import MeasurementConfig
from .errors import (
    ConfigError,
    DownloadError,
    InsecureUrlError,
    ResponseTooLargeError,
    SpeedMeterError,
)
from .models import MeasurementReport, RequestSample

__version__ = "1.0.0"

__all__ = [
    "ConfigError",
    "DownloadError",
    "InsecureUrlError",
    "MeasurementConfig",
    "MeasurementReport",
    "RequestSample",
    "ResponseTooLargeError",
    "SpeedMeterError",
    "__version__",
]
