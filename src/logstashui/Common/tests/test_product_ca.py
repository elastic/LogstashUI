#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for product CA generation and enrollment token payload."""

import hashlib

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
    (tmp_path / "data").mkdir(exist_ok=True)

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
    (tmp_path / "data").mkdir(exist_ok=True)
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
    (tmp_path / "data").mkdir(exist_ok=True)
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
    (tmp_path / "data").mkdir(exist_ok=True)

    resp = client.get("/.well-known/logstashui/ca.crt")
    assert resp.status_code == 200
    assert b"BEGIN CERTIFICATE" in resp.content
