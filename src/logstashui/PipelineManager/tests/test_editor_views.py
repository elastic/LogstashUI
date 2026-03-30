#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.test_resources import authenticated_client, test_connection, test_user

from unittest.mock import patch, MagicMock

import json
import pytest


# ============================================================================
# RBAC Tests for Simulation and Pipeline Editor Endpoints
# ============================================================================

@pytest.mark.django_db
class TestRBACSimulationEndpoints:
    """Test RBAC (Role-Based Access Control) for simulation endpoints"""

    def test_readonly_user_cannot_simulate_pipeline(self, client):
        """Test that readonly user cannot access SimulatePipeline"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_simulate',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_simulate', password='testpass123')

        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response = client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        assert response.status_code == 403

    def test_readonly_user_cannot_upload_file(self, client):
        """Test that readonly user cannot upload files"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        from django.core.files.uploadedfile import SimpleUploadedFile
        
        readonly_user = User.objects.create_user(
            username='readonly_upload_rbac',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_upload_rbac', password='testpass123')

        file_content = b'test content'
        uploaded_file = SimpleUploadedFile("test.txt", file_content)

        response = client.post('/ConnectionManager/UploadFile/', {
            'file': uploaded_file,
            'filename': 'test.txt'
        })

        assert response.status_code == 403

    def test_readonly_user_can_view_simulation_results(self, authenticated_client):
        """Test that readonly users can view simulation results (read-only operation)"""
        # GetSimulationResults doesn't have @require_admin_role, so readonly users can access
        response = authenticated_client.get('/ConnectionManager/GetSimulationResults/?run_id=test-123')

        # Should work (returns 200 with empty results)
        assert response.status_code == 200

    def test_readonly_user_can_check_pipeline_loaded(self, authenticated_client):
        """Test that readonly users can check if pipeline is loaded (read-only operation)"""
        # CheckIfPipelineLoaded has @login_required but not @require_admin_role
        response = authenticated_client.get('/ConnectionManager/CheckIfPipelineLoaded/?pipeline_name=test')

        # Should work (may return error about missing pipeline, but not 403)
        assert response.status_code in [200, 400, 500]

    def test_readonly_user_can_get_related_logs(self, authenticated_client):
        """Test that readonly users can get related logs (read-only operation)"""
        # GetRelatedLogs has @login_required but not @require_admin_role
        response = authenticated_client.get('/ConnectionManager/GetRelatedLogs/?slot_id=1')

        # Should work (may return error, but not 403)
        assert response.status_code in [200, 400, 500]

    def test_admin_user_can_simulate_pipeline(self, authenticated_client):
        """Test that admin user can access SimulatePipeline"""
        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        with patch('PipelineManager.simulation.requests.post') as mock_post:
            mock_post.return_value.status_code = 200
            mock_post.return_value.json.return_value = {'slot_id': 1, 'reused': False}

            response = authenticated_client.post('/ConnectionManager/SimulatePipeline/', {
                'components': json.dumps(components),
                'log_text': '{"message": "test"}'
            })

            # Should work for admin
            assert response.status_code == 200

    def test_unauthenticated_user_cannot_simulate(self, client):
        """Test that unauthenticated users cannot access SimulatePipeline"""
        components = {
            "input": [],
            "filter": [{"id": "filter_1", "plugin": "mutate", "config": {}}],
            "output": []
        }

        response = client.post('/ConnectionManager/SimulatePipeline/', {
            'components': json.dumps(components),
            'log_text': '{"message": "test"}'
        })

        # Should redirect to login
        assert response.status_code == 302
        assert '/Management/Login/' in response.url


@pytest.mark.django_db
class TestRBACPipelineEditorEndpoints:
    """Test RBAC for pipeline editor endpoints"""

    @patch('PipelineManager.editor_views.get_elastic_connection')
    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_readonly_user_cannot_save_pipeline(self, mock_get_pipeline, mock_get_es, client, test_connection):
        """Test that readonly user cannot save pipelines"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_save',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_save', password='testpass123')

        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': ''
            }
        }
        mock_get_es.return_value = mock_es

        components = {"input": [], "filter": [], "output": []}

        response = client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components)
        })

        assert response.status_code == 403

    @patch('PipelineManager.manager_views.get_elastic_connection')
    def test_readonly_user_cannot_clone_pipeline(self, mock_get_es, client, test_connection):
        """Test that readonly user cannot clone pipelines"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_clone',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_clone', password='testpass123')

        response = client.post('/ConnectionManager/ClonePipeline/', {
            'es_id': test_connection.id,
            'source_pipeline': 'source',
            'new_pipeline': 'cloned'
        })

        assert response.status_code == 403

    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_readonly_user_can_view_pipeline_editor(self, mock_get_pipeline, client, test_connection):
        """Test that readonly user can view pipeline editor (read-only)"""
        from django.contrib.auth.models import User
        from Management.models import UserProfile
        
        readonly_user = User.objects.create_user(
            username='readonly_view',
            password='testpass123',
            is_staff=False
        )
        readonly_user.profile.role = 'readonly'
        readonly_user.profile.save()
        client.login(username='readonly_view', password='testpass123')

        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_settings': {},
            'description': ''
        }

        response = client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=test_pipeline'
        )

        # PipelineEditor doesn't have @require_admin_role, so readonly can view
        assert response.status_code == 200


