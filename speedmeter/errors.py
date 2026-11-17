"""Exception hierarchy.

A single root exception lets the CLI catch everything the library raises
without also swallowing unrelated bugs.
"""

from __future__ import annotations


class SpeedMeterError(Exception):
    """Base class for every error raised by this package."""


class ConfigError(SpeedMeterError, ValueError):
    """The requested measurement makes no sense."""


class InsecureUrlError(ConfigError):
    """The URL violates the transport-security policy."""


class DownloadError(SpeedMeterError):
    """A request could not be completed."""


class ResponseTooLargeError(DownloadError):
    """The response body exceeds the configured safety limit."""


class TrustStoreError(SpeedMeterError):
    """No trustworthy CA certificates are available, so TLS cannot be verified."""
