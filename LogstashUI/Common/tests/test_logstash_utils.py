#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from unittest.mock import Mock, patch, MagicMock

from Common.logstash_utils import get_logstash_pipeline


class TestGetLogstashPipeline:
    """Tests for get_logstash_pipeline function"""

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_returns_pipeline_document_on_success(self, mock_get_connection):
        """Test that the pipeline document is returned when found"""
        pipeline_name = 'my_pipeline'
        expected_doc = {
            'pipeline': 'input { stdin {} } output { stdout {} }',
            'last_modified': '2024-01-01T00:00:00Z',
            'username': 'elastic'
        }

        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {pipeline_name: expected_doc}
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name=pipeline_name)

        assert result == expected_doc

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_calls_get_elastic_connection_with_correct_id(self, mock_get_connection):
        """Test that get_elastic_connection is called with the provided es_id"""
        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {'pipe': {'pipeline': 'input {}'}}
        mock_get_connection.return_value = mock_es

        get_logstash_pipeline(es_id=42, pipeline_name='pipe')

        mock_get_connection.assert_called_once_with(42)

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_calls_get_pipeline_with_correct_name(self, mock_get_connection):
        """Test that logstash.get_pipeline is called with the correct pipeline name"""
        pipeline_name = 'target_pipeline'
        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {pipeline_name: {'pipeline': ''}}
        mock_get_connection.return_value = mock_es

        get_logstash_pipeline(es_id=1, pipeline_name=pipeline_name)

        mock_es.logstash.get_pipeline.assert_called_once_with(id=pipeline_name)

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_returns_none_on_key_error(self, mock_get_connection):
        """Test that None is returned when pipeline name not found in response (KeyError)"""
        mock_es = Mock()
        # Pipeline name not in response dict → KeyError
        mock_es.logstash.get_pipeline.return_value = {'other_pipeline': {}}
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name='nonexistent_pipeline')

        assert result is None

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_returns_none_on_connection_error(self, mock_get_connection):
        """Test that None is returned when an exception occurs during connection"""
        mock_get_connection.side_effect = Exception("Connection refused")

        result = get_logstash_pipeline(es_id=1, pipeline_name='my_pipeline')

        assert result is None

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_returns_none_on_api_error(self, mock_get_connection):
        """Test that None is returned when the ES API call raises an exception"""
        mock_es = Mock()
        mock_es.logstash.get_pipeline.side_effect = Exception("API Error: 500")
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name='my_pipeline')

        assert result is None

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_logs_error_on_key_error(self, mock_get_connection, caplog):
        """Test that an error is logged when pipeline is not found (KeyError)"""
        pipeline_name = 'missing_pipeline'
        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {}  # Missing key
        mock_get_connection.return_value = mock_es

        get_logstash_pipeline(es_id=5, pipeline_name=pipeline_name)

        assert pipeline_name in caplog.text

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_logs_error_on_generic_exception(self, mock_get_connection, caplog):
        """Test that an error is logged when a generic exception occurs"""
        pipeline_name = 'error_pipeline'
        mock_es = Mock()
        mock_es.logstash.get_pipeline.side_effect = ConnectionError("Timeout")
        mock_get_connection.return_value = mock_es

        get_logstash_pipeline(es_id=3, pipeline_name=pipeline_name)

        assert pipeline_name in caplog.text

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_returns_full_pipeline_document_structure(self, mock_get_connection):
        """Test that the full pipeline document structure is preserved"""
        pipeline_name = 'complex_pipeline'
        expected_doc = {
            'pipeline': 'input { beats { port => 5044 } } output { elasticsearch {} }',
            'last_modified': '2024-03-01T12:00:00Z',
            'username': 'kibana_system',
            'metadata': {
                'type': 'logstash_pipeline',
                'version': 1
            }
        }

        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {pipeline_name: expected_doc}
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name=pipeline_name)

        assert result == expected_doc
        assert result['pipeline'] == expected_doc['pipeline']
        assert result['username'] == 'kibana_system'

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_handles_multiple_pipelines_in_response(self, mock_get_connection):
        """Test correct pipeline is returned when response contains multiple pipelines"""
        target_name = 'target'
        target_doc = {'pipeline': 'input { stdin {} }'}
        other_doc = {'pipeline': 'input { beats {} }'}

        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {
            target_name: target_doc,
            'other': other_doc
        }
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name=target_name)

        assert result == target_doc
        assert result != other_doc

    @patch('Common.logstash_utils.get_elastic_connection')
    def test_handles_empty_pipeline_response(self, mock_get_connection):
        """Test returns None when response is completely empty dict"""
        mock_es = Mock()
        mock_es.logstash.get_pipeline.return_value = {}
        mock_get_connection.return_value = mock_es

        result = get_logstash_pipeline(es_id=1, pipeline_name='any_pipeline')

        assert result is None
