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
from .models import UserProfile
import logging
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