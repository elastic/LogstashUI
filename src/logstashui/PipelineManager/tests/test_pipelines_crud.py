#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection, Policy, Pipeline

from unittest.mock import patch, MagicMock
import json
import pytest


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def test_policy(db):
    """Create a test policy"""
    policy = Policy.objects.create(
        name='Test Policy',
        settings_path='/etc/logstash/',
        logs_path='/var/log/logstash',
        binary_path='/usr/share/logstash/bin',
        logstash_yml='http.host: "0.0.0.0"',
        jvm_options='-Xms1g\n-Xmx1g',
        log4j2_properties='logger.logstash.name = logstash'
    )
    return policy


@pytest.fixture
def test_pipeline(db, test_policy):
    """Create a test pipeline"""
    pipeline = Pipeline.objects.create(
        policy=test_policy,
        name='test_pipeline',
        lscl='input { beats { port => 5044 } } filter {} output { elasticsearch { hosts => ["localhost:9200"] } }',
        description='Test pipeline description'
    )
    return pipeline


# ============================================================================
# CreatePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestCreatePipeline:
    """Test Pipeline Create operations"""

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_create_pipeline_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline creation for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 200
        assert b'Pipeline created successfully!' in response.content
        assert 'HX-Redirect' in response

        # Verify put_pipeline was called
        mock_es.logstash.put_pipeline.assert_called_once()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['id'] == 'test_pipeline'
        assert call_args[1]['body']['pipeline'] == 'input {}\nfilter {}\noutput {}'

    def test_create_pipeline_agent_success(self, authenticated_client, test_policy):
        """Test successful pipeline creation for agent policy"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'policy_id': test_policy.id,
            'pipeline': 'new_pipeline',
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 200
        assert b'Pipeline created successfully!' in response.content
        assert 'HX-Redirect' in response

        # Verify pipeline was created
        assert Pipeline.objects.filter(policy=test_policy, name='new_pipeline').exists()

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    def test_create_pipeline_agent_duplicate_name(self, authenticated_client, test_policy, test_pipeline):
        """Test creating pipeline with duplicate name in agent policy"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'policy_id': test_policy.id,
            'pipeline': 'test_pipeline',  # Already exists
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 400
        assert b'already exists' in response.content

    def test_create_pipeline_invalid_name(self, authenticated_client, test_connection):
        """Test pipeline creation with invalid name"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid',  # Can't start with number
        })

        assert response.status_code == 400
        assert b'Pipeline ID must begin with a letter or underscore' in response.content

    def test_create_pipeline_empty_name(self, authenticated_client, test_connection):
        """Test pipeline creation with empty name"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '',
        })

        assert response.status_code == 400
        assert b'Pipeline name cannot be empty' in response.content

    def test_create_pipeline_nonexistent_policy(self, authenticated_client):
        """Test creating pipeline for non-existent policy"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'policy_id': 99999,
            'pipeline': 'test_pipeline',
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 404
        assert b'not found' in response.content

    def test_create_pipeline_no_context(self, authenticated_client):
        """Test creating pipeline without es_id or policy_id"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'pipeline': 'test_pipeline',
            'pipeline_config': 'input {}\nfilter {}\noutput {}'
        })

        assert response.status_code == 400
        assert b'neither policy_id nor es_id provided' in response.content


# ============================================================================
# DeletePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestDeletePipeline:
    """Test Pipeline Delete operations"""

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_delete_pipeline_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline deletion for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline'
        })

        assert response.status_code == 204

        # Verify delete_pipeline was called
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='test_pipeline')

    def test_delete_pipeline_agent_success(self, authenticated_client, test_policy, test_pipeline):
        """Test successful pipeline deletion for agent policy"""
        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'policy_id': test_policy.id,
            'pipeline': 'test_pipeline'
        })

        assert response.status_code == 204

        # Verify pipeline was deleted
        assert not Pipeline.objects.filter(policy=test_policy, name='test_pipeline').exists()

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    def test_delete_pipeline_agent_json_format(self, authenticated_client, test_policy, test_pipeline):
        """Test deleting pipeline with JSON request body"""
        response = authenticated_client.post(
            '/ConnectionManager/DeletePipeline/',
            data=json.dumps({
                'policy_id': test_policy.id,
                'pipeline': 'test_pipeline'
            }),
            content_type='application/json'
        )

        assert response.status_code == 204

        # Verify pipeline was deleted
        assert not Pipeline.objects.filter(policy=test_policy, name='test_pipeline').exists()

    def test_delete_pipeline_invalid_name(self, authenticated_client, test_connection):
        """Test deleting pipeline with invalid name"""
        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_delete_pipeline_nonexistent_agent(self, authenticated_client, test_policy):
        """Test deleting non-existent pipeline from agent policy"""
        response = authenticated_client.post('/ConnectionManager/DeletePipeline/', {
            'policy_id': test_policy.id,
            'pipeline': 'nonexistent'
        })

        assert response.status_code == 404
        assert b'not found' in response.content


