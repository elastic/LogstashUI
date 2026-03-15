#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

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


# ============================================================================
# SECTION 6: Management View
# ============================================================================

@pytest.mark.django_db
class TestManagementView:
    """Tests for the Management() view — basic smoke tests"""

    def test_management_page_loads(self, authenticated_client):
        """GET /Management/ should render successfully"""
        response = authenticated_client.get('/Management/')
        assert response.status_code == 200

    def test_management_page_uses_template(self, authenticated_client):
        """Management view should use management.html template"""
        response = authenticated_client.get('/Management/')
        assert response.status_code == 200
        assert any(
            'management.html' in t.name
            for t in response.templates
        )


# ============================================================================
# SECTION 7: Users View — GET + Edge Cases
# ============================================================================

@pytest.mark.django_db
class TestUsersViewGet:
    """Tests for the Users() GET request path"""

    def test_users_page_loads(self, authenticated_client, test_user):
        """GET /Management/Users/ should render 200"""
        response = authenticated_client.get('/Management/Users/')
        assert response.status_code == 200

    def test_users_page_lists_users(self, authenticated_client, test_user):
        """Users page should include existing usernames in the response"""
        response = authenticated_client.get('/Management/Users/')
        assert response.status_code == 200
        assert b'testuser' in response.content

    def test_create_user_with_readonly_role(self, authenticated_client):
        """Creating a user with role='readonly' should set is_superuser=False"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'add',
            'username': 'rouser',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'ro@example.com',
            'role': 'readonly',
        })
        assert response.status_code == 200
        assert b'window.location.reload()' in response.content
        user = User.objects.get(username='rouser')
        assert not user.is_superuser
        assert not user.is_staff
        assert user.profile.role == 'readonly'

    def test_update_password_user_not_found(self, authenticated_client):
        """update_password with a non-existent user_id returns a friendly error"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_password',
            'user_id': 999999,
            'new_password': 'NewPass123!',
            'new_password2': 'NewPass123!',
        })
        assert response.status_code == 200
        assert b'User not found' in response.content

    def test_update_password_weak_rejected(self, authenticated_client, db):
        """update_password should reject a weak password and not change it"""
        target = User.objects.create_user(
            username='weakpwuser', password='OldPass123!', email='w@example.com'
        )
        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_password',
            'user_id': target.id,
            'new_password': '123',
            'new_password2': '123',
        })
        assert response.status_code == 200
        assert b'red-500' in response.content
        target.refresh_from_db()
        assert target.check_password('OldPass123!'), "Password must not have changed"

    def test_delete_nonexistent_user(self, authenticated_client, test_user, db):
        """delete action with a non-existent user_id returns a toast script error"""
        # Ensure there are at least two users so the last-user guard doesn't fire
        User.objects.create_user(username='extra', password='pass123', email='e@e.com')
        response = authenticated_client.post('/Management/Users/', {
            'action': 'delete',
            'user_id': 999999,
        })
        assert response.status_code == 200
        assert b'User not found' in response.content

    def test_unknown_action_returns_users_page(self, authenticated_client, test_user):
        """An unrecognised POST action should fall through to the GET render"""
        response = authenticated_client.post('/Management/Users/', {
            'action': 'completely_made_up',
        })
        # Falls through all elif branches → renders users.html
        assert response.status_code == 200


# ============================================================================
# SECTION 8: _set_django_permissions Unit Tests
# ============================================================================

@pytest.mark.django_db
class TestSetDjangoPermissions:
    """Unit tests for the _set_django_permissions helper"""

    def test_admin_role_sets_superuser_and_staff(self, test_user):
        """admin role → is_superuser=True, is_staff=True"""
        from Management.views import _set_django_permissions
        test_user.is_superuser = False
        test_user.is_staff = False
        test_user.save()
        _set_django_permissions(test_user, 'admin')
        test_user.refresh_from_db()
        assert test_user.is_superuser
        assert test_user.is_staff

    def test_readonly_role_clears_superuser_and_staff(self, test_user):
        """readonly role → is_superuser=False, is_staff=False"""
        from Management.views import _set_django_permissions
        _set_django_permissions(test_user, 'readonly')
        test_user.refresh_from_db()
        assert not test_user.is_superuser
        assert not test_user.is_staff


