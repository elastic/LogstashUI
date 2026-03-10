#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import pytest
from django.test import RequestFactory, Client
from django.http import JsonResponse, HttpResponse
from Utilities.views import (
    GrokDebugger,
    get_grok_patterns,
    simulate_grok,
    generate_results_html
)
import json
import os
from django.conf import settings
from Common.test_resources import request_factory, authenticated_client, test_user, client


@pytest.fixture
def sample_log_data():
    """Sample log data for testing grok patterns"""
    return {
        'simple': '192.168.1.1 - - [01/Jan/2024:12:00:00 +0000] "GET /index.html HTTP/1.1" 200 1234',
        'multiline': 'Line 1\nLine 2\nLine 3',
        'special_chars': '<script>alert("xss")</script>',
        'unicode': 'User José logged in from München'
    }


@pytest.fixture
def custom_patterns():
    """Custom grok pattern definitions for testing"""
    return r"""CUSTOM_EMAIL [A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}
CUSTOM_DATE \d{4}-\d{2}-\d{2}"""


@pytest.fixture
def grok_patterns_file_path():
    """Path to the grok patterns file"""
    utilities_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    patterns_file = os.path.join(utilities_dir, 'data', 'grok-patterns.txt')
    
    if not os.path.exists(patterns_file):
        patterns_file = os.path.join(utilities_dir, 'grok-patterns')
    
    if not os.path.exists(patterns_file):
        patterns_file = os.path.join(utilities_dir, 'static', 'grok-patterns')
    
    return patterns_file


@pytest.mark.django_db
class TestGrokDebuggerView:
    """Tests for the main Grok Debugger view"""
    
    def test_grok_debugger_renders_template(self, request_factory):
        """Test that GrokDebugger view renders the correct template"""
        request = request_factory.get('/Utilities/GrokDebugger/')
        response = GrokDebugger(request)
        
        assert response.status_code == 200
    
    def test_grok_debugger_get_request(self, authenticated_client):
        """Test GET request to Grok Debugger"""
        response = authenticated_client.get('/Utilities/GrokDebugger/')
        assert response.status_code == 200


@pytest.mark.django_db
class TestGetGrokPatternsView:
    """Tests for get_grok_patterns view"""
    
    def test_get_grok_patterns_success(self, request_factory, grok_patterns_file_path):
        """Test successful loading of grok patterns"""
        request = request_factory.get('/Utilities/GrokDebugger/patterns/')
        response = get_grok_patterns(request)
        
        assert response.status_code == 200
        assert isinstance(response, JsonResponse)
        
        data = json.loads(response.content)
        assert 'patterns' in data
        assert isinstance(data['patterns'], dict)
        assert len(data['patterns']) > 0
    
    def test_get_grok_patterns_contains_common_patterns(self, request_factory):
        """Test that common patterns are present"""
        request = request_factory.get('/Utilities/GrokDebugger/patterns/')
        response = get_grok_patterns(request)
        
        data = json.loads(response.content)
        patterns = data['patterns']
        
        # Check for some common patterns
        common_patterns = ['USERNAME', 'IP', 'WORD', 'NUMBER', 'DATA']
        for pattern in common_patterns:
            assert pattern in patterns, f"Pattern {pattern} should be in grok patterns"
    
    def test_get_grok_patterns_file_exists(self, grok_patterns_file_path):
        """Test that the grok patterns file exists"""
        assert os.path.exists(grok_patterns_file_path), "Grok patterns file should exist"


