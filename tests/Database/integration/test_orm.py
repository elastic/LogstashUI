#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
ORM integration tests against real database containers.

All Django interaction happens in subprocesses so each test gets a clean
interpreter with the container env applied to settings.  Each test migrates
(idempotently) then runs its CRUD script which self-cleans at the end.
"""

import json
import os
import subprocess
import sys

import pytest

from LogstashUI import migrate_engine as me


# ---------------------------------------------------------------------------
# Subprocess helper
# ---------------------------------------------------------------------------

def _run_python(code: str, extra_env: dict[str, str]) -> str:
    env = os.environ.copy()
    env.update(extra_env)
    env.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
    me._with_package_pythonpath(env)
    proc = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"python -c exited {proc.returncode}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc.stdout


def _migrate(env: dict[str, str]) -> None:
    me.run_manage(["migrate", "--noinput", "--verbosity", "0"], env)


# ---------------------------------------------------------------------------
# Inline CRUD scripts (each cleans up its own data)
# ---------------------------------------------------------------------------

_POLICY_CRUD = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Policy
TAG = "crud-policy-test"
Policy.objects.filter(name=TAG).delete()
p = Policy.objects.create(
    name=TAG,
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
pk = p.pk
assert Policy.objects.get(pk=pk).name == TAG
Policy.objects.filter(pk=pk).update(logstash_yml="http.host: 127.0.0.1")
assert Policy.objects.get(pk=pk).logstash_yml == "http.host: 127.0.0.1"
Policy.objects.filter(pk=pk).delete()
assert Policy.objects.filter(pk=pk).count() == 0
print(json.dumps({"ok": True}))
"""

