#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for product CA generation and enrollment token payload."""

import hashlib
import ipaddress
import socket

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from django.test import override_settings


@pytest.mark.django_db
def test_ensure_product_ca_generates_and_fingerprints(tmp_path, settings):
    from Common import product_ca

    # Isolate CA storage
    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)

    pem1, fp1 = product_ca.ensure_product_ca()
    assert b"BEGIN CERTIFICATE" in pem1
    assert len(fp1) == 64
    cert = x509.load_pem_x509_certificate(pem1)
    der = cert.public_bytes(serialization.Encoding.DER)
    assert hashlib.sha256(der).hexdigest() == fp1

    # Second call is cached / reloads same files
    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    pem2, fp2 = product_ca.ensure_product_ca()
    assert fp1 == fp2
    assert pem1 == pem2


@pytest.mark.django_db
def test_build_enrollment_token_payload_includes_fingerprint(tmp_path, settings):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    settings.LOGSTASHUI_CONFIG = {
        "agent": {"include_ca_fingerprint": True},
    }

    payload = product_ca.build_enrollment_token_payload("secret-token")
    assert payload["enrollment_token"] == "secret-token"
    assert payload["token_version"] == 2
    assert "fingerprint" in payload
    assert len(payload["fingerprint"]) == 64
    assert "ui_url" not in payload


@pytest.mark.django_db
def test_build_enrollment_token_payload_omits_fingerprint(tmp_path, settings):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    settings.LOGSTASHUI_CONFIG = {
        "agent": {"include_ca_fingerprint": False},
    }

    payload = product_ca.build_enrollment_token_payload("secret-token")
    assert "fingerprint" not in payload


def test_product_ca_endpoint(client, tmp_path, settings):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)

    resp = client.get("/.well-known/logstashui/ca.crt")
    assert resp.status_code == 200
    assert b"BEGIN CERTIFICATE" in resp.content


@pytest.mark.django_db
def test_default_ui_server_cert_includes_compose_sans(tmp_path, settings, monkeypatch):
    """Product default leaf must cover localhost and logstashui service name."""
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.delenv("LOGSTASHUI_TLS_SANS", raising=False)
    monkeypatch.delenv("LOGSTASHUI_HOST_HOSTNAME", raising=False)
    monkeypatch.delenv("LOGSTASHUI_HOST_IPS", raising=False)

    cert_path, key_path = product_ca.ensure_default_ui_server_cert()
    assert cert_path.is_file()
    assert key_path.is_file()
    leaf = x509.load_pem_x509_certificate(cert_path.read_bytes())
    ext = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    dns = {n.value for n in ext.value if isinstance(n, x509.DNSName)}
    assert "localhost" in dns
    assert "logstashui" in dns
    assert product_ca.get_ui_server_mode() == "product"


@pytest.mark.django_db
def test_ui_cert_includes_host_ips_and_reissues_on_san_change(tmp_path, settings, monkeypatch):
    from Common import product_ca
    import ipaddress

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    settings.LOGSTASHUI_CONFIG = {}

    monkeypatch.setenv("LOGSTASHUI_HOST_HOSTNAME", "docker-host.example")
    monkeypatch.setenv("LOGSTASHUI_HOST_IPS", "10.20.30.40,10.20.30.41")
    monkeypatch.delenv("LOGSTASHUI_TLS_SANS", raising=False)

    product_ca.ensure_default_ui_server_cert()
    leaf = x509.load_pem_x509_certificate(product_ca.ui_server_cert_path().read_bytes())
    ext = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
    dns = {n.value for n in ext.value if isinstance(n, x509.DNSName)}
    ips = {n.value for n in ext.value if isinstance(n, x509.IPAddress)}
    assert "docker-host.example" in dns
    assert ipaddress.IPv4Address("10.20.30.40") in ips
    assert ipaddress.IPv4Address("10.20.30.41") in ips
    fp1 = product_ca.fingerprint_sha256_der(leaf)

    # New host IP → must re-issue
    monkeypatch.setenv("LOGSTASHUI_HOST_IPS", "10.20.30.40,10.20.30.41,10.20.30.99")
    assert product_ca.product_ui_cert_needs_reissue() is True
    product_ca.ensure_default_ui_server_cert()
    leaf2 = x509.load_pem_x509_certificate(product_ca.ui_server_cert_path().read_bytes())
    ips2 = {
        n.value
        for n in leaf2.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if isinstance(n, x509.IPAddress)
    }
    assert ipaddress.IPv4Address("10.20.30.99") in ips2
    fp2 = product_ca.fingerprint_sha256_der(leaf2)
    assert fp1 != fp2


