import pytest
import os
import re


@pytest.mark.django_db
class TestGrokPatternsFile:
    """Tests for the grok-patterns.txt file"""
    
    def test_grok_patterns_file_exists(self, grok_patterns_file_path):
        """Verify grok-patterns.txt file exists"""
        assert os.path.exists(grok_patterns_file_path), \
            f"Grok patterns file should exist at {grok_patterns_file_path}"
    
    def test_grok_patterns_file_readable(self, grok_patterns_file_path):
        """Verify file is readable"""
        try:
            with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            assert len(content) > 0, "Grok patterns file should not be empty"
        except Exception as e:
            pytest.fail(f"Failed to read grok patterns file: {e}")
    
    def test_grok_patterns_file_format(self, grok_patterns_file_path):
        """Verify all patterns follow correct format"""
        with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Pattern should be: NAME definition
                if ' ' not in line:
                    pytest.fail(
                        f"Line {line_num} is malformed (no space separator): {line}"
                    )
                
                parts = line.split(None, 1)
                if len(parts) != 2:
                    pytest.fail(
                        f"Line {line_num} is malformed (expected 2 parts): {line}"
                    )
                
                pattern_name, pattern_def = parts
                
                # Pattern name should be uppercase alphanumeric with underscores
                if not re.match(r'^[A-Z0-9_]+$', pattern_name):
                    pytest.fail(
                        f"Line {line_num} has invalid pattern name '{pattern_name}': "
                        f"should be uppercase alphanumeric with underscores"
                    )
    
    def test_grok_patterns_no_duplicates(self, grok_patterns_file_path):
        """Verify no duplicate pattern names"""
        pattern_names = []
        
        with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                if ' ' in line:
                    pattern_name = line.split(None, 1)[0]
                    pattern_names.append(pattern_name)
        
        duplicates = [name for name in pattern_names if pattern_names.count(name) > 1]
        duplicates = list(set(duplicates))
        
        assert len(duplicates) == 0, \
            f"Found duplicate pattern names: {duplicates}"
    
    def test_grok_patterns_contains_essential_patterns(self, grok_patterns_file_path):
        """Verify essential patterns are present"""
        essential_patterns = [
            'USERNAME', 'USER', 'INT', 'NUMBER', 'WORD', 
            'NOTSPACE', 'SPACE', 'DATA', 'GREEDYDATA', 'IP', 'IPV4'
        ]
        
        with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        missing_patterns = []
        for pattern in essential_patterns:
            # Look for pattern at start of line (with word boundary)
            if not re.search(rf'^{pattern}\s', content, re.MULTILINE):
                missing_patterns.append(pattern)
        
        assert len(missing_patterns) == 0, \
            f"Missing essential patterns: {missing_patterns}"
    
    def test_grok_patterns_encoding(self, grok_patterns_file_path):
        """Verify file uses UTF-8 encoding"""
        try:
            with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
                f.read()
        except UnicodeDecodeError:
            pytest.fail("Grok patterns file should be UTF-8 encoded")
    
    def test_grok_patterns_no_trailing_whitespace(self, grok_patterns_file_path):
        """Verify no lines have trailing whitespace (code quality check)"""
        lines_with_trailing_ws = []
        
        with open(grok_patterns_file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                # Check for trailing whitespace (but not newlines)
                if line.rstrip('\r\n') != line.rstrip():
                    lines_with_trailing_ws.append(line_num)
        
        # This is a soft check - we'll warn but not fail
        if lines_with_trailing_ws:
            print(f"Warning: Lines with trailing whitespace: {lines_with_trailing_ws[:10]}")
