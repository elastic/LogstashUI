#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.test import RequestFactory

from Common.error_handlers import handler400, handler403, handler404, handler500

# All tests in this file require DB access because Django's render() triggers
# context processors (navigation_highlight) that query Connection/Device models.
pytestmark = pytest.mark.django_db


@pytest.fixture
def request_factory():
    """Django RequestFactory for creating mock requests"""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a basic GET mock request"""
    return request_factory.get('/some/path/')


class TestHandler400:
    """Tests for handler400 (Bad Request)"""

    def test_returns_400_status(self, mock_request):
        """Test that handler400 returns a 400 status code"""
        response = handler400(mock_request)
        assert response.status_code == 400

    def test_correct_error_code_in_context(self, mock_request):
        """Test that context contains correct error code"""
        response = handler400(mock_request)
        assert response.context_data['error_code'] == '400'

    def test_correct_error_title(self, mock_request):
        """Test that context contains correct error title"""
        response = handler400(mock_request)
        assert response.context_data['error_title'] == 'Bad Request'

    def test_correct_error_message(self, mock_request):
        """Test that context contains appropriate error message"""
        response = handler400(mock_request)
        assert 'could not understand' in response.context_data['error_message']

    def test_with_exception(self, mock_request):
        """Test that exception class name is included when exception is provided"""
        exc = ValueError("bad input")
        response = handler400(mock_request, exception=exc)
        assert response.context_data['exception'] == 'ValueError'

    def test_without_exception(self, mock_request):
        """Test that exception is None when no exception is provided"""
        response = handler400(mock_request)
        assert response.context_data['exception'] is None

    def test_with_none_exception(self, mock_request):
        """Test that explicitly passing None exception gives None in context"""
        response = handler400(mock_request, exception=None)
        assert response.context_data['exception'] is None

    def test_uses_error_template(self, mock_request):
        """Test that the error.html template is used"""
        response = handler400(mock_request)
        assert response.template_name == 'error.html'


class TestHandler403:
    """Tests for handler403 (Access Denied)"""

    def test_returns_403_status(self, mock_request):
        """Test that handler403 returns a 403 status code"""
        response = handler403(mock_request)
        assert response.status_code == 403

    def test_correct_error_code(self, mock_request):
        """Test correct error code in context"""
        response = handler403(mock_request)
        assert response.context_data['error_code'] == '403'

    def test_correct_error_title(self, mock_request):
        """Test correct error title"""
        response = handler403(mock_request)
        assert response.context_data['error_title'] == 'Access Denied'

    def test_correct_error_message(self, mock_request):
        """Test permission-related error message"""
        response = handler403(mock_request)
        assert 'permission' in response.context_data['error_message'].lower()

    def test_with_exception(self, mock_request):
        """Test exception class name in context"""
        exc = PermissionError("Access denied")
        response = handler403(mock_request, exception=exc)
        assert response.context_data['exception'] == 'PermissionError'

    def test_without_exception(self, mock_request):
        """Test that exception is None when not provided"""
        response = handler403(mock_request)
        assert response.context_data['exception'] is None

    def test_uses_error_template(self, mock_request):
        """Test that the error.html template is used"""
        response = handler403(mock_request)
        assert response.template_name == 'error.html'


class TestHandler404:
    """Tests for handler404 (Page Not Found)"""

    def test_returns_404_status(self, mock_request):
        """Test that handler404 returns a 404 status code"""
        response = handler404(mock_request)
        assert response.status_code == 404

    def test_correct_error_code(self, mock_request):
        """Test correct error code in context"""
        response = handler404(mock_request)
        assert response.context_data['error_code'] == '404'

    def test_correct_error_title(self, mock_request):
        """Test correct error title"""
        response = handler404(mock_request)
        assert response.context_data['error_title'] == 'Page Not Found'

    def test_correct_error_message(self, mock_request):
        """Test not-found error message"""
        response = handler404(mock_request)
        assert 'does not exist' in response.context_data['error_message']

    def test_path_included_in_context(self, request_factory):
        """Test that request path is included in context for 404"""
        request = request_factory.get('/missing/page/')
        response = handler404(request)
        assert response.context_data['path'] == '/missing/page/'

    def test_with_exception(self, mock_request):
        """Test exception class name in context"""
        exc = LookupError("Not found")
        response = handler404(mock_request, exception=exc)
        assert response.context_data['exception'] == 'LookupError'

    def test_without_exception(self, mock_request):
        """Test that exception is None when not provided"""
        response = handler404(mock_request)
        assert response.context_data['exception'] is None

    def test_uses_error_template(self, mock_request):
        """Test that the error.html template is used"""
        response = handler404(mock_request)
        assert response.template_name == 'error.html'

    def test_path_reflects_actual_request(self, request_factory):
        """Test that path value matches the actual request path"""
        request = request_factory.get('/admin/nonexistent/')
        response = handler404(request)
        assert response.context_data['path'] == '/admin/nonexistent/'


class TestHandler500:
    """Tests for handler500 (Server Error)"""

    def test_returns_500_status(self, mock_request):
        """Test that handler500 returns a 500 status code"""
        response = handler500(mock_request)
        assert response.status_code == 500

    def test_correct_error_code(self, mock_request):
        """Test correct error code in context"""
        response = handler500(mock_request)
        assert response.context_data['error_code'] == '500'

    def test_correct_error_title(self, mock_request):
        """Test correct error title"""
        response = handler500(mock_request)
        assert response.context_data['error_title'] == 'Server Error'

    def test_correct_error_message(self, mock_request):
        """Test server error message"""
        response = handler500(mock_request)
        assert 'Something went wrong' in response.context_data['error_message']

    def test_path_included_in_context(self, request_factory):
        """Test that request path is included in context for 500"""
        request = request_factory.get('/api/some-endpoint/')
        response = handler500(request)
        assert response.context_data['path'] == '/api/some-endpoint/'

    def test_with_exception(self, mock_request):
        """Test exception class name in context"""
        exc = RuntimeError("Something blew up")
        response = handler500(mock_request, exception=exc)
        assert response.context_data['exception'] == 'RuntimeError'

    def test_without_exception(self, mock_request):
        """Test that exception is None when not provided"""
        response = handler500(mock_request)
        assert response.context_data['exception'] is None

    def test_uses_error_template(self, mock_request):
        """Test that the error.html template is used"""
        response = handler500(mock_request)
        assert response.template_name == 'error.html'

    def test_path_reflects_actual_request(self, request_factory):
        """Test that path value matches the actual request path"""
        request = request_factory.get('/pipeline/1/deploy/')
        response = handler500(request)
        assert response.context_data['path'] == '/pipeline/1/deploy/'


class TestErrorHandlerEdgeCases:
    """Edge case tests across all error handlers"""

    def test_all_handlers_use_same_template(self, mock_request):
        """Test that all four handlers use the same error.html template"""
        for handler in [handler400, handler403, handler404, handler500]:
            response = handler(mock_request)
            assert response.template_name == 'error.html', \
                f"{handler.__name__} should use 'error.html' template"

    def test_exception_class_name_not_message(self, mock_request):
        """Test that context stores class name, not exception message"""
        exc = ValueError("This is the message, not the class name")
        response = handler400(mock_request, exception=exc)
        # Should be class name, not the message
        assert response.context_data['exception'] == 'ValueError'
        assert 'message' not in response.context_data['exception']

    def test_handler404_and_500_include_path_not_400_403(self, mock_request):
        """Test that only 404 and 500 include path in context"""
        # 400 and 403 should NOT have path
        assert 'path' not in handler400(mock_request).context_data
        assert 'path' not in handler403(mock_request).context_data
        # 404 and 500 SHOULD have path
        assert 'path' in handler404(mock_request).context_data
        assert 'path' in handler500(mock_request).context_data

    @pytest.mark.parametrize("handler,expected_status", [
        (handler400, 400),
        (handler403, 403),
        (handler404, 404),
        (handler500, 500),
    ])
    def test_status_codes(self, mock_request, handler, expected_status):
        """Parametrized test verifying each handler returns the correct status code"""
        response = handler(mock_request)
        assert response.status_code == expected_status

    @pytest.mark.parametrize("handler,expected_code", [
        (handler400, '400'),
        (handler403, '403'),
        (handler404, '404'),
        (handler500, '500'),
    ])
    def test_error_codes_in_context(self, mock_request, handler, expected_code):
        """Parametrized test verifying error_code in context matches HTTP status"""
        response = handler(mock_request)
        assert response.context_data['error_code'] == expected_code
