"""HTTP transport: turns a URL into a stream of body chunks.

The rest of the package depends on the :class:`Transport` protocol, not on
``urllib`` -- that keeps the measurement logic free of network details and
trivially testable with a stub.
"""

from __future__ import annotations

import ssl
import urllib.error
import urllib.request
from collections.abc import Iterator
from typing import Protocol

from .errors import DownloadError, ResponseTooLargeError
from .security import UrlPolicy, create_tls_context

#: Sent with every request.
#:
#: ``identity`` keeps the measurement honest (we count the bytes that actually
#: crossed the wire) and sidesteps decompression bombs; the no-cache pair asks
#: intermediaries not to answer from a cache; ``close`` means every sample pays
#: its own connection + TLS handshake, so all 10 samples are comparable.
DEFAULT_HEADERS: dict[str, str] = {
    "User-Agent": "speedmeter/1.0",
    "Accept": "*/*",
    "Accept-Encoding": "identity",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Connection": "close",
}


class Transport(Protocol):
    """Streams the body of a GET request."""

    def stream(self, url: str, *, timeout: float, chunk_size: int) -> Iterator[bytes]:
        """Yield response-body chunks, or raise :class:`DownloadError`."""
        ...


class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Re-applies the URL policy to every redirect hop.

    Without this, a single ``302`` could move an ``https://`` measurement onto
    plaintext ``http://``.
    """

    def __init__(self, policy: UrlPolicy) -> None:
        self._policy = policy

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001, ANN201 - urllib signature
        return super().redirect_request(
            req, fp, code, msg, headers, self._policy.validate(newurl)
        )


def build_opener(
    policy: UrlPolicy, tls_context: ssl.SSLContext | None = None
) -> urllib.request.OpenerDirector:
    """Assemble an opener that cannot silently do anything unsafe."""
    return urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=tls_context or create_tls_context()),
        SafeRedirectHandler(policy),
        # Ignore *_proxy environment variables: an unexpected proxy is a
        # man-in-the-middle and would also invalidate the measurement.
        urllib.request.ProxyHandler({}),
    )


class UrllibTransport:
    """:class:`Transport` implementation on top of the standard library."""

    def __init__(
        self,
        policy: UrlPolicy,
        *,
        max_bytes: int,
        opener: urllib.request.OpenerDirector | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._policy = policy
        self._max_bytes = max_bytes
        self._opener = opener if opener is not None else build_opener(policy)
        self._headers = dict(headers if headers is not None else DEFAULT_HEADERS)

    def stream(self, url: str, *, timeout: float, chunk_size: int) -> Iterator[bytes]:
        # Validated again here: the transport must be safe on its own, whoever
        # calls it.
        request = urllib.request.Request(
            self._policy.validate(url), headers=self._headers, method="GET"
        )
        try:
            with self._opener.open(request, timeout=timeout) as response:
                self._reject_oversized_declaration(response)
                yield from self._read_chunks(response, chunk_size)
        except urllib.error.HTTPError as exc:
            raise DownloadError(f"server answered HTTP {exc.code} {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise DownloadError(f"could not reach {url}: {exc.reason}") from exc
        except OSError as exc:  # socket timeouts, resets, TLS failures
            raise DownloadError(f"transfer from {url} failed: {exc}") from exc

    def _reject_oversized_declaration(self, response) -> None:  # noqa: ANN001
        """Refuse a body that is already declared too large to download."""
        declared = response.headers.get("Content-Length")
        if declared is None:
            return
        try:
            size = int(declared)
        except ValueError:
            return
        if size > self._max_bytes:
            raise ResponseTooLargeError(
                f"response declares {size} bytes, limit is {self._max_bytes}"
            )

    def _read_chunks(self, response, chunk_size: int) -> Iterator[bytes]:  # noqa: ANN001
        downloaded = 0
        while True:
            chunk = response.read(chunk_size)
            if not chunk:
                return
            downloaded += len(chunk)
            if downloaded > self._max_bytes:
                raise ResponseTooLargeError(
                    f"response exceeded the {self._max_bytes} byte limit"
                )
            yield chunk
