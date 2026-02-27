import pytest
from django.test import RequestFactory
from django.contrib.auth import get_user_model
import os

User = get_user_model()


@pytest.fixture
def request_factory():
    """Provide Django RequestFactory for creating mock requests"""
    return RequestFactory()


@pytest.fixture
def sample_grok_patterns():
    """Sample grok patterns for testing"""
    return {
        'USERNAME': '[a-zA-Z0-9._-]+',
        'USER': '%{USERNAME}',
        'EMAILLOCALPART': '[a-zA-Z0-9!#$%&\'*+/=?^_`{|}~-]+(?:\\.[a-zA-Z0-9!#$%&\'*+/=?^_`{|}~-]+)*',
        'HOSTNAME': '\\b(?:[0-9A-Za-z][0-9A-Za-z-]{0,62})(?:\\.(?:[0-9A-Za-z][0-9A-Za-z-]{0,62}))*(\\.?|\\b)',
        'EMAILADDRESS': '%{EMAILLOCALPART}@%{HOSTNAME}',
        'INT': '(?:[+-]?(?:[0-9]+))',
        'BASE10NUM': '(?<![0-9.+-])(?>[+-]?(?:(?:[0-9]+(?:\\.[0-9]+)?)|(?:\\.[0-9]+)))',
        'NUMBER': '(?:%{BASE10NUM})',
        'WORD': '\\b\\w+\\b',
        'NOTSPACE': '\\S+',
        'SPACE': '\\s*',
        'DATA': '.*?',
        'GREEDYDATA': '.*',
        'QUOTEDSTRING': '(?:(?:"(?:[^"\\\\]|\\\\.)*")|(?:\'(?:[^\'\\\\]|\\\\.)*\'))',
        'UUID': '[A-Fa-f0-9]{8}-(?:[A-Fa-f0-9]{4}-){3}[A-Fa-f0-9]{12}',
        'IP': '(?:%{IPV6}|%{IPV4})',
        'IPV4': '(?<![0-9])(?:(?:[0-1]?[0-9]{1,2}|2[0-4][0-9]|25[0-5])[.](?:[0-1]?[0-9]{1,2}|2[0-4][0-9]|25[0-5])[.](?:[0-1]?[0-9]{1,2}|2[0-4][0-9]|25[0-5])[.](?:[0-1]?[0-9]{1,2}|2[0-4][0-9]|25[0-5]))(?![0-9])',
    }


@pytest.fixture
def sample_log_data():
    """Sample log data for testing grok patterns"""
    return {
        'simple': '192.168.1.1 - frank [10/Oct/2000:13:55:36 -0700] "GET /apache_pb.gif HTTP/1.0" 200 2326',
        'email': 'User email is john.doe@example.com',
        'multiline': '''Line 1: Error occurred
Line 2: Stack trace follows
Line 3: End of error''',
        'special_chars': '<script>alert("XSS")</script>',
        'unicode': 'User: José García, Email: josé@example.com',
    }


@pytest.fixture
def sample_grok_pattern():
    """Sample grok pattern for testing"""
    return '%{IP:client_ip} - %{WORD:user} \\[%{DATA:timestamp}\\] "%{WORD:method} %{DATA:request} HTTP/%{NUMBER:http_version}" %{INT:status_code} %{INT:bytes}'


@pytest.fixture
def custom_patterns():
    """Sample custom patterns"""
    return """POSTFIX_QUEUEID [0-9A-F]{10,11}
CUSTOM_EMAIL [a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}
CUSTOM_DATE \\d{4}-\\d{2}-\\d{2}"""


@pytest.fixture
def authenticated_user(db):
    """Create an authenticated user for testing"""
    User = get_user_model()
    user = User.objects.create_user(
        username='testuser',
        password='testpass123',
        email='test@example.com'
    )
    return user


@pytest.fixture
def authenticated_client(client, authenticated_user):
    """Provide an authenticated Django test client"""
    client.force_login(authenticated_user)
    return client


@pytest.fixture
def grok_patterns_file_path():
    """Get the path to the grok patterns file"""
    from Utilities import views
    return os.path.join(os.path.dirname(views.__file__), 'data', 'grok-patterns.txt')
