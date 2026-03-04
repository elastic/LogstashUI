"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

import pytest
from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse
from django.test import RequestFactory
from unittest.mock import Mock

from Common.decorators import require_admin_role
from Management.models import UserProfile


@pytest.fixture
def request_factory():
    """Django RequestFactory for creating mock requests"""
    return RequestFactory()


@pytest.fixture
def admin_user(db):
    """Create a user with admin profile"""
    user = User.objects.create_user(
        username='admin_user',
        password='testpass123',
        email='admin@example.com'
    )
    # Signal creates profile automatically, just ensure it's admin
    profile, created = UserProfile.objects.get_or_create(user=user, defaults={'role': 'admin'})
    if not created:
        profile.role = 'admin'
        profile.save()
    return user


@pytest.fixture
def readonly_user(db):
    """Create a user with readonly profile"""
    user = User.objects.create_user(
        username='readonly_user',
        password='testpass123',
        email='readonly@example.com'
    )
    # Signal creates profile automatically, update to readonly
    profile = UserProfile.objects.get(user=user)
    profile.role = 'readonly'
    profile.save()
    # Refresh user from database to get updated profile relationship
    user.refresh_from_db()
    return user


@pytest.fixture
def user_without_profile(db):
    """Create a user without a profile (edge case for bug 2a)"""
    from django.db.models.signals import post_save
    from Management.models import create_user_profile
    
    # Temporarily disconnect the signal to prevent auto-creation
    post_save.disconnect(create_user_profile, sender=User)
    
    try:
        user = User.objects.create_user(
            username='no_profile_user',
            password='testpass123',
            email='noprofile@example.com'
        )
        # Explicitly ensure no profile exists
        UserProfile.objects.filter(user=user).delete()
    finally:
        # Reconnect the signal
        post_save.connect(create_user_profile, sender=User)
    
    return user


@pytest.fixture
def mock_view():
    """Create a mock view function"""
    def view_func(request, *args, **kwargs):
        return HttpResponse("Success", status=200)
    view_func.__name__ = "mock_view_function"
    return view_func


