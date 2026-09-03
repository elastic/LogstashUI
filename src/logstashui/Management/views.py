#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.shortcuts import render, redirect
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.http import HttpResponse, FileResponse
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import UserProfile, Settings
from django.http import JsonResponse
from datetime import timedelta
import logging
import json
import os
from html import escape
from Common.decorators import require_admin_role

logger = logging.getLogger(__name__)

class BootstrapLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    def get_form_class(self):
        # Dynamically choose between login form and registration form
        if not User.objects.exists():
            return UserCreationForm
        return AuthenticationForm

    def get_form_kwargs(self):
        """
        LoginView normally passes `request` into form kwargs.
        UserCreationForm doesn't accept it, so strip it out.
        """
        kwargs = super().get_form_kwargs()
        if self.get_form_class() == UserCreationForm:
            kwargs.pop("request", None)
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["is_first_run"] = not User.objects.exists()
        return context

    def form_valid(self, form):
        """
        Handle POST — if no users exist, create the first user and log them in.
        Otherwise, fall back to normal login behavior.
        Uses atomic transaction to prevent race condition.
        """
        # Check if this is first-run (no users exist)
        if isinstance(form, UserCreationForm):
            # First-run registration flow
            with transaction.atomic():
                # Lock the User table and re-check if users exist
                # This prevents TOCTOU race condition
                if not User.objects.select_for_update().exists():
                    user = form.save()
                    user.is_superuser = True
                    user.is_staff = True
                    user.save()
                    # Ensure the first user is always Admin
                    if hasattr(user, 'profile'):
                        user.profile.role = 'admin'
                        user.profile.save()
                    logger.info(f"First user '{user.username}' created during initial setup as Admin")
                    login(self.request, user)
                    return redirect("/")
                else:
                    # Race condition: another request created a user concurrently
                    # We have a UserCreationForm but need to login instead
                    # Redirect to login page with a message
                    logger.warning(f"Race condition detected: user creation attempted but users already exist")
                    from django.contrib import messages
                    messages.info(self.request, "A user was just created. Please log in with your credentials.")
                    return redirect(self.request.path)
        else:
            # Normal login flow - delegate to parent LoginView
            return super().form_valid(form)

def Management(request):
    return render(request, 'management.html')

def _set_django_permissions(user, role):
    """Set Django is_superuser and is_staff flags based on role"""
    if role == 'admin':
        user.is_superuser = True
        user.is_staff = True
    else:
        user.is_superuser = False
        user.is_staff = False
    user.save()

def _generate_user_table_rows(users, request):
    """Helper function to generate user table rows HTML using template partial"""
    rows_html = ''
    for user in users:
        rows_html += render_to_string('components/user_row.html', {
            'user': user,
            'csrf_token': request.META.get('CSRF_COOKIE', '')
        }, request=request)
    return rows_html

