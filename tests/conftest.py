#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from django.contrib.auth.models import User
from django.test import Client, RequestFactory
from PipelineManager.models import Connection

import pytest

# A6 neutralization (spec logstashui-django-debug-default-false r2): with the
# DEBUG default now false, import-time SECURE_SSL_REDIRECT follows TLS_ENABLED
# (true by default), which 301-redirects plain-HTTP test clients. Django is
# configured by pytest-django before conftest imports, so this runtime override
# neutralizes the redirect for the suite. DEBUG stays unset throughout — this
# is neutralization of the redirect, not masking of the flip.
from django.conf import settings as _dj_settings

_dj_settings.SECURE_SSL_REDIRECT = False


@pytest.fixture
def request_factory():
    return RequestFactory()


@pytest.fixture
def authenticated_client(client, test_user):
    client.login(username='testuser', password='testpass123')
    return client


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def test_user(db):
    from Management.models import UserProfile

    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )
    user.is_superuser = True
    user.is_staff = True
    user.save()

    UserProfile.objects.get_or_create(
        user=user,
        defaults={'role': 'admin'}
    )

    return user


@pytest.fixture
def test_connection(db):
    connection = Connection.objects.create(
        name='Test Connection',
        connection_type='CENTRALIZED',
        host='https://localhost:9200',
        username='elastic',
        password='changeme'
    )
    return connection
