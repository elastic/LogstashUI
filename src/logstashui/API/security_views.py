#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""REST API views for Security — bootstrap, users, and API keys.

Endpoints
---------
GET    /api/security/bootstrap/             bootstrap_view   (unauthenticated)
POST   /api/security/bootstrap/             bootstrap_view   (unauthenticated, pre-bootstrap only)
GET    /api/security/me/                    me_view          (any authenticated user)

GET    /api/security/users/                 user_list        (admin)
POST   /api/security/users/                 user_list        (admin)
GET    /api/security/users/{id}/            user_detail      (admin)
PUT    /api/security/users/{id}/            user_detail      (admin)
DELETE /api/security/users/{id}/            user_detail      (admin)

GET    /api/security/keys/                  key_list         (admin)
POST   /api/security/keys/                  key_list         (admin)
POST   /api/security/keys/{id}/revoke/      key_revoke       (admin)
DELETE /api/security/keys/{id}/             key_detail       (admin)
"""

import logging

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from Management.models import UserProfile
from PipelineManager.models import ApiKey

from API.auth import api_require_auth, api_require_admin, parse_request_body

User = get_user_model()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _user_data(user):
    """Serialize a User + profile for API responses (no passwords)."""
    role = user.profile.role if hasattr(user, 'profile') else 'admin'
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'role': role,
        'date_joined': user.date_joined.isoformat(),
        'last_login': user.last_login.isoformat() if user.last_login else None,
        'is_active': user.is_active,
    }


def _key_data(key):
    """Serialize an ApiKey for API responses (no secrets)."""
    return {
        'id': key.id,
        'name': key.name,
        'masked': key.masked,
        'created_at': key.created_at.isoformat(),
        'last_used_at': key.last_used_at.isoformat() if key.last_used_at else None,
        'expires_at': key.expires_at.isoformat() if key.expires_at else None,
        'revoked_at': key.revoked_at.isoformat() if key.revoked_at else None,
        'is_active': key.is_active,
        'created_by': key.user.username if key.user else None,
    }


def _set_django_permissions(user, role):
    """Mirror admin/readonly onto Django is_superuser/is_staff."""
    user.is_superuser = (role == 'admin')
    user.is_staff = (role == 'admin')
    user.save()


# ---------------------------------------------------------------------------
# /api/security/bootstrap/
# ---------------------------------------------------------------------------

@csrf_exempt
def bootstrap_view(request):
    """Check or perform first-time bootstrap.

    GET  — returns {bootstrapped: bool}. Always open, no auth required.

    POST — creates the first admin user. Returns 409 if users already exist.
           Accepts {username, password, email?, create_key?, key_name?}.
           When create_key is true a one-time API key is minted and returned
           in the response alongside the user; this is the only time the
           plaintext key is available.
    """
    if request.method == 'GET':
        return JsonResponse({'bootstrapped': User.objects.exists()})

    if request.method == 'POST':
        return _do_bootstrap(request)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _do_bootstrap(request):
    if User.objects.exists():
        return JsonResponse(
            {'success': False, 'error': 'System is already bootstrapped. Use /api/security/users/ to manage users.'},
            status=409,
        )

    data = parse_request_body(request)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()
    create_key = bool(data.get('create_key', False))
    key_name = (data.get('key_name') or 'Bootstrap Key').strip()

    if not username:
        return JsonResponse({'success': False, 'error': 'username is required.'}, status=400)
    if not password:
        return JsonResponse({'success': False, 'error': 'password is required.'}, status=400)

    # Validate password strength
    try:
        temp_user = User(username=username, email=email)
        validate_password(password, user=temp_user)
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.messages}, status=400)

    try:
        with transaction.atomic():
            # Re-check inside the transaction to avoid races
            if User.objects.select_for_update().exists():
                return JsonResponse(
                    {'success': False, 'error': 'System is already bootstrapped.'},
                    status=409,
                )

            user = User.objects.create_user(username=username, password=password, email=email)
            user.is_superuser = True
            user.is_staff = True
            user.save()

            if hasattr(user, 'profile'):
                user.profile.role = 'admin'
                user.profile.save()
            else:
                UserProfile.objects.create(user=user, role='admin')

            logger.warning("API bootstrap: first admin user '%s' created.", username)

            response_data = {
                'success': True,
                'message': f"Admin user '{username}' created.",
                'user': _user_data(user),
            }

            if create_key:
                key, raw_token = ApiKey.issue_for_user(user, name=key_name)
                response_data['api_key'] = {
                    'id': key.id,
                    'name': key.name,
                    'token': raw_token,  # one-time plaintext — store it now
                }
                logger.warning("API bootstrap: API key '%s' issued for '%s'.", key_name, username)

            return JsonResponse(response_data, status=201)

    except Exception as exc:
        logger.error("API bootstrap failed: %s", exc)
        return JsonResponse({'success': False, 'error': str(exc)}, status=500)


# ---------------------------------------------------------------------------
# /api/security/me/
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_auth
def me_view(request):
    """Return the identity and role of the current caller.

    GET /api/security/me/
        Works for both session-authenticated and API-key-authenticated callers.
        Token metadata (name, expiry) is included when the request carries an
        API key.
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    data = _user_data(request.user)

    token = getattr(request, '_api_token', None)
    if token:
        data['api_key'] = {
            'id': token.id,
            'name': token.name,
            'expires_at': token.expires_at.isoformat() if token.expires_at else None,
            'is_active': token.is_active,
        }

    return JsonResponse({'success': True, 'me': data})


