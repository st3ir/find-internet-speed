"""Transport-security policy.

Everything security related lives here, so there is exactly one place to audit
and exactly one place to change: which URLs we are willing to open
(:class:`UrlPolicy`), where our trust anchors come from
(:func:`resolve_ca_bundle`) and how the TLS session is pinned down
(:func:`create_tls_context`).
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

from .errors import InsecureUrlError, TrustStoreError

SECURE_SCHEME = "https"
PLAINTEXT_SCHEME = "http"

#: TLS 1.2 suites: forward secrecy (ECDHE) plus AEAD (AES-GCM / ChaCha20-Poly1305)
#: only -- no CBC, no RSA key transport, no static DH. TLS 1.3 suites are
#: negotiated through a separate OpenSSL list and are all AEAD already.
TLS12_CIPHERS = "ECDHE+AESGCM:ECDHE+CHACHA20"

#: Well-known system CA bundles, tried when OpenSSL's own default store is
#: empty -- which is the normal state of a python.org build on macOS, where
#: OpenSSL cannot read the Keychain.
SYSTEM_CA_BUNDLES = (
    "/etc/ssl/cert.pem",  # macOS, Alpine, FreeBSD
    "/etc/ssl/certs/ca-certificates.crt",  # Debian, Ubuntu
    "/etc/pki/tls/certs/ca-bundle.crt",  # RHEL, Fedora
    "/etc/ssl/ca-bundle.pem",  # openSUSE
)


@dataclass(frozen=True, slots=True)
class UrlPolicy:
    """Decides whether a URL may be opened.

    Applied to the user-supplied address *and* to every redirect target, which
    is what stops a server from downgrading the connection to plaintext mid-run.
    """

    allow_plaintext_http: bool = False

    @property
    def allowed_schemes(self) -> tuple[str, ...]:
        if self.allow_plaintext_http:
            return (SECURE_SCHEME, PLAINTEXT_SCHEME)
        return (SECURE_SCHEME,)

    def validate(self, url: str) -> str:
        """Return the normalised URL or raise :class:`InsecureUrlError`."""
        parts = urlsplit(url.strip())
        scheme = parts.scheme.lower()

        if scheme not in self.allowed_schemes:
            raise InsecureUrlError(
                f"refusing to use scheme {scheme or '(none)'!r}: "
                f"allowed schemes are {', '.join(self.allowed_schemes)} "
                "(pass --allow-plaintext-http to permit http://)"
            )
        if not parts.hostname:
            raise InsecureUrlError(f"URL has no host: {url!r}")
        if parts.username or parts.password:
            # Credentials in a URL leak into logs, proxies and Referer headers.
            raise InsecureUrlError("credentials must not be embedded in the URL")

        return urlunsplit(parts._replace(scheme=scheme))


def resolve_ca_bundle() -> str | None:
    """Best available trust anchor file, or ``None`` if there is none to add."""
    try:
        import certifi
    except ModuleNotFoundError:
        pass
    else:
        return certifi.where()
    return next((path for path in SYSTEM_CA_BUNDLES if os.path.isfile(path)), None)


def _load_bundle(context: ssl.SSLContext, path: str) -> None:
    try:
        context.load_verify_locations(cafile=path)
    except OSError as exc:
        raise TrustStoreError(f"cannot load CA bundle {path!r}: {exc}") from exc


def _has_trust_anchors(context: ssl.SSLContext) -> bool:
    return context.cert_store_stats()["x509_ca"] > 0


def create_tls_context(ca_bundle: str | None = None) -> ssl.SSLContext:
    """Build a deliberately strict client-side TLS context.

    ``create_default_context`` already gives certificate-chain verification,
    hostname checking and sane defaults; everything below tightens it further.
    There is intentionally no "insecure" switch -- a measurement is not worth
    accepting an unverified peer for. If no trust anchors can be found we fail
    loudly rather than continue without verification.
    """
    context = ssl.create_default_context()

    # Verify the chain against the trust store and match the hostname.
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED

    # Drop TLS 1.0/1.1 (and SSLv3) outright.
    context.minimum_version = ssl.TLSVersion.TLSv1_2

    # Stricter RFC 5280 conformance checks on the presented chain.
    context.verify_flags |= ssl.VERIFY_X509_STRICT

    # Forward secrecy + AEAD only.
    context.set_ciphers(TLS12_CIPHERS)

    # TLS-level compression enables CRIME; renegotiation is a DoS/attack vector.
    context.options |= ssl.OP_NO_COMPRESSION
    context.options |= getattr(ssl, "OP_NO_RENEGOTIATION", 0)

    # Advertise exactly the protocol we speak.
    context.set_alpn_protocols(["http/1.1"])

    if ca_bundle is not None:
        _load_bundle(context, ca_bundle)
    elif not _has_trust_anchors(context):
        # OpenSSL's default store came up empty (typical for python.org builds
        # on macOS): fall back to certifi or the OS bundle.
        fallback = resolve_ca_bundle()
        if fallback is not None:
            _load_bundle(context, fallback)

    if not _has_trust_anchors(context):
        raise TrustStoreError(
            "no CA certificates available to verify the server with; "
            "install certifi (pip install certifi) or pass --ca-bundle PATH"
        )
    return context
