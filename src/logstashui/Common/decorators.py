#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from functools import wraps
from django.http import HttpResponse, JsonResponse
import logging

logger = logging.getLogger(__name__)


def _denied(request, message):
    """Build a denial a browser *or* a script can read.

    The HX-Trigger toast is meaningless to curl, so API-token callers get JSON.
    """
    if getattr(request, '_api_token', None) is not None:
        return JsonResponse({'success': False, 'error': message}, status=403)
    response = HttpResponse(message, status=403)
    response['HX-Trigger'] = (
        '{"showToastEvent": {"message": "%s", "type": "error"}}' % message
    )
    return response


def require_admin_role(view_func):
    """
    Decorator to check if user has admin role before allowing access to view.
    Returns error toast message if user is readonly.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check if user is authenticated
        if not request.user.is_authenticated:
            return _denied(request, 'You must be logged in to perform this action')

        # Check if user has admin role
        if not hasattr(request.user, 'profile') or request.user.profile.role != 'admin':
            role_info = f"'{request.user.profile.role}'" if hasattr(request.user, 'profile') else 'no profile'
            logger.warning(f"User '{request.user.username}' with {role_info} attempted to access admin-only function: {view_func.__name__}")
            return _denied(request, 'Access denied: Admin role required')

        # User is admin, proceed with the view
        return view_func(request, *args, **kwargs)

    return wrapper