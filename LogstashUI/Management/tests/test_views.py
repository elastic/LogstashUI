"""
Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License.
"""

import pytest
from django.contrib.auth.models import User
from Common.test_resources import authenticated_client, test_user


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def readonly_user(db):
    """Create a readonly-role test user"""
    user = User.objects.create_user(
        username='readonlyuser',
        password='testpass123',
        email='readonly@example.com'
    )
    user.is_superuser = False
    user.is_staff = False
    user.save()
    # The signal creates a profile with role='admin' by default; override it.
    user.profile.role = 'readonly'
    user.profile.save()
    return user


@pytest.fixture
def readonly_client(client, readonly_user):
    """Client authenticated as a readonly user"""
    client.login(username='readonlyuser', password='testpass123')
    return client


# ============================================================================
# SECTION 1: BootstrapLoginView — First-Run & Login Tests
# ============================================================================

@pytest.mark.django_db
class TestFirstRunLogin:
    """
    Tests for BootstrapLoginView: the first-user registration flow and
    the normal login flow (finding 4e).
    """

    def test_first_run_shows_registration_form(self, client):
        """
        With no users in the database, the login page should render the
        UserCreationForm (first-run registration mode).
        """
        assert not User.objects.exists()
        response = client.get('/Management/Login/')
        assert response.status_code == 200
        # Context flag must be True to drive the template
        assert response.context['is_first_run'] is True
        # Registration fields should be present
        assert b'password1' in response.content or b'Create Your Account' in response.content

    def test_first_run_creates_admin_user(self, client):
        """
        POSTing valid credentials on first run should create a user with
        is_superuser=True and role='admin'.
        """
        assert not User.objects.exists()

        response = client.post('/Management/Login/', {
            'username': 'firstadmin',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        })

        # Should redirect after successful creation
        assert response.status_code in (200, 302)
        assert User.objects.filter(username='firstadmin').exists()

        user = User.objects.get(username='firstadmin')
        assert user.is_superuser, "First user must be is_superuser"
        assert user.is_staff, "First user must be is_staff"
        assert user.profile.role == 'admin', "First user must have role='admin'"

    def test_first_run_weak_password_rejected(self, client):
        """
        A weak password on the first-run form should be rejected and no user
        should be created.
        """
        assert not User.objects.exists()

        response = client.post('/Management/Login/', {
            'username': 'firstadmin',
            'password1': '123',
            'password2': '123',
        })

        # Form should re-render with errors, not redirect
        assert response.status_code == 200
        assert not User.objects.exists(), "No user should be created with a weak password"

    def test_normal_login_shows_auth_form(self, db):
        """
        When at least one user exists, the login page should render the
        AuthenticationForm (normal login mode).
        """
        from django.test import Client
        User.objects.create_user(username='existinguser', password='pass123')
        client = Client()
        response = client.get('/Management/Login/')
        assert response.status_code == 200
        assert response.context['is_first_run'] is False
        assert b'Sign In' in response.content or b'password' in response.content

    def test_normal_login_success(self, db):
        """
        Correct credentials on the standard login form should log the user in
        and redirect to the home page.
        """
        from django.test import Client
        User.objects.create_user(username='loginuser', password='ValidPass123!')
        client = Client()
        response = client.post('/Management/Login/', {
            'username': 'loginuser',
            'password': 'ValidPass123!',
        })
        # Successful login redirects
        assert response.status_code == 302

    def test_normal_login_wrong_password(self, db):
        """
        Wrong credentials should re-render the form with errors and not log in.
        """
        from django.test import Client
        User.objects.create_user(username='loginuser', password='ValidPass123!')
        client = Client()
        response = client.post('/Management/Login/', {
            'username': 'loginuser',
            'password': 'WrongPassword!',
        })
        # Should re-render the page (200), not redirect
        assert response.status_code == 200
        assert response.context['form'].errors

    def test_first_run_form_not_shown_after_user_exists(self, db):
        """
        Once a user exists, a second visitor should NOT see the registration
        form — even if they know to hit /Management/Login/ on a fresh browser.
        This tests the first-run guard doesn't leak to after setup.
        """
        from django.test import Client
        User.objects.create_user(username='alreadysetup', password='pass123')
        client = Client()
        response = client.get('/Management/Login/')
        assert response.context['is_first_run'] is False
        # Registration-only fields should not appear
        assert b'password1' not in response.content