def Users(request):
    if request.method == 'POST':
        # Check if user has admin role for any POST operations
        if hasattr(request.user, 'profile') and request.user.profile.role != 'admin':
            response = HttpResponse('Access denied: Admin role required', status=403)
            response['HX-Trigger'] = '{"showToastEvent": {"message": "Access denied: Admin role required", "type": "error"}}'
            return response
        
        action = request.POST.get('action')
        
        if action == 'add':
            username = request.POST.get('username')
            password = request.POST.get('password')
            password2 = request.POST.get('password2')
            email = request.POST.get('email', '')
            role = request.POST.get('role', 'admin')
            
            # Validate role
            if role not in ['admin', 'readonly']:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">Invalid role. Must be "admin" or "readonly".</div>')
            
            # Validate username
            if User.objects.filter(username=username).exists():
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">Username already exists</div>')
            
            # Check if passwords match
            if password != password2:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">The two password fields didn\'t match.</div>')
            
            # Validate password using Django's validators
            try:
                # Create a temporary user object for validation
                temp_user = User(username=username, email=email)
                validate_password(password, user=temp_user)
                
                # If validation passes, create the user
                user = User.objects.create_user(username=username, password=password, email=email)
                
                # Set Django permissions based on role
                _set_django_permissions(user, role)
                
                # Set the role
                if hasattr(user, 'profile'):
                    user.profile.role = role
                    user.profile.save()
                else:
                    UserProfile.objects.create(user=user, role=role)
                
                logger.info(f"User '{request.user.username}' created new user '{username}' with role '{role}'")
                # Return success and trigger page reload
                return HttpResponse('<script>window.location.reload();</script>')
            except ValidationError as e:
                # Return password validation errors
                error_messages = '<br>'.join(e.messages)
                return HttpResponse(f'<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">{error_messages}</div>')
        
        elif action == 'update_password':
            user_id = request.POST.get('user_id')
            new_password = request.POST.get('new_password', '').strip()
            new_password2 = request.POST.get('new_password2', '').strip()

            try:
                user = User.objects.get(id=user_id)

                # Check if passwords match
                if new_password != new_password2:
                    return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">The two password fields didn\'t match.</div>')

                # Validate password using Django's validators
                try:
                    validate_password(new_password, user=user)
                    user.set_password(new_password)
                    user.save()
                    logger.info(f"User '{request.user.username}' updated password for user '{user.username}'")
                    return HttpResponse('<script>window.location.reload();</script>')
                except ValidationError as e:
                    # Return password validation errors
                    error_messages = '<br>'.join(e.messages)
                    return HttpResponse(f'<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">{error_messages}</div>')
            except User.DoesNotExist:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">User not found</div>')

        elif action == 'update_role':
            user_id = request.POST.get('user_id')
            role = request.POST.get('role', 'admin')
            
            # Validate role
            if role not in ['admin', 'readonly']:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">Invalid role. Must be "admin" or "readonly".</div>')

            try:
                user = User.objects.get(id=user_id)

                # Update role
                if hasattr(user, 'profile'):
                    if user.profile.role != role:
                        user.profile.role = role
                        user.profile.save()
                        
                        # Sync Django permissions with role
                        _set_django_permissions(user, role)
                        
                        logger.info(f"User '{request.user.username}' updated role for user '{user.username}' to '{role}'")
                        return HttpResponse('<script>window.location.reload();</script>')
                    else:
                        return HttpResponse('<div class="p-4 mb-4 bg-blue-500/10 border border-blue-500/50 rounded-lg text-blue-300 text-sm">No changes made</div>')
                else:
                    UserProfile.objects.create(user=user, role=role)
                    
                    # Sync Django permissions with role
                    _set_django_permissions(user, role)
                    
                    logger.info(f"User '{request.user.username}' created profile and set role for user '{user.username}' to '{role}'")
                    return HttpResponse('<script>window.location.reload();</script>')
            except User.DoesNotExist:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">User not found</div>')
        
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            
            try:
                # Check if this is the last user
                if User.objects.count() <= 1:
                    # Return the current table body unchanged + show toast
                    users = User.objects.all().order_by('username')
                    html = _generate_user_table_rows(users, request)
                    html += '''
                        <script>
                            showToast('Cannot delete the last user in the system', 'error');
                        </script>
                    '''
                    return HttpResponse(html)
                
                user = User.objects.get(id=user_id)
                if user == request.user:
                    # Return the current table body unchanged + show toast
                    users = User.objects.all().order_by('username')
                    html = _generate_user_table_rows(users, request)
                    html += '''
                        <script>
                            showToast('You cannot delete your own account', 'error');
                        </script>
                    '''
                    return HttpResponse(html)
                else:
                    deleted_username = user.username
                    user.delete()
                    logger.warning(f"User '{request.user.username}' deleted user '{deleted_username}'")
                    # Return updated user list
                    users = User.objects.all().order_by('username')
                    html = _generate_user_table_rows(users, request)
                    return HttpResponse(html)
            except User.DoesNotExist:
                return HttpResponse('''
                    <script>
                        showToast('User not found', 'error');
                    </script>
                ''')
    
    users = User.objects.all().order_by('username')
    return render(request, 'users.html', {'users': users})

def _read_log_file(log_path, user_filter=None):
    """Helper function to read and optionally filter log file"""
    log_lines = []
    
    if not os.path.exists(log_path):
        return log_lines
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
        for line in lines:
            line = line.rstrip()
            if user_filter:
                if user_filter.lower() in line.lower():
                    log_lines.append(line)
            else:
                log_lines.append(line)
        
        return log_lines[-1000:]
    except Exception as e:
        logger.error(f"Error reading log file: {e}")
        return []

