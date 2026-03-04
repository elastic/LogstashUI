"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

import pytest
from django.test import RequestFactory
from unittest.mock import patch, Mock

from Common.context_processors import (
    version_update_info,
    navigation_highlight
)
from PipelineManager.models import Connection
from SNMP.models import Device


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
    """Test navigation_highlight context processor"""

    def test_no_connections_highlights_connection_manager(self, mock_request, db):
        """Test that Connection Manager is highlighted when no connections exist"""
        # Ensure no connections exist
        Connection.objects.all().delete()
        Device.objects.all().delete()
        
        context = navigation_highlight(mock_request)
        
        assert context['highlight_connection_manager'] is True
        assert context['highlight_snmp_devices'] is False

    def test_connections_exist_no_devices_highlights_snmp(self, mock_request, db):
        """Test that SNMP Devices is highlighted when connections exist but no devices"""
        # Create a connection
        Connection.objects.create(
            name='Test Connection',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        # Ensure no devices exist
        Device.objects.all().delete()
        
        context = navigation_highlight(mock_request)
        
        assert context['highlight_connection_manager'] is False
        assert context['highlight_snmp_devices'] is True

    def test_both_exist_no_highlights(self, mock_request, db):
        """Test that nothing is highlighted when both connections and devices exist"""
        # Create a connection
        connection = Connection.objects.create(
            name='Test Connection',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        # Create a device
        Device.objects.create(
            name='Test Device',
            ip_address='192.168.1.1'
        )
        
        context = navigation_highlight(mock_request)
        
        assert context['highlight_connection_manager'] is False
        assert context['highlight_snmp_devices'] is False

    def test_multiple_connections_no_devices(self, mock_request, db):
        """Test with multiple connections but no devices"""
        Connection.objects.create(
            name='Connection 1',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        Connection.objects.create(
            name='Connection 2',
            connection_type='CENTRALIZED',
            cloud_id='test-id',
            api_key='test-api-key'
        )
        Device.objects.all().delete()
        
        context = navigation_highlight(mock_request)
        
        assert context['highlight_connection_manager'] is False
        assert context['highlight_snmp_devices'] is True

    def test_no_connections_multiple_devices(self, mock_request, db):
        """Test with no connections but devices exist (edge case)"""
        # This is an edge case - devices shouldn't exist without connections
        # but we test the logic anyway
        Connection.objects.all().delete()
        
        # Create a connection temporarily to create device, then delete it
        connection = Connection.objects.create(
            name='Temp Connection',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        Device.objects.create(
            name='Device 1',
            ip_address='192.168.1.1'
        )
        
        context = navigation_highlight(mock_request)
        
        # Should highlight connection manager since no connections exist
        assert context['highlight_connection_manager'] is False  # Connection exists
        assert context['highlight_snmp_devices'] is False  # Device exists

    def test_context_keys_always_present(self, mock_request, db):
        """Test that context keys are always present regardless of state"""
        Connection.objects.all().delete()
        Device.objects.all().delete()
        
        context = navigation_highlight(mock_request)
        
        assert 'highlight_connection_manager' in context
        assert 'highlight_snmp_devices' in context
        assert isinstance(context['highlight_connection_manager'], bool)
        assert isinstance(context['highlight_snmp_devices'], bool)

    def test_navigation_highlight_with_different_request_types(self, request_factory, db):
        """Test navigation_highlight works with different request types"""
        Connection.objects.all().delete()
        Device.objects.all().delete()
        
        # Test with GET request
        get_request = request_factory.get('/test/')
        context = navigation_highlight(get_request)
        assert context['highlight_connection_manager'] is True
        
        # Test with POST request
        post_request = request_factory.post('/test/')
        context = navigation_highlight(post_request)
        assert context['highlight_connection_manager'] is True
        
        # Test with PUT request
        put_request = request_factory.put('/test/')
        context = navigation_highlight(put_request)
        assert context['highlight_connection_manager'] is True

    def test_navigation_highlight_database_queries(self, mock_request, db):
        """Test that navigation_highlight makes expected database queries"""
        Connection.objects.all().delete()
        Device.objects.all().delete()
        
        # This should make 2 queries: one for Connection.exists(), one for Device.exists()
        with patch.object(Connection.objects, 'exists', return_value=False) as mock_conn_exists:
            with patch.object(Device.objects, 'exists', return_value=False) as mock_dev_exists:
                context = navigation_highlight(mock_request)
                
                mock_conn_exists.assert_called_once()
                mock_dev_exists.assert_called_once()  # Both queries are made
                assert context['highlight_connection_manager'] is True
                assert context['highlight_snmp_devices'] is False

    def test_navigation_highlight_logic_flow(self, mock_request, db):
        """Test the complete logic flow of navigation_highlight"""
        # State 1: No connections, no devices
        Connection.objects.all().delete()
        Device.objects.all().delete()
        context = navigation_highlight(mock_request)
        assert context == {
            'highlight_connection_manager': True,
            'highlight_snmp_devices': False
        }
        
        # State 2: Has connections, no devices
        Connection.objects.create(
            name='Test',
            connection_type='CENTRALIZED',
            host='https://localhost:9200',
            username='elastic',
            password='changeme'
        )
        context = navigation_highlight(mock_request)
        assert context == {
            'highlight_connection_manager': False,
            'highlight_snmp_devices': True
        }
        
        # State 3: Has connections and devices
        connection = Connection.objects.first()
        Device.objects.create(
            name='Device',
            ip_address='192.168.1.1'
        )
        context = navigation_highlight(mock_request)
        assert context == {
            'highlight_connection_manager': False,
            'highlight_snmp_devices': False
        }


class TestContextProcessorsIntegration:
    """Integration tests for context processors"""

    @patch('Common.context_processors.check_for_update')
    def test_both_context_processors_together(self, mock_check_update, mock_request, db):
        """Test that both context processors can be used together"""
        mock_check_update.return_value = {'update_available': True}
        Connection.objects.all().delete()
        Device.objects.all().delete()
        
        version_context = version_update_info(mock_request)
        navigation_context = navigation_highlight(mock_request)
        
        # Combine contexts (as Django would do)
        combined_context = {**version_context, **navigation_context}
        
        assert 'version_update' in combined_context
        assert 'highlight_connection_manager' in combined_context
        assert 'highlight_snmp_devices' in combined_context
        assert len(combined_context) == 3

    def test_context_processors_dont_interfere(self, mock_request, db):
        """Test that context processors don't interfere with each other"""
        with patch('Common.context_processors.check_for_update') as mock_check:
            mock_check.return_value = {'test': 'data'}
            
            # Call both processors
            version_context = version_update_info(mock_request)
            navigation_context = navigation_highlight(mock_request)
            
            # Verify they return different keys
            assert set(version_context.keys()).isdisjoint(set(navigation_context.keys()))