@pytest.mark.django_db
class TestSimulateGrokView:
    """Tests for simulate_grok view"""
    
    def test_simulate_grok_single_line_match(self, request_factory, sample_log_data):
        """Test successful pattern matching on single line"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': sample_log_data['simple'],
            'grok_pattern': '%{IP:client_ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        assert isinstance(response, HttpResponse)
        
        content = response.content.decode('utf-8')
        assert '192.168.1.1' in content
        assert 'Match Found' in content or 'success' in content.lower()
    
    def test_simulate_grok_single_line_no_match(self, request_factory):
        """Test pattern that doesn't match input"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': 'This is plain text',
            'grok_pattern': '%{IP:client_ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'No Match' in content or 'did not match' in content.lower()
    
    def test_simulate_grok_multiline_mode(self, request_factory, sample_log_data):
        """Test multiline mode treats entire input as single string"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': sample_log_data['multiline'],
            'grok_pattern': '%{GREEDYDATA:message}',
            'custom_patterns': '',
            'multiline_mode': 'true'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        # In multiline mode, should treat as one input
        assert 'Line 1' in content
    
    def test_simulate_grok_multiple_patterns(self, request_factory):
        """Test multiple patterns against single input"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1',
            'grok_pattern': '%{IP:ip}\n%{WORD:word}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        # Should show results for Pattern 1 and Pattern 2
        assert 'Pattern 1' in content
        assert 'Pattern 2' in content
    
    def test_simulate_grok_custom_patterns(self, request_factory, custom_patterns):
        """Test with custom pattern definitions"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': 'test@example.com',
            'grok_pattern': '%{CUSTOM_EMAIL:email}',
            'custom_patterns': custom_patterns,
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'test@example.com' in content
    
    def test_simulate_grok_dot_notation_fields(self, request_factory):
        """Test field names with dots create nested dictionaries"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1',
            'grok_pattern': '%{IP:client.ip.address}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        # Should show nested structure
        assert 'client' in content
        assert '192.168.1.1' in content
    
    def test_simulate_grok_pattern_compilation_error(self, request_factory):
        """Test invalid grok pattern syntax"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': 'test data',
            'grok_pattern': '%{INVALID_PATTERN_THAT_DOES_NOT_EXIST:field}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'error' in content.lower() or 'compilation' in content.lower()
    
    def test_simulate_grok_empty_sample_data(self, request_factory):
        """Test with empty sample data"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '',
            'grok_pattern': '%{IP:ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
    
    def test_simulate_grok_empty_pattern(self, request_factory):
        """Test with empty pattern"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': 'test data',
            'grok_pattern': '',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
    
    def test_simulate_grok_invalid_request_method(self, request_factory):
        """Test GET request to simulate endpoint (should only accept POST)"""
        request = request_factory.get('/Utilities/GrokDebugger/simulate/')
        response = simulate_grok(request)
        
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        assert 'Invalid request method' in content
    
    def test_simulate_grok_special_characters(self, request_factory, sample_log_data):
        """Test handling of special characters and potential XSS"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': sample_log_data['special_chars'],
            'grok_pattern': '%{GREEDYDATA:data}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        # Check that HTML is escaped
        assert '&lt;script&gt;' in content or '<script>' not in content
    
    def test_simulate_grok_unicode_handling(self, request_factory, sample_log_data):
        """Test handling of Unicode characters"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': sample_log_data['unicode'],
            'grok_pattern': '%{GREEDYDATA:message}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        assert 'José' in content or 'jos' in content.lower()
    
    def test_simulate_grok_multiple_inputs_multiple_patterns(self, request_factory):
        """Test multiple inputs against multiple patterns"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1\n10.0.0.1\n172.16.0.1',
            'grok_pattern': '%{IP:ip}\n%{WORD:word}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        
        response = simulate_grok(request)
        assert response.status_code == 200
        
        content = response.content.decode('utf-8')
        # Should have results for each pattern against each input
        assert 'Pattern 1' in content
        assert 'Pattern 2' in content
        assert '192.168.1.1' in content


@pytest.mark.django_db
class TestGenerateResultsHtml:
    """Tests for generate_results_html function"""
    
    def test_generate_results_html_success(self):
        """Test HTML generation for successful matches"""
        results = [{
            'pattern': '%{IP:ip}',
            'pattern_number': 1,
            'matches': [{
                'line_number': 1,
                'sample': '192.168.1.1',
                'success': True,
                'parsed_data': {'ip': '192.168.1.1'}
            }]
        }]
        
        html = generate_results_html(results)
        
        assert 'Pattern 1' in html
        assert '192.168.1.1' in html
        assert 'Match Found' in html
        assert 'badge-success' in html
    
    def test_generate_results_html_failure(self):
        """Test HTML generation for failed matches"""
        results = [{
            'pattern': '%{IP:ip}',
            'pattern_number': 1,
            'matches': [{
                'line_number': 1,
                'sample': 'not an ip',
                'success': False,
                'error': 'Pattern did not match'
            }]
        }]
        
        html = generate_results_html(results)
        
        assert 'Pattern 1' in html
        assert 'No Match' in html
        assert 'badge-error' in html
        assert 'Pattern did not match' in html
    
    def test_generate_results_html_mixed_results(self):
        """Test HTML generation with both successes and failures"""
        results = [{
            'pattern': '%{IP:ip}',
            'pattern_number': 1,
            'matches': [
                {
                    'line_number': 1,
                    'sample': '192.168.1.1',
                    'success': True,
                    'parsed_data': {'ip': '192.168.1.1'}
                },
                {
                    'line_number': 2,
                    'sample': 'not an ip',
                    'success': False,
                    'error': 'Pattern did not match'
                }
            ]
        }]
        
        html = generate_results_html(results)
        
        assert '1 matched' in html
        assert '1 failed' in html
    
    def test_generate_results_html_escapes_special_chars(self):
        """Test that special characters are escaped in HTML output"""
        results = [{
            'pattern': '<script>alert("xss")</script>',
            'pattern_number': 1,
            'matches': [{
                'line_number': 1,
                'sample': '<img src=x onerror=alert(1)>',
                'success': False,
                'error': '<script>evil</script>'
            }]
        }]
        
        html = generate_results_html(results)
        
        # All user input should be escaped
        assert '&lt;script&gt;' in html
        assert '&lt;img' in html
    
    def test_generate_results_html_nested_data(self):
        """Test HTML generation with nested parsed data"""
        results = [{
            'pattern': '%{IP:client.ip}',
            'pattern_number': 1,
            'matches': [{
                'line_number': 1,
                'sample': '192.168.1.1',
                'success': True,
                'parsed_data': {'client': {'ip': '192.168.1.1'}}
            }]
        }]
        
        html = generate_results_html(results)
        
        assert 'client' in html
        assert '192.168.1.1' in html


