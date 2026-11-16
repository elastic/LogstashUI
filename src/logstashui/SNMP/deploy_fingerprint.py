#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Fingerprint of every input that feeds SNMP pipeline generation.

The undeployed-changes indicator compares this against the fingerprint stored
at the last deploy. Equal fingerprints mean generation would produce the same
pipelines and keystore values, so a change that is reverted, a save with no
edits, or a secret re-entered with the same value does not light the indicator.

Only input rows are hashed; no pipeline is generated. Secrets are hashed by
plaintext because Fernet ciphertext changes on every save.

Not covered: drift made outside LogstashUI (a CPM pipeline edited directly in
Elasticsearch, or an agent's SNMP pipeline deleted by hand). Opening the deploy
diff still catches those.
"""

import hashlib
import json
import os

from django.conf import settings

from Common.encryption import decrypt_credential
from PipelineManager.models import Connection

from .models import Credential, Device, DeviceTemplate, Network, Profile

_TIMESTAMP_FIELDS = {'created_at', 'updated_at'}

_TEMPLATE_FIELDS = ('id', 'name', 'type', 'vendor', 'product', 'model')
_PROFILE_FIELDS = ('id', 'name', 'profile_data', 'normalizers')
_CREDENTIAL_FIELDS = (
    'id', 'version', 'security_name', 'security_level', 'auth_protocol',
    'priv_protocol', 'community', 'auth_pass', 'priv_pass',
)
_CREDENTIAL_SECRETS = {'community', 'auth_pass', 'priv_pass'}
_CONNECTION_FIELDS = (
    'id', 'host', 'port', 'cloud_id', 'allow_self_signed_certs', 'policy_id',
    'username', 'password', 'api_key',
)
_CONNECTION_SECRETS = {'password', 'api_key'}

_CHUNK = 2000


def _model_fields(model):
    """Return every concrete column of ``model`` except the timestamps.

    New columns are picked up automatically. A column that changes at runtime
    without a user edit must be excluded here, or the indicator never clears.
    """
    return tuple(
        f.attname for f in model._meta.concrete_fields
        if f.name not in _TIMESTAMP_FIELDS
    )


def _secret_digest(ciphertext):
    """Return a SHA-256 of the decrypted secret, or ``''`` when unset.

    An undecryptable value hashes its ciphertext so the fingerprint is still
    stable and a later fix to the key registers as a change.
    """
    if not ciphertext:
        return ''
    try:
        plaintext = decrypt_credential(ciphertext)
    except Exception:
        plaintext = f'undecryptable:{ciphertext}'
    return hashlib.sha256(str(plaintext).encode('utf-8')).hexdigest()


def _official_profile_files():
    """Yield ``(filename, sha256)`` for the bundled official profile JSON files."""
    directory = os.path.join(settings.BASE_DIR, 'SNMP', 'data', 'official_profiles')
    try:
        names = sorted(os.listdir(directory))
    except OSError:
        return
    for name in names:
        path = os.path.join(directory, name)
        try:
            with open(path, 'rb') as fh:
                yield name, hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            yield name, 'unreadable'


def compute_input_fingerprint():
    """Return a SHA-256 hex digest of the SNMP pipeline-generation inputs.

    Rows are streamed in primary-key order, serialized with sorted keys, and
    fed into one hash, so the result depends only on stored values.

    Returns:
        64-character hex string.

    Examples:
        >>> fp = compute_input_fingerprint()  # doctest: +SKIP
        >>> fp == compute_input_fingerprint()  # doctest: +SKIP
        True
    """
    digest = hashlib.sha256()

    def feed(section, rows):
        digest.update(f'[{section}]\n'.encode('utf-8'))
        for row in rows:
            digest.update(json.dumps(row, sort_keys=True, default=str).encode('utf-8'))
            digest.update(b'\n')

    def stream(queryset, fields):
        return queryset.order_by('pk').values_list(*fields).iterator(chunk_size=_CHUNK)

    def with_secrets(rows, fields, secrets):
        secret_idx = [i for i, name in enumerate(fields) if name in secrets]
        for row in rows:
            row = list(row)
            for i in secret_idx:
                row[i] = _secret_digest(row[i])
            yield row

    feed('version', [getattr(settings, '__VERSION__', '')])
    feed('network', stream(Network.objects.all(), _model_fields(Network)))
    feed('device', stream(Device.objects.all(), _model_fields(Device)))
    feed('template', stream(DeviceTemplate.objects.all(), _TEMPLATE_FIELDS))
    feed('template_profiles', stream(
        DeviceTemplate.profiles.through.objects.all(),
        ('devicetemplate_id', 'profile_id'),
    ))
    feed('profile', stream(Profile.objects.all(), _PROFILE_FIELDS))
    feed('official_profile_files', _official_profile_files())
    feed('credential', with_secrets(
        stream(Credential.objects.all(), _CREDENTIAL_FIELDS),
        _CREDENTIAL_FIELDS, _CREDENTIAL_SECRETS,
    ))

    connection_ids = {
        pk for pair in Network.objects.values_list('connection_id', 'agent_connection_id')
        for pk in pair if pk is not None
    }
    feed('connection', with_secrets(
        stream(Connection.objects.filter(pk__in=connection_ids), _CONNECTION_FIELDS),
        _CONNECTION_FIELDS, _CONNECTION_SECRETS,
    ))

    return digest.hexdigest()
