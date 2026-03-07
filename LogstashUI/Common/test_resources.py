#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

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
    """Create a test user with admin profile"""
    from Management.models import UserProfile
    
    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )
    user.is_superuser = True
    user.is_staff = True
    user.save()
    
    # Create admin profile (use get_or_create to avoid UNIQUE constraint errors)
    UserProfile.objects.get_or_create(
        user=user,
        defaults={'role': 'admin'}
    )
    
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
