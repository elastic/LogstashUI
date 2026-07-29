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
    """
    Global default for generated --logstash-ui-url in enroll commands.

    Precedence:
      1. Management Settings.agent_ui_url (UI-editable)
      2. logstashui.yml agent.ui_url
    """
    try:
        from Management.models import Settings as AppSettings

        db_url = (AppSettings.get_settings().agent_ui_url or "").strip()
        if db_url:
            return db_url.rstrip("/")
    except Exception:
        pass
    cfg = getattr(settings, "LOGSTASHUI_CONFIG", {}) or {}
    agent_cfg = cfg.get("agent") or {}
    url = (agent_cfg.get("ui_url") or "").strip()
    return url.rstrip("/") if url else ""


# ---------------------------------------------------------------------------
# UI server certificate (what nginx / TLS terminator should present)
# ---------------------------------------------------------------------------

UI_SERVER_CERT = "ui-server.crt"
UI_SERVER_KEY = "ui-server.key"
UI_SERVER_CHAIN = "ui-server.chain.crt"
UI_SERVER_MODE = "ui-server.mode"  # "product" | "custom"


def ui_server_cert_path() -> Path:
    return tls_data_dir() / UI_SERVER_CERT


def ui_server_key_path() -> Path:
    return tls_data_dir() / UI_SERVER_KEY


def ui_server_chain_path() -> Path:
    return tls_data_dir() / UI_SERVER_CHAIN


def ui_server_mode_path() -> Path:
    return tls_data_dir() / UI_SERVER_MODE


def get_ui_server_mode() -> str:
    """Return 'custom' if operator uploaded a cert, else 'product'."""
    mode_file = ui_server_mode_path()
    if mode_file.is_file():
        mode = mode_file.read_text(encoding="utf-8").strip().lower()
        if mode in ("custom", "product"):
            return mode
    if ui_server_cert_path().is_file() and ui_server_key_path().is_file():
        # Infer: if cert is signed by our product CA → product, else custom
        try:
            leaf = x509.load_pem_x509_certificate(ui_server_cert_path().read_bytes())
            ca = x509.load_pem_x509_certificate(get_ca_pem())
            if leaf.issuer == ca.subject:
                return "product"
            return "custom"
        except Exception:
            return "custom"
    return "product"


def _write_mode(mode: str) -> None:
    ui_server_mode_path().write_text(mode + "\n", encoding="utf-8")


def _load_private_key(key_pem: bytes):
    return serialization.load_pem_private_key(key_pem, password=None)


def _cert_info(cert: x509.Certificate) -> dict:
    sans = []
    try:
        ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        for name in ext.value:
            if isinstance(name, x509.DNSName):
                sans.append(f"DNS:{name.value}")
            elif isinstance(name, x509.IPAddress):
                sans.append(f"IP:{name.value}")
    except x509.ExtensionNotFound:
        pass
    cn = ""
    try:
        cn = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except (IndexError, ValueError):
        pass
    try:
        not_after = cert.not_valid_after_utc
    except AttributeError:
        not_after = cert.not_valid_after
    return {
        "subject_cn": cn,
        "issuer": cert.issuer.rfc4514_string(),
        "not_after": not_after.isoformat() if hasattr(not_after, "isoformat") else str(not_after),
        "sans": sans,
        "fingerprint_sha256": fingerprint_sha256_der(cert),
    }


