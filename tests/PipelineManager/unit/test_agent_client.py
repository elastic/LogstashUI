#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""UI → agent API authentication headers."""

from unittest.mock import Mock, patch

import json
import pytest

from PipelineManager.agent_client import agent_auth_headers
from PipelineManager.models import Connection, Policy


@pytest.fixture
def embedded_key(settings):
    settings.LOGSTASH_AGENT_API_KEY = "embedded-secret"
    return "embedded-secret"


@pytest.fixture
def enrolled_conn(db):
    policy = Policy.objects.create(
        name="Sim Policy",
        settings_path="/etc/logstash/",
        logs_path="/var/log/logstash",
        binary_path="/usr/share/logstash/bin",
        policy_type=Policy.PolicyType.SIMULATE,
    )
    return Connection.objects.create(
        name="sim-1",
        connection_type="AGENT",
        host="sim.example.com",
        agent_id="sim-agent-1",
        policy=policy,
    )


def test_no_connection_uses_embedded_key(embedded_key):
    assert agent_auth_headers() == {"Authorization": "ApiKey embedded-secret"}


def test_no_embedded_key_configured_sends_nothing(settings):
    settings.LOGSTASH_AGENT_API_KEY = None
    assert agent_auth_headers() == {}


@pytest.mark.django_db
def test_embedded_connection_uses_embedded_key(embedded_key):
    from PipelineManager.agent_modes import ensure_embedded_connection

    conn = ensure_embedded_connection(probe=False)
    assert agent_auth_headers(conn) == {"Authorization": "ApiKey embedded-secret"}
    assert agent_auth_headers(conn.pk) == {"Authorization": "ApiKey embedded-secret"}


def test_enrolled_connection_uses_its_own_key(enrolled_conn, embedded_key):
    enrolled_conn.agent_inbound_key = "conn-secret"
    enrolled_conn.save()
    assert agent_auth_headers(enrolled_conn) == {"Authorization": "ApiKey conn-secret"}
    assert agent_auth_headers(enrolled_conn.pk) == {"Authorization": "ApiKey conn-secret"}


def test_enrolled_connection_without_key_never_gets_embedded_key(enrolled_conn, embedded_key):
    assert agent_auth_headers(enrolled_conn) == {}


@pytest.mark.django_db
def test_unknown_connection_id_sends_nothing(embedded_key):
    assert agent_auth_headers(999999) == {}


@pytest.mark.django_db
@patch("PipelineManager.simulation.requests.get")
def test_simulation_view_sends_auth_header(mock_get, authenticated_client, embedded_key):
    mock_get.return_value = Mock(status_code=200, json=Mock(return_value={"running_pipelines": []}))
    response = authenticated_client.get(
        "/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=slot1-filter1"
    )
    assert response.status_code == 200
    assert json.loads(response.content)["is_running"] is False
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"].startswith("ApiKey ")
