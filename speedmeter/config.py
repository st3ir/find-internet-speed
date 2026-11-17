"""Immutable description of a measurement run."""

from __future__ import annotations

from dataclasses import dataclass

from .errors import ConfigError

DEFAULT_REQUEST_COUNT = 10
DEFAULT_TIMEOUT_SECONDS = 30.0
DEFAULT_CHUNK_SIZE = 64 * 1024
DEFAULT_MAX_BYTES = 1024 * 1024 * 1024  # 1 GiB per response


def _require_positive(name: str, value: float) -> None:
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value!r}")


@dataclass(frozen=True, slots=True)
class MeasurementConfig:
    """Validated parameters of a run.

    Frozen on purpose: a config is passed around freely, and nobody should be
    able to change the meaning of a measurement half-way through it.
    """

    url: str
    request_count: int = DEFAULT_REQUEST_COUNT
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    chunk_size: int = DEFAULT_CHUNK_SIZE
    max_bytes: int = DEFAULT_MAX_BYTES
    allow_plaintext_http: bool = False
    ca_bundle: str | None = None
    """PEM file with the trust anchors; ``None`` auto-detects."""

    def __post_init__(self) -> None:
        if not self.url.strip():
            raise ConfigError("url must not be empty")
        _require_positive("request_count", self.request_count)
        _require_positive("timeout", self.timeout)
        _require_positive("chunk_size", self.chunk_size)
        _require_positive("max_bytes", self.max_bytes)