# ============================================================================
# UpdatePipelineSettings Tests
# ============================================================================

@pytest.mark.django_db
class TestUpdatePipelineSettings:
    """Test Pipeline Settings Update operations"""

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    @patch('PipelineManager.pipelines_crud.get_logstash_pipeline')
    def test_update_pipeline_settings_centralized_success(self, mock_get_pipeline, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline settings update for centralized connection"""
        # Mock existing pipeline
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'description': 'Updated description',
            'pipeline_workers': '2',
            'pipeline_batch_size': '250'
        })

        assert response.status_code == 200

        # Verify put_pipeline was called with updated settings
        mock_es.logstash.put_pipeline.assert_called()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['body']['description'] == 'Updated description'
        assert call_args[1]['body']['pipeline_settings']['pipeline.workers'] == 2
        assert call_args[1]['body']['pipeline_settings']['pipeline.batch.size'] == 250

    def test_update_pipeline_settings_agent_success(self, authenticated_client, test_policy, test_pipeline):
        """Test successful pipeline settings update for agent policy"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'ls_id': test_policy.id,
            'pipeline': 'test_pipeline',
            'description': 'Updated description',
            'pipeline_workers': '4',
            'pipeline_batch_size': '512'
        })

        assert response.status_code == 200

        # Verify pipeline was updated
        test_pipeline.refresh_from_db()
        assert test_pipeline.description == 'Updated description'
        assert test_pipeline.pipeline_workers == 4
        assert test_pipeline.pipeline_batch_size == 512

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    def test_update_pipeline_settings_queue_settings(self, authenticated_client, test_policy, test_pipeline):
        """Test updating queue settings"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'ls_id': test_policy.id,
            'pipeline': 'test_pipeline',
            'queue_type': 'persisted',
            'queue_max_bytes': '10',
            'queue_max_bytes_unit': 'gb',
            'queue_checkpoint_writes': '2048'
        })

        assert response.status_code == 200

        # Verify pipeline was updated
        test_pipeline.refresh_from_db()
        assert test_pipeline.queue_type == 'persisted'
        assert test_pipeline.queue_max_bytes == '10gb'
        assert test_pipeline.queue_checkpoint_writes == 2048

    def test_update_pipeline_settings_missing_pipeline_id(self, authenticated_client):
        """Test updating settings without pipeline ID or connection ID"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'pipeline': 'test_pipeline',
            'description': 'Updated'
        })

        assert response.status_code == 400
        assert b'Missing pipeline ID or connection ID' in response.content

    def test_update_pipeline_settings_invalid_name(self, authenticated_client, test_connection):
        """Test updating settings with invalid pipeline name"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_update_pipeline_settings_nonexistent_agent(self, authenticated_client, test_policy):
        """Test updating settings for non-existent agent pipeline"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineSettings/', {
            'ls_id': test_policy.id,
            'pipeline': 'nonexistent',
            'description': 'Test'
        })

        assert response.status_code == 404
        assert b'not found' in response.content

    def test_update_pipeline_settings_wrong_method(self, authenticated_client):
        """Test that GET requests are rejected"""
        response = authenticated_client.get('/ConnectionManager/UpdatePipelineSettings/')

        assert response.status_code == 405
        assert b'Invalid request method' in response.content


