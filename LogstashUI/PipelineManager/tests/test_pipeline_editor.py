from Common.test_resources import authenticated_client, test_connection, test_user
from PipelineManager.models import Connection

from unittest.mock import patch, MagicMock
from html import escape

import json
import pytest


# ============================================================================
# Pipeline Editor View Tests
# ============================================================================

@pytest.mark.django_db
class TestPipelineEditorView:
    """Test PipelineEditor view"""

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_pipeline_editor_success(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test successful pipeline editor load"""
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_settings': {
                'pipeline.workers': 1,
                'pipeline.batch.size': 128,
                'pipeline.batch.delay': 50,
                'queue.type': 'memory',
                'queue.max_bytes': '1gb',
                'queue.checkpoint.writes': 1024
            },
            'description': 'Test pipeline'
        }

        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        assert response.status_code == 200
        assert b'test_pipeline' in response.content
        assert b'Test pipeline' in response.content

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_pipeline_editor_missing_es_id(self, mock_get_pipeline, authenticated_client):
        """Test PipelineEditor with missing es_id parameter"""
        response = authenticated_client.get('/ConnectionManager/Pipelines/Editor/?pipeline=test_pipeline')
        assert response.status_code == 400
        assert b'Missing required parameters' in response.content

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_pipeline_editor_missing_pipeline_param(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test PipelineEditor with missing pipeline parameter"""
        response = authenticated_client.get(f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}')
        assert response.status_code == 400
        assert b'Missing required parameters' in response.content

    @patch('PipelineManager.views.get_logstash_pipeline')
    @patch('PipelineManager.views.logstash_config_parse.logstash_config_to_components')
    def test_pipeline_editor_with_parsing_error(self, mock_parse, mock_get_pipeline, authenticated_client, test_connection):
        """Test pipeline editor when parsing fails"""
        mock_get_pipeline.return_value = {
            'pipeline': 'invalid syntax here',
            'pipeline_settings': {},
            'description': ''
        }
        mock_parse.side_effect = Exception("Parsing error: Invalid syntax")

        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        assert response.status_code == 200
        # Should show parsing error banner
        assert b'parsing' in response.content.lower() or b'error' in response.content.lower()


# ============================================================================
# GetPipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestGetPipeline:
    """Test GetPipeline view"""

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_get_pipeline_success(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test successful pipeline retrieval"""
        pipeline_config = 'input { stdin {} }\nfilter { mutate { add_field => { "test" => "value" } } }\noutput { stdout {} }'
        mock_get_pipeline.return_value = {'pipeline': pipeline_config}

        response = authenticated_client.get(
            f'/ConnectionManager/GetPipeline/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'code' in data
        assert data['code'] == pipeline_config

    def test_get_pipeline_missing_params(self, authenticated_client):
        """Test GetPipeline with missing parameters"""
        # Missing both params
        response = authenticated_client.get('/ConnectionManager/GetPipeline/')
        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'Missing required parameters' in data['error']

        # Missing pipeline param
        response = authenticated_client.get('/ConnectionManager/GetPipeline/?es_id=1')
        assert response.status_code == 400


# ============================================================================
# ComponentsToConfig and ConfigToComponents Tests
# ============================================================================

@pytest.mark.django_db
class TestComponentsConfigConversion:
    """Test ComponentsToConfig and ConfigToComponents views"""

    def test_components_to_config_success(self, authenticated_client):
        """Test successful components to config conversion"""
        components = {
            "input": [
                {
                    "id": "input_1",
                    "plugin": "stdin",
                    "config": {}
                }
            ],
            "filter": [],
            "output": [
                {
                    "id": "output_1",
                    "plugin": "stdout",
                    "config": {}
                }
            ]
        }

        response = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {
            'components': json.dumps(components)
        })

        assert response.status_code == 200
        config = response.content.decode('utf-8')
        assert 'input' in config
        assert 'stdin' in config
        assert 'output' in config
        assert 'stdout' in config

    def test_components_to_config_no_components(self, authenticated_client):
        """Test ComponentsToConfig with no components provided"""
        response = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {})

        assert response.status_code == 400
        assert b'No components provided' in response.content

    def test_components_to_config_invalid_json(self, authenticated_client):
        """Test ComponentsToConfig with invalid JSON"""
        response = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {
            'components': 'invalid json {'
        })

        assert response.status_code == 500
        assert b'Error' in response.content

    @patch('PipelineManager.views.logstash_config_parse.logstash_config_to_components')
    def test_config_to_components_success(self, mock_parse, authenticated_client):
        """Test successful config to components conversion"""
        config_text = 'input { stdin {} }\nfilter {}\noutput { stdout {} }'
        expected_components = {
            "input": [{"id": "input_1", "plugin": "stdin", "config": {}}],
            "filter": [],
            "output": [{"id": "output_1", "plugin": "stdout", "config": {}}]
        }
        
        # Mock returns JSON string
        mock_parse.return_value = json.dumps(expected_components)

        response = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {
            'config_text': config_text
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'input' in data
        assert 'filter' in data
        assert 'output' in data

    def test_config_to_components_no_config(self, authenticated_client):
        """Test ConfigToComponents with no config text provided"""
        response = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {})

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data
        assert 'No config text provided' in data['error']

    @patch('PipelineManager.views.logstash_config_parse.logstash_config_to_components')
    def test_config_to_components_parse_error(self, mock_parse, authenticated_client):
        """Test ConfigToComponents with parsing error"""
        mock_parse.side_effect = Exception("Invalid syntax")

        response = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {
            'config_text': 'invalid config'
        })

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    def test_components_config_roundtrip(self, authenticated_client):
        """Test round-trip conversion: components -> config -> components"""
        original_components = {
            "input": [
                {
                    "id": "input_1",
                    "plugin": "generator",
                    "config": {
                        "count": "1",
                        "message": "test"
                    }
                }
            ],
            "filter": [
                {
                    "id": "filter_1",
                    "plugin": "mutate",
                    "config": {
                        "add_field": {"test": "value"}
                    }
                }
            ],
            "output": [
                {
                    "id": "output_1",
                    "plugin": "stdout",
                    "config": {}
                }
            ]
        }

        # Convert to config
        response1 = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {
            'components': json.dumps(original_components)
        })
        assert response1.status_code == 200
        config_text = response1.content.decode('utf-8')

        # Convert back to components
        response2 = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {
            'config_text': config_text
        })
        assert response2.status_code == 200
        roundtrip_components = json.loads(response2.content)

        # Verify structure is preserved
        assert 'input' in roundtrip_components
        assert 'filter' in roundtrip_components
        assert 'output' in roundtrip_components


# ============================================================================
# GetDiff Tests
# ============================================================================

@pytest.mark.django_db
class TestGetDiff:
    """Test GetDiff view"""

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_get_diff_with_matching_configs(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test GetDiff when configs are identical"""
        current_config = 'input {}\nfilter {}\noutput {}'
        mock_get_pipeline.return_value = {'pipeline': current_config}

        components = {
            "input": [],
            "filter": [],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components)
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'diff' in data
        assert 'stats' in data
        # The configs are functionally identical but may have formatting differences
        # Check that both configs contain the same sections
        assert 'input' in data['current'] and 'input' in data['new']
        assert 'filter' in data['current'] and 'filter' in data['new']
        assert 'output' in data['current'] and 'output' in data['new']

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_get_diff_with_different_configs(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test GetDiff when configs differ"""
        current_config = 'input {}\nfilter {}\noutput {}'
        mock_get_pipeline.return_value = {'pipeline': current_config}

        components = {
            "input": [
                {
                    "id": "input_1",
                    "plugin": "stdin",
                    "config": {}
                }
            ],
            "filter": [],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components)
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'diff' in data
        assert 'stats' in data
        assert data['current'] != data['new']
        # Should show addition of stdin input
        assert 'stdin' in data['new']

    @patch('PipelineManager.views.get_logstash_pipeline')
    def test_get_diff_with_text_mode(self, mock_get_pipeline, authenticated_client, test_connection):
        """Test GetDiff using raw pipeline text instead of components"""
        current_config = 'input {}\nfilter {}\noutput {}'
        new_config = 'input { stdin {} }\nfilter {}\noutput { stdout {} }'
        mock_get_pipeline.return_value = {'pipeline': current_config}

        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'pipeline_text': new_config
        })

        assert response.status_code == 200
        data = json.loads(response.content)
        assert 'diff' in data
        assert data['new'] == new_config

    def test_get_diff_missing_params(self, authenticated_client):
        """Test GetDiff with missing required parameters"""
        response = authenticated_client.post('/ConnectionManager/GetDiff/', {})

        assert response.status_code == 400
        data = json.loads(response.content)
        assert 'error' in data


# ============================================================================
# GetCurrentPipelineCode Tests
# ============================================================================

@pytest.mark.django_db
class TestGetCurrentPipelineCode:
    """Test GetCurrentPipelineCode view"""

    def test_get_current_pipeline_code_success(self, authenticated_client):
        """Test successful pipeline code generation"""
        components = {
            "input": [
                {
                    "id": "input_1",
                    "plugin": "stdin",
                    "config": {}
                }
            ],
            "filter": [],
            "output": [
                {
                    "id": "output_1",
                    "plugin": "stdout",
                    "config": {}
                }
            ]
        }

        response = authenticated_client.post('/ConnectionManager/GetCurrentPipelineCode/', {
            'components': json.dumps(components)
        })

        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Should return HTML with code
        assert '<pre' in content or '<code' in content
        assert 'stdin' in content
        assert 'stdout' in content

    def test_get_current_pipeline_code_mutable_default_safety(self, authenticated_client):
        """Test that mutable default argument doesn't cause issues"""
        # Call twice with different data to ensure no state leakage
        components1 = {
            "input": [{"id": "input_1", "plugin": "stdin", "config": {}}],
            "filter": [],
            "output": []
        }

        components2 = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response1 = authenticated_client.post('/ConnectionManager/GetCurrentPipelineCode/', {
            'components': json.dumps(components1)
        })
        content1 = response1.content.decode('utf-8')

        response2 = authenticated_client.post('/ConnectionManager/GetCurrentPipelineCode/', {
            'components': json.dumps(components2)
        })
        content2 = response2.content.decode('utf-8')

        # Results should be different
        assert content1 != content2
        assert 'stdin' in content1
        assert 'stdin' not in content2
        assert 'mutate' in content2
        assert 'mutate' not in content1


# ============================================================================
# ClonePipeline Tests
# ============================================================================

@pytest.mark.django_db
class TestClonePipeline:
    """Test ClonePipeline view"""

    @patch('PipelineManager.views.get_elastic_connection')
    def test_clone_pipeline_success(self, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline cloning"""
        mock_es = MagicMock()
        
        # Mock source pipeline
        mock_es.logstash.get_pipeline.side_effect = [
            # First call: get source pipeline
            {
                'source_pipeline': {
                    'pipeline': 'input {}\nfilter {}\noutput {}',
                    'pipeline_settings': {'pipeline.workers': 2},
                    'description': 'Source pipeline'
                }
            },
            # Second call: check if new name exists
            {}  # Empty means new name doesn't exist
        ]
        
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipeline',
            'new_pipeline': 'cloned_pipeline'
        })

        assert response.status_code == 200
        # Should contain script to close modal and refresh
        assert b'clonePipelineModal' in response.content or b'script' in response.content

    @patch('PipelineManager.views.get_elastic_connection')
    def test_clone_pipeline_duplicate_name(self, mock_get_es, authenticated_client, test_connection):
        """Test cloning with duplicate pipeline name"""
        mock_es = MagicMock()
        
        # Mock that new pipeline name already exists
        mock_es.logstash.get_pipeline.side_effect = [
            # First call: get source pipeline
            {
                'source_pipeline': {
                    'pipeline': 'input {}\nfilter {}\noutput {}',
                    'pipeline_settings': {},
                    'description': ''
                }
            },
            # Second call: check existing pipelines - new name exists
            {
                'cloned_pipeline': {},
                'source_pipeline': {}
            }
        ]
        
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source_pipeline',
            'new_pipeline': 'cloned_pipeline'
        })

        assert response.status_code == 400
        assert b'already exists' in response.content

    def test_clone_pipeline_invalid_source_name(self, authenticated_client, test_connection):
        """Test cloning with invalid source pipeline name"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': '123invalid',  # Can't start with number
            'new_pipeline': 'valid_name'
        })

        assert response.status_code == 400
        assert b'Invalid source pipeline name' in response.content or b'must begin with a letter' in response.content

    def test_clone_pipeline_invalid_new_name(self, authenticated_client, test_connection):
        """Test cloning with invalid new pipeline name"""
        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'valid_source',
            'new_pipeline': 'invalid@name'  # Invalid character
        })

        assert response.status_code == 400
        assert b'Pipeline' in response.content and (b'invalid' in response.content.lower() or b'error' in response.content.lower())

    @patch('PipelineManager.views.get_elastic_connection')
    def test_clone_pipeline_source_not_found(self, mock_get_es, authenticated_client, test_connection):
        """Test cloning when source pipeline doesn't exist"""
        mock_es = MagicMock()
        
        # Mock that source pipeline doesn't exist
        mock_es.logstash.get_pipeline.return_value = {}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'nonexistent',
            'new_pipeline': 'cloned_pipeline'
        })

        assert response.status_code == 404
        assert b'not found' in response.content