@pytest.mark.django_db
class TestGrokDebuggerIntegration:
    """Integration tests for the full Grok Debugger workflow"""
    
    def test_full_workflow_simple_pattern(self, authenticated_client):
        """Test complete workflow from page load to simulation"""
        # Load the page
        response = authenticated_client.get('/Utilities/GrokDebugger/')
        assert response.status_code == 200
        
        # Simulate a grok pattern
        response = authenticated_client.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1',
            'grok_pattern': '%{IP:ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        assert response.status_code == 200
        assert b'192.168.1.1' in response.content
    
    def test_full_workflow_with_custom_patterns(self, authenticated_client, custom_patterns):
        """Test workflow with custom patterns"""
        response = authenticated_client.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '2024-01-15',
            'grok_pattern': '%{CUSTOM_DATE:date}',
            'custom_patterns': custom_patterns,
            'multiline_mode': 'false'
        })
        assert response.status_code == 200
        assert b'2024-01-15' in response.content


# ============================================================================
# Additional gap-filling tests
# ============================================================================

@pytest.mark.django_db
class TestGetGrokPatternsErrors:
    """Test error-handling branches in get_grok_patterns"""

    def test_get_grok_patterns_file_missing_returns_500(self, request_factory):
        """When the grok-patterns file does not exist, the view returns 500 with an error key"""
        from unittest.mock import patch
        request = request_factory.get('/Utilities/GrokDebugger/patterns/')

        with patch('Utilities.views.open', side_effect=FileNotFoundError("no such file")):
            response = get_grok_patterns(request)

        assert response.status_code == 500
        data = json.loads(response.content)
        assert 'error' in data

    def test_get_grok_patterns_skips_comment_and_blank_lines(self, request_factory):
        """Lines starting with # or blank lines are not included as patterns"""
        from unittest.mock import patch, mock_open
        fake_content = "# This is a comment\n\nWORD \\b\\w+\\b\n"
        request = request_factory.get('/Utilities/GrokDebugger/patterns/')

        with patch('builtins.open', mock_open(read_data=fake_content)):
            response = get_grok_patterns(request)

        data = json.loads(response.content)
        patterns = data['patterns']
        # Only WORD should be loaded; the comment and blank line must be absent
        assert 'WORD' in patterns
        for key in patterns:
            assert not key.startswith('#')

    def test_get_grok_patterns_skips_lines_without_space(self, request_factory):
        """Lines with no whitespace (can't be split into name + definition) are silently skipped"""
        from unittest.mock import patch, mock_open
        fake_content = "BADLINE\nGOOD pattern_def\n"
        request = request_factory.get('/Utilities/GrokDebugger/patterns/')

        with patch('builtins.open', mock_open(read_data=fake_content)):
            response = get_grok_patterns(request)

        data = json.loads(response.content)
        patterns = data['patterns']
        assert 'GOOD' in patterns
        assert 'BADLINE' not in patterns


