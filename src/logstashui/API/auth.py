#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Shared auth decorators and request helpers for the REST API.

These are intentionally separate from ``Common.decorators`` because the API
layer always returns JSON — no htmx toasts, no browser redirects.
"""

import json
import logging
from functools import wraps

from django.http import JsonResponse

logger = logging.getLogger(__name__)


def api_require_auth(view_func):
    """Return 401 JSON for unauthenticated callers."""
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'error': 'Authentication required. Provide Authorization: ApiKey <token>.'},
                status=401,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def api_require_admin(view_func):
    """Return 401/403 JSON for callers without an admin role.

    Unauthenticated → 401, authenticated-but-not-admin → 403.
    Always JSON — no htmx toasts.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse(
                {'success': False, 'error': 'Authentication required. Provide Authorization: ApiKey <token>.'},
                status=401,
            )
        if not hasattr(request.user, 'profile') or request.user.profile.role != 'admin':
            logger.warning(
                "API: user '%s' attempted admin operation without admin role: %s",
                request.user.username, view_func.__name__,
            )
            return JsonResponse(
                {'success': False, 'error': 'Access denied: Admin role required.'},
                status=403,
            )
        return view_func(request, *args, **kwargs)
    return wrapper


def parse_request_body(request):
    """Return request data as a plain dict.

    Accepts JSON body (``Content-Type: application/json``) or falls back to
    ``request.POST`` for form-encoded submissions.
    """
    content_type = request.content_type or ''
    if 'application/json' in content_type:
        try:
            result = json.loads(request.body)
            # H2 fix: if the body is a JSON array or scalar (not a dict),
            # callers expect a dict and will crash with AttributeError.
            if not isinstance(result, dict):
                logger.warning(
                    "parse_request_body: expected JSON object, got %s — ignoring body",
                    type(result).__name__,
                )
                return {}
            return result
        except (json.JSONDecodeError, ValueError):
            logger.warning("parse_request_body: invalid JSON body — ignoring")
            return {}
return request.POST.dict()