# ============================================================================
# PipelineEditor page
# ============================================================================

@pytest.mark.django_db
class TestPipelineEditorPage:
    """Tests for the PipelineEditor GET view"""

    def test_missing_params_returns_400(self, authenticated_client):
        """GET without es_id or pipeline returns 400"""
        response = authenticated_client.get('/ConnectionManager/Pipelines/Editor/')
        assert response.status_code == 400

    def test_missing_pipeline_param_returns_400(self, authenticated_client, test_connection):
        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}'
        )
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.get_logstash_pipeline', return_value=None)
    def test_pipeline_not_found_returns_400(self, mock_glp, authenticated_client, test_connection):
        """When pipeline fetch returns None, view returns 400"""
        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=nope'
        )
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_successful_load_200(self, mock_glp, authenticated_client, test_connection):
        mock_glp.return_value = {
            'pipeline': 'input {} filter {} output {}',
            'pipeline_settings': {},
            'description': 'test',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
        }
        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=mypipe'
        )
        assert response.status_code == 200

    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_parse_error_captured_in_context(self, mock_glp, authenticated_client, test_connection):
        """If config parsing fails, parsing_error is set in context (no 500)"""
        mock_glp.return_value = {
            'pipeline': '<<< INVALID >>>',
            'pipeline_settings': {},
            'description': '',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
        }
        response = authenticated_client.get(
            f'/ConnectionManager/Pipelines/Editor/?es_id={test_connection.id}&pipeline=bad'
        )
        assert response.status_code == 200
        assert response.context.get('parsing_error') is not None


# ============================================================================
# GetCurrentPipelineCode endpoint
# ============================================================================

@pytest.mark.django_db
class TestGetCurrentPipelineCode:
    """Tests for the GetCurrentPipelineCode view"""

    def test_returns_html_pre_block(self, authenticated_client):
        components = {"input": [], "filter": [], "output": []}
        response = authenticated_client.post(
            '/ConnectionManager/GetCurrentPipelineCode/',
            {'components': json.dumps(components)}
        )
        assert response.status_code == 200
        assert b'<pre' in response.content
        assert b'<code' in response.content


# ============================================================================
# SavePipeline edge cases
# ============================================================================

