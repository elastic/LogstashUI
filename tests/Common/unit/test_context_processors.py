#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.test import RequestFactory
from unittest.mock import patch, Mock

from Common.context_processors import (
    version_update_info,
    navigation_highlight
)
from PipelineManager.models import Connection


@pytest.fixture
def request_factory():
    """Django RequestFactory for creating mock requests"""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a basic mock request"""
    return request_factory.get('/')


class TestVersionUpdateInfo:
    """Test version_update_info context processor"""

    @patch('Common.context_processors.check_for_update')
    def test_version_update_info_returns_context(self, mock_check_update, mock_request):
        """Test that version_update_info returns correct context"""
        mock_update_data = {
            'update_available': True,
            'latest_version': '2.0.0',
            'current_version': '1.0.0'
        }
        mock_check_update.return_value = mock_update_data
        
        context = version_update_info(mock_request)
        
        assert 'version_update' in context
        assert context['version_update'] == mock_update_data
        mock_check_update.assert_called_once()

    @patch('Common.context_processors.check_for_update')
    def test_version_update_info_no_update(self, mock_check_update, mock_request):
        """Test version_update_info when no update is available"""
        mock_update_data = {
            'update_available': False,
            'latest_version': '1.0.0',
            'current_version': '1.0.0'
        }
        mock_check_update.return_value = mock_update_data
        
        context = version_update_info(mock_request)
        
        assert context['version_update']['update_available'] is False

    @patch('Common.context_processors.check_for_update')
    def test_version_update_info_none_response(self, mock_check_update, mock_request):
        """Test version_update_info when check_for_update returns None"""
        mock_check_update.return_value = None
        
        context = version_update_info(mock_request)
        
        assert 'version_update' in context
        assert context['version_update'] is None

    @patch('Common.context_processors.check_for_update')
    def test_version_update_info_error_handling(self, mock_check_update, mock_request):
        """Test version_update_info handles errors gracefully"""
        mock_check_update.side_effect = Exception("Network error")
        
        # Should raise the exception (no error handling in the function)
        with pytest.raises(Exception):
            version_update_info(mock_request)


class TestNavigationHighlight:
    """Test navigation_highlight context processor.

    highlight_snmp_devices was removed from the server-side context processor;
    that logic now lives in client-side localStorage.  The processor only tracks
    whether any Connection exists and exposes:
      - highlight_connection_manager (bool)
      - has_connections (bool)
    """

    def test_no_connections_highlights_connection_manager(self, mock_request, db):
        """Connection Manager is highlighted when no connections exist"""
        Connection.objects.all().delete()

        context = navigation_highlight(mock_request)

        assert context['highlight_connection_manager'] is True
        assert context['has_connections'] is False

    def test_connections_exist_does_not_highlight_connection_manager(self, mock_request, db):
        """Connection Manager is NOT highlighted when at least one connection exists"""
        Connection.objects.create(
            name='Test Connection',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme',
            port=None,
        )

        context = navigation_highlight(mock_request)

        assert context['highlight_connection_manager'] is False
        assert context['has_connections'] is True

    def test_multiple_connections(self, mock_request, db):
        """has_connections is True when multiple connections exist"""
        Connection.objects.create(
            name='Connection 1',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme',
            port=None,
        )
        Connection.objects.create(
            name='Connection 2',
            connection_type='CENTRALIZED',
            cloud_id='test-id',
            api_key='test-api-key',
        )

        context = navigation_highlight(mock_request)

        assert context['highlight_connection_manager'] is False
        assert context['has_connections'] is True

    def test_context_keys_always_present(self, mock_request, db):
        """highlight_connection_manager and has_connections are always in context"""
        Connection.objects.all().delete()

        context = navigation_highlight(mock_request)

        assert 'highlight_connection_manager' in context
        assert 'has_connections' in context
        assert isinstance(context['highlight_connection_manager'], bool)
        assert isinstance(context['has_connections'], bool)

    def test_navigation_highlight_with_different_request_types(self, request_factory, db):
        """navigation_highlight works regardless of HTTP method"""
        Connection.objects.all().delete()

        for method in ('get', 'post', 'put'):
            request = getattr(request_factory, method)('/test/')
            context = navigation_highlight(request)
            assert context['highlight_connection_manager'] is True

    def test_navigation_highlight_database_queries(self, mock_request, db):
        """navigation_highlight queries Connection.objects.exists() exactly once"""
        Connection.objects.all().delete()

        with patch.object(Connection.objects, 'exists', return_value=False) as mock_conn_exists:
            context = navigation_highlight(mock_request)

            mock_conn_exists.assert_called_once()
            assert context['highlight_connection_manager'] is True
            assert context['has_connections'] is False

    def test_navigation_highlight_logic_flow(self, mock_request, db):
        """Complete logic: no connections → highlight; connection added → no highlight"""
        Connection.objects.all().delete()

        # State 1: No connections
        context = navigation_highlight(mock_request)
        assert context == {
            'highlight_connection_manager': True,
            'has_connections': False,
        }

        # State 2: Connection added
        Connection.objects.create(
            name='Test',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme',
            port=None,
        )
        context = navigation_highlight(mock_request)
        assert context == {
            'highlight_connection_manager': False,
            'has_connections': True,
        }


class TestContextProcessorsIntegration:
    """Integration tests for context processors"""

    @patch('Common.context_processors.check_for_update')
    def test_both_context_processors_together(self, mock_check_update, mock_request, db):
        """Both context processors can be used together without key collisions"""
        mock_check_update.return_value = {'update_available': True}
        Connection.objects.all().delete()

        version_context = version_update_info(mock_request)
        navigation_context = navigation_highlight(mock_request)

        combined_context = {**version_context, **navigation_context}

        assert 'version_update' in combined_context
        assert 'highlight_connection_manager' in combined_context
        assert 'has_connections' in combined_context
        # version_update + highlight_connection_manager + has_connections
        assert len(combined_context) == 3

    def test_context_processors_dont_interfere(self, mock_request, db):
        """Context processors return disjoint key sets"""
        with patch('Common.context_processors.check_for_update') as mock_check:
            mock_check.return_value = {'test': 'data'}

            version_context = version_update_info(mock_request)
            navigation_context = navigation_highlight(mock_request)

            assert set(version_context.keys()).isdisjoint(set(navigation_context.keys()))