def test_reverse_lookup_fqdns_filters_short_and_ip(monkeypatch):
    from Common import product_ca

    def _fake(ip):
        if ip == "10.0.0.5":
            return ("host.example.com.", ["alias.example.com"], ["10.0.0.5"])
        if ip == "10.0.0.6":
            return ("shortname", [], ["10.0.0.6"])
        raise socket.herror("no PTR")

    monkeypatch.setattr(product_ca.socket, "gethostbyaddr", _fake)
    assert product_ca._reverse_lookup_fqdns("10.0.0.5") == [
        "host.example.com",
        "alias.example.com",
    ]
    assert product_ca._reverse_lookup_fqdns("10.0.0.6") == []
    assert product_ca._reverse_lookup_fqdns("10.0.0.7") == []


def test_prefer_ptr_fqdns_over_short_hostnames(monkeypatch):
    from Common import product_ca

    def _fake(ip):
        if ip == "10.9.5.31":
            return ("mac.untergeek.dev", [], [ip])
        raise socket.herror("no PTR")

    monkeypatch.setattr(product_ca.socket, "gethostbyaddr", _fake)

    dns = ["localhost", "logstashui", "Palpatine"]
    ips = [
        ipaddress.IPv4Address("127.0.0.1"),
        ipaddress.IPv4Address("10.9.5.31"),
    ]
    product_ca._prefer_ptr_fqdns_over_short_hostnames(dns, ips)
    assert "mac.untergeek.dev" in dns
    assert "localhost" in dns
    assert "logstashui" in dns
    assert "Palpatine" not in dns


def test_collect_desired_ui_sans_uses_ptr_over_bare_hostname(monkeypatch, settings):
    from Common import product_ca

    settings.LOGSTASHUI_CONFIG = {}
    monkeypatch.setenv("LOGSTASHUI_HOST_HOSTNAME", "Palpatine")
    monkeypatch.setenv("LOGSTASHUI_HOST_IPS", "172.19.7.21")
    monkeypatch.delenv("LOGSTASHUI_TLS_SANS", raising=False)

    def _fake(ip):
        if ip == "172.19.7.21":
            return ("palpatine.untergeek.net", [], [ip])
        raise socket.herror("no PTR")

    monkeypatch.setattr(product_ca.socket, "gethostbyaddr", _fake)
    # Avoid noise from local interface discovery / getfqdn
    monkeypatch.setattr(product_ca.socket, "gethostname", lambda: "Palpatine")
    monkeypatch.setattr(product_ca.socket, "getfqdn", lambda: "Palpatine")
    monkeypatch.setattr(product_ca.socket, "getaddrinfo", lambda *a, **k: [])
    # Skip UDP outbound-IP trick (would discover real LAN IPs and PTR them)
    monkeypatch.setattr(
        product_ca.socket,
        "socket",
        lambda *a, **k: (_ for _ in ()).throw(OSError("skip")),
    )

    dns, ips = product_ca.collect_desired_ui_sans()
    assert "palpatine.untergeek.net" in dns
    assert "Palpatine" not in dns
    assert "localhost" in dns
    assert "logstashui" in dns
    assert ipaddress.IPv4Address("172.19.7.21") in ips


