"""End-to-end runs against a throwaway local HTTP(S) server.

These exercise the real socket/urllib path -- only the server is local, so the
tests stay fast and offline.
"""

from __future__ import annotations

import http.server
import io
import json
import os
import shutil
import ssl
import subprocess
import tempfile
import threading
import unittest

from speedmeter.cli import EXIT_FAILURE, EXIT_OK, main

PAYLOAD = b"x" * (256 * 1024)


class _PayloadHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    served_paths: list[str] = []

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        type(self).served_paths.append(self.path)
        if self.path == "/payload":
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(len(PAYLOAD)))
            self.end_headers()
            self.wfile.write(PAYLOAD)
        elif self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/payload")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            self.send_error(404, "no such thing")

    def log_message(self, fmt: str, *args: object) -> None:
        """Keep the test output clean."""


class _QuietServer(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request: object, client_address: object) -> None:
        """Expected during the TLS-rejection test; nothing to report."""


def start_server(cert: tuple[str, str] | None = None) -> tuple[_QuietServer, str]:
    """Start a local server and return it together with its base URL."""
    server = _QuietServer(("127.0.0.1", 0), _PayloadHandler)
    scheme = "http"
    if cert is not None:
        certfile, keyfile = cert
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        server.socket = context.wrap_socket(server.socket, server_side=True)
        scheme = "https"
    threading.Thread(target=server.serve_forever, daemon=True).start()
    host, port = server.server_address[:2]
    return server, f"{scheme}://{host}:{port}"


def make_self_signed_cert(directory: str) -> tuple[str, str]:
    certfile = os.path.join(directory, "cert.pem")
    keyfile = os.path.join(directory, "key.pem")
    subprocess.run(
        [
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", keyfile, "-out", certfile,
            "-days", "1", "-subj", "/CN=127.0.0.1",
        ],
        check=True,
        capture_output=True,
    )
    return certfile, keyfile


class PlaintextServerTest(unittest.TestCase):
    """Plaintext is only used because it is explicitly allowed on the command line."""

    def setUp(self) -> None:
        _PayloadHandler.served_paths = []
        self.server, self.base_url = start_server()
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        code = main(list(argv), stdout=out, stderr=err)
        return code, out.getvalue(), err.getvalue()

    def test_measures_three_sequential_downloads(self) -> None:
        code, out, _ = self.run_cli(
            f"{self.base_url}/payload", "-n", "3", "--allow-plaintext-http", "--json", "-q"
        )

        self.assertEqual(code, EXIT_OK)
        payload = json.loads(out)
        self.assertEqual(payload["requests"], 3)
        self.assertEqual(payload["total_bytes"], 3 * len(PAYLOAD))
        self.assertEqual(payload["average_bytes"], len(PAYLOAD))
        self.assertEqual(len(payload["samples"]), 3)
        self.assertGreater(payload["speed_mbit_per_second"], 0)
        self.assertEqual(_PayloadHandler.served_paths, ["/payload"] * 3)

    def test_prints_a_human_report_with_progress(self) -> None:
        code, out, err = self.run_cli(
            f"{self.base_url}/payload", "-n", "2", "--allow-plaintext-http"
        )

        self.assertEqual(code, EXIT_OK)
        self.assertIn("Download speed", out)
        self.assertIn(f"{2 * len(PAYLOAD)} bytes", out)
        self.assertIn("[1/2]", err)

    def test_follows_a_redirect(self) -> None:
        code, out, _ = self.run_cli(
            f"{self.base_url}/redirect", "-n", "1", "--allow-plaintext-http", "--json", "-q"
        )

        self.assertEqual(code, EXIT_OK)
        self.assertEqual(json.loads(out)["total_bytes"], len(PAYLOAD))
        self.assertEqual(_PayloadHandler.served_paths, ["/redirect", "/payload"])

    def test_plaintext_is_refused_without_the_flag(self) -> None:
        code, out, err = self.run_cli(f"{self.base_url}/payload", "-n", "1")

        self.assertEqual(code, EXIT_FAILURE)
        self.assertEqual(out, "")
        self.assertIn("refusing to use scheme", err)
        self.assertEqual(_PayloadHandler.served_paths, [])

    def test_a_missing_resource_is_reported(self) -> None:
        code, _, err = self.run_cli(
            f"{self.base_url}/missing", "-n", "1", "--allow-plaintext-http", "-q"
        )

        self.assertEqual(code, EXIT_FAILURE)
        self.assertIn("404", err)

    def test_an_oversized_response_is_refused(self) -> None:
        code, _, err = self.run_cli(
            f"{self.base_url}/payload", "-n", "1", "--allow-plaintext-http",
            "--max-bytes", "1024", "-q",
        )

        self.assertEqual(code, EXIT_FAILURE)
        self.assertIn("limit", err)


@unittest.skipUnless(shutil.which("openssl"), "openssl CLI is needed to mint a test certificate")
class UntrustedTlsServerTest(unittest.TestCase):
    """The whole point of the strict TLS context: an unverifiable peer is refused."""

    def setUp(self) -> None:
        _PayloadHandler.served_paths = []
        directory = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, directory, True)
        self.server, self.base_url = start_server(make_self_signed_cert(directory))
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.server.server_close)

    def test_self_signed_certificate_is_rejected(self) -> None:
        out, err = io.StringIO(), io.StringIO()

        code = main(
            [f"{self.base_url}/payload", "-n", "1", "-q"], stdout=out, stderr=err
        )

        self.assertEqual(code, EXIT_FAILURE)
        self.assertEqual(out.getvalue(), "")
        self.assertIn("certificate", err.getvalue().lower())
        self.assertEqual(_PayloadHandler.served_paths, [], "no data must be exchanged")


if __name__ == "__main__":
    unittest.main()
