#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/pipelines_views.py — pipeline REST endpoints."""

import json
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import Connection, Pipeline, Policy, Revision, SimulationResult
from PipelineManager.simulation import SimulationStart


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def policy(db):
    return Policy.objects.create(
        name='Test Policy',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='',
    )


@pytest.fixture
def pipeline(db, policy):
    return Pipeline.objects.create(
        policy=policy,
        name='test-pipeline',
        lscl='input { beats { port => 5044 } } filter {} output { stdout {} }',
        description='A test pipeline',
        managed_by='user',
    )


@pytest.fixture
def readonly_user(db):
    user = User.objects.create_user(username='rouser', password='Sup3rS3cur3!Pass')
    UserProfile.objects.update_or_create(user=user, defaults={'role': 'readonly'})
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    client.login(username='rouser', password='Sup3rS3cur3!Pass')
    return client


_SIMPLE_LSCL = 'input { beats { port => 5044 } } filter { mutate { add_field => { "x" => "y" } } } output { stdout {} }'


def _post(client, url, body, **headers):
    return client.post(url, data=json.dumps(body), content_type='application/json', **headers)


def _put(client, url, body, **headers):
    return client.put(url, data=json.dumps(body), content_type='application/json', **headers)


# ---------------------------------------------------------------------------
# Agent Pipeline — List
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentPipelineList:

    def test_list_requires_policy_id(self, authenticated_client):
        response = authenticated_client.get('/api/pipelines/')
        assert response.status_code == 400

    def test_list_404_for_unknown_policy(self, authenticated_client):
        response = authenticated_client.get('/api/pipelines/?policy_id=99999')
        assert response.status_code == 404

    def test_list_returns_200(self, authenticated_client, policy, pipeline):
        response = authenticated_client.get(f'/api/pipelines/?policy_id={policy.id}')
        assert response.status_code == 200

    def test_list_envelope_fields(self, authenticated_client, policy):
        data = authenticated_client.get(f'/api/pipelines/?policy_id={policy.id}').json()
        for key in ('policy_id', 'policy_name', 'has_undeployed_changes', 'pipelines', 'count'):
            assert key in data

    def test_list_includes_pipeline(self, authenticated_client, policy, pipeline):
        data = authenticated_client.get(f'/api/pipelines/?policy_id={policy.id}').json()
        ids = [p['id'] for p in data['pipelines']]
        assert pipeline.id in ids

    def test_list_only_user_pipelines_by_default(self, authenticated_client, policy):
        Pipeline.objects.create(policy=policy, name='snmp-pipe', lscl='input{}filter{}output{}', managed_by='snmp')
        data = authenticated_client.get(f'/api/pipelines/?policy_id={policy.id}').json()
        names = [p['name'] for p in data['pipelines']]
        assert 'snmp-pipe' not in names

    def test_list_no_auth_returns_401(self, client, policy):
        response = client.get(f'/api/pipelines/?policy_id={policy.id}')
        assert response.status_code == 401

    def test_list_wrong_method_returns_405(self, authenticated_client):
        response = authenticated_client.patch('/api/pipelines/')
        assert response.status_code == 405