def ensure_default_ui_server_cert(extra_dns: Optional[list] = None) -> Tuple[Path, Path]:
    """
    Ensure a product-CA-signed UI server leaf exists (OOTB self-signed path).

    Does not overwrite custom uploads (mode=custom).
    """
    if get_ui_server_mode() == "custom" and ui_server_cert_path().is_file():
        return ui_server_cert_path(), ui_server_key_path()

    if (
        get_ui_server_mode() == "product"
        and ui_server_cert_path().is_file()
        and ui_server_key_path().is_file()
    ):
        return ui_server_cert_path(), ui_server_key_path()

    ensure_product_ca()
    ca_cert = x509.load_pem_x509_certificate(ca_cert_path().read_bytes())
    ca_key = serialization.load_pem_private_key(ca_key_path().read_bytes(), password=None)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    dns_names = ["localhost", "logstashui"]
    if extra_dns:
        for d in extra_dns:
            if d and d not in dns_names:
                dns_names.append(d)
    # Also add agent.ui_url hostname if configured
    try:
        from urllib.parse import urlparse

        agent_url = get_agent_ui_url_default()
        if agent_url:
            host = urlparse(agent_url).hostname
            if host and host not in dns_names:
                dns_names.append(host)
    except Exception:
        pass

    san_list = [x509.DNSName(n) for n in dns_names]
    # localhost IPs
    import ipaddress

    san_list.append(x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")))
    san_list.append(x509.IPAddress(ipaddress.IPv6Address("::1")))

    now = datetime.now(timezone.utc)
    subject = x509.Name([
        x509.NameAttribute(NameOID.ORGANIZATION_NAME, "LogstashUI"),
        x509.NameAttribute(NameOID.COMMON_NAME, dns_names[0]),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(ca_cert.subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                key_encipherment=True,
                content_commitment=False,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(x509.SubjectAlternativeName(san_list), critical=False)
        .sign(ca_key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    ui_server_cert_path().write_bytes(cert_pem)
    ui_server_key_path().write_bytes(key_pem)
    try:
        ui_server_key_path().chmod(0o600)
        ui_server_cert_path().chmod(0o644)
    except OSError:
        pass
    _write_mode("product")
    # Remove stale chain from previous custom upload
    if ui_server_chain_path().is_file():
        try:
            ui_server_chain_path().unlink()
        except OSError:
            pass
    logger.info("Generated product-CA-signed UI server certificate")
    return ui_server_cert_path(), ui_server_key_path()


def save_custom_ui_certificate(
    cert_pem: bytes,
    key_pem: bytes,
    chain_pem: Optional[bytes] = None,
) -> dict:
    """
    Install a customer-provided UI server certificate (public CA or other).

    Does not replace the product CA. Validates that key matches leaf cert.
    """
    if not cert_pem or not key_pem:
        raise ValueError("Certificate and private key are required")

    # Support multi-cert PEM: first is leaf
    certs = []
    remaining = cert_pem
    while b"BEGIN CERTIFICATE" in remaining:
        try:
            c = x509.load_pem_x509_certificate(remaining)
            certs.append(c)
            # advance past this cert in PEM stream
            end = remaining.find(b"-----END CERTIFICATE-----")
            if end < 0:
                break
            remaining = remaining[end + len(b"-----END CERTIFICATE-----") :]
        except Exception:
            break
    if not certs:
        raise ValueError("Could not parse certificate PEM")

    leaf = certs[0]
    try:
        key = _load_private_key(key_pem)
    except Exception as e:
        raise ValueError(f"Could not parse private key: {e}") from e

    # Key matches leaf?
    leaf_pub = leaf.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    key_pub = key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    if leaf_pub != key_pub:
        raise ValueError("Private key does not match the certificate public key")

    tls_data_dir()
    # Write leaf only to ui-server.crt; extras to chain file
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM)
    ui_server_cert_path().write_bytes(leaf_pem)
    ui_server_key_path().write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    try:
        ui_server_key_path().chmod(0o600)
    except OSError:
        pass

    chain_parts = []
    if len(certs) > 1:
        chain_parts.extend(
            c.public_bytes(serialization.Encoding.PEM) for c in certs[1:]
        )
    if chain_pem and b"BEGIN CERTIFICATE" in chain_pem:
        chain_parts.append(chain_pem if isinstance(chain_pem, bytes) else chain_pem.encode())
    if chain_parts:
        ui_server_chain_path().write_bytes(b"".join(chain_parts))
    elif ui_server_chain_path().is_file():
        ui_server_chain_path().unlink(missing_ok=True)

    _write_mode("custom")
    info = _cert_info(leaf)
    logger.info(
        "Installed custom UI server certificate CN=%s fingerprint=%s…",
        info.get("subject_cn"),
        info.get("fingerprint_sha256", "")[:16],
    )
    return {"mode": "custom", **info, "paths": ui_tls_paths_for_display()}


def revert_ui_certificate_to_product_default() -> dict:
    """Remove custom cert and regenerate product-CA-signed leaf."""
    for p in (ui_server_cert_path(), ui_server_key_path(), ui_server_chain_path(), ui_server_mode_path()):
        try:
            if p.is_file():
                p.unlink()
        except OSError as e:
            logger.warning("Could not remove %s: %s", p, e)
    ensure_default_ui_server_cert()
    return get_ui_tls_status()


def ui_tls_paths_for_display() -> dict:
    return {
        "cert": str(ui_server_cert_path()),
        "key": str(ui_server_key_path()),
        "chain": str(ui_server_chain_path()),
        "product_ca": str(ca_cert_path()),
        "well_known_ca": WELL_KNOWN_CA_PATH,
    }


def get_ui_tls_status() -> dict:
    """Status blob for Management → Settings."""
    ensure_product_ca()
    mode = get_ui_server_mode()
    # Ensure product leaf exists when in product mode
    if mode == "product":
        try:
            ensure_default_ui_server_cert()
        except Exception as e:
            logger.warning("Could not ensure default UI cert: %s", e)

    status = {
        "mode": mode,
        "paths": ui_tls_paths_for_display(),
        "product_ca_fingerprint": get_ca_fingerprint(),
        "certificate": None,
        "has_custom": mode == "custom",
        "nginx_hint": (
            f"Point your TLS terminator at:\n"
            f"  ssl_certificate     {ui_server_cert_path()};\n"
            f"  ssl_certificate_key {ui_server_key_path()};\n"
            f"Optional chain: {ui_server_chain_path()}"
        ),
    }
    if ui_server_cert_path().is_file():
        try:
            leaf = x509.load_pem_x509_certificate(ui_server_cert_path().read_bytes())
            status["certificate"] = _cert_info(leaf)
        except Exception as e:
            status["certificate_error"] = str(e)
    return status

