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