# ============================================================================
# SECTION 2: User Management CRUD Tests
# ============================================================================

@pytest.mark.django_db
class TestUserManagementCRUD:
    """Test User Create, Read, Update, Delete operations"""

    def test_create_user_success(self, authenticated_client):
        """Test successful user creation"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'newuser',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'newuser@example.com',
            'role': 'admin'
        })

        assert response.status_code == 200
        assert b'window.location.reload()' in response.content

        # Verify user was created
        assert User.objects.filter(username='newuser').exists()
        new_user = User.objects.get(username='newuser')
        assert new_user.is_superuser
        assert new_user.is_staff

    def test_create_user_duplicate_username(self, authenticated_client, test_user):
        """Test creating user with duplicate username"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'testuser',  # Already exists
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'duplicate@example.com'
        })

        assert response.status_code == 200
        assert b'Username already exists' in response.content

    def test_create_user_password_mismatch(self, authenticated_client):
        """Test creating user with mismatched passwords"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'newuser',
            'password': 'SecurePass123!',
            'password2': 'DifferentPass123!',
            'email': 'newuser@example.com'
        })

        assert response.status_code == 200
        assert b"didn't match" in response.content

    def test_create_user_weak_password(self, authenticated_client):
        """Test creating user with weak password"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'newuser',
            'password': '123',  # Too short
            'password2': '123',
            'email': 'newuser@example.com'
        })

        assert response.status_code == 200
        # Should contain password validation error
        assert b'red-500' in response.content

    def test_update_user_password_success(self, authenticated_client, db):
        """Test successful user password update"""
        # Create a second user to update
        other_user = User.objects.create_user(
            username='otheruser',
            password='oldpass123',
            email='other@example.com'
        )

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_password',
            'user_id': other_user.id,
            'new_password': 'NewSecurePass123!',
            'new_password2': 'NewSecurePass123!'
        })

        assert response.status_code == 200
        assert b'window.location.reload()' in response.content

        # Verify password was updated
        other_user.refresh_from_db()
        assert other_user.check_password('NewSecurePass123!')

    def test_update_user_password_mismatch(self, authenticated_client, db):
        """Test updating user password with mismatch"""
        other_user = User.objects.create_user(
            username='otheruser',
            password='oldpass123',
            email='other@example.com'
        )

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_password',
            'user_id': other_user.id,
            'new_password': 'NewPass123!',
            'new_password2': 'DifferentPass123!'
        })

        assert response.status_code == 200
        assert b"didn't match" in response.content

    def test_delete_user_success(self, authenticated_client, db):
        """Test successful user deletion"""
        # Create a second user to delete
        other_user = User.objects.create_user(
            username='deleteuser',
            password='pass123',
            email='delete@example.com'
        )
        user_id = other_user.id

        response = authenticated_client.post('/Management/Users/', {
            'action': 'delete',
            'user_id': user_id
        })

        assert response.status_code == 200

        # Verify user was deleted
        assert not User.objects.filter(id=user_id).exists()

    def test_delete_last_user_prevented(self, authenticated_client, test_user):
        """Test that deleting the last user is prevented"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'delete',
            'user_id': test_user.id
        })

        assert response.status_code == 200
        assert b'Cannot delete the last user' in response.content

        # Verify user still exists
        assert User.objects.filter(id=test_user.id).exists()

    def test_delete_own_account_prevented(self, authenticated_client, test_user, db):
        """Test that users cannot delete their own account"""
        # Create a second user so we're not the last user
        User.objects.create_user(
            username='otheruser',
            password='pass123',
            email='other@example.com'
        )

        response = authenticated_client.post('/Management/Users/', {
            'action': 'delete',
            'user_id': test_user.id
        })

        assert response.status_code == 200
        assert b'cannot delete your own account' in response.content

        # Verify user still exists
        assert User.objects.filter(id=test_user.id).exists()


# ============================================================================
# SECTION 3: Authorization / Role Enforcement Tests
# ============================================================================

@pytest.mark.django_db
class TestReadonlyUserBlocked:
    """
    Verify that a user with role='readonly' cannot perform any write
    operations on the Users management endpoint (finding 4a / issue 2c).
    """

    def test_readonly_cannot_add_user(self, readonly_client):
        """Readonly user should receive 403 when attempting to add a user"""
        response = readonly_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'shouldnotexist',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'nope@example.com'
        })

        assert response.status_code == 403
        assert b'Access denied' in response.content
        assert not User.objects.filter(username='shouldnotexist').exists()

    def test_readonly_cannot_delete_user(self, readonly_client, test_user):
        """Readonly user should receive 403 when attempting to delete a user"""
        response = readonly_client.post('/Management/Users/', {
            'action': 'delete',
            'user_id': test_user.id
        })

        assert response.status_code == 403
        assert b'Access denied' in response.content
        # Confirm the user was NOT deleted
        assert User.objects.filter(id=test_user.id).exists()

    def test_readonly_cannot_update_password(self, readonly_client, test_user):
        """Readonly user should receive 403 when attempting to update a password"""
        response = readonly_client.post('/Management/Users/', {
            'action': 'update_password',
            'user_id': test_user.id,
            'new_password': 'HackedPass123!',
            'new_password2': 'HackedPass123!'
        })

        assert response.status_code == 403
        assert b'Access denied' in response.content
        # Confirm original password still works
        test_user.refresh_from_db()
        assert test_user.check_password('testpass123')

    def test_readonly_cannot_update_role(self, readonly_client, test_user):
        """Readonly user should receive 403 when attempting to change a user role"""
        response = readonly_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': test_user.id,
            'role': 'readonly'
        })

        assert response.status_code == 403
        assert b'Access denied' in response.content

    def test_readonly_can_view_users_page(self, readonly_client):
        """Readonly user should still be able to GET the users page"""
        response = readonly_client.get('/Management/Users/')
        assert response.status_code == 200


@pytest.mark.django_db
class TestRoleValidation:
    """
    Confirm that only valid role values ('admin', 'readonly') are accepted
    server-side in add and update_role actions (finding 2c).
    """

    def test_add_user_with_invalid_role_rejected(self, authenticated_client):
        """Submitting an invalid role string should return an error and not create the user"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'rolebreaker',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'rolebreaker@example.com',
            'role': 'superadmin'   # Not a valid choice
        })
        # Should return error response
        assert response.status_code == 200
        assert b'Invalid role' in response.content
        # User should not be created
        assert not User.objects.filter(username='rolebreaker').exists()

    def test_update_role_with_invalid_role_rejected(self, authenticated_client, test_user):
        """Submitting an invalid role to update_role should not persist it"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': test_user.id,
            'role': 'god'   # Not a valid choice
        })
        test_user.refresh_from_db()
        assert test_user.profile.role in ('admin', 'readonly'), (
            f"Invalid role '{test_user.profile.role}' was saved to the database"
        )


# ============================================================================
# SECTION 4: Update Role Tests
# ============================================================================

@pytest.mark.django_db
class TestUpdateRole:
    """Test the update_role action on the Users management endpoint (finding 4b)"""

    def test_update_role_admin_to_readonly(self, authenticated_client, test_user, db):
        """Successfully change a user's role from admin to readonly"""
        # Create a second user with admin role (signal default)
        other_user = User.objects.create_user(
            username='otheradmin',
            password='pass123',
            email='other@example.com'
        )
        assert other_user.profile.role == 'admin'

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': other_user.id,
            'role': 'readonly'
        })

        assert response.status_code == 200
        other_user.refresh_from_db()
        assert other_user.profile.role == 'readonly'
        # Verify Django permissions were synced
        assert not other_user.is_superuser
        assert not other_user.is_staff

    def test_update_role_readonly_to_admin(self, authenticated_client, db):
        """Successfully change a user's role from readonly to admin"""
        user = User.objects.create_user(
            username='readonlyuser',
            password='pass123',
            email='ro@example.com'
        )
        user.profile.role = 'readonly'
        user.profile.save()

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': user.id,
            'role': 'admin'
        })

        assert response.status_code == 200
        user.refresh_from_db()
        assert user.profile.role == 'admin'
        # Verify Django permissions were synced
        assert user.is_superuser
        assert user.is_staff

    def test_update_role_no_change_returns_message(self, authenticated_client, db):
        """Submitting the same role that already exists should return a message, not reload"""
        user = User.objects.create_user(
            username='sameroleuser',
            password='pass123',
            email='same@example.com'
        )
        # Default role is 'admin'
        assert user.profile.role == 'admin'

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': user.id,
            'role': 'admin'
        })

        assert response.status_code == 200
        # Should say no changes made, NOT trigger a reload
        assert b'No changes made' in response.content
        assert b'window.location.reload()' not in response.content

    def test_update_role_user_not_found(self, authenticated_client):
        """Passing a non-existent user_id should return a friendly error"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': 999999,
            'role': 'readonly'
        })

        assert response.status_code == 200
        assert b'User not found' in response.content


# ============================================================================
# SECTION 5: Logs Endpoint Tests
# ============================================================================

@pytest.mark.django_db
class TestLogsEndpoints:
    """Tests for the Logs view, LogsFilter, and LogsDownload (finding 4d)"""

    def test_logs_page_loads(self, authenticated_client):
        """The Logs page should render successfully"""
        response = authenticated_client.get('/Management/Logs/')
        assert response.status_code == 200
        assert b'Log Entries' in response.content

    def test_logs_page_no_file_shows_empty(self, authenticated_client, settings, tmp_path):
        """
        When the log file does not exist, the page should still render and
        show zero entries rather than raising an error.
        """
        # Point LOGS_DIR to a temp directory that has NO log file
        settings.LOGS_DIR = tmp_path
        response = authenticated_client.get('/Management/Logs/')
        # Should still render (not 500)
        assert response.status_code == 200

    def test_logs_filter_returns_fragment(self, authenticated_client):
        """LogsFilter should return an HTML fragment, not a full page"""
        response = authenticated_client.get('/Management/Logs/filter')
        assert response.status_code == 200
        # Should be an HTML fragment, not a full Django page with base template
        assert b'<!DOCTYPE html>' not in response.content
        assert b'<div' in response.content

    def test_logs_filter_with_search_term(self, authenticated_client, settings, tmp_path):
        """LogsFilter should filter log lines by the search term"""
        # Write a fake log file with known content
        log_file = tmp_path / 'logstashui.log'
        log_file.write_text(
            "[INFO] 2026-01-01 admin logged in\n"
            "[INFO] 2026-01-01 testuser did something\n"
            "[ERROR] 2026-01-01 testuser caused an error\n",
            encoding='utf-8'
        )
        settings.LOGS_DIR = tmp_path

        response = authenticated_client.get(
            '/Management/Logs/filter',
            {'user_filter': 'testuser'}
        )

        assert response.status_code == 200
        content = response.content.decode()
        assert 'testuser' in content
        # Lines containing 'admin' only should not appear
        assert 'admin logged in' not in content

    def test_logs_download_file_not_found(self, authenticated_client, settings, tmp_path):
        """LogsDownload should return 404 when the log file does not exist"""
        # Use an empty temp directory — no log file present
        settings.LOGS_DIR = tmp_path
        response = authenticated_client.get('/Management/Logs/download')
        assert response.status_code == 404

    def test_logs_download_success(self, authenticated_client, settings, tmp_path):
        """LogsDownload should return the log file with correct headers"""
        log_file = tmp_path / 'logstashui.log'
        log_file.write_text("[INFO] 2026-01-01 some log entry\n", encoding='utf-8')
        settings.LOGS_DIR = tmp_path

        response = authenticated_client.get('/Management/Logs/download')

        assert response.status_code == 200
        assert response['Content-Type'] == 'text/plain'
        assert 'attachment' in response['Content-Disposition']
        assert 'logstashui.log' in response['Content-Disposition']

    def test_logs_filter_no_xss_in_output(self, authenticated_client, settings, tmp_path):
        """
        Log lines containing HTML special characters must be escaped in
        the LogsFilter response to prevent XSS (security finding 2b).
        """
        log_file = tmp_path / 'logstashui.log'
        log_file.write_text(
            '[INFO] 2026-01-01 User <script>alert("xss")</script> logged in\n',
            encoding='utf-8'
        )
        settings.LOGS_DIR = tmp_path

        response = authenticated_client.get('/Management/Logs/filter')

        assert response.status_code == 200
        content = response.content.decode()
        # The raw <script> tag must NOT appear unescaped
        assert '<script>alert' not in content
        # The escaped version should be present (or at minimum the raw tag is absent)
        assert '&lt;script&gt;' in content or '<script>' not in content