def Logs(request):
    log_path = os.path.join(settings.LOGS_DIR, 'logstashui.log')
    log_lines = _read_log_file(log_path)
    return render(request, 'logs.html', {'log_lines': log_lines})

def LogsFilter(request):
    user_filter = request.GET.get('user_filter', '').strip()
    log_path = os.path.join(settings.LOGS_DIR, 'logstashui.log')
    log_lines = _read_log_file(log_path, user_filter if user_filter else None)
    
    html = '<div class="font-mono text-sm space-y-1">'
    if log_lines:
        for line in log_lines:
            # Determine color class based on log level (mutually exclusive)
            if 'ERROR' in line or 'CRITICAL' in line:
                color_class = 'text-red-400'
            elif 'WARNING' in line:
                color_class = 'text-yellow-400'
            elif 'INFO' in line:
                color_class = 'text-blue-400'
            else:
                color_class = 'text-gray-300'
            
            css_class = f'{color_class} hover:bg-gray-700/50 px-2 py-1 rounded'
            html += f'<div class="{css_class}">{escape(line)}</div>'
    else:
        html += '<div class="text-gray-500 text-center py-8">No log entries found.</div>'
    
    html += '</div>'
    return HttpResponse(html)

def LogsDownload(request):
    log_path = os.path.join(settings.LOGS_DIR, 'logstashui.log')
    
    if not os.path.exists(log_path):
        return HttpResponse('Log file not found', status=404)
    
    try:
        response = FileResponse(open(log_path, 'rb'), content_type='text/plain')
        response['Content-Disposition'] = 'attachment; filename="logstashui.log"'
        logger.info(f"User '{request.user.username}' downloaded log file")
        return response
    except Exception as e:
        logger.error(f"Error downloading log file: {e}")
        return HttpResponse('Error downloading log file', status=500)

@require_admin_role
def SettingsView(request):
    app_settings = Settings.get_settings()

    if request.method == 'POST':
        try:
            experimental_mode = request.POST.get('experimental_mode') == 'on'
            agent_ui_url = (request.POST.get('agent_ui_url') or '').strip()

            app_settings = Settings.get_settings()
            previous_url = (app_settings.agent_ui_url or "").strip()
            app_settings.experimental_mode = experimental_mode
            app_settings.agent_ui_url = agent_ui_url
            app_settings.save()

            logger.info(
                f"User '{request.user.username}' updated settings "
                f"(experimental_mode={experimental_mode}, agent_ui_url={agent_ui_url!r})"
            )

            cert_note = ""
            if agent_ui_url != previous_url:
                try:
                    from Common.product_ca import ensure_default_ui_server_cert, get_ui_server_mode

                    if get_ui_server_mode() == "product":
                        ensure_default_ui_server_cert()  # re-issues when SANs change
                        cert_note = (
                            " Product UI certificate was re-checked for new callback URL SANs; "
                            "restart the UI container so gunicorn reloads the leaf if it changed."
                        )
                except Exception as e:
                    logger.warning("Could not re-issue UI cert after agent_ui_url change: %s", e)

            return JsonResponse({
                'success': True,
                'message': 'Settings saved successfully' + cert_note,
            })
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            return JsonResponse({
                'success': False,
                'message': f'Error: {str(e)}. Please run migrations first.'
            })

    from Common.product_ca import get_ui_tls_status

    try:
        tls_status = get_ui_tls_status()
    except Exception as e:
        logger.error(f"Error loading TLS status: {e}", exc_info=True)
        tls_status = {
            'mode': 'unknown',
            'certificate': None,
            'paths': {},
            'nginx_hint': '',
            'error': str(e),
        }

    return render(request, 'management_settings.html', {
        'app_settings': app_settings,
        'tls_status': tls_status,
    })