# ============================================================================
# ClonePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestClonePipeline:
    """Test Pipeline Clone operations"""

    def test_clone_pipeline_agent_success(self, authenticated_client, test_policy, test_pipeline):
        """Test successful pipeline cloning for agent policy"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'test_pipeline',
            'new_pipeline': 'cloned_pipeline'
        })

        assert response.status_code == 200
        assert b'Pipeline cloned successfully!' in response.content
        assert 'HX-Trigger' in response

        # Verify cloned pipeline was created
        cloned = Pipeline.objects.get(policy=test_policy, name='cloned_pipeline')
        assert cloned.lscl == test_pipeline.lscl
        assert cloned.description == 'Cloned from test_pipeline'

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_clone_pipeline_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline cloning for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'source_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {'pipeline.workers': 2},
                'description': 'Source pipeline'
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipeline',
            'new_pipeline': 'cloned_pipeline'
        })

        assert response.status_code == 200
        assert b'Pipeline cloned successfully!' in response.content

        # Verify put_pipeline was called
        mock_es.logstash.put_pipeline.assert_called_once()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['id'] == 'cloned_pipeline'

    def test_clone_pipeline_duplicate_name(self, authenticated_client, test_policy, test_pipeline):
        """Test cloning pipeline with duplicate name"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'test_pipeline',
            'new_pipeline': 'test_pipeline'  # Same name
        })

        assert response.status_code == 400
        assert b'already exists' in response.content

    def test_clone_pipeline_invalid_source_name(self, authenticated_client, test_policy):
        """Test cloning with invalid source pipeline name"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': '123invalid',
            'new_pipeline': 'new_pipeline'
        })

        assert response.status_code == 400
        assert b'Invalid source pipeline name' in response.content

    def test_clone_pipeline_invalid_new_name(self, authenticated_client, test_policy, test_pipeline):
        """Test cloning with invalid new pipeline name"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'test_pipeline',
            'new_pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_clone_pipeline_nonexistent_source(self, authenticated_client, test_policy):
        """Test cloning non-existent source pipeline"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'nonexistent',
            'new_pipeline': 'new_pipeline'
        })

        assert response.status_code == 404
        assert b'not found' in response.content


# ============================================================================
# RenamePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestRenamePipeline:
    """Test Pipeline Rename operations"""

    def test_rename_pipeline_agent_success(self, authenticated_client, test_policy, test_pipeline):
        """Test successful pipeline renaming for agent policy"""
        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'test_pipeline',
            'new_pipeline': 'renamed_pipeline'
        })

        assert response.status_code == 200
        assert b'Pipeline renamed successfully!' in response.content
        assert 'HX-Trigger' in response

        # Verify renamed pipeline exists
        assert Pipeline.objects.filter(policy=test_policy, name='renamed_pipeline').exists()

        # Verify original pipeline was deleted
        assert not Pipeline.objects.filter(policy=test_policy, name='test_pipeline').exists()

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_rename_pipeline_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline renaming for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'source_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {'pipeline.workers': 2},
                'description': 'Source pipeline'
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_es.logstash.delete_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipeline',
            'new_pipeline': 'renamed_pipeline'
        })

        assert response.status_code == 200
        assert b'Pipeline renamed successfully!' in response.content

        # Verify put_pipeline and delete_pipeline were called
        mock_es.logstash.put_pipeline.assert_called_once()
        mock_es.logstash.delete_pipeline.assert_called_once_with(id='source_pipeline')

    def test_rename_pipeline_duplicate_name(self, authenticated_client, test_policy):
        """Test renaming pipeline to existing name"""
        # Create two pipelines
        Pipeline.objects.create(
            policy=test_policy,
            name='pipeline1',
            lscl='input {} filter {} output {}'
        )
        Pipeline.objects.create(
            policy=test_policy,
            name='pipeline2',
            lscl='input {} filter {} output {}'
        )

        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'pipeline1',
            'new_pipeline': 'pipeline2'  # Already exists
        })

        assert response.status_code == 400
        assert b'already exists' in response.content

    def test_rename_pipeline_invalid_source_name(self, authenticated_client, test_policy):
        """Test renaming with invalid source pipeline name"""
        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': '123invalid',
            'new_pipeline': 'new_pipeline'
        })

        assert response.status_code == 400
        assert b'Invalid source pipeline name' in response.content

    def test_rename_pipeline_invalid_new_name(self, authenticated_client, test_policy, test_pipeline):
        """Test renaming with invalid new pipeline name"""
        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'test_pipeline',
            'new_pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_rename_pipeline_nonexistent_source(self, authenticated_client, test_policy):
        """Test renaming non-existent source pipeline"""
        response = authenticated_client.post('/ConnectionManager/RenamePipeline/', {
            'policy_id': test_policy.id,
            'source_pipeline': 'nonexistent',
            'new_pipeline': 'new_pipeline'
        })

        assert response.status_code == 404
        assert b'not found' in response.content


# ============================================================================
# UpdatePipelineDescription Tests
# ============================================================================

@pytest.mark.django_db
class TestUpdatePipelineDescription:
    """Test Pipeline Description Update operations"""

    def test_update_description_agent_success(self, authenticated_client, test_policy, test_pipeline):
        """Test successful description update for agent policy"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineDescription/', {
            'policy_id': test_policy.id,
            'pipeline_name': 'test_pipeline',
            'description': 'Updated description'
        })

        assert response.status_code == 200
        assert b'Pipeline description updated successfully!' in response.content
        assert 'HX-Trigger' in response

        # Verify description was updated
        test_pipeline.refresh_from_db()
        assert test_pipeline.description == 'Updated description'

        # Verify policy marked as changed
        test_policy.refresh_from_db()
        assert test_policy.has_undeployed_changes is True

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_update_description_centralized_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful description update for centralized connection"""
        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': 'Old description'
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/UpdatePipelineDescription/', {
            'es_id': test_connection.id,
            'pipeline_name': 'test_pipeline',
            'description': 'New description'
        })

        assert response.status_code == 200
        assert b'Pipeline description updated successfully!' in response.content

        # Verify put_pipeline was called with new description
        mock_es.logstash.put_pipeline.assert_called_once()
        call_args = mock_es.logstash.put_pipeline.call_args
        assert call_args[1]['body']['description'] == 'New description'

    def test_update_description_invalid_name(self, authenticated_client, test_policy):
        """Test updating description with invalid pipeline name"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineDescription/', {
            'policy_id': test_policy.id,
            'pipeline_name': '123invalid',
            'description': 'Test'
        })

        assert response.status_code == 400
        assert b'Invalid pipeline name' in response.content

    def test_update_description_nonexistent_agent(self, authenticated_client, test_policy):
        """Test updating description for non-existent agent pipeline"""
        response = authenticated_client.post('/ConnectionManager/UpdatePipelineDescription/', {
            'policy_id': test_policy.id,
            'pipeline_name': 'nonexistent',
            'description': 'Test'
        })

        assert response.status_code == 404
        assert b'not found' in response.content


