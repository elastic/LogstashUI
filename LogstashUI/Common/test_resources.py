from django.contrib.auth.models import User
from django.test import Client
from PipelineManager.models import Connection

import pytest


##### Fixtures #####
@pytest.fixture
def authenticated_client(client, test_user):
    """Client with authenticated user"""
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def client():
    """Django test client"""
    return Client()


@pytest.fixture
def test_user(db):
    """Create a test user"""
    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )
    user.is_superuser = True
    user.is_staff = True
    user.save()
    return user




@pytest.fixture
def test_connection(db):
    """Create a test connection"""
    connection = Connection.objects.create(
        name='Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )
    return connection