@require_admin_role
def SettingsTlsUpload(request):
    """Upload a custom UI server certificate (replaces product default leaf only)."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        from Common.product_ca import save_custom_ui_certificate, get_ui_tls_status

        cert_file = request.FILES.get('certificate')
        key_file = request.FILES.get('private_key')
        chain_file = request.FILES.get('chain')
        if not cert_file or not key_file:
            return JsonResponse({
                'success': False,
                'message': 'Certificate and private key files are required',
            }, status=400)

        cert_pem = cert_file.read()
        key_pem = key_file.read()
        chain_pem = chain_file.read() if chain_file else None

        save_custom_ui_certificate(cert_pem, key_pem, chain_pem)
        logger.info(f"User '{request.user.username}' uploaded custom UI server certificate")
        return JsonResponse({
            'success': True,
            'message': (
                'Custom certificate installed. Restart the UI process/container so gunicorn reloads certs. '
                'then restart the UI process/container. Product CA for agents is unchanged.'
            ),
            'tls_status': get_ui_tls_status(),
        })
    except ValueError as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=400)
    except Exception as e:
        logger.error(f"Error uploading TLS certificate: {e}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Error: {e}'}, status=500)


@require_admin_role
def SettingsTlsRevert(request):
    """Revert UI server cert to product-CA-signed default."""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'message': 'Method not allowed'}, status=405)
    try:
        from Common.product_ca import revert_ui_certificate_to_product_default

        status = revert_ui_certificate_to_product_default()
        logger.info(f"User '{request.user.username}' reverted UI certificate to product default")
        return JsonResponse({
            'success': True,
            'message': 'Reverted to product default certificate. Restart the UI so gunicorn reloads certs.',
            'tls_status': status,
        })
    except Exception as e:
        logger.error(f"Error reverting TLS certificate: {e}", exc_info=True)
        return JsonResponse({'success': False, 'message': f'Error: {e}'}, status=500)


# ---------------------------------------------------------------------------
# API tokens
# ---------------------------------------------------------------------------

def _token_error(message):
    return HttpResponse(
        '<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg '
        f'text-red-300 text-sm">{escape(message)}</div>'
    )


def _generate_token_table_rows(tokens, request):
    """Render the token table body, reused for htmx swaps after revoke/delete."""
    rows_html = ''
    for token in tokens:
        rows_html += render_to_string('components/api_token_row.html', {
            'token': token,
            'csrf_token': request.META.get('CSRF_COOKIE', ''),
        }, request=request)
    return rows_html


@require_admin_role
def ApiTokens(request):
    """Mint, list, revoke and delete admin API tokens.

    A token acts as its owning user, so the caller's own account is the owner —
    that keeps audit lines like "User 'x' added connection" meaningful, and
    means a readonly user's token is readonly.
    """
    from PipelineManager.models import ApiKey

    def _all_tokens():
        return (
            ApiKey.objects.filter(user__isnull=False)
            .select_related('user')
            .order_by('-created_at', '-id')
        )

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'create':
            name = (request.POST.get('name') or '').strip()
            if not name:
                return _token_error('A token name is required.')
            if len(name) > 100:
                return _token_error('Token name must be 100 characters or fewer.')

            expires_at = None
            raw_days = (request.POST.get('expires_days') or '').strip()
            if raw_days:
                try:
                    days = int(raw_days)
                except ValueError:
                    return _token_error('Expiry must be a whole number of days.')
                if days < 1:
                    return _token_error('Expiry must be at least 1 day.')
                expires_at = timezone.now() + timedelta(days=days)

            token, raw = ApiKey.issue_for_user(
                request.user, name=name, expires_at=expires_at
            )
            # Deliberately not logged — this is the only time the secret exists.
            logger.info(
                f"User '{request.user.username}' created API token '{name}' "
                f"(prefix {token.prefix})"
            )
            return render(request, 'components/api_token_created.html', {
                'token': token,
                'raw_token': raw,
            })

        if action in ('revoke', 'delete'):
            token_id = request.POST.get('token_id')
            token = ApiKey.objects.filter(
                id=token_id, user__isnull=False
            ).first()
            if token is None:
                return _token_error('Token not found.')

            if action == 'revoke':
                if token.revoked_at is None:
                    token.revoked_at = timezone.now()
                    token.save()
                logger.warning(
                    f"User '{request.user.username}' revoked API token "
                    f"'{token.name}' (prefix {token.prefix})"
                )
            else:
                logger.warning(
                    f"User '{request.user.username}' deleted API token "
                    f"'{token.name}' (prefix {token.prefix})"
                )
                token.delete()

            return HttpResponse(_generate_token_table_rows(_all_tokens(), request))

        return _token_error('Unknown action.')

    return render(request, 'api_tokens.html', {'tokens': _all_tokens()})