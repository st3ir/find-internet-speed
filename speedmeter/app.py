"""Composition root: the one place where concrete classes are wired together."""

from __future__ import annotations

from dataclasses import replace

from .config import MeasurementConfig
from .measurement import SpeedMeter
from .security import UrlPolicy, create_tls_context
from .transport import UrllibTransport, build_opener


def build_meter(config: MeasurementConfig) -> SpeedMeter:
    """Assemble a meter for ``config``, failing fast on an unsafe setup."""
    policy = UrlPolicy(allow_plaintext_http=config.allow_plaintext_http)
    validated = replace(config, url=policy.validate(config.url))
    opener = build_opener(policy, create_tls_context(validated.ca_bundle))
    transport = UrllibTransport(policy, max_bytes=validated.max_bytes, opener=opener)
    return SpeedMeter(transport=transport, config=validated)