@pytest.mark.django_db
class TestSimulateGrokAdditional:
    """Additional simulate_grok edge-case tests"""

    def test_whitespace_only_lines_filtered_from_sample(self, request_factory):
        """Whitespace-only sample lines are filtered out before matching"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '   \n  \t  ',
            'grok_pattern': '%{IP:ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        response = simulate_grok(request)
        assert response.status_code == 200
        # No sample lines to process → HTML has no match results
        content = response.content.decode('utf-8')
        assert 'Match Found' not in content
        assert 'No Match' not in content

    def test_whitespace_only_pattern_lines_filtered(self, request_factory):
        """Whitespace-only pattern lines are filtered; result is empty HTML"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1',
            'grok_pattern': '   \n\t',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        response = simulate_grok(request)
        assert response.status_code == 200
        # No patterns → empty body (no Pattern N headings)
        content = response.content.decode('utf-8')
        assert 'Pattern 1' not in content

    def test_custom_patterns_blank_and_comment_lines_ignored(self, request_factory):
        """Blank lines and lines without a space in custom_patterns are silently skipped"""
        custom = "# comment\n\nMY_IP (?:\\d{1,3}\\.){3}\\d{1,3}\n"
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '10.0.0.1',
            'grok_pattern': '%{MY_IP:ip}',
            'custom_patterns': custom,
            'multiline_mode': 'false'
        })
        response = simulate_grok(request)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # MY_IP should have been parsed; match should succeed
        assert 'Match Found' in content

    def test_multiline_mode_false_splits_on_newlines(self, request_factory):
        """When multiline_mode is false, each non-blank line is treated independently"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1\n10.0.0.1',
            'grok_pattern': '%{IP:ip}',
            'custom_patterns': '',
            'multiline_mode': 'false'
        })
        response = simulate_grok(request)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Both IPs should appear in Line 1 and Line 2 results
        assert 'Line 1' in content
        assert 'Line 2' in content
        assert '192.168.1.1' in content
        assert '10.0.0.1' in content

    def test_multiline_mode_true_no_split(self, request_factory):
        """When multiline_mode is true, the two-line input is treated as a single chunk"""
        request = request_factory.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1\n10.0.0.1',
            'grok_pattern': '%{GREEDYDATA:msg}',
            'custom_patterns': '',
            'multiline_mode': 'true'
        })
        response = simulate_grok(request)
        assert response.status_code == 200
        content = response.content.decode('utf-8')
        # Only one entry (Line 1); Line 2 label must not appear
        assert 'Line 2' not in content


@pytest.mark.django_db
class TestGenerateResultsHtmlAdditional:
    """Additional generate_results_html tests"""

    def test_empty_results_list_returns_empty_string(self):
        """No results → empty string (no crash, no stray HTML)"""
        output = generate_results_html([])
        assert output == ''

    def test_pattern_error_field_shown_in_html(self):
        """When a result has pattern_error set, the error information is included"""
        results = [{
            'pattern': '%{BAD_PATTERN:x}',
            'pattern_number': 1,
            'pattern_error': 'Undefined pattern: BAD_PATTERN',
            'matches': [{
                'line_number': 1,
                'sample': 'anything',
                'success': False,
                'error': 'Pattern compilation error: Undefined pattern: BAD_PATTERN',
                'error_type': 'compilation'
            }]
        }]
        output = generate_results_html(results)
        # The pattern header and the failed match entry should both be present
        assert 'Pattern 1' in output
        assert 'No Match' in output
        assert 'compilation' in output.lower() or 'Pattern compilation' in output

    def test_zero_matched_badge_correct(self):
        """Badge shows 0 matched when all lines fail"""
        results = [{
            'pattern': '%{IP:ip}',
            'pattern_number': 1,
            'matches': [
                {'line_number': 1, 'sample': 'hello', 'success': False, 'error': 'no match'},
                {'line_number': 2, 'sample': 'world', 'success': False, 'error': 'no match'},
            ]
        }]
        output = generate_results_html(results)
        assert '0 matched' in output
        assert '2 failed' in output

    def test_all_matched_badge_correct(self):
        """Badge shows 0 failed when all lines succeed"""
        results = [{
            'pattern': '%{IP:ip}',
            'pattern_number': 1,
            'matches': [
                {'line_number': 1, 'sample': '1.1.1.1', 'success': True, 'parsed_data': {'ip': '1.1.1.1'}},
                {'line_number': 2, 'sample': '2.2.2.2', 'success': True, 'parsed_data': {'ip': '2.2.2.2'}},
            ]
        }]
        output = generate_results_html(results)
        assert '2 matched' in output
        assert '0 failed' in output

    def test_html_escape_in_error_message(self):
        """Error messages containing HTML special chars are escaped"""
        results = [{
            'pattern': 'p',
            'pattern_number': 1,
            'matches': [{
                'line_number': 1,
                'sample': 'x',
                'success': False,
                'error': '<b>bad</b> & "error"'
            }]
        }]
        output = generate_results_html(results)
        assert '<b>' not in output          # raw tag must not appear
        assert '&lt;b&gt;' in output        # escaped version must appear


@pytest.mark.django_db
class TestAuthenticationAndRouting:
    """URL-level authentication and routing tests"""

    def test_grok_debugger_requires_authentication(self, client):
        """Unauthenticated request to GrokDebugger redirects to login"""
        response = client.get('/Utilities/GrokDebugger/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_simulate_grok_requires_authentication(self, client):
        """Unauthenticated POST to simulate endpoint redirects to login"""
        response = client.post('/Utilities/GrokDebugger/simulate/', {
            'sample_data': '192.168.1.1',
            'grok_pattern': '%{IP:ip}',
        })
        assert response.status_code == 302
        assert '/Management/Login/' in response.url

    def test_get_grok_patterns_requires_authentication(self, client):
        """Unauthenticated GET to patterns endpoint redirects to login"""
        response = client.get('/Utilities/GrokDebugger/patterns/')
        assert response.status_code == 302
        assert '/Management/Login/' in response.url