# ---------------------------------------------------------------------------
# /api/security/users/  — list + create
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def user_list(request):
    """List all users or create a new one.

    GET  /api/security/users/  — list; admin only.
    POST /api/security/users/  — create; admin only.
                                 Body: {username, password, email?, role?}
    """
    if request.method == 'GET':
        users = User.objects.select_related('profile').order_by('username')
        return JsonResponse({'success': True, 'users': [_user_data(u) for u in users]})

    if request.method == 'POST':
        return _create_user(request)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _create_user(request):
    data = parse_request_body(request)
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()
    role = (data.get('role') or 'admin').strip()

    if not username:
        return JsonResponse({'success': False, 'error': 'username is required.'}, status=400)
    if not password:
        return JsonResponse({'success': False, 'error': 'password is required.'}, status=400)
    if role not in ('admin', 'readonly'):
        return JsonResponse({'success': False, 'error': 'role must be "admin" or "readonly".'}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({'success': False, 'error': f"Username '{username}' already exists."}, status=409)

    try:
        temp_user = User(username=username, email=email)
        validate_password(password, user=temp_user)
    except ValidationError as exc:
        return JsonResponse({'success': False, 'error': exc.messages}, status=400)

    user = User.objects.create_user(username=username, password=password, email=email)
    _set_django_permissions(user, role)

    if hasattr(user, 'profile'):
        user.profile.role = role
        user.profile.save()
    else:
        UserProfile.objects.create(user=user, role=role)

    logger.info("API: user '%s' created by '%s' with role '%s'.", username, request.user.username, role)
    # Discrepancy B fix: include top-level user_id for docs compatibility as well
    # as the full nested 'user' object.
    return JsonResponse({'success': True, 'user_id': user.id, 'user': _user_data(user)}, status=201)


# ---------------------------------------------------------------------------
# /api/security/users/{id}/  — read, update, delete
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def user_detail(request, user_id):
    """Read, update, or delete a single user.

    GET    /api/security/users/{id}/  — fetch user detail.
    PUT    /api/security/users/{id}/  — update password and/or role.
                                        Body: {password?, role?}
    DELETE /api/security/users/{id}/  — delete user.
                                        Guards: cannot delete self or last user.
    """
    try:
        user = User.objects.select_related('profile').get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'User not found.'}, status=404)

    if request.method == 'GET':
        return JsonResponse({'success': True, 'user': _user_data(user)})

    if request.method == 'PUT':
        return _update_user(request, user)

    if request.method == 'DELETE':
        return _delete_user(request, user)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _update_user(request, user):
    data = parse_request_body(request)
    changed = []

    # Role update
    new_role = data.get('role')
    if new_role is not None:
        new_role = str(new_role).strip()
        if new_role not in ('admin', 'readonly'):
            return JsonResponse({'success': False, 'error': 'role must be "admin" or "readonly".'}, status=400)
        if new_role != getattr(getattr(user, 'profile', None), 'role', None):
            if hasattr(user, 'profile'):
                user.profile.role = new_role
                user.profile.save()
            else:
                UserProfile.objects.create(user=user, role=new_role)
            _set_django_permissions(user, new_role)
            changed.append('role')
            logger.info("API: '%s' updated role for '%s' to '%s'.", request.user.username, user.username, new_role)

    # Password update
    new_password = data.get('password')
    if new_password:
        try:
            validate_password(new_password, user=user)
        except ValidationError as exc:
            return JsonResponse({'success': False, 'error': exc.messages}, status=400)
        user.set_password(new_password)
        user.save()
        changed.append('password')
        logger.info("API: '%s' updated password for '%s'.", request.user.username, user.username)

    if not changed:
        return JsonResponse({'success': False, 'error': 'No changes supplied. Provide role and/or password.'}, status=400)

    return JsonResponse({'success': True, 'updated': changed, 'user': _user_data(user)})


