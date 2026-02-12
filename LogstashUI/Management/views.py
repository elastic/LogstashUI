from django.shortcuts import render, redirect
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm, SetPasswordForm
from django.contrib.auth.models import User
from django.contrib.auth import login
from django.http import HttpResponse
from django.contrib import messages
from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
import logging

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
        """
        if not User.objects.exists():
            user = form.save()
            user.is_superuser = True
            user.is_staff = True
            user.save()
            logger.info(f"First user '{user.username}' created during initial setup")
            login(self.request, user)
            return redirect("/")  # redirect wherever your dashboard/home is
        else:
            return super().form_valid(form)

def Management(request):
    return render(request, 'management.html')

def _generate_user_table_rows(users):
    """Helper function to generate user table rows HTML"""
    html = ''
    for u in users:
        html += f'''
        <tr class="hover:bg-gray-700/50 transition-colors">
          <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-300">
            {u.username}
          </td>
          <td class="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
            <div class="flex justify-end space-x-2">
              <button onclick="openEditModal('{u.id}', '{u.username}')" 
                      class="text-blue-400 hover:text-blue-300 mr-3">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
              </button>
              <button hx-post="/Management/Users/" 
                      hx-vals='{{"action": "delete", "user_id": "{u.id}"}}'
                      hx-target="#userTableBody"
                      hx-confirm="Are you sure you want to delete this user?"
                      class="text-red-400 hover:text-red-300">
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                </svg>
              </button>
            </div>
          </td>
        </tr>
        '''
    return html

def Users(request):
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            username = request.POST.get('username')
            password = request.POST.get('password')
            password2 = request.POST.get('password2')
            email = request.POST.get('email', '')
            
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
                user.is_superuser = True
                user.is_staff = True
                user.save()
                
                logger.info(f"User '{request.user.username}' created new user '{username}'")
                # Return success and trigger page reload
                return HttpResponse('<script>window.location.reload();</script>')
            except ValidationError as e:
                # Return password validation errors
                error_messages = '<br>'.join(e.messages)
                return HttpResponse(f'<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">{error_messages}</div>')
        
        elif action == 'update':
            user_id = request.POST.get('user_id')
            new_password = request.POST.get('new_password')
            new_password2 = request.POST.get('new_password2')
            
            try:
                user = User.objects.get(id=user_id)
                if new_password:
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
                else:
                    return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">Password cannot be empty</div>')
            except User.DoesNotExist:
                return HttpResponse('<div class="p-4 mb-4 bg-red-500/10 border border-red-500/50 rounded-lg text-red-300 text-sm">User not found</div>')
        
        elif action == 'delete':
            user_id = request.POST.get('user_id')
            
            try:
                # Check if this is the last user
                if User.objects.count() <= 1:
                    # Return the current table body unchanged + show toast
                    users = User.objects.all().order_by('username')
                    html = _generate_user_table_rows(users)
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
                    html = _generate_user_table_rows(users)
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
                    html = _generate_user_table_rows(users)
                    return HttpResponse(html)
            except User.DoesNotExist:
                return HttpResponse('''
                    <script>
                        showToast('User not found', 'error');
                    </script>
                ''')
    
    users = User.objects.all().order_by('username')
    return render(request, 'users.html', {'users': users})