_CONNECTION_CRUD = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Connection, Policy
Policy.objects.filter(name="crud-conn-policy").delete()
policy = Policy.objects.create(
    name="crud-conn-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
Connection.objects.filter(name="crud-conn-test").delete()
c = Connection.objects.create(
    name="crud-conn-test",
    connection_type=Connection.ConnectionType.AGENT,
    host="127.0.0.1",
    policy=policy,
    status_blob={"health": "green"},
)
pk = c.pk
assert Connection.objects.get(pk=pk).name == "crud-conn-test"
Connection.objects.filter(pk=pk).update(status_blob={"health": "yellow"})
assert Connection.objects.get(pk=pk).status_blob["health"] == "yellow"
Connection.objects.filter(pk=pk).delete()
policy.delete()
assert Connection.objects.filter(pk=pk).count() == 0
print(json.dumps({"ok": True}))
"""

_PIPELINE_CRUD = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Pipeline, Policy
Policy.objects.filter(name="crud-pipe-policy").delete()
policy = Policy.objects.create(
    name="crud-pipe-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
Pipeline.objects.filter(policy=policy, name="test-pipeline").delete()
p = Pipeline.objects.create(
    policy=policy,
    name="test-pipeline",
    lscl="input { stdin{} } output { stdout{} }",
)
pk = p.pk
assert Pipeline.objects.get(pk=pk).name == "test-pipeline"
Pipeline.objects.filter(pk=pk).delete()
policy.delete()
assert Pipeline.objects.filter(pk=pk).count() == 0
print(json.dumps({"ok": True}))
"""

_REVISION_JSON = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Policy, Revision
Policy.objects.filter(name="rev-json-policy").delete()
policy = Policy.objects.create(
    name="rev-json-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
snapshot = {
    "pipelines": [{"name": "main", "lscl": "input{} output{}"}],
    "meta": {"tags": ["a", "b"], "nested": {"k": 1}},
}
r = Revision.objects.create(
    policy=policy, revision_number=1, snapshot_json=snapshot, created_by="testrunner"
)
pk = r.pk
fetched = Revision.objects.get(pk=pk)
assert fetched.snapshot_json == snapshot, f"mismatch: {fetched.snapshot_json!r}"
Revision.objects.filter(pk=pk).delete()
policy.delete()
print(json.dumps({"ok": True}))
"""

_STATUS_BLOB_JSON = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Connection, Policy
Policy.objects.filter(name="blob-policy").delete()
policy = Policy.objects.create(
    name="blob-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
blob = {"health": "green", "n": 42, "nested": {"k": [1, 2, 3]}}
Connection.objects.filter(name="blob-conn").delete()
c = Connection.objects.create(
    name="blob-conn",
    connection_type=Connection.ConnectionType.AGENT,
    host="127.0.0.1",
    policy=policy,
    status_blob=blob,
)
pk = c.pk
fetched = Connection.objects.get(pk=pk)
assert fetched.status_blob == blob, f"mismatch: {fetched.status_blob!r}"
Connection.objects.filter(pk=pk).delete()
policy.delete()
print(json.dumps({"ok": True}))
"""

_STATUS_BLOB_NULL = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from PipelineManager.models import Connection, Policy
Policy.objects.filter(name="null-blob-policy").delete()
policy = Policy.objects.create(
    name="null-blob-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
Connection.objects.filter(name="null-blob-conn").delete()
c = Connection.objects.create(
    name="null-blob-conn",
    connection_type=Connection.ConnectionType.AGENT,
    host="127.0.0.1",
    policy=policy,
    status_blob=None,
)
pk = c.pk
assert Connection.objects.get(pk=pk).status_blob is None
Connection.objects.filter(pk=pk).delete()
policy.delete()
print(json.dumps({"ok": True}))
"""

_SNMP_NETWORK_CRUD = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from SNMP.models import Network
Network.objects.filter(name="crud-network-test").delete()
n = Network.objects.create(name="crud-network-test", network_range="10.0.0.0/24")
pk = n.pk
assert Network.objects.get(pk=pk).name == "crud-network-test"
Network.objects.filter(pk=pk).delete()
assert Network.objects.filter(pk=pk).count() == 0
print(json.dumps({"ok": True}))
"""

_UNIQUE_POLICY_NAME = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.db import IntegrityError
from PipelineManager.models import Policy
Policy.objects.filter(name="dupe-policy").delete()
p1 = Policy.objects.create(
    name="dupe-policy",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
try:
    Policy.objects.create(
        name="dupe-policy",
        logstash_yml="different",
        jvm_options="-Xmx512m",
        log4j2_properties="status = warn",
    )
    raise AssertionError("Expected IntegrityError for duplicate Policy.name")
except IntegrityError:
    pass
finally:
    Policy.objects.filter(name="dupe-policy").delete()
print(json.dumps({"ok": True}))
"""

_UNIQUE_PIPELINE_PER_POLICY = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.db import IntegrityError
from PipelineManager.models import Pipeline, Policy
Policy.objects.filter(name__in=["uq-pol-a", "uq-pol-b"]).delete()
pol_a = Policy.objects.create(
    name="uq-pol-a",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
pol_b = Policy.objects.create(
    name="uq-pol-b",
    logstash_yml="http.host: 0.0.0.0",
    jvm_options="-Xms512m",
    log4j2_properties="status = error",
)
# Same name under different policies is allowed
Pipeline.objects.create(policy=pol_a, name="shared-pipe", lscl="input{} output{}")
Pipeline.objects.create(policy=pol_b, name="shared-pipe", lscl="input{} output{}")
# Same name under same policy must raise
try:
    Pipeline.objects.create(policy=pol_a, name="shared-pipe", lscl="input{} output{}")
    raise AssertionError("Expected IntegrityError for duplicate pipeline name per policy")
except IntegrityError:
    pass
pol_a.delete()
pol_b.delete()
print(json.dumps({"ok": True}))
"""

# Validates utf8mb4_bin on MySQL and native case-sensitivity on PostgreSQL.
# "CaseNet" and "casenet" must be distinct; second "CaseNet" must fail.
_CASE_SENSITIVE_UNIQUE = """
import json, os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "LogstashUI.settings")
django.setup()
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from SNMP.models import Network
Network.objects.filter(name__in=["CaseNet", "casenet"]).delete()
try:
    Network.objects.create(name="CaseNet", network_range="10.1.0.0/24")
    # Different case must succeed. This is the actual collation assertion:
    # Network.save() -> full_clean() -> validate_unique() runs
    # SELECT ... WHERE name = 'casenet', which matches 'CaseNet' under a
    # case-insensitive collation and raises ValidationError.
    Network.objects.create(name="casenet", network_range="10.2.0.0/24")
    # Exact duplicate via the ORM: full_clean() rejects it before the INSERT.
    try:
        Network.objects.create(name="CaseNet", network_range="10.3.0.0/24")
        raise AssertionError("Expected ValidationError for duplicate Network.name")
    except ValidationError:
        pass
    # ...and the DB unique index still holds when full_clean() is bypassed.
    # bulk_create() does not call save(). atomic() so the aborted statement is
    # rolled back and the cleanup below can still run on PostgreSQL.
    try:
        with transaction.atomic():
            Network.objects.bulk_create(
                [Network(name="CaseNet", network_range="10.3.0.0/24")]
            )
        raise AssertionError("Expected IntegrityError for duplicate Network.name")
    except IntegrityError:
        pass
finally:
    Network.objects.filter(name__in=["CaseNet", "casenet"]).delete()
print(json.dumps({"ok": True}))
"""


# ---------------------------------------------------------------------------
# Tests (all parametrized over postgres + mysql via engine_env)
# ---------------------------------------------------------------------------

def test_policy_crud(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_POLICY_CRUD, full_env).strip())["ok"] is True


def test_connection_crud(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_CONNECTION_CRUD, full_env).strip())["ok"] is True


def test_pipeline_crud(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_PIPELINE_CRUD, full_env).strip())["ok"] is True


def test_revision_json_roundtrip(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_REVISION_JSON, full_env).strip())["ok"] is True


def test_status_blob_roundtrip(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_STATUS_BLOB_JSON, full_env).strip())["ok"] is True


def test_status_blob_null_roundtrip(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_STATUS_BLOB_NULL, full_env).strip())["ok"] is True


def test_snmp_network_crud(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_SNMP_NETWORK_CRUD, full_env).strip())["ok"] is True


def test_unique_policy_name(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_UNIQUE_POLICY_NAME, full_env).strip())["ok"] is True


def test_unique_pipeline_per_policy(engine_env, tmp_path):
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_UNIQUE_PIPELINE_PER_POLICY, full_env).strip())["ok"] is True


def test_case_sensitive_unique(engine_env, tmp_path):
    """Both engines treat unique names as case-sensitive.

    On MySQL this validates utf8mb4_bin is active; on PostgreSQL it's the default.
    The collation check rides on validate_unique(), since Network.save() calls
    full_clean() and so never reaches the INSERT. The DB-level unique index is
    verified separately via bulk_create(), which bypasses save().
    """
    engine, env = engine_env
    full_env = {**env, "LOGSTASHUI_DATA_DIR": str(tmp_path)}
    _migrate(full_env)
    assert json.loads(_run_python(_CASE_SENSITIVE_UNIQUE, full_env).strip())["ok"] is True