# ============================================================================
# SECTION 9: _read_log_file Unit Tests
# ============================================================================

class TestReadLogFile:
    """Unit tests for the _read_log_file helper (no DB needed)"""

    def test_returns_empty_list_when_file_missing(self, tmp_path):
        """Returns [] if the log file does not exist"""
        from Management.views import _read_log_file
        result = _read_log_file(str(tmp_path / 'nonexistent.log'))
        assert result == []

    def test_reads_all_lines(self, tmp_path):
        """All lines from the file are returned when no filter is applied"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        log_file.write_text("line1\nline2\nline3\n", encoding='utf-8')
        result = _read_log_file(str(log_file))
        assert result == ['line1', 'line2', 'line3']

    def test_filter_returns_only_matching_lines(self, tmp_path):
        """user_filter returns only lines containing the search term (case-insensitive)"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        log_file.write_text(
            "INFO admin logged in\nINFO testuser did something\nERROR testuser failed\n",
            encoding='utf-8'
        )
        result = _read_log_file(str(log_file), user_filter='testuser')
        assert len(result) == 2
        assert all('testuser' in line for line in result)

    def test_filter_is_case_insensitive(self, tmp_path):
        """Filter search is case-insensitive"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        log_file.write_text("INFO AdminUser logged in\nINFO other user\n", encoding='utf-8')
        result = _read_log_file(str(log_file), user_filter='adminuser')
        assert len(result) == 1
        assert 'AdminUser' in result[0]

    def test_returns_at_most_1000_lines(self, tmp_path):
        """Only the last 1000 lines are returned, not the whole file"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        lines = [f"line {i}" for i in range(1500)]
        log_file.write_text('\n'.join(lines), encoding='utf-8')
        result = _read_log_file(str(log_file))
        assert len(result) == 1000
        # The LAST 1000 lines should be returned
        assert result[0] == 'line 500'
        assert result[-1] == 'line 1499'

    def test_returns_empty_list_on_exception(self, tmp_path, monkeypatch):
        """If an error occurs reading the file, returns [] instead of raising"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        log_file.write_text("some content\n", encoding='utf-8')

        # Monkeypatch open to raise an OSError mid-read
        def bad_open(*args, **kwargs):
            raise OSError("disk error")

        monkeypatch.setattr('builtins.open', bad_open)
        result = _read_log_file(str(log_file))
        assert result == []

    def test_strips_trailing_newlines(self, tmp_path):
        """Lines are right-stripped of whitespace/newlines"""
        from Management.views import _read_log_file
        log_file = tmp_path / 'test.log'
        log_file.write_bytes(b"line with spaces   \nline2\n")
        result = _read_log_file(str(log_file))
        assert result[0] == 'line with spaces'
        assert result[1] == 'line2'


# ============================================================================
# SECTION 10: LogsFilter Color-Coding Tests
# ============================================================================

@pytest.mark.django_db
class TestLogsFilterColorCoding:
    """Verify that LogsFilter assigns the correct CSS color classes"""

    def _write_log(self, tmp_path, content):
        log_file = tmp_path / 'logstashui.log'
        log_file.write_text(content, encoding='utf-8')
        return tmp_path

    def test_error_line_gets_red_class(self, authenticated_client, settings, tmp_path):
        """Lines containing 'ERROR' get text-red-400"""
        settings.LOGS_DIR = self._write_log(tmp_path, "2026-01-01 ERROR something failed\n")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'text-red-400' in response.content

    def test_critical_line_gets_red_class(self, authenticated_client, settings, tmp_path):
        """Lines containing 'CRITICAL' also get text-red-400"""
        settings.LOGS_DIR = self._write_log(tmp_path, "2026-01-01 CRITICAL catastrophic\n")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'text-red-400' in response.content

    def test_warning_line_gets_yellow_class(self, authenticated_client, settings, tmp_path):
        """Lines containing 'WARNING' get text-yellow-400"""
        settings.LOGS_DIR = self._write_log(tmp_path, "2026-01-01 WARNING low disk space\n")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'text-yellow-400' in response.content

    def test_info_line_gets_blue_class(self, authenticated_client, settings, tmp_path):
        """Lines containing 'INFO' get text-blue-400"""
        settings.LOGS_DIR = self._write_log(tmp_path, "2026-01-01 INFO user logged in\n")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'text-blue-400' in response.content

    def test_debug_line_gets_gray_class(self, authenticated_client, settings, tmp_path):
        """Lines without a recognised level get text-gray-300"""
        settings.LOGS_DIR = self._write_log(tmp_path, "2026-01-01 DEBUG some detail\n")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'text-gray-300' in response.content

    def test_empty_log_shows_no_entries_message(self, authenticated_client, settings, tmp_path):
        """When no log entries exist, shows 'No log entries found' message"""
        settings.LOGS_DIR = self._write_log(tmp_path, "")
        response = authenticated_client.get('/Management/Logs/filter')
        assert b'No log entries found' in response.content


# ============================================================================
# SECTION 11: LogsDownload Error Path
# ============================================================================

@pytest.mark.django_db
class TestLogsDownloadErrorPath:
    """Test the error handling path for LogsDownload"""

    def test_logs_download_open_error_returns_500(
        self, authenticated_client, settings, tmp_path, monkeypatch
    ):
        """If opening the log file raises an exception, return 500"""
        log_file = tmp_path / 'logstashui.log'
        log_file.write_text("some content\n", encoding='utf-8')
        settings.LOGS_DIR = tmp_path

        # Patch open to raise an OSError
        original_open = open

        def bad_open(path, *args, **kwargs):
            if 'logstashui.log' in str(path):
                raise OSError("simulated disk error")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr('builtins.open', bad_open)

        response = authenticated_client.get('/Management/Logs/download')
        assert response.status_code == 500
        assert b'Error downloading log file' in response.content


# ============================================================================
# SECTION 12: BootstrapLoginView — Race Condition Test
# ============================================================================

@pytest.mark.django_db
class TestFirstRunRaceCondition:
    """
    Test the race-condition guard in BootstrapLoginView.form_valid (lines 71–78).
    When a concurrent request creates a user between the form-class selection and
    the select_for_update() check inside the atomic block, the view must redirect
    back to the login page without creating a duplicate user.
    """

    def test_race_condition_redirects_to_login(self, client):
        """
        Simulate a concurrent first-user creation: select_for_update().exists()
        returns True even though no users existed when the form class was chosen.
        The view should redirect back to the login path and create no user.
        """
        from unittest.mock import MagicMock, patch

        assert not User.objects.exists()

        mock_qs = MagicMock()
        mock_qs.exists.return_value = True

        with patch.object(User.objects, 'select_for_update', return_value=mock_qs):
            response = client.post('/Management/Login/', {
                'username': 'firstadmin',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            })

        # Should redirect back to the login page
        assert response.status_code == 302
        # No user should have been created
        assert not User.objects.exists()


# ============================================================================
# SECTION 13: Profile-Less User Edge Cases
# ============================================================================

@pytest.mark.django_db
class TestProfileLessBranches:
    """
    Cover the defensive else-branches in Users() that run when a user has no
    profile record.  Normally the post_save signal always creates one, but the
    view guards against the case where that record is absent.
    """

    def test_update_role_creates_profile_when_missing(self, authenticated_client, db):
        """
        update_role on a user whose profile was deleted should create a new
        UserProfile with the requested role rather than raising an error.
        """
        from Management.models import UserProfile

        user = User.objects.create_user(
            username='noprofileuser', password='pass123', email='np@example.com'
        )
        # Remove the signal-created profile so the else-branch is exercised
        UserProfile.objects.filter(user=user).delete()

        response = authenticated_client.post('/Management/Users/', {
            'action': 'update_role',
            'user_id': user.id,
            'role': 'readonly',
        })

        assert response.status_code == 200
        # Profile should now exist with the correct role
        assert UserProfile.objects.filter(user=user, role='readonly').exists()
        user.refresh_from_db()
        assert not user.is_superuser
        assert not user.is_staff


# ============================================================================
# SECTION 14: Unauthenticated Access
# ============================================================================

@pytest.mark.django_db
class TestUnauthenticatedAccess:
    """
    Verify that unauthenticated (anonymous) requests cannot reach or mutate
    protected views.  An anonymous POST to /Management/Users/ must not be able
    to create a user regardless of whether auth is enforced by a decorator,
    middleware, or URL-level login_required.
    """

    def test_anonymous_get_users_page_blocked(self, client, db):
        """Anonymous GET to Users page should be redirected to login"""
        User.objects.create_user(username='existing', password='pass123')
        response = client.get('/Management/Users/')
        assert response.status_code == 302

    def test_anonymous_post_cannot_create_user(self, client, db):
        """Anonymous POST must not create a new user"""
        User.objects.create_user(username='existing', password='pass123')
        response = client.post('/Management/Users/', {
            'action': 'add',
            'username': 'hacker',
            'password': 'SecurePass123!',
            'password2': 'SecurePass123!',
            'email': 'hacker@evil.com',
        })
        assert response.status_code == 302
        assert not User.objects.filter(username='hacker').exists()

    def test_anonymous_get_logs_page_blocked(self, client, db):
        """Anonymous GET to Logs page should be redirected to login"""
        User.objects.create_user(username='existing', password='pass123')
        response = client.get('/Management/Logs/')
        assert response.status_code == 302

    def test_anonymous_get_management_page_blocked(self, client, db):
        """Anonymous GET to Management page should be redirected to login"""
        User.objects.create_user(username='existing', password='pass123')
        response = client.get('/Management/')
        assert response.status_code == 302


# ============================================================================
# SECTION 15: _generate_user_table_rows Unit Tests
# ============================================================================

@pytest.mark.django_db
class TestGenerateUserTableRows:
    """Unit tests for the _generate_user_table_rows helper"""

    def test_returns_empty_string_for_empty_queryset(self, rf):
        """Returns an empty string when passed an empty queryset"""
        from Management.views import _generate_user_table_rows

        request = rf.get('/Management/Users/')
        result = _generate_user_table_rows(User.objects.none(), request)
        assert result == ''

    def test_renders_row_for_each_user(self, rf, db):
        """Result contains each user's username"""
        from Management.views import _generate_user_table_rows

        User.objects.create_user(username='alice', password='pass123')
        User.objects.create_user(username='bob', password='pass123')
        request = rf.get('/Management/Users/')
        result = _generate_user_table_rows(User.objects.all(), request)
        assert 'alice' in result
        assert 'bob' in result

    def test_concatenates_multiple_rows(self, rf, db):
        """HTML rows are concatenated into a single string"""
        from Management.views import _generate_user_table_rows

        User.objects.create_user(username='user1', password='pass123')
        User.objects.create_user(username='user2', password='pass123')
        User.objects.create_user(username='user3', password='pass123')
        request = rf.get('/Management/Users/')
        result = _generate_user_table_rows(User.objects.all(), request)
        # Three users means at least three separate occurrences of row markup
        assert result.count('user1') >= 1
        assert result.count('user2') >= 1
        assert result.count('user3') >= 1