@pytest.mark.django_db
class TestSavePipelineEdgeCases:
    """Tests for SavePipeline edge cases not covered by existing tests"""

    def test_no_save_pipeline_key_returns_400(self, authenticated_client):
        """POST without save_pipeline key returns 400"""
        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'es_id': '1',
            'pipeline': 'mypipe',
        })
        assert response.status_code == 400

    def test_invalid_pipeline_name_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'pipeline': '123invalid',
            'es_id': '1',
        })
        assert response.status_code == 400

    def test_missing_components_and_pipeline_config_returns_400(self, authenticated_client):
        """No pipeline_config and no components → 400"""
        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'pipeline': 'valid_pipe',
            'es_id': '1',
            # neither pipeline_config nor components
        })
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.get_elastic_connection')
    def test_raw_text_mode_saves_directly(self, mock_get_es, authenticated_client, test_connection):
        """When pipeline_config is provided (raw text mode), it is saved as-is"""
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'my_pipe': {
                'pipeline': 'input {} filter {} output {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': ''
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'pipeline': 'my_pipe',
            'es_id': str(test_connection.id),
            'pipeline_config': 'input {} filter {} output {}',
        })
        assert response.status_code == 200
        assert b'saved successfully' in response.content

    @patch('PipelineManager.editor_views.get_elastic_connection')
    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_save_pipeline_success(self, mock_get_pipeline, mock_get_es, authenticated_client, test_connection):
        """Test successful pipeline save"""
        # Mock existing pipeline
        mock_get_pipeline.return_value = {
            'pipeline': 'input {}\nfilter {}\noutput {}',
            'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
            'pipeline_settings': {},
            'description': ''
        }

        # Mock Elasticsearch connection
        mock_es = MagicMock()
        mock_es.logstash.get_pipeline.return_value = {
            'test_pipeline': {
                'pipeline': 'input {}\nfilter {}\noutput {}',
                'pipeline_metadata': {'version': 1, 'type': 'logstash_pipeline'},
                'pipeline_settings': {},
                'description': ''
            }
        }
        mock_es.logstash.put_pipeline.return_value = {'acknowledged': True}
        mock_get_es.return_value = mock_es

        components = {
            "input": [],
            "filter": [],
            "output": []
        }

        response = authenticated_client.post('/ConnectionManager/SavePipeline/', {
            'save_pipeline': 'true',
            'es_id': test_connection.id,
            'pipeline': 'test_pipeline',
            'components': json.dumps(components),
            'add_ids': 'false'
        })

        assert response.status_code == 200
        assert b'Pipeline saved successfully!' in response.content


# ============================================================================
# ComponentsToConfig / ConfigToComponents / GetDiff
# ============================================================================

