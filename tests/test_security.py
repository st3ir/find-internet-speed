"""The transport-security policy: URL vetting, TLS hardening, redirect safety."""

from __future__ import annotations

import ssl
import unittest
import urllib.request

from speedmeter.errors import InsecureUrlError, TrustStoreError
from speedmeter.security import (
    TLS12_CIPHERS,
    UrlPolicy,
    create_tls_context,
    resolve_ca_bundle,
)
from speedmeter.transport import SafeRedirectHandler


class UrlPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.strict = UrlPolicy()
        self.permissive = UrlPolicy(allow_plaintext_http=True)

    def test_https_is_accepted(self) -> None:
        self.assertEqual(
            self.strict.validate("https://example.com/image.jpg"),
            "https://example.com/image.jpg",
        )

    def test_plaintext_http_is_refused_by_default(self) -> None:
        with self.assertRaises(InsecureUrlError) as caught:
            self.strict.validate("http://example.com/image.jpg")

        self.assertIn("--allow-plaintext-http", str(caught.exception))

    def test_plaintext_http_can_be_opted_into(self) -> None:
        self.assertEqual(
            self.permissive.validate("http://example.com/image.jpg"),
            "http://example.com/image.jpg",
        )

    def test_other_schemes_are_always_refused(self) -> None:
        for url in (
            "ftp://example.com/image.jpg",
            "file:///etc/passwd",
            "gopher://example.com",
            "example.com/image.jpg",  # no scheme at all
        ):
            with self.subTest(url=url):
                for policy in (self.strict, self.permissive):
                    with self.assertRaises(InsecureUrlError):
                        policy.validate(url)

    def test_url_without_host_is_refused(self) -> None:
        with self.assertRaises(InsecureUrlError):
            self.strict.validate("https:///image.jpg")

    def test_embedded_credentials_are_refused(self) -> None:
        for url in (
            "https://user:secret@example.com/image.jpg",
            "https://user@example.com/image.jpg",
        ):
            with self.subTest(url=url):
                with self.assertRaises(InsecureUrlError) as caught:
                    self.strict.validate(url)
                self.assertIn("credentials", str(caught.exception))

    def test_normalises_scheme_case_and_surrounding_space(self) -> None:
        self.assertEqual(
            self.strict.validate("  HTTPS://example.com/a.jpg?q=1  "),
            "https://example.com/a.jpg?q=1",
        )

    def test_allowed_schemes_depend_on_the_flag(self) -> None:
        self.assertEqual(self.strict.allowed_schemes, ("https",))
        self.assertEqual(self.permissive.allowed_schemes, ("https", "http"))


class TlsContextTest(unittest.TestCase):
    def setUp(self) -> None:
        if resolve_ca_bundle() is None and not _default_store_has_anchors():
            self.skipTest("no CA trust store available on this machine")
        self.context = create_tls_context()

    def test_verifies_certificate_and_hostname(self) -> None:
        self.assertTrue(self.context.check_hostname)
        self.assertEqual(self.context.verify_mode, ssl.CERT_REQUIRED)

    def test_refuses_tls_below_1_2(self) -> None:
        self.assertEqual(self.context.minimum_version, ssl.TLSVersion.TLSv1_2)

    def test_uses_strict_x509_checks(self) -> None:
        self.assertTrue(self.context.verify_flags & ssl.VERIFY_X509_STRICT)

    def test_disables_tls_compression(self) -> None:
        self.assertTrue(self.context.options & ssl.OP_NO_COMPRESSION)

    def test_only_forward_secret_aead_ciphers_are_offered(self) -> None:
        names = [cipher["name"] for cipher in self.context.get_ciphers()]

        self.assertTrue(names, "cipher list must not be empty")
        for name in names:
            with self.subTest(cipher=name):
                # TLS 1.3 suites are listed too and are AEAD + ephemeral by design.
                if name.startswith("TLS_"):
                    continue
                self.assertTrue(name.startswith("ECDHE-"), name)
                self.assertTrue(("GCM" in name) or ("CHACHA20" in name), name)

    def test_has_trust_anchors_loaded(self) -> None:
        self.assertGreater(self.context.cert_store_stats()["x509_ca"], 0)

    def test_missing_ca_bundle_fails_loudly(self) -> None:
        with self.assertRaises(TrustStoreError):
            create_tls_context(ca_bundle="/nonexistent/ca-bundle.pem")

    def test_cipher_string_is_the_documented_one(self) -> None:
        self.assertEqual(TLS12_CIPHERS, "ECDHE+AESGCM:ECDHE+CHACHA20")


class SafeRedirectHandlerTest(unittest.TestCase):
    """A redirect must not be able to weaken the connection."""

    def _redirect_to(self, newurl: str, policy: UrlPolicy) -> urllib.request.Request:
        handler = SafeRedirectHandler(policy)
        request = urllib.request.Request("https://example.com/image.jpg")
        return handler.redirect_request(request, None, 302, "Found", {}, newurl)

    def test_https_to_http_downgrade_is_blocked(self) -> None:
        with self.assertRaises(InsecureUrlError):
            self._redirect_to("http://example.com/image.jpg", UrlPolicy())

    def test_redirect_to_other_scheme_is_blocked(self) -> None:
        with self.assertRaises(InsecureUrlError):
            self._redirect_to("file:///etc/passwd", UrlPolicy())

    def test_redirect_with_credentials_is_blocked(self) -> None:
        with self.assertRaises(InsecureUrlError):
            self._redirect_to("https://user:pw@example.com/x.jpg", UrlPolicy())

    def test_https_redirect_is_followed(self) -> None:
        redirected = self._redirect_to("https://cdn.example.com/x.jpg", UrlPolicy())

        self.assertEqual(redirected.full_url, "https://cdn.example.com/x.jpg")
        self.assertEqual(redirected.get_method(), "GET")

    def test_downgrade_is_allowed_only_when_explicitly_permitted(self) -> None:
        redirected = self._redirect_to(
            "http://example.com/image.jpg", UrlPolicy(allow_plaintext_http=True)
        )

        self.assertEqual(redirected.full_url, "http://example.com/image.jpg")


def _default_store_has_anchors() -> bool:
    return ssl.create_default_context().cert_store_stats()["x509_ca"] > 0


if __name__ == "__main__":
    unittest.main()