# ============================================================================
# GetPipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPipeline:
    """Test GetPipeline endpoint"""

    @patch('PipelineManager.pipelines_crud.get_logstash_pipeline')
    def test_get_pipeline_success(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test successful pipeline retrieval"""
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}'
        }

        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        assert response.status_code == 200
        data = response.json()
        assert 'code' in data
        assert data['code'] == 'input {}\nfilter {}\noutput {}'

    def test_get_pipeline_missing_es_id(self, authenticated_client):
        """Test getting pipeline without es_id"""
        response = authenticated_client.get('/ConnectionManager/GetPipeline/?pipeline=test_pipeline')

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'Missing required parameters' in data['error']

    def test_get_pipeline_missing_pipeline_name(self, authenticated_client, test_connection):
        """Test getting pipeline without pipeline name"""
        response = authenticated_client.get(f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}')

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'Missing required parameters' in data['error']

    @patch('Common.logstash_utils.get_logstash_pipeline')
    def test_get_pipeline_not_found(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test getting non-existent pipeline"""
        mock_get_pipeline.return_value = None

        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}&pipeline=nonexistent'
        )

        assert response.status_code == 400
        data = response.json()
        assert 'error' in data
        assert 'Could not fetch pipeline' in data['error']


# ============================================================================
# Pipeline Name Validation Tests
# ============================================================================

@pytest.mark.django_db
class TestPipelineNameValidation:
    """Test pipeline name validation"""

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_pipeline_name_starts_with_letter(self, mock_get_es, authenticated_client, test_connection):
        """Test that pipeline name can start with a letter"""
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'valid_pipeline'
        })

        assert response.status_code == 200

    @patch('PipelineManager.pipelines_crud.get_elastic_connection')
    def test_pipeline_name_starts_with_underscore(self, mock_get_es, authenticated_client, test_connection):
        """Test that pipeline name can start with underscore"""
        mock_es = MagicMock()
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '_valid_pipeline'
        })

        assert response.status_code == 200

    def test_pipeline_name_starts_with_number_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot start with a number"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': '123invalid'
        })

        assert response.status_code == 400
        assert b'must begin with a letter or underscore' in response.content

    def test_pipeline_name_special_chars_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot contain special characters"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': 'invalid@pipeline'
        })

        assert response.status_code == 400
        # Pipeline name starts with a letter but contains invalid @ character
        # Check for the actual error message from the validator
        assert (b'can only contain letters' in response.content or 
                b'underscores, dashes, hyphens' in response.content)

    def test_pipeline_name_empty_invalid(self, authenticated_client, test_connection):
        """Test that pipeline name cannot be empty"""
        response = authenticated_client.post('/ConnectionManager/CreatePipeline/', {
            'es_id': test_connection.id,
            'pipeline': ''
        })

        assert response.status_code == 400
        assert b'Pipeline name cannot be empty' in response.content
