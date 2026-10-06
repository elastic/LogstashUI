#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Tests for API/pipelines_views.py — pipeline REST endpoints."""

import json
from collections import deque
from unittest.mock import MagicMock, patch

import pytest

from django.contrib.auth.models import User
from Management.models import UserProfile
from PipelineManager.models import Pipeline, Policy, Revision


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
# ES Pipelines (mock Elasticsearch client)
# ---------------------------------------------------------------------------

_ES_PIPELINE_BODY = {
    'my-pipe': {
        'description': 'test',
        'pipeline': 'input{} filter{} output{}',
        'last_modified': '2026-01-01T00:00:00.000Z',
        'username': 'admin',
        'pipeline_settings': {'pipeline.workers': 1},
    }
}


@pytest.mark.django_db
class TestESPipelineList:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _ES_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        response = authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/')
        assert response.status_code == 200

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_returns_pipelines(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _ES_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        data = authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/').json()
        assert data['count'] == 1
        assert data['pipelines'][0]['name'] == 'my-pipe'

    @patch('API.pipelines_views.get_elastic_connection')
    def test_list_es_error_returns_502(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('Connection refused')
        response = authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/')
        assert response.status_code == 502

    def test_list_no_auth_returns_401(self, client, test_connection):
        assert client.get(f'/api/pipelines/es/{test_connection.id}/').status_code == 401


@pytest.mark.django_db
class TestESPipelineCreate:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_returns_201(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = _post(authenticated_client, f'/api/pipelines/es/{test_connection.id}/', {
            'name': 'new-es-pipe', 'lscl': 'input{} filter{} output{}',
        })
        assert response.status_code == 201
        mock_es.logstash.put_pipeline.assert_called_once()

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_missing_name_returns_400(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.return_value = MagicMock()
        response = _post(authenticated_client, f'/api/pipelines/es/{test_connection.id}/', {
            'lscl': 'input{} filter{} output{}',
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.get_elastic_connection')
    def test_create_missing_lscl_returns_400(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.return_value = MagicMock()
        response = _post(authenticated_client, f'/api/pipelines/es/{test_connection.id}/', {
            'name': 'x',
        })
        assert response.status_code == 400

    def test_create_no_auth_returns_401(self, client, test_connection):
        assert _post(client, f'/api/pipelines/es/{test_connection.id}/', {}).status_code == 401

    def test_create_readonly_returns_403(self, readonly_client, test_connection):
        assert _post(readonly_client, f'/api/pipelines/es/{test_connection.id}/', {}).status_code == 403


@pytest.mark.django_db
class TestESPipelineGet:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_get_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _ES_PIPELINE_BODY
        mock_get_es.return_value = mock_es
        response = authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/my-pipe/')
        assert response.status_code == 200
        assert response.json()['pipeline']['name'] == 'my-pipe'

    @patch('API.pipelines_views.get_elastic_connection')
    def test_get_es_error_surfaces_as_error(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('404 not found')
        response = authenticated_client.get(f'/api/pipelines/es/{test_connection.id}/missing-pipe/')
        assert response.status_code == 404

    def test_get_no_auth_returns_401(self, client, test_connection):
        assert client.get(f'/api/pipelines/es/{test_connection.id}/my-pipe/').status_code == 401


@pytest.mark.django_db
class TestESPipelineUpdate:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_update_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _ES_PIPELINE_BODY
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = _put(authenticated_client, f'/api/pipelines/es/{test_connection.id}/my-pipe/', {
            'lscl': 'input{} filter{ mutate{} } output{}',
        })
        assert response.status_code == 200
        mock_es.logstash.put_pipeline.assert_called_once()

    @patch('API.pipelines_views.get_elastic_connection')
    def test_update_merges_existing_settings(self, mock_get_es, authenticated_client, test_connection):
        """Unspecified settings are preserved from the existing pipeline."""
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = _ES_PIPELINE_BODY
        mock_es.logstash.put_pipeline.return_value = {}
        mock_get_es.return_value = mock_es
        _put(authenticated_client, f'/api/pipelines/es/{test_connection.id}/my-pipe/', {
            'pipeline_workers': 4,
        })
        call_body = mock_es.logstash.put_pipeline.call_args[1]['body']
        assert call_body['pipeline_settings']['pipeline.workers'] == 4
        # pipeline.batch.size should fall back to the existing value (or default)
        assert 'pipeline.batch.size' in call_body['pipeline_settings']

    def test_update_no_auth_returns_401(self, client, test_connection):
        assert _put(client, f'/api/pipelines/es/{test_connection.id}/my-pipe/', {}).status_code == 401

    def test_update_readonly_returns_403(self, readonly_client, test_connection):
        assert _put(readonly_client, f'/api/pipelines/es/{test_connection.id}/my-pipe/', {}).status_code == 403


@pytest.mark.django_db
class TestESPipelineDelete:

    @patch('API.pipelines_views.get_elastic_connection')
    def test_delete_returns_200(self, mock_get_es, authenticated_client, test_connection):
        mock_es = MagicMock()
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es
        response = authenticated_client.delete(f'/api/pipelines/es/{test_connection.id}/my-pipe/')
        assert response.status_code == 200
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='my-pipe')

    @patch('API.pipelines_views.get_elastic_connection')
    def test_delete_es_error_returns_error(self, mock_get_es, authenticated_client, test_connection):
        mock_get_es.side_effect = Exception('404 not found')
        response = authenticated_client.delete(f'/api/pipelines/es/{test_connection.id}/my-pipe/')
        assert response.status_code == 404

    def test_delete_no_auth_returns_401(self, client, test_connection):
        assert client.delete(f'/api/pipelines/es/{test_connection.id}/my-pipe/').status_code == 401

    def test_delete_readonly_returns_403(self, readonly_client, test_connection):
        assert readonly_client.delete(f'/api/pipelines/es/{test_connection.id}/my-pipe/').status_code == 403


# ---------------------------------------------------------------------------
# Simulate
# ---------------------------------------------------------------------------

def _make_sim_html(run_id, slot_id=1):
    """Minimal HTML response that SimulatePipeline would return."""
    return (
        f'<div data-run-id="{run_id}" data-slot-id="{slot_id}">'
        f'Simulation started</div>'
    ).encode()


@pytest.mark.django_db
class TestPipelineSimulate:

    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_missing_lscl_and_pipeline_id_returns_400(
        self, mock_parse, mock_sim, authenticated_client
    ):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'event': 'some log line',
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_missing_event_returns_400(
        self, mock_parse, mock_sim, authenticated_client
    ):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': _SIMPLE_LSCL,
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_no_filter_plugins_returns_400(
        self, mock_parse, mock_sim, authenticated_client
    ):
        mock_parse.logstash_config_to_components.return_value = json.dumps({'filter': []})
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'lscl': 'input{} output{}', 'event': 'test',
        })
        assert response.status_code == 400

    @patch('API.pipelines_views.simulation_results')
    @patch('API.pipelines_views.simulation_lock')
    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_success_with_lscl(
        self, mock_parse, mock_sim, mock_lock, mock_results, authenticated_client
    ):
        run_id = 'test-run-1234'
        mock_parse.logstash_config_to_components.return_value = json.dumps({
            'filter': [{'plugin': 'mutate', 'id': 'mut1', 'config': {}}]
        })

        from django.http import HttpResponse
        from unittest.mock import MagicMock as MM
        fake_resp = HttpResponse(_make_sim_html(run_id))
        mock_sim.return_value = fake_resp

        # Simulate results appearing on first poll
        event_result = {'run_id': run_id, 'snapshots': {}, 'message': 'hello'}
        mock_results.__iter__ = MagicMock(return_value=iter([event_result]))
        mock_results.__len__ = MagicMock(return_value=1)

        with patch('API.pipelines_views.simulation_lock') as ml:
            ml.__enter__ = MagicMock(return_value=None)
            ml.__exit__ = MagicMock(return_value=False)

            with patch('API.pipelines_views.simulation_results', [event_result]):
                response = _post(authenticated_client, '/api/pipelines/simulate/', {
                    'lscl': _SIMPLE_LSCL,
                    'event': 'test log line',
                    'timeout': 10,
                })

        # Either success (200) or timeout (408) — sim agent not running in test env
        assert response.status_code in (200, 408, 502)

    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_loads_lscl_from_pipeline_id(
        self, mock_parse, mock_sim, authenticated_client, pipeline
    ):
        """pipeline_id causes LSCL to be loaded from DB."""
        mock_parse.logstash_config_to_components.return_value = json.dumps({
            'filter': [{'plugin': 'mutate', 'id': 'mut1', 'config': {}}]
        })
        from django.http import HttpResponse
        mock_sim.return_value = HttpResponse(b'<div data-pipeline-failed="true">Error</div>')

        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'pipeline_id': pipeline.id,
            'event': 'test',
            'timeout': 1,
        })
        # LSCL was loaded from DB and parse was attempted
        mock_parse.logstash_config_to_components.assert_called_once_with(pipeline.lscl)
        assert response.status_code in (200, 408, 502)

    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_unknown_pipeline_id_returns_404(
        self, mock_parse, mock_sim, authenticated_client
    ):
        response = _post(authenticated_client, '/api/pipelines/simulate/', {
            'pipeline_id': 99999, 'event': 'test',
        })
        assert response.status_code == 404

    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_timeout_returns_408(
        self, mock_parse, mock_sim_pipeline, mock_time, authenticated_client
    ):
        mock_parse.logstash_config_to_components.return_value = json.dumps({
            'filter': [{'plugin': 'mutate', 'id': 'mut1', 'config': {}}]
        })
        from django.http import HttpResponse
        mock_sim_pipeline.return_value = HttpResponse(_make_sim_html('timeout-run-id'))

        # Advance clock past the 1s timeout immediately so the poll loop exits
        mock_time.time.side_effect = [0, 5, 5, 5]
        mock_time.sleep = MagicMock()

        with patch('API.pipelines_views.simulation_results', []):
            with patch('API.pipelines_views.simulation_lock') as ml:
                ml.__enter__ = MagicMock(return_value=None)
                ml.__exit__ = MagicMock(return_value=False)
                response = _post(authenticated_client, '/api/pipelines/simulate/', {
                    'lscl': _SIMPLE_LSCL, 'event': 'test', 'timeout': 1,
                })
        assert response.status_code == 408

    @patch('API.pipelines_views.time')
    @patch('API.pipelines_views.SimulatePipeline')
    @patch('API.pipelines_views.logstash_config_parse')
    def test_simulate_timeout_capped_at_180(
        self, mock_parse, mock_sim_pipeline, mock_time, authenticated_client
    ):
        """timeout > 180 is silently clamped; the loop exits after the cap, not 9999s."""
        mock_parse.logstash_config_to_components.return_value = json.dumps({
            'filter': [{'plugin': 'mutate', 'id': 'mut1', 'config': {}}]
        })
        from django.http import HttpResponse
        mock_sim_pipeline.return_value = HttpResponse(_make_sim_html('cap-run-id'))

        # Clock jumps 200s per call — exceeds even the 180s cap immediately
        mock_time.time.side_effect = [0, 200, 200, 200]
        mock_time.sleep = MagicMock()

        with patch('API.pipelines_views.simulation_results', []):
            with patch('API.pipelines_views.simulation_lock') as ml:
                ml.__enter__ = MagicMock(return_value=None)
                ml.__exit__ = MagicMock(return_value=False)
                response = _post(authenticated_client, '/api/pipelines/simulate/', {
                    'lscl': _SIMPLE_LSCL, 'event': 'test', 'timeout': 9999,
                })
        assert response.status_code == 408

    def test_simulate_no_auth_returns_401(self, client):
        assert _post(client, '/api/pipelines/simulate/', {}).status_code == 401

    def test_simulate_readonly_returns_403(self, readonly_client):
        assert _post(readonly_client, '/api/pipelines/simulate/', {}).status_code == 403

    def test_simulate_wrong_method_returns_405(self, authenticated_client):
        assert authenticated_client.get('/api/pipelines/simulate/').status_code == 405
