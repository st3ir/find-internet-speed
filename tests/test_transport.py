"""HTTP transport behaviour, exercised without touching the network."""

from __future__ import annotations

import io
import unittest
import urllib.error
import urllib.request

from speedmeter.errors import DownloadError, InsecureUrlError, ResponseTooLargeError
from speedmeter.security import UrlPolicy
from speedmeter.transport import UrllibTransport

URL = "https://example.com/image.jpg"


class FakeResponse:
    """Minimal stand-in for ``http.client.HTTPResponse``."""

    def __init__(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self._buffer = io.BytesIO(body)
        self.headers = dict(headers or {})
        self.closed = False

    def read(self, amount: int) -> bytes:
        return self._buffer.read(amount)

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, *exc: object) -> bool:
        self.closed = True
        return False


class FakeOpener:
    """Records what it was asked to open and replays a canned answer."""

    def __init__(self, response: object = None, error: Exception | None = None) -> None:
        self.response = response
        self._error = error
        self.requests: list[urllib.request.Request] = []
        self.timeouts: list[float] = []

    def open(self, request, timeout=None):  # noqa: ANN001, ANN201 - urllib signature
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self._error is not None:
            raise self._error
        return self.response


def make_transport(
    body: bytes = b"",
    *,
    headers: dict[str, str] | None = None,
    error: Exception | None = None,
    max_bytes: int = 1024 * 1024,
    policy: UrlPolicy | None = None,
) -> tuple[UrllibTransport, FakeOpener]:
    opener = FakeOpener(FakeResponse(body, headers), error)
    transport = UrllibTransport(
        policy or UrlPolicy(), max_bytes=max_bytes, opener=opener
    )
    return transport, opener


class StreamingTest(unittest.TestCase):
    def test_yields_the_whole_body_in_chunks(self) -> None:
        body = bytes(range(256)) * 40  # 10 240 bytes
        transport, _ = make_transport(body)

        chunks = list(transport.stream(URL, timeout=5, chunk_size=1024))

        self.assertEqual(b"".join(chunks), body)
        self.assertEqual([len(chunk) for chunk in chunks], [1024] * 10)

    def test_closes_the_response(self) -> None:
        transport, opener = make_transport(b"abc")

        list(transport.stream(URL, timeout=5, chunk_size=8))

        self.assertTrue(opener.response.closed)

    def test_passes_the_timeout_through(self) -> None:
        transport, opener = make_transport(b"abc")

        list(transport.stream(URL, timeout=7.5, chunk_size=8))

        self.assertEqual(opener.timeouts, [7.5])

    def test_sends_hardened_headers(self) -> None:
        transport, opener = make_transport(b"abc")

        list(transport.stream(URL, timeout=5, chunk_size=8))

        headers = opener.requests[0].headers
        self.assertEqual(headers["Accept-encoding"], "identity")
        self.assertEqual(headers["Cache-control"], "no-cache")
        self.assertEqual(headers["Connection"], "close")
        self.assertEqual(headers["User-agent"], "speedmeter/1.0")
        self.assertEqual(opener.requests[0].get_method(), "GET")


class SafetyLimitTest(unittest.TestCase):
    def test_refuses_a_body_declared_too_large(self) -> None:
        transport, _ = make_transport(
            b"x" * 10, headers={"Content-Length": "999999"}, max_bytes=1024
        )

        with self.assertRaises(ResponseTooLargeError):
            list(transport.stream(URL, timeout=5, chunk_size=8))

    def test_refuses_a_body_that_outgrows_the_limit_while_streaming(self) -> None:
        transport, _ = make_transport(b"x" * 5000, max_bytes=1024)

        with self.assertRaises(ResponseTooLargeError):
            list(transport.stream(URL, timeout=5, chunk_size=256))

    def test_ignores_an_unparsable_content_length(self) -> None:
        transport, _ = make_transport(b"x" * 10, headers={"Content-Length": "many"})

        self.assertEqual(b"".join(transport.stream(URL, timeout=5, chunk_size=8)), b"x" * 10)

    def test_validates_the_url_even_when_called_directly(self) -> None:
        transport, _ = make_transport(b"abc")

        with self.assertRaises(InsecureUrlError):
            list(transport.stream("http://example.com/image.jpg", timeout=5, chunk_size=8))


class ErrorTranslationTest(unittest.TestCase):
    def test_http_error_becomes_download_error(self) -> None:
        error = urllib.error.HTTPError(URL, 404, "Not Found", {}, None)  # type: ignore[arg-type]
        transport, _ = make_transport(error=error)

        with self.assertRaises(DownloadError) as caught:
            list(transport.stream(URL, timeout=5, chunk_size=8))

        self.assertIn("404", str(caught.exception))

    def test_unreachable_host_becomes_download_error(self) -> None:
        transport, _ = make_transport(error=urllib.error.URLError("nodename nor servname"))

        with self.assertRaises(DownloadError) as caught:
            list(transport.stream(URL, timeout=5, chunk_size=8))

        self.assertIn("could not reach", str(caught.exception))

    def test_socket_failure_becomes_download_error(self) -> None:
        transport, _ = make_transport(error=TimeoutError("timed out"))

        with self.assertRaises(DownloadError):
            list(transport.stream(URL, timeout=5, chunk_size=8))


if __name__ == "__main__":
    unittest.main()