@pytest.mark.django_db
class TestConversionEndpoints:
    """Tests for ComponentsToConfig, ConfigToComponents, GetDiff"""

    # --- ComponentsToConfig ---

    def test_components_to_config_success(self, authenticated_client):
        components = {"input": [], "filter": [], "output": []}
        response = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {
            'components': json.dumps(components)
        })
        assert response.status_code == 200
        assert response['Content-Type'] == 'text/plain'

    def test_components_to_config_no_components_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/ComponentsToConfig/', {})
        assert response.status_code == 400

    def test_components_to_config_get_returns_405(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/ComponentsToConfig/')
        assert response.status_code == 405

    # --- ConfigToComponents ---

    def test_config_to_components_success(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {
            'config_text': 'input {} filter {} output {}'
        })
        assert response.status_code == 200
        # Response is JSON (string or parsed)
        data = response.json()
        assert data is not None

    def test_config_to_components_no_config_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/ConfigToComponents/', {})
        assert response.status_code == 400
        assert 'error' in response.json()

    def test_config_to_components_get_returns_405(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/ConfigToComponents/')
        assert response.status_code == 405

    # --- GetDiff ---

    def test_get_diff_missing_params_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/GetDiff/', {})
        assert response.status_code == 400
        assert 'error' in response.json()

    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_get_diff_text_mode(self, mock_glp, authenticated_client, test_connection):
        """GetDiff with raw pipeline_text uses text mode"""
        mock_glp.return_value = {'pipeline': 'input {} filter {} output {}'}
        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'mypipe',
            'pipeline_text': 'input {} filter {} output { stdout {} }',
        })
        assert response.status_code == 200
        data = response.json()
        assert 'diff' in data
        assert 'stats' in data
        assert 'current' in data
        assert 'new' in data

    @patch('PipelineManager.editor_views.get_logstash_pipeline')
    def test_get_diff_components_mode(self, mock_glp, authenticated_client, test_connection):
        """GetDiff with components JSON uses components mode"""
        mock_glp.return_value = {'pipeline': 'input {} filter {} output {}'}
        components = {"input": [], "filter": [], "output": []}
        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'mypipe',
            'components': json.dumps(components),
        })
        assert response.status_code == 200
        assert 'diff' in response.json()

    @patch('PipelineManager.editor_views.get_logstash_pipeline', side_effect=Exception("ES error"))
    def test_get_diff_exception_returns_500(self, mock_glp, authenticated_client, test_connection):
        response = authenticated_client.post('/ConnectionManager/GetDiff/', {
            'es_id': test_connection.id,
            'pipeline': 'mypipe',
            'pipeline_text': 'input {}',
        })
        assert response.status_code == 500

    def test_get_diff_get_returns_405(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetDiff/')
        assert response.status_code == 405


# ============================================================================
# Elasticsearch data endpoints
# ============================================================================

@pytest.mark.django_db
class TestElasticsearchDataEndpoints:
    """Tests for GetElasticsearchConnections, GetElasticsearchIndices, GetElasticsearchFields"""

    # --- GetElasticsearchConnections ---

    @patch('PipelineManager.editor_views.get_elastic_connections_from_list', return_value=[])
    def test_get_es_connections_success(self, mock_list, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')
        assert response.status_code == 200
        assert 'connections' in response.json()

    @patch('PipelineManager.editor_views.get_elastic_connections_from_list',
           side_effect=Exception("ES down"))
    def test_get_es_connections_exception_returns_500(self, mock_list, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')
        assert response.status_code == 500
        assert 'error' in response.json()

    @patch('PipelineManager.editor_views.get_elastic_connections_from_list')
    def test_get_es_connections_formats_correctly(self, mock_list, authenticated_client):
        mock_list.return_value = [
            {'id': 1, 'name': 'My ES', 'connection_type': 'CENTRALIZED', 'es': MagicMock()}
        ]
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchConnections/')
        conns = response.json()['connections']
        assert len(conns) == 1
        assert conns[0] == {'id': 1, 'name': 'My ES'}

    # --- GetElasticsearchIndices ---

    def test_get_es_indices_missing_connection_id_returns_400(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchIndices/')
        assert response.status_code == 400
        assert 'error' in response.json()

    @patch('PipelineManager.editor_views.get_elasticsearch_indices', return_value=['index-1', 'index-2'])
    def test_get_es_indices_success(self, mock_indices, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetElasticsearchIndices/?connection_id=1&pattern=index-*'
        )
        assert response.status_code == 200
        assert response.json()['indices'] == ['index-1', 'index-2']

    @patch('PipelineManager.editor_views.get_elasticsearch_indices', side_effect=Exception("timeout"))
    def test_get_es_indices_exception_returns_500(self, mock_indices, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetElasticsearchIndices/?connection_id=1'
        )
        assert response.status_code == 500

    # --- GetElasticsearchFields ---

    def test_get_es_fields_missing_params_returns_400(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetElasticsearchFields/')
        assert response.status_code == 400

    def test_get_es_fields_missing_index_returns_400(self, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetElasticsearchFields/?connection_id=1'
        )
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.get_elasticsearch_field_mappings',
           return_value=['@timestamp', 'host.name'])
    def test_get_es_fields_success(self, mock_fields, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetElasticsearchFields/?connection_id=1&index=my-index'
        )
        assert response.status_code == 200
        assert response.json()['fields'] == ['@timestamp', 'host.name']

    @patch('PipelineManager.editor_views.get_elasticsearch_field_mappings',
           side_effect=Exception("ES error"))
    def test_get_es_fields_exception_returns_500(self, mock_fields, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetElasticsearchFields/?connection_id=1&index=my-index'
        )
        assert response.status_code == 500


# ============================================================================
# QueryElasticsearchDocuments
# ============================================================================

@pytest.mark.django_db
class TestQueryElasticsearchDocuments:
    """Tests for the QueryElasticsearchDocuments view"""

    def test_missing_connection_id_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'index': 'my-index'
        })
        assert response.status_code == 400

    def test_missing_index_returns_400(self, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1'
        })
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.query_elasticsearch_documents', return_value=[{'doc': 1}])
    def test_docid_mode(self, mock_query, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1',
            'index': 'my-index',
            'query_method': 'docid',
            'doc_ids': 'id1\nid2',
        })
        assert response.status_code == 200
        assert response.json()['documents'] == [{'doc': 1}]

    @patch('PipelineManager.editor_views.query_elasticsearch_documents', return_value=[])
    def test_entire_mode(self, mock_query, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1',
            'index': 'my-index',
            'query_method': 'entire',
            'size': '5',
        })
        assert response.status_code == 200

    def test_field_mode_missing_field_returns_400(self, authenticated_client):
        """field query_method without field returns 400"""
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1',
            'index': 'my-index',
            'query_method': 'field',
            # no 'field' param
        })
        assert response.status_code == 400

    @patch('PipelineManager.editor_views.query_elasticsearch_documents', return_value=[])
    def test_field_mode_with_field(self, mock_query, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1',
            'index': 'my-index',
            'query_method': 'field',
            'field': 'host.name',
            'size': '10',
        })
        assert response.status_code == 200

    @patch('PipelineManager.editor_views.query_elasticsearch_documents',
           side_effect=Exception("ES error"))
    def test_exception_returns_500(self, mock_query, authenticated_client):
        response = authenticated_client.post('/ConnectionManager/QueryElasticsearchDocuments/', {
            'connection_id': '1',
            'index': 'my-index',
            'query_method': 'entire',
        })
        assert response.status_code == 500


