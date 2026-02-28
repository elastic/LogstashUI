import pytest
from django.contrib.auth.models import User
from Common.test_resources import authenticated_client, test_user


# ============================================================================
# User Management CRUD Tests
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
            'email': 'newuser@example.com'
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