@pytest.mark.django_db
def test_sign_agent_csr(tmp_path, settings):
    from Common import product_ca
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from cryptography import x509
    from datetime import datetime, timedelta, timezone

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    csr = (
        x509.CertificateSigningRequestBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "agent1")]))
        .add_extension(
            x509.SubjectAlternativeName([
                x509.DNSName("agent1"),
                x509.DNSName("localhost"),
            ]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    signed = product_ca.sign_agent_csr(csr.public_bytes(serialization.Encoding.PEM))
    assert "BEGIN CERTIFICATE" in signed["certificate_pem"]
    assert "BEGIN CERTIFICATE" in signed["ca_pem"]
    leaf = x509.load_pem_x509_certificate(signed["certificate_pem"].encode())
    assert leaf.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value == "agent1"


@pytest.mark.django_db
def test_custom_ui_cert_and_revert(tmp_path, settings):
    from Common import product_ca
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.x509.oid import NameOID
    from datetime import datetime, timedelta, timezone

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)

    # Self-signed standalone cert (simulates public/custom CA leaf)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "custom.example")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("custom.example")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )

    info = product_ca.save_custom_ui_certificate(cert_pem, key_pem)
    assert info["mode"] == "custom"
    assert info["subject_cn"] == "custom.example"
    assert product_ca.get_ui_server_mode() == "custom"

    status = product_ca.revert_ui_certificate_to_product_default()
    assert status["mode"] == "product"
    assert product_ca.ui_server_cert_path().is_file()


@pytest.mark.django_db
def test_settings_saves_agent_ui_url(admin_client):
    from Management.models import Settings

    # Ensure admin has profile role admin (signal creates admin by default)
    resp = admin_client.post(
        "/Management/Settings/",
        {"experimental_mode": "on", "agent_ui_url": "https://10.0.0.5:8443"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    s = Settings.get_settings()
    assert s.agent_ui_url == "https://10.0.0.5:8443"
    assert s.experimental_mode is True


def test_ensure_product_ca_disabled_writes_nothing(tmp_path, settings, monkeypatch):
    from Common import product_ca
    from Common.product_ca import ProductCADisabled

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")

    with pytest.raises(ProductCADisabled):
        product_ca.ensure_product_ca()
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def test_ensure_default_ui_server_cert_disabled_writes_nothing(tmp_path, settings, monkeypatch):
    from Common import product_ca
    from Common.product_ca import ProductCADisabled

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")

    with pytest.raises(ProductCADisabled):
        product_ca.ensure_default_ui_server_cert()
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def test_enrollment_token_omits_fingerprint_when_insecure(tmp_path, settings, monkeypatch):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    settings.LOGSTASHUI_CONFIG = {"agent": {"include_ca_fingerprint": True}}
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")

    payload = product_ca.build_enrollment_token_payload("secret-token")
    assert "fingerprint" not in payload
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def test_agent_requests_verify_false_when_insecure(tmp_path, settings, monkeypatch):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    assert product_ca.agent_requests_verify() is False
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def test_get_ui_tls_status_insecure_does_not_ensure(tmp_path, settings, monkeypatch):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    status = product_ca.get_ui_tls_status()
    assert status["insecure_http"] is True
    assert status["mode"] == "disabled"
    assert not status.get("product_ca_fingerprint")
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def test_get_agent_ui_url_default_rewrites_https(settings, monkeypatch):
    from Common import product_ca

    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    settings.LOGSTASHUI_CONFIG = {
        "agent": {"ui_url": "https://ui.example:8443", "include_ca_fingerprint": True}
    }

    class _Fake:
        agent_ui_url = "https://from-db.example:8443"

    monkeypatch.setattr(
        "Management.models.Settings.get_settings", lambda: _Fake()
    )
    url = product_ca.get_agent_ui_url_default()
    assert url.startswith("http://")
    assert "https://" not in url


def test_product_ca_endpoint_404_when_insecure(client, tmp_path, settings, monkeypatch):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    resp = client.get("/.well-known/logstashui/ca.crt")
    assert resp.status_code == 404
    tls_dir = settings.DATA_DIR / "tls"
    assert not tls_dir.exists() or not any(tls_dir.iterdir())


def _seed_custom_leaf(settings, tmp_path):
    from Common import product_ca

    product_ca._cached_cert_pem = None
    product_ca._cached_fingerprint = None
    settings.BASE_DIR = tmp_path
    settings.DATA_DIR = tmp_path / "data"
    settings.DATA_DIR.mkdir(exist_ok=True)
    tls = settings.DATA_DIR / "tls"
    tls.mkdir(exist_ok=True)
    cert_bytes = b"KEEP-CUSTOM-CERT"
    key_bytes = b"KEEP-CUSTOM-KEY"
    (tls / "ui-server.crt").write_bytes(cert_bytes)
    (tls / "ui-server.key").write_bytes(key_bytes)
    (tls / "ui-server.mode").write_text("custom")
    return tls, cert_bytes, key_bytes


def test_save_custom_raises_and_preserves_files_when_insecure(tmp_path, settings, monkeypatch):
    from Common import product_ca
    from Common.product_ca import ProductCADisabled

    tls, cert_bytes, key_bytes = _seed_custom_leaf(settings, tmp_path)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    with pytest.raises(ProductCADisabled):
        product_ca.save_custom_ui_certificate(b"NEW-CERT", b"NEW-KEY")
    assert (tls / "ui-server.crt").read_bytes() == cert_bytes
    assert (tls / "ui-server.key").read_bytes() == key_bytes
    assert (tls / "ui-server.mode").read_text() == "custom"


def test_revert_raises_and_preserves_files_when_insecure(tmp_path, settings, monkeypatch):
    from Common import product_ca
    from Common.product_ca import ProductCADisabled

    tls, cert_bytes, key_bytes = _seed_custom_leaf(settings, tmp_path)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    with pytest.raises(ProductCADisabled):
        product_ca.revert_ui_certificate_to_product_default()
    assert (tls / "ui-server.crt").read_bytes() == cert_bytes
    assert (tls / "ui-server.key").read_bytes() == key_bytes
    assert (tls / "ui-server.mode").read_text() == "custom"


def test_tls_upload_409_preserves_custom_leaf_when_insecure(
    admin_client, tmp_path, settings, monkeypatch
):
    from django.core.files.uploadedfile import SimpleUploadedFile

    tls, cert_bytes, key_bytes = _seed_custom_leaf(settings, tmp_path)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    resp = admin_client.post(
        "/Management/Settings/Tls/",
        {
            "certificate": SimpleUploadedFile("cert.pem", b"NEW-CERT"),
            "private_key": SimpleUploadedFile("key.pem", b"NEW-KEY"),
        },
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["success"] is False
    assert "INSECURE_HTTP" in data["message"]
    assert (tls / "ui-server.crt").read_bytes() == cert_bytes
    assert (tls / "ui-server.key").read_bytes() == key_bytes


def test_tls_revert_409_preserves_custom_leaf_when_insecure(
    admin_client, tmp_path, settings, monkeypatch
):
    tls, cert_bytes, key_bytes = _seed_custom_leaf(settings, tmp_path)
    monkeypatch.setenv("LOGSTASHUI_INSECURE_HTTP", "true")
    resp = admin_client.post(
        "/Management/Settings/Tls/Revert/",
        data="{}",
        content_type="application/json",
    )
    assert resp.status_code == 409
    data = resp.json()
    assert data["success"] is False
    assert "INSECURE_HTTP" in data["message"]
    assert (tls / "ui-server.crt").read_bytes() == cert_bytes
    assert (tls / "ui-server.key").read_bytes() == key_bytes
    assert (tls / "ui-server.mode").read_text() == "custom"