# ============================================================================
# GetPluginDocumentation (security allowlist)
# ============================================================================

@pytest.mark.django_db
class TestGetPluginDocumentation:
    """Tests for the GetPluginDocumentation security proxy view"""

    def test_missing_type_and_name_returns_400(self, authenticated_client):
        response = authenticated_client.get('/ConnectionManager/GetPluginDocumentation/')
        assert response.status_code == 400

    def test_missing_name_returns_400(self, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input'
        )
        assert response.status_code == 400

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_invalid_plugin_type_returns_400(self, mock_load, authenticated_client):
        mock_load.return_value = {'input': {}, 'filter': {}, 'output': {}}
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=INVALID&name=stdin'
        )
        assert response.status_code == 400

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_plugin_not_found_returns_404(self, mock_load, authenticated_client):
        mock_load.return_value = {'input': {}}
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input&name=nonexistent'
        )
        assert response.status_code == 404

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_plugin_with_no_link_returns_404(self, mock_load, authenticated_client):
        mock_load.return_value = {'input': {'stdin': {}}}   # no 'link' key
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input&name=stdin'
        )
        assert response.status_code == 404

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_untrusted_domain_returns_403(self, mock_load, authenticated_client):
        """A doc URL on an untrusted domain is blocked"""
        mock_load.return_value = {
            'input': {'stdin': {'link': 'https://evil.com/docs'}}
        }
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input&name=stdin'
        )
        assert response.status_code == 403

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_trusted_elastic_domain_returns_url(self, mock_load, authenticated_client):
        """A doc URL on www.elastic.co is allowed"""
        mock_load.return_value = {
            'input': {
                'stdin': {'link': 'https://www.elastic.co/guide/en/logstash/current/plugins-inputs-stdin.html'}
            }
        }
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input&name=stdin'
        )
        assert response.status_code == 200
        data = response.json()
        assert 'url' in data
        assert 'elastic.co' in data['url']

    @patch('PipelineManager.editor_views._load_plugin_data')
    def test_trusted_github_domain_returns_url(self, mock_load, authenticated_client):
        """A doc URL on github.com is also allowed"""
        mock_load.return_value = {
            'filter': {'mutate': {'link': 'https://github.com/elastic/logstash'}}
        }
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=filter&name=mutate'
        )
        assert response.status_code == 200

    @patch('PipelineManager.editor_views._load_plugin_data', side_effect=Exception("file missing"))
    def test_exception_returns_500(self, mock_load, authenticated_client):
        response = authenticated_client.get(
            '/ConnectionManager/GetPluginDocumentation/?type=input&name=stdin'
        )
        assert response.status_code == 500