class TestRequireAdminRoleDecorator:
    """Test require_admin_role decorator"""

    def test_unauthenticated_request_denied(self, request_factory, mock_view):
        """Test that unauthenticated requests are denied"""
        request = request_factory.get('/test/')
        request.user = Mock()
        request.user.is_authenticated = False
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        assert response.status_code == 403
        assert b'You must be logged in to perform this action' in response.content
        assert 'HX-Trigger' in response
        assert 'showToastEvent' in response['HX-Trigger']

    def test_admin_user_allowed(self, request_factory, mock_view, admin_user):
        """Test that admin users are allowed access"""
        request = request_factory.get('/test/')
        request.user = admin_user
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        assert response.status_code == 200
        assert b'Success' in response.content

    def test_readonly_user_denied(self, request_factory, mock_view, readonly_user):
        """Test that readonly users are denied access"""
        request = request_factory.get('/test/')
        request.user = readonly_user
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        assert response.status_code == 403
        assert b'Access denied: Admin role required' in response.content
        assert 'HX-Trigger' in response
        assert 'showToastEvent' in response['HX-Trigger']

    def test_user_without_profile_denied(self, request_factory, mock_view, user_without_profile):
        """
        CRITICAL TEST for bug 2a: Test that users without profiles are denied access.
        This is the missing-profile edge case that was a security vulnerability.
        """
        request = request_factory.get('/test/')
        request.user = user_without_profile
        
        # Verify user has no profile
        assert not hasattr(user_without_profile, 'profile') or not UserProfile.objects.filter(user=user_without_profile).exists()
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        # User should be DENIED, not allowed
        assert response.status_code == 403
        assert b'Access denied: Admin role required' in response.content
        assert 'HX-Trigger' in response
        assert 'showToastEvent' in response['HX-Trigger']

    def test_superuser_without_profile_denied(self, request_factory, mock_view, db):
        """
        Test that even superusers without profiles are denied.
        This simulates a superuser created via createsuperuser before signal fires.
        """
        from django.db.models.signals import post_save
        from Management.models import create_user_profile
        
        # Temporarily disconnect the signal
        post_save.disconnect(create_user_profile, sender=User)
        
        try:
            superuser = User.objects.create_superuser(
                username='superuser',
                password='testpass123',
                email='super@example.com'
            )
            # Ensure no profile exists
            UserProfile.objects.filter(user=superuser).delete()
        finally:
            # Reconnect the signal
            post_save.connect(create_user_profile, sender=User)
        
        request = request_factory.get('/test/')
        request.user = superuser
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        # Even superuser should be denied without profile
        assert response.status_code == 403
        assert b'Access denied: Admin role required' in response.content

    def test_decorator_preserves_view_metadata(self, mock_view):
        """Test that decorator preserves original view function metadata"""
        decorated_view = require_admin_role(mock_view)
        
        # functools.wraps should preserve __name__
        assert decorated_view.__name__ == mock_view.__name__

    def test_decorator_with_view_args_and_kwargs(self, request_factory, admin_user):
        """Test that decorator properly passes args and kwargs to view"""
        def view_with_args(request, arg1, arg2, kwarg1=None):
            return HttpResponse(f"{arg1}-{arg2}-{kwarg1}", status=200)
        
        view_with_args.__name__ = "view_with_args"
        
        request = request_factory.get('/test/')
        request.user = admin_user
        
        decorated_view = require_admin_role(view_with_args)
        response = decorated_view(request, "val1", "val2", kwarg1="val3")
        
        assert response.status_code == 200
        assert b'val1-val2-val3' in response.content

    def test_logging_for_readonly_user(self, request_factory, mock_view, readonly_user, caplog):
        """Test that readonly user access attempts are logged"""
        request = request_factory.get('/test/')
        request.user = readonly_user
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        # Check that warning was logged with role information
        assert "readonly_user" in caplog.text
        assert "'readonly'" in caplog.text
        assert "mock_view_function" in caplog.text

    def test_logging_for_user_without_profile(self, request_factory, mock_view, user_without_profile, caplog):
        """Test that users without profiles have 'no profile' logged"""
        request = request_factory.get('/test/')
        request.user = user_without_profile
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        # Check that warning was logged with 'no profile' information
        assert "no_profile_user" in caplog.text
        assert "no profile" in caplog.text
        assert "mock_view_function" in caplog.text

    def test_htmx_trigger_header_format(self, request_factory, mock_view, readonly_user):
        """Test that HX-Trigger header is properly formatted JSON"""
        import json
        
        request = request_factory.get('/test/')
        request.user = readonly_user
        
        decorated_view = require_admin_role(mock_view)
        response = decorated_view(request)
        
        # Verify HX-Trigger is valid JSON
        trigger_data = json.loads(response['HX-Trigger'])
        assert 'showToastEvent' in trigger_data
        assert trigger_data['showToastEvent']['type'] == 'error'
        assert 'Admin role required' in trigger_data['showToastEvent']['message']

    def test_multiple_decorators_stacking(self, request_factory, admin_user):
        """Test that decorator can be stacked with other decorators"""
        def another_decorator(view_func):
            def wrapper(request, *args, **kwargs):
                response = view_func(request, *args, **kwargs)
                response['X-Custom-Header'] = 'test'
                return response
            wrapper.__name__ = view_func.__name__
            return wrapper
        
        def view_func(request):
            return HttpResponse("Success", status=200)
        view_func.__name__ = "stacked_view"
        
        # Stack decorators
        decorated_view = require_admin_role(another_decorator(view_func))
        
        request = request_factory.get('/test/')
        request.user = admin_user
        
        response = decorated_view(request)
        
        assert response.status_code == 200
        assert 'X-Custom-Header' in response
