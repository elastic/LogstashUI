#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.test import RequestFactory
from django.http import HttpResponse

from Common.middleware import SecurityHeadersMiddleware


@pytest.fixture
def request_factory():
    """Django RequestFactory for creating mock requests"""
    return RequestFactory()


@pytest.fixture
def mock_request(request_factory):
    """Create a basic GET mock request"""
    return request_factory.get('/')


@pytest.fixture
def middleware():
    """Create middleware instance with a simple get_response callable"""
    def get_response(request):
        return HttpResponse("OK", status=200)

    return SecurityHeadersMiddleware(get_response)


@pytest.fixture
def middleware_with_custom_response():
    """Factory fixture to create middleware with a custom response"""
    def factory(response):
        return SecurityHeadersMiddleware(lambda r: response)
    return factory


class TestSecurityHeadersMiddlewareInit:
    """Tests for SecurityHeadersMiddleware initialization"""

    def test_middleware_stores_get_response(self):
        """Test that middleware stores the get_response callable"""
        def get_response(request):
            return HttpResponse("OK")

        mw = SecurityHeadersMiddleware(get_response)
        assert mw.get_response is get_response

    def test_middleware_callable(self, middleware, mock_request):
        """Test that middleware is callable and returns a response"""
        response = middleware(mock_request)
        assert response is not None
        assert response.status_code == 200


class TestContentSecurityPolicy:
    """Tests for the Content-Security-Policy header"""

    def test_csp_header_is_set(self, middleware, mock_request):
        """Test that CSP header is present in the response"""
        response = middleware(mock_request)
        assert 'Content-Security-Policy' in response

    def test_csp_default_src_self(self, middleware, mock_request):
        """Test that default-src is restricted to self"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "default-src 'self'" in csp

    def test_csp_script_src_includes_self(self, middleware, mock_request):
        """Test that script-src includes self"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "script-src 'self'" in csp

    def test_csp_script_src_allows_unsafe_inline(self, middleware, mock_request):
        """Test that script-src allows unsafe-inline (required for htmx)"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        # Need unsafe-inline for htmx and dynamic JS
        assert "'unsafe-inline'" in csp

    def test_csp_style_src_allows_unsafe_inline(self, middleware, mock_request):
        """Test that style-src allows unsafe-inline (required for Tailwind)"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "style-src 'self' 'unsafe-inline'" in csp

    def test_csp_img_src_allows_data_and_https(self, middleware, mock_request):
        """Test that img-src allows data URIs and HTTPS sources"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "img-src 'self' data: https:" in csp

    def test_csp_font_src_allows_data(self, middleware, mock_request):
        """Test that font-src allows data URIs"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "font-src 'self' data:" in csp

    def test_csp_connect_src_self_only(self, middleware, mock_request):
        """Test that connect-src is restricted to self"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "connect-src 'self'" in csp

    def test_csp_frame_src_includes_elastic(self, middleware, mock_request):
        """Test that frame-src includes elastic.co documentation domains"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "https://www.elastic.co" in csp
        assert "https://elastic.co" in csp

    def test_csp_frame_src_includes_github(self, middleware, mock_request):
        """Test that frame-src includes github.com for plugin docs"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "https://github.com" in csp

    def test_csp_frame_src_includes_rubydoc(self, middleware, mock_request):
        """Test that frame-src includes rubydoc.info for plugin docs"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "https://rubydoc.info" in csp

    def test_csp_frame_ancestors_self_only(self, middleware, mock_request):
        """Test that frame-ancestors restricts framing to same origin (anti-clickjacking)"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert "frame-ancestors 'self'" in csp

    def test_csp_directives_separated_by_semicolons(self, middleware, mock_request):
        """Test that CSP directives are joined with semicolons"""
        response = middleware(mock_request)
        csp = response['Content-Security-Policy']
        assert '; ' in csp


class TestAdditionalSecurityHeaders:
    """Tests for X-Content-Type-Options and Referrer-Policy headers"""

    def test_x_content_type_options_nosniff(self, middleware, mock_request):
        """Test that X-Content-Type-Options is set to nosniff"""
        response = middleware(mock_request)
        assert response['X-Content-Type-Options'] == 'nosniff'

    def test_referrer_policy_set(self, middleware, mock_request):
        """Test that Referrer-Policy header is set"""
        response = middleware(mock_request)
        assert 'Referrer-Policy' in response

    def test_referrer_policy_value(self, middleware, mock_request):
        """Test Referrer-Policy has the correct value"""
        response = middleware(mock_request)
        assert response['Referrer-Policy'] == 'no-referrer-when-downgrade'


class TestMiddlewarePassthrough:
    """Tests ensuring middleware doesn't break normal response behavior"""

    def test_middleware_preserves_response_status(self, request_factory):
        """Test that middleware preserves the original response status code"""
        def get_response(request):
            return HttpResponse("Created", status=201)

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.get('/')
        response = mw(request)
        assert response.status_code == 201

    def test_middleware_preserves_response_body(self, request_factory):
        """Test that middleware preserves the original response body"""
        def get_response(request):
            return HttpResponse("Hello World")

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.get('/')
        response = mw(request)
        assert b'Hello World' in response.content

    def test_middleware_does_not_remove_existing_headers(self, request_factory):
        """Test that middleware does not remove headers already set by the view"""
        def get_response(request):
            resp = HttpResponse("OK")
            resp['X-Custom-Header'] = 'custom-value'
            return resp

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.get('/')
        response = mw(request)
        assert response['X-Custom-Header'] == 'custom-value'

    def test_middleware_works_with_post_request(self, request_factory):
        """Test that middleware applies headers to POST requests too"""
        def get_response(request):
            return HttpResponse("Posted", status=200)

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.post('/submit/')
        response = mw(request)
        assert 'Content-Security-Policy' in response
        assert response['X-Content-Type-Options'] == 'nosniff'

    def test_middleware_works_with_json_response(self, request_factory):
        """Test that middleware works with JSON responses"""
        from django.http import JsonResponse

        def get_response(request):
            return JsonResponse({'key': 'value'})

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.get('/api/data/')
        response = mw(request)
        assert 'Content-Security-Policy' in response
        assert response['X-Content-Type-Options'] == 'nosniff'

    def test_middleware_applies_to_error_responses(self, request_factory):
        """Test that security headers are added even to error responses"""
        def get_response(request):
            return HttpResponse("Not Found", status=404)

        mw = SecurityHeadersMiddleware(get_response)
        request = request_factory.get('/missing/')
        response = mw(request)
        assert response.status_code == 404
        assert 'Content-Security-Policy' in response

    def test_headers_applied_on_every_request(self, request_factory):
        """Test that headers are applied on every call (not just first)"""
        def get_response(request):
            return HttpResponse("OK")

        mw = SecurityHeadersMiddleware(get_response)

        for _ in range(3):
            request = request_factory.get('/')
            response = mw(request)
            assert 'Content-Security-Policy' in response
            assert response['X-Content-Type-Options'] == 'nosniff'