def _delete_user(request, user):
    if user == request.user:
        return JsonResponse({'success': False, 'error': 'You cannot delete your own account.'}, status=400)
    if User.objects.count() <= 1:
        return JsonResponse({'success': False, 'error': 'Cannot delete the last user in the system.'}, status=400)

    username = user.username
    user.delete()
    logger.warning("API: user '%s' deleted by '%s'.", username, request.user.username)
    return JsonResponse({'success': True, 'message': f"User '{username}' deleted."})


# ---------------------------------------------------------------------------
# /api/security/keys/  — list + create
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def key_list(request):
    """List all API keys or create a new one.

    GET  /api/security/keys/  — list all admin API keys (no secrets).
    POST /api/security/keys/  — mint a new key.
                                Body: {name, expires_days?}
                                Returns the one-time plaintext token.
    """
    if request.method == 'GET':
        keys = (
            ApiKey.objects.filter(user__isnull=False)
            .select_related('user')
            .order_by('-created_at', '-id')
        )
        return JsonResponse({'success': True, 'keys': [_key_data(k) for k in keys]})

    if request.method == 'POST':
        return _create_key(request)

    return JsonResponse({'error': 'Method not allowed'}, status=405)


def _create_key(request):
    data = parse_request_body(request)
    name = (data.get('name') or '').strip()
    expires_days = data.get('expires_days')

    if not name:
        return JsonResponse({'success': False, 'error': 'name is required.'}, status=400)
    if len(name) > 100:
        return JsonResponse({'success': False, 'error': 'name must be 100 characters or fewer.'}, status=400)

    expires_at = None
    if expires_days is not None:
        try:
            expires_at = timezone.now() + timezone.timedelta(days=int(expires_days))
        except (ValueError, TypeError):
            return JsonResponse({'success': False, 'error': 'expires_days must be an integer.'}, status=400)

    key, raw_token = ApiKey.issue_for_user(request.user, name=name, expires_at=expires_at)
    logger.info("API: key '%s' created by '%s'.", name, request.user.username)

    return JsonResponse({
        'success': True,
        'token': raw_token,  # one-time plaintext — store it now
        'key': _key_data(key),
    }, status=201)


# ---------------------------------------------------------------------------
# /api/security/keys/{id}/revoke/  — revoke
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def key_revoke(request, key_id):
    """Revoke an API key immediately.

    POST /api/security/keys/{id}/revoke/
        Sets revoked_at; the key stops working immediately. The row is kept
        for audit purposes. Use DELETE to remove it entirely.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        key = ApiKey.objects.select_related('user').get(id=key_id, user__isnull=False)
    except ApiKey.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'API key not found.'}, status=404)

    if key.revoked_at:
        return JsonResponse({'success': False, 'error': 'API key is already revoked.'}, status=400)

    key.revoked_at = timezone.now()
    key.save(update_fields=['revoked_at'])
    logger.warning("API: key '%s' (ID: %s) revoked by '%s'.", key.name, key.id, request.user.username)

    return JsonResponse({'success': True, 'message': f"API key '{key.name}' revoked.", 'key': _key_data(key)})


# ---------------------------------------------------------------------------
# /api/security/keys/{id}/  — delete
# ---------------------------------------------------------------------------

@csrf_exempt
@api_require_admin
def key_detail(request, key_id):
    """Delete an API key.

    DELETE /api/security/keys/{id}/  — hard delete. Permanent.
    """
    if request.method != 'DELETE':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        key = ApiKey.objects.select_related('user').get(id=key_id, user__isnull=False)
    except ApiKey.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'API key not found.'}, status=404)

    name = key.name
    key.delete()
    logger.warning("API: key '%s' (ID: %s) deleted by '%s'.", name, key_id, request.user.username)
    return JsonResponse({'success': True, 'message': f"API key '{name}' deleted."})
