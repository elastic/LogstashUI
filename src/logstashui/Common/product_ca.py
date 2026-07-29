#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Product CA for LogstashUI.

- Generated once on first use and stored under data/tls/
- Serves the public CA cert at /.well-known/logstashui/ca.crt
- Fingerprint (SHA-256 of DER, lowercase hex) is embedded in enrollment tokens
  when agent.include_ca_fingerprint is true (default)
"""

from __future__ import annotations

import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from django.conf import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cached_cert_pem: Optional[bytes] = None
_cached_fingerprint: Optional[str] = None

WELL_KNOWN_CA_PATH = "/.well-known/logstashui/ca.crt"


def tls_data_dir() -> Path:
    d = Path(settings.BASE_DIR) / "data" / "tls"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ca_cert_path() -> Path:
    return tls_data_dir() / "product-ca.crt"


def ca_key_path() -> Path:
    return tls_data_dir() / "product-ca.key"


def fingerprint_sha256_der(cert: x509.Certificate) -> str:
    """SHA-256 of the certificate DER encoding, lowercase hex."""
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _generate_ca() -> Tuple[bytes, bytes, str]:
    """Create a new product CA; return (cert_pem, key_pem, fingerprint_hex)."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LogstashUI"),
        x509.NameAttribute(NameOID.COMMON_NAME, "LogstashUI Product CA"),
    ])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=3650))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_cert_sign=True,
                crl_sign=True,
                content_commitment=False,
                key_encipherment=False,
                data_encipherment=False,
                key_agreement=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fp = fingerprint_sha256_der(cert)
    return cert_pem, key_pem, fp


def ensure_product_ca() -> Tuple[bytes, str]:
    """
    Ensure product CA exists on disk; return (cert_pem_bytes, fingerprint_hex).
    """
    global _cached_cert_pem, _cached_fingerprint
    with _lock:
        if _cached_cert_pem and _cached_fingerprint:
            return _cached_cert_pem, _cached_fingerprint

        cert_path = ca_cert_path()
        key_path = ca_key_path()

        if cert_path.is_file() and key_path.is_file():
            cert_pem = cert_path.read_bytes()
            cert = x509.load_pem_x509_certificate(cert_pem)
            fp = fingerprint_sha256_der(cert)
            _cached_cert_pem = cert_pem
            _cached_fingerprint = fp
            logger.debug("Loaded product CA fingerprint=%s…", fp[:16])
            return cert_pem, fp

        logger.info("Generating new LogstashUI product CA at %s", tls_data_dir())
        cert_pem, key_pem, fp = _generate_ca()
        cert_path.write_bytes(cert_pem)
        key_path.write_bytes(key_pem)
        try:
            key_path.chmod(0o600)
            cert_path.chmod(0o644)
        except OSError:
            pass
        _cached_cert_pem = cert_pem
        _cached_fingerprint = fp
        logger.info("Product CA ready fingerprint=%s", fp)
        return cert_pem, fp


def get_ca_pem() -> bytes:
    cert_pem, _ = ensure_product_ca()
    return cert_pem


def get_ca_fingerprint() -> str:
    _, fp = ensure_product_ca()
    return fp


def build_enrollment_token_payload(raw_token: str) -> dict:
    """
    Build v2 enrollment token payload for base64 encoding.

    Always includes enrollment_token and token_version.
    Includes fingerprint when agent.include_ca_fingerprint is true (default).
    Does not include ui_url (CLI --logstash-ui-url).
    """
    payload = {
        "enrollment_token": raw_token,
        "token_version": 2,
    }
    cfg = getattr(settings, "LOGSTASHUI_CONFIG", {}) or {}
    agent_cfg = cfg.get("agent") or {}
    include_fp = agent_cfg.get("include_ca_fingerprint", True)
    if include_fp:
        try:
            payload["fingerprint"] = get_ca_fingerprint()
        except Exception as e:
            logger.warning("Could not add CA fingerprint to enrollment token: %s", e)
    return payload


def get_agent_ui_url_default() -> str:
    """Global default for generated --logstash-ui-url in enroll commands."""
    cfg = getattr(settings, "LOGSTASHUI_CONFIG", {}) or {}
    agent_cfg = cfg.get("agent") or {}
    url = (agent_cfg.get("ui_url") or "").strip()
    return url.rstrip("/") if url else ""