# ---------------------------------------------------------------------------
# Agent Pipeline — Create
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentPipelineCreate:

    def test_create_returns_201(self, authenticated_client, policy):
        response = _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id,
            'name': 'new-pipe',
            'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 201
        assert response.json()['success'] is True
        assert 'id' in response.json()

    def test_create_persists_to_db(self, authenticated_client, policy):
        _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id, 'name': 'persisted', 'lscl': _SIMPLE_LSCL,
        })
        assert Pipeline.objects.filter(name='persisted', policy=policy).exists()

    def test_create_marks_undeployed(self, authenticated_client, policy):
        policy.has_undeployed_changes = False
        policy.save()
        _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id, 'name': 'dirty', 'lscl': _SIMPLE_LSCL,
        })
        policy.refresh_from_db()
        assert policy.has_undeployed_changes is True

    def test_create_missing_policy_id_returns_400(self, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/', {
            'name': 'nopolicy', 'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 400

    def test_create_missing_name_returns_400(self, authenticated_client, policy):
        response = _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id, 'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 400

    def test_create_missing_lscl_returns_400(self, authenticated_client, policy):
        response = _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id, 'name': 'nolscl',
        })
        assert response.status_code == 400

    def test_create_unknown_policy_returns_404(self, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/', {
            'policy_id': 99999, 'name': 'x', 'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 404

    def test_create_no_auth_returns_401(self, client):
        response = _post(client, '/api/pipelines/', {'policy_id': 1, 'name': 'x', 'lscl': 'y'})
        assert response.status_code == 401

    def test_create_readonly_returns_403(self, readonly_client):
        response = _post(readonly_client, '/api/pipelines/', {'policy_id': 1, 'name': 'x', 'lscl': 'y'})
        assert response.status_code == 403

    def test_create_with_settings(self, authenticated_client, policy):
        _post(authenticated_client, '/api/pipelines/', {
            'policy_id': policy.id,
            'name': 'with-settings',
            'lscl': _SIMPLE_LSCL,
            'pipeline_workers': 4,
            'pipeline_batch_size': 256,
            'queue_type': 'persisted',
        })
        p = Pipeline.objects.get(name='with-settings', policy=policy)
        assert p.pipeline_workers == 4
        assert p.pipeline_batch_size == 256
        assert p.queue_type == 'persisted'


# ---------------------------------------------------------------------------
# Agent Pipeline — Get
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentPipelineGet:

    def test_get_returns_200(self, authenticated_client, pipeline):
        response = authenticated_client.get(f'/api/pipelines/{pipeline.id}/')
        assert response.status_code == 200
        assert response.json()['pipeline']['id'] == pipeline.id

    def test_get_returns_full_fields(self, authenticated_client, pipeline):
        p = authenticated_client.get(f'/api/pipelines/{pipeline.id}/').json()['pipeline']
        for field in ('id', 'policy_id', 'name', 'managed_by', 'description', 'lscl',
                      'pipeline_hash', 'last_updated', 'revision_number',
                      'pipeline_workers', 'pipeline_batch_size', 'pipeline_batch_delay',
                      'queue_type', 'queue_max_bytes', 'queue_checkpoint_writes',
                      'no_input', 'non_reloadable'):
            assert field in p, f'Missing field: {field}'

    def test_get_nonexistent_returns_404(self, authenticated_client):
        assert authenticated_client.get('/api/pipelines/99999/').status_code == 404

    def test_get_no_auth_returns_401(self, client, pipeline):
        assert client.get(f'/api/pipelines/{pipeline.id}/').status_code == 401

    def test_get_readonly_allowed(self, readonly_client, pipeline):
        assert readonly_client.get(f'/api/pipelines/{pipeline.id}/').status_code == 200


# ---------------------------------------------------------------------------
# Agent Pipeline — Update
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentPipelineUpdate:

    def test_update_lscl(self, authenticated_client, pipeline):
        new_lscl = 'input{} filter{ mutate{} } output{}'
        _put(authenticated_client, f'/api/pipelines/{pipeline.id}/', {'lscl': new_lscl})
        pipeline.refresh_from_db()
        assert pipeline.lscl == new_lscl

    def test_update_description(self, authenticated_client, pipeline):
        _put(authenticated_client, f'/api/pipelines/{pipeline.id}/', {'description': 'Updated desc'})
        pipeline.refresh_from_db()
        assert pipeline.description == 'Updated desc'

    def test_update_settings(self, authenticated_client, pipeline):
        _put(authenticated_client, f'/api/pipelines/{pipeline.id}/', {
            'pipeline_workers': 8, 'queue_type': 'persisted',
        })
        pipeline.refresh_from_db()
        assert pipeline.pipeline_workers == 8
        assert pipeline.queue_type == 'persisted'

    def test_update_marks_undeployed(self, authenticated_client, pipeline, policy):
        policy.has_undeployed_changes = False
        policy.save()
        _put(authenticated_client, f'/api/pipelines/{pipeline.id}/', {'description': 'x'})
        policy.refresh_from_db()
        assert policy.has_undeployed_changes is True

    def test_update_recomputes_hash(self, authenticated_client, pipeline):
        old_hash = pipeline.pipeline_hash
        _put(authenticated_client, f'/api/pipelines/{pipeline.id}/', {
            'lscl': 'input{} filter{ grok{} } output{}',
        })
        pipeline.refresh_from_db()
        assert pipeline.pipeline_hash != old_hash

    def test_update_nonexistent_returns_404(self, authenticated_client):
        assert _put(authenticated_client, '/api/pipelines/99999/', {}).status_code == 404

    def test_update_no_auth_returns_401(self, client, pipeline):
        assert _put(client, f'/api/pipelines/{pipeline.id}/', {}).status_code == 401

    def test_update_readonly_returns_403(self, readonly_client, pipeline):
        assert _put(readonly_client, f'/api/pipelines/{pipeline.id}/', {}).status_code == 403


# ---------------------------------------------------------------------------
# Agent Pipeline — Delete
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAgentPipelineDelete:

    def test_delete_removes_row(self, authenticated_client, pipeline):
        pid = pipeline.id
        response = authenticated_client.delete(f'/api/pipelines/{pid}/')
        assert response.status_code == 200
        assert not Pipeline.objects.filter(id=pid).exists()

    def test_delete_marks_undeployed(self, authenticated_client, pipeline, policy):
        policy.has_undeployed_changes = False
        policy.save()
        authenticated_client.delete(f'/api/pipelines/{pipeline.id}/')
        policy.refresh_from_db()
        assert policy.has_undeployed_changes is True

    def test_delete_nonexistent_returns_404(self, authenticated_client):
        assert authenticated_client.delete('/api/pipelines/99999/').status_code == 404

    def test_delete_no_auth_returns_401(self, client, pipeline):
        assert client.delete(f'/api/pipelines/{pipeline.id}/').status_code == 401

    def test_delete_readonly_returns_403(self, readonly_client, pipeline):
        assert readonly_client.delete(f'/api/pipelines/{pipeline.id}/').status_code == 403

    def test_delete_wrong_method_returns_405(self, authenticated_client, pipeline):
        assert authenticated_client.patch(f'/api/pipelines/{pipeline.id}/').status_code == 405


# ---------------------------------------------------------------------------
# Deploy
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPolicyDeploy:

    def test_deploy_returns_200(self, authenticated_client, policy):
        response = authenticated_client.post(f'/api/pipelines/policies/{policy.id}/deploy/',
                                             content_type='application/json')
        assert response.status_code == 200
        assert response.json()['success'] is True

    def test_deploy_creates_revision(self, authenticated_client, policy):
        before = Revision.objects.filter(policy=policy).count()
        authenticated_client.post(f'/api/pipelines/policies/{policy.id}/deploy/',
                                  content_type='application/json')
        assert Revision.objects.filter(policy=policy).count() == before + 1

    def test_deploy_increments_revision_number(self, authenticated_client, policy):
        old = policy.current_revision_number
        authenticated_client.post(f'/api/pipelines/policies/{policy.id}/deploy/',
                                  content_type='application/json')
        policy.refresh_from_db()
        assert policy.current_revision_number == old + 1

    def test_deploy_sets_last_deployed_at(self, authenticated_client, policy):
        assert policy.last_deployed_at is None
        authenticated_client.post(f'/api/pipelines/policies/{policy.id}/deploy/',
                                  content_type='application/json')
        policy.refresh_from_db()
        assert policy.last_deployed_at is not None

    def test_deploy_response_contains_revision_number(self, authenticated_client, policy):
        data = authenticated_client.post(
            f'/api/pipelines/policies/{policy.id}/deploy/',
            content_type='application/json',
        ).json()
        assert 'revision_number' in data
        assert data['revision_number'] >= 1

    def test_deploy_nonexistent_policy_returns_404(self, authenticated_client):
        response = authenticated_client.post('/api/pipelines/policies/99999/deploy/',
                                             content_type='application/json')
        assert response.status_code == 404

    def test_deploy_get_returns_405(self, authenticated_client, policy):
        assert authenticated_client.get(f'/api/pipelines/policies/{policy.id}/deploy/').status_code == 405

    def test_deploy_no_auth_returns_401(self, client, policy):
        assert client.post(f'/api/pipelines/policies/{policy.id}/deploy/').status_code == 401

    def test_deploy_readonly_returns_403(self, readonly_client, policy):
        assert readonly_client.post(f'/api/pipelines/policies/{policy.id}/deploy/').status_code == 403


# ---------------------------------------------------------------------------
# Centralized (CPM) Logstash pipelines (mock Elasticsearch client)
# ---------------------------------------------------------------------------

_CPM_PIPELINE_BODY = {
    'my-pipe': {
        'description': 'test',
        'pipeline': 'input{} filter{} output{}',
        'last_modified': '2026-01-01T00:00:00.000Z',
        'username': 'admin',
        'pipeline_settings': {'pipeline.workers': 1},
    }
}


@pytest.mark.django_db
class TestCentralizedPipelineList:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        response = authenticated_client.get(f'/api/pipelines/centralized/{test_connection.id}/')
        assert response.status_code == 200

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_returns_pipelines(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        data = authenticated_client.get(f'/api/pipelines/centralized/{test_connection.id}/').json()
        assert data['count'] == 1
        assert data['pipelines'][0]['name'] == 'my-pipe'
        assert data['pipelines'][0]['lscl'] == 'input{} filter{} output{}'

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_can_omit_lscl(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.return_value.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        data = authenticated_client.get(
            f'/api/pipelines/centralized/{test_connection.id}/?include_lscl=false'
        ).json()
        assert data['pipelines'][0]['name'] == 'my-pipe'
        assert 'lscl' not in data['pipelines'][0]

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_es_error_returns_502(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('Connection refused')
        response = authenticated_client.get(f'/api/pipelines/centralized/{test_connection.id}/')
        assert response.status_code == 502

    def test_list_no_auth_returns_401(self, client, test_connection):
        assert client.get(f'/api/pipelines/centralized/{test_connection.id}/').status_code == 401

    @patch('API.pipelines_views.get_elastic_connection')
    def test_deprecated_es_alias_still_routes(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        assert authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/').status_code == 200
        assert authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/my-pipe/').status_code == 200


@pytest.mark.django_db
class TestCentralizedPipelineCreate:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_returns_201(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = _post(authenticated_client, f'/api/pipelines/centralized/{test_connection.id}/', {
            'name': 'new-es-pipe', 'lscl': 'input{} filter{} output{}',
        })
        assert response.status_code == 201
        mock_es.logstash.put_pipeline.assert_called_once()

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_missing_name_returns_400(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.return_value = MagicMock()
        response = _post(authenticated_client, f'/api/pipelines/centralized/{test_connection.id}/', {
            'lscl': 'input{} filter{} output{}',
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_missing_lscl_returns_400(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.return_value = MagicMock()
        response = _post(authenticated_client, f'/api/pipelines/centralized/{test_connection.id}/', {
            'name': 'x',
        })
        assert response.status_code == 400

    def test_create_no_auth_returns_401(self, client, test_connection):
        assert _post(client, f'/api/pipelines/centralized/{test_connection.id}/', {}).status_code == 401

    def test_create_readonly_returns_403(self, readonly_client, test_connection):
        assert _post(readonly_client, f'/api/pipelines/centralized/{test_connection.id}/', {}).status_code == 403


@pytest.mark.django_db
class TestCentralizedPipelineGet:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_get_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        response = authenticated_client.get(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/')
        assert response.status_code == 200
        assert response.json()['pipeline']['name'] == 'my-pipe'

    @patch('API.pipelines_views.get_elastic_connection')
    def test_get_es_error_surfaces_as_error(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('404 not found')
        response = authenticated_client.get(f'/api/pipelines/centralized/{test_connection.id}/missing-pipe/')
        assert response.status_code == 404

    def test_get_no_auth_returns_401(self, client, test_connection):
        assert client.get(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/').status_code == 401


@pytest.mark.django_db
class TestCentralizedPipelineUpdate:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_update_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = _put(authenticated_client, f'/api/pipelines/centralized/{test_connection.id}/my-pipe/', {
            'lscl': 'input{} filter{ mutate{} } output{}',
        })
        assert response.status_code == 200
        mock_es.logstash.put_pipeline.assert_called_once()

    @patch('API.pipelines_views.get_elastic_connection')
    def test_update_merges_existing_settings(self, mock_get_es, authenticated_client, test_connection):
        """Unspecified settings are preserved from the existing pipeline."""
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _CPM_PIPELINE_BODY
        mock_es.logstash.put_pipeline.return_value = {}
        mock_get_es.return_value = mock_es
        _put(authenticated_client, f'/api/pipelines/centralized/{test_connection.id}/my-pipe/', {
            'pipeline_workers': 4,
        })
        call_body = mock_es.logstash.put_pipeline.call_args[1]['body']
        assert call_body['pipeline_settings']['pipeline.workers'] == 4
        # pipeline.batch.size should fall back to the existing value (or default)
        assert 'pipeline.batch.size' in call_body['pipeline_settings']

    def test_update_no_auth_returns_401(self, client, test_connection):
        assert _put(client, f'/api/pipelines/centralized/{test_connection.id}/my-pipe/', {}).status_code == 401

    def test_update_readonly_returns_403(self, readonly_client, test_connection):
        assert _put(readonly_client, f'/api/pipelines/centralized/{test_connection.id}/my-pipe/', {}).status_code == 403


@pytest.mark.django_db
class TestCentralizedPipelineDelete:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_delete_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = authenticated_client.delete(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/')
        assert response.status_code == 200
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='my-pipe')

    @patch('API.pipelines_views.get_elastic_connection')
    def test_delete_es_error_returns_error(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('404 not found')
        response = authenticated_client.delete(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/')
        assert response.status_code == 404

    def test_delete_no_auth_returns_401(self, client, test_connection):
        assert client.delete(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/').status_code == 401

    def test_delete_readonly_returns_403(self, readonly_client, test_connection):
        assert readonly_client.delete(f'/api/pipelines/centralized/{test_connection.id}/my-pipe/').status_code == 403


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestPipelineFind:

    @pytest.fixture
    def cpm(self):
        """CPM pipelines returned by every CENTRALIZED connection."""
        with patch('API.pipelines_views.get_elastic_connection') as mock_get_es:
            get_pipeline = mock_get_es.return_value.options.return_value.logstash.get_pipeline
            get_pipeline.return_value = {
                'asa-new': {'last_modified': '2026-10-12T15:03:11.204Z'},
                'asa-new-fixed': {'last_modified': '2026-10-14T09:41:52.118Z'},
                'syslog': {},
            }
            yield get_pipeline

    def test_finds_cpm_pipeline_with_similar_names(self, authenticated_client, test_connection, cpm):
        response = authenticated_client.get('/api/pipelines/find/?name=asa-new')

        assert response.status_code == 200
        body = response.json()
        assert body['matches'] == [{
            'type': 'cpm', 'name': 'asa-new', 'connection_id': test_connection.id,
            'connection_name': test_connection.name, 'last_modified': '2026-10-12T15:03:11.204Z',
        }]
        assert [p['name'] for p in body['similar']] == ['asa-new-fixed']
        assert body['unreachable'] == []

    def test_topic_keyword_returns_every_pipeline_containing_it(
        self, authenticated_client, test_connection, cpm
    ):
        body = authenticated_client.get('/api/pipelines/find/?name=ASA').json()

        assert body['matches'] == []
        assert sorted(p['name'] for p in body['similar']) == ['asa-new', 'asa-new-fixed']

    def test_finds_agent_pipeline_and_cpm_pipeline_with_same_name(
        self, authenticated_client, test_connection, cpm, policy
    ):
        agent = Pipeline.objects.create(policy=policy, name='asa-new', lscl='', managed_by='user')

        matches = authenticated_client.get('/api/pipelines/find/?name=asa-new').json()['matches']

        assert {m['type'] for m in matches} == {'agent', 'cpm'}
        agent_match = next(m for m in matches if m['type'] == 'agent')
        assert agent_match == {
            'type': 'agent', 'name': 'asa-new', 'pipeline_id': agent.id, 'policy_id': policy.id,
            'policy_name': policy.name, 'managed_by': 'user',
            'last_modified': agent.last_updated.isoformat(),
        }

    def test_embedded_policies_are_not_searched(self, authenticated_client, policy):
        policy.policy_type = Policy.PolicyType.EMBEDDED
        policy.save()
        Pipeline.objects.create(policy=policy, name='asa-new', lscl='', managed_by='user')

        body = authenticated_client.get('/api/pipelines/find/?name=asa-new').json()

        assert body['matches'] == [] and body['similar'] == []

    def test_unreachable_connection_is_reported_not_treated_as_empty(
        self, authenticated_client, test_connection, cpm
    ):
        cpm.side_effect = Exception('connection timed out')

        body = authenticated_client.get('/api/pipelines/find/?name=asa-new').json()

        assert body['matches'] == []
        assert body['unreachable'] == [{
            'connection_id': test_connection.id, 'connection_name': test_connection.name,
            'error': 'connection timed out',
        }]

    def test_agent_connections_are_not_queried(self, authenticated_client, cpm):
        Connection.objects.create(name='agent-1', connection_type='AGENT', host='10.0.0.5')

        authenticated_client.get('/api/pipelines/find/?name=asa-new')

        cpm.assert_not_called()

    def test_name_is_required(self, authenticated_client):
        assert authenticated_client.get('/api/pipelines/find/?name=%20').status_code == 400

    def test_readonly_allowed(self, readonly_client):
        assert readonly_client.get('/api/pipelines/find/?name=x').status_code == 200

    def test_no_auth_returns_401(self, client):
        assert client.get('/api/pipelines/find/?name=x').status_code == 401

    def test_post_returns_405(self, authenticated_client):
        assert authenticated_client.post('/api/pipelines/find/?name=x').status_code == 405


_MUTATE_COMPONENTS = json.dumps({'filter': [{'plugin': 'mutate', 'id': 'mut1', 'config': {}}]})


def _started(run_id='run-a', slot_id=1, **fields):
    """A successful ``start_simulation`` result."""
    return SimulationStart(run_id=run_id, slot_id=slot_id, agent_url='http://agent', **fields)


def _agent_delivers(*results_per_call):
    """``send_simulation_event`` stand-in that stores results the way the agent would."""
    def send(agent_url, slot_id, run_id, log_text, agent_headers=None):
        for result in results_per_call[send.calls]:
            SimulationResult.add({**result, 'run_id': run_id})
        send.calls += 1
        return True, None
    send.calls = 0
    return send


@pytest.mark.django_db
class TestPipelineSimulate:

    @patch('API.pipelines_views.start_simulation')
    def test_simulate_missing_lscl_and_pipeline_id_returns_400(self, mock_start, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'event': 'some log line',
        })
        assert response.status_code == 400
        mock_start.assert_not_called()

    @patch('API.pipelines_views.start_simulation')
    def test_simulate_missing_event_returns_400(self, mock_start, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_no_filter_plugins_returns_400(self, mock_parse, mock_start, authenticated_client):
        mock_parse.logstash_config_to_components.return_value = json.dumps({'filter': []})
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': 'input{} output{}', 'event': 'test',
        })
        assert response.status_code == 400
        mock_start.assert_not_called()

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_success_with_lscl(self, mock_parse, mock_start, authenticated_client):
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started(slot_id=3)
        SimulationResult.add({'run_id': 'run-a', 'simulation': {'step': '0'}})
        SimulationResult.add({'run_id': 'run-a', 'snapshots': {'mut1': {}}, 'message': 'hello'})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'test log line', 'timeout': 10,
            'policy_id': 7, 'sim_connection_id': 2,
        })

        assert response.status_code == 200
        body = response.json()
        assert body['run_id'] == 'run-a' and body['slot_id'] == 3
        assert body['complete'] is True and body['count'] == 2
        assert not SimulationResult.objects.exists()
        args, kwargs = mock_start.call_args
        assert args[1] == 'test log line'
        assert kwargs['session'] == {}
        assert kwargs['policy_id'] == 7 and kwargs['sim_connection_id'] == 2

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_start_error_returns_502(self, mock_parse, mock_start, authenticated_client):
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = SimulationStart(
            error='Error allocating slot: boom', slot_id=2, pipeline_failed=True,
        )
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'x',
        })
        assert response.status_code == 502
        assert response.json() == {
            'success': False, 'error': 'Error allocating slot: boom', 'slot_id': 2,
        }

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_loads_lscl_from_pipeline_id(
        self, mock_parse, mock_start, authenticated_client, pipeline
    ):
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = SimulationStart(error='Error: boom')

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'pipeline_id': pipeline.id, 'event': 'test', 'timeout': 1,
        })
        mock_parse.logstash_config_to_components.assert_called_once_with(pipeline.lscl)
        assert response.status_code == 502

    @patch('API.pipelines_views.start_simulation')
    def test_simulate_unknown_pipeline_id_returns_404(self, mock_start, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'pipeline_id': 99999, 'event': 'test',
        })
        assert response.status_code == 404
        mock_start.assert_not_called()

    @pytest.mark.parametrize('timeout, clock', [(1, 5), (9999, 200)])
    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_timeout_returns_408(
        self, mock_parse, mock_start, mock_time, authenticated_client, timeout, clock
    ):
        """No results by the deadline is a 408; a timeout over 180 is clamped to 180."""
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started()
        mock_time.time.side_effect = [0, 0, clock, clock]

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'test', 'timeout': timeout,
        })
        assert response.status_code == 408
        assert response.json()['run_id'] == 'run-a'

    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_timeout_starts_after_slot_allocation(
        self, mock_parse, mock_start, mock_time, authenticated_client
    ):
        """A slow slot allocation doesn't use up the wait for results."""
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started()
        # Allocation finishes at t=100; the result lands during the first wait.
        mock_time.time.side_effect = [0, 100, 101, 102, 103]
        mock_time.sleep.side_effect = lambda _s: SimulationResult.add(
            {'run_id': 'run-a', 'snapshots': {'mut1': {}}})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'test', 'timeout': 30,
        })
        assert response.status_code == 200
        assert response.json()['complete'] is True

    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_send_error_returns_502(
        self, mock_parse, mock_start, mock_time, authenticated_client
    ):
        """When sending the event failed and nothing came back, the send error is reported."""
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started(forward_error='401 Client Error: Unauthorized')
        mock_time.time.side_effect = [0, 0, 5, 5]

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'test', 'timeout': 1,
        })
        assert response.status_code == 502
        assert '401 Client Error' in response.json()['error']

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_final_event_without_snapshots_completes(
        self, mock_parse, mock_start, authenticated_client
    ):
        """No filter ran (every filter is behind a conditional): the run still finishes."""
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started()
        SimulationResult.add({'run_id': 'run-a', 'message': 'x', 'simulation': {'id': 'original'}})
        SimulationResult.add({'run_id': 'run-a', 'message': 'x', 'simulation': {'id': 'final'}})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'x', 'detail': 'steps', 'timeout': 10,
        })
        body = response.json()
        assert response.status_code == 200
        assert body['complete'] is True
        assert body['final'] == {'message': 'x'} and body['steps'] == []
        assert body['elapsed_ms'] < 5000

    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_locked_database_is_retried(self, mock_parse, mock_start, authenticated_client):
        """A "database is locked" read is skipped for that tick; the results are read on the next."""
        from django.db import OperationalError

        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started()
        done = {'run-a': [{'run_id': 'run-a', 'snapshots': {'mut1': {}}}]}
        with patch('API.pipelines_views.SimulationResult.take',
                   side_effect=[OperationalError('database is locked'), done]):
            response = _post(authenticated_client, '/api/pipelines/simulate/', {
                'lscl': _SIMPLE_LSCL, 'event': 'x', 'timeout': 10,
            })
        assert response.status_code == 200
        assert response.json()['complete'] is True

    @pytest.mark.parametrize('body', [
        {'connection_id': 1},
        {'name': 'asa-new'},
        {'lscl': _SIMPLE_LSCL, 'connection_id': 1, 'name': 'asa-new'},
        {'pipeline_id': 1, 'connection_id': 1, 'name': 'asa-new'},
    ])
    @patch('API.pipelines_views.start_simulation')
    def test_simulate_cpm_source_conflicts_return_400(self, mock_start, authenticated_client, body):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'event': 'test', **body,
        })
        assert response.status_code == 400
        mock_start.assert_not_called()

    @patch('API.pipelines_views.get_elastic_connection')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_loads_lscl_from_cpm_pipeline(
        self, mock_parse, mock_start, mock_get_es, authenticated_client, test_connection
    ):
        mock_get_es.return_value.logstash.get_pipeline.return_value = {
            'asa-new': {'pipeline': 'filter { mutate {} }'},
        }
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = SimulationStart(error='Error: boom')

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'connection_id': test_connection.id, 'name': 'asa-new', 'event': 'test',
        })

        mock_get_es.return_value.logstash.get_pipeline.assert_called_once_with(id='asa-new')
        mock_parse.logstash_config_to_components.assert_called_once_with('filter { mutate {} }')
        assert response.status_code == 502

    @pytest.mark.parametrize('lookup', [
        {'return_value': {}},
        {'side_effect': Exception('404 Not Found')},
    ])
    @patch('API.pipelines_views.get_elastic_connection')
    @patch('API.pipelines_views.start_simulation')
    def test_simulate_unknown_cpm_pipeline_returns_404(
        self, mock_start, mock_get_es, authenticated_client, test_connection, lookup
    ):
        mock_get_es.return_value.logstash.get_pipeline.configure_mock(**lookup)
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'connection_id': test_connection.id, 'name': 'asa-fixed', 'event': 'test',
        })
        assert response.status_code == 404
        assert 'asa-fixed' in response.json()['error']
        mock_start.assert_not_called()

    @patch('API.pipelines_views.start_simulation')
    def test_simulate_unknown_cpm_connection_returns_404(self, mock_start, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'connection_id': 999999, 'name': 'asa-new', 'event': 'test',
        })
        assert response.status_code == 404
        mock_start.assert_not_called()

    @pytest.mark.parametrize('body', [
        {'event': 'one', 'events': ['two']},
        {'events': []},
        {'events': 'not-a-list'},
        {'events': ['x'] * 101},
        {'events': ['ok', '  ']},
        {'events': ['ok', 42]},
    ])
    @patch('API.pipelines_views.start_simulation')
    def test_simulate_bulk_invalid_events_returns_400(self, mock_start, authenticated_client, body):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, **body,
        })
        assert response.status_code == 400
        mock_start.assert_not_called()

    @patch('API.pipelines_views.send_simulation_event')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_bulk_reuses_slot_and_returns_events_in_order(
        self, mock_parse, mock_start, mock_send, authenticated_client
    ):
        """The first event starts the run; the rest go straight to the same slot."""
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started(slot_id=4, agent_headers={'Authorization': 'ApiKey k'})
        mock_send.side_effect = _agent_delivers([
            {'simulation': {'step': '0'}},
            {'snapshots': {'mut1': {}}, 'message': 'b'},
        ])
        SimulationResult.add({'run_id': 'other', 'snapshots': {'x': {}}})
        SimulationResult.add({'run_id': 'run-a', 'snapshots': {'mut1': {}}, 'message': 'a'})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL,
            'events': ['line a', {'message': 'b'}],
            'timeout': 5,
        })

        assert response.status_code == 200
        body = response.json()
        assert body['slot_id'] == 4
        assert body['count'] == 2 and body['complete_count'] == 2
        assert body['events'][0]['run_id'] == 'run-a'
        assert len(body['events'][1]['results']) == 2
        assert 'error' not in body['events'][0]
        assert list(SimulationResult.objects.values_list('run_id', flat=True)) == ['other']

        mock_start.assert_called_once()
        assert mock_start.call_args.args[1] == 'line a'
        agent_url, slot_id, run_id, log_text = mock_send.call_args.args
        assert (agent_url, slot_id) == ('http://agent', 4)
        assert run_id == body['events'][1]['run_id']
        assert json.loads(log_text) == {'message': 'b'}
        assert mock_send.call_args.kwargs['agent_headers'] == {'Authorization': 'ApiKey k'}

    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.send_simulation_event', return_value=(False, 'connection refused'))
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_bulk_partial_timeout_reports_incomplete_events(
        self, mock_parse, mock_start, mock_send, mock_time, authenticated_client
    ):
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = _started()
        mock_time.time.side_effect = [0, 0, 5, 5]
        SimulationResult.add({'run_id': 'run-a', 'snapshots': {'mut1': {}}})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'events': ['a', 'b'], 'timeout': 1,
        })

        assert response.status_code == 200
        body = response.json()
        assert body['complete_count'] == 1
        assert body['events'][0]['complete'] is True
        assert body['events'][1]['complete'] is False
        assert body['events'][1]['error'] == 'connection refused'

    @patch('API.pipelines_views.send_simulation_event')
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_bulk_first_event_failure_returns_502(
        self, mock_parse, mock_start, mock_send, authenticated_client
    ):
        mock_parse.logstash_config_to_components.return_value = _MUTATE_COMPONENTS
        mock_start.return_value = SimulationStart(error='Error allocating slot: boom')
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'events': ['a', 'b', 'c'],
        })
        assert response.status_code == 502
        mock_send.assert_not_called()

    @patch('API.pipelines_views.start_simulation')
    def test_simulate_invalid_detail_returns_400(self, mock_start, authenticated_client):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'event': 'x', 'detail': 'verbose',
        })
        assert response.status_code == 400
        assert 'detail' in response.json()['error']
        mock_start.assert_not_called()

    @pytest.mark.parametrize('body', [
        {'event': 'line a'},
        {'events': ['line a']},
    ])
    @patch('API.pipelines_views.start_simulation')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_steps_detail_returns_diffs_not_raw_results(
        self, mock_parse, mock_start, authenticated_client, body
    ):
        mock_parse.logstash_config_to_components.return_value = json.dumps({
            'filter': [{'plugin': 'grok', 'id': 'filter_grok_0', 'config': {'id': 'hdr'}}]
        })
        mock_start.return_value = _started()
        step = {'message': 'line a', 'w': 'line',
                'simulation': {'step': '1', 'id': 'filter_grok_0'}}
        SimulationResult.add({'run_id': 'run-a', 'message': 'line a', 'simulation': {'id': 'original'}})
        SimulationResult.add({**step, 'run_id': 'run-a', 'snapshots': {'filter_grok_0': step}})

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL, 'detail': 'steps', 'timeout': 5, **body,
        })

        assert response.status_code == 200
        data = response.json()
        shaped = data['events'][0] if 'events' in body else data
        assert 'results' not in shaped
        assert shaped['detail'] == 'steps'
        assert shaped['final'] == {'message': 'line a', 'w': 'line'}
        assert shaped['steps'] == [
            {'step': 1, 'plugin': 'grok', 'component': 'filter_grok_0', 'id': 'hdr', 'ms': 0.0,
             'added': {'w': 'line'}},
        ]

    def test_simulate_no_auth_returns_401(self, client):
        assert _post(client, '/api/pipelines/simulate/', {}).status_code == 401

    def test_simulate_readonly_returns_403(self, readonly_client):
        assert _post(readonly_client, '/api/pipelines/simulate/', {}).status_code == 403

    def test_simulate_wrong_method_returns_405(self, authenticated_client):
        assert authenticated_client.get('/api/pipelines/simulate/').status_code == 405
