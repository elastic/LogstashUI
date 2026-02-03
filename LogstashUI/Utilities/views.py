from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from pygrok import Grok
import json
import os

def GrokDebugger(request):
    return render(request, 'grok_debugger.html')

def get_grok_patterns(request):
    """Load grok patterns from file and return as JSON"""
    patterns = {}
    patterns_file = os.path.join(os.path.dirname(__file__), 'data', 'grok-patterns.txt')
    
    try:
        with open(patterns_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                # Parse pattern: NAME definition
                if ' ' in line:
                    parts = line.split(None, 1)
                    if len(parts) == 2:
                        pattern_name, pattern_def = parts
                        patterns[pattern_name] = pattern_def
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)
    
    return JsonResponse({'patterns': patterns})

def simulate_grok(request):
    if request.method == 'POST':
        sample_data = request.POST.get('sample_data', '')
        grok_pattern = request.POST.get('grok_pattern', '')
        custom_patterns = request.POST.get('custom_patterns', '')
        multiline_mode = request.POST.get('multiline_mode', 'false').lower() == 'true'
        
        # Helper function to convert dot notation to underscores for PyGrok
        # Also track which fields originally had dots so we can convert them back
        dot_fields = set()
        
        def convert_dots_to_underscores(pattern):
            import re
            # Match field names with dots like :field.name or :field.name.nested
            # Pattern: %{PATTERN:field.name} or %{PATTERN:field.name:type}
            def replace_dots(match):
                full_match = match.group(0)
                field_name = match.group(1)
                # Track this field as having dots
                dot_fields.add(field_name)
                # Replace dots with a special marker that won't conflict with underscores
                new_field_name = field_name.replace('.', '__DOT__')
                return full_match.replace(field_name, new_field_name)
            
            # Match %{...:field.name...} patterns
            return re.sub(r'%\{[^:]+:([^:}]+(?:\.[^:}]+)+)(?::[^}]+)?\}', replace_dots, pattern)
        
        # Helper function to convert results into nested dictionaries for dot notation
        def create_nested_dict(data_dict):
            result = {}
            for key, value in data_dict.items():
                # Check if this key was originally a dot-notation field
                if '__DOT__' in key:
                    # Convert back to dots and split into parts
                    original_key = key.replace('__DOT__', '.')
                    parts = original_key.split('.')
                    
                    # Create nested structure
                    current = result
                    for part in parts[:-1]:
                        if part not in current:
                            current[part] = {}
                        current = current[part]
                    current[parts[-1]] = value
                else:
                    # Keep underscores as-is
                    result[key] = value
            return result
        
        # Parse inputs into lines
        # In multiline mode, treat entire sample_data as a single input
        if multiline_mode:
            sample_lines = [sample_data] if sample_data.strip() else []
        else:
            sample_lines = [line for line in sample_data.split('\n') if line.strip()]
        pattern_lines = [line for line in grok_pattern.split('\n') if line.strip()]
        
        # Parse custom patterns into a dictionary
        custom_patterns_dict = {}
        if custom_patterns.strip():
            for line in custom_patterns.split('\n'):
                line = line.strip()
                if line and ' ' in line:
                    parts = line.split(None, 1)  # Split on first whitespace
                    if len(parts) == 2:
                        pattern_name, pattern_def = parts
                        custom_patterns_dict[pattern_name] = pattern_def
        
        # Process each grok pattern
        results = []
        for pattern_idx, pattern in enumerate(pattern_lines, 1):
            # Convert dots to underscores for PyGrok compatibility
            pygrok_pattern = convert_dots_to_underscores(pattern)
            
            pattern_result = {
                'pattern': pattern,  # Store original pattern for display
                'pattern_number': pattern_idx,
                'matches': [],
                'pattern_error': None
            }
            
            # Try to compile the pattern first to catch syntax errors
            try:
                grok = Grok(pygrok_pattern, custom_patterns=custom_patterns_dict)
            except Exception as e:
                # Pattern compilation failed - this is a syntax error
                pattern_result['pattern_error'] = str(e)
                # Add entries for each sample line showing the pattern error
                for line_idx, sample_line in enumerate(sample_lines, 1):
                    pattern_result['matches'].append({
                        'line_number': line_idx,
                        'sample': sample_line,
                        'success': False,
                        'error': f'Pattern compilation error: {str(e)}',
                        'error_type': 'compilation'
                    })
                results.append(pattern_result)
                continue
            
            # Test each sample data line against this pattern
            for line_idx, sample_line in enumerate(sample_lines, 1):
                try:
                    match = grok.match(sample_line)
                    
                    if match:
                        # Remove null values from the match result
                        filtered_match = {k: v for k, v in match.items() if v is not None}
                        # Convert to nested dictionaries for dot notation (Logstash-style)
                        nested_match = create_nested_dict(filtered_match)
                        pattern_result['matches'].append({
                            'line_number': line_idx,
                            'sample': sample_line,
                            'success': True,
                            'parsed_data': nested_match
                        })
                    else:
                        pattern_result['matches'].append({
                            'line_number': line_idx,
                            'sample': sample_line,
                            'success': False,
                            'error': 'Pattern did not match the input. The pattern structure may not align with the log format.',
                            'error_type': 'no_match'
                        })
                except Exception as e:
                    # Runtime error during matching
                    pattern_result['matches'].append({
                        'line_number': line_idx,
                        'sample': sample_line,
                        'success': False,
                        'error': f'Runtime error: {str(e)}',
                        'error_type': 'runtime'
                    })
            
            results.append(pattern_result)
        
        # Generate HTML response
        html_response = generate_results_html(results)
        return HttpResponse(html_response)
    
    return HttpResponse('<p class="text-error">Invalid request method</p>')

def generate_results_html(results):
    """Generate HTML for the grok results"""
    html_parts = []
    
    for result in results:
        pattern = result['pattern']
        pattern_num = result['pattern_number']
        matches = result['matches']
        
        # Count successes and failures
        success_count = sum(1 for m in matches if m['success'])
        failure_count = len(matches) - success_count
        
        # Pattern header
        html_parts.append(f'''
        <div class="mb-6">
            <div class="flex items-center justify-between mb-3 pb-2 border-b border-base-300">
                <h3 class="text-lg font-semibold text-base-content">Pattern {pattern_num}</h3>
                <div class="flex gap-2 text-xs">
                    <span class="badge badge-success">{success_count} matched</span>
                    <span class="badge badge-error">{failure_count} failed</span>
                </div>
            </div>
            <div class="bg-base-300 rounded p-3 mb-4">
                <code class="text-sm font-mono text-base-content">{pattern}</code>
            </div>
        ''')
        
        # Results for each sample line
        for match in matches:
            line_num = match['line_number']
            sample = match['sample']
            success = match['success']
            
            if success:
                parsed_data = match['parsed_data']
                html_parts.append(f'''
                <div class="mb-3 p-3 bg-success/10 border border-success/30 rounded">
                    <div class="flex items-start gap-2 mb-2">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-success flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                            <p class="text-xs font-semibold text-success mb-1">Line {line_num} - Match Found</p>
                            <p class="text-xs text-base-content/70 mb-2 font-mono bg-base-200 p-2 rounded">{sample}</p>
                            <div class="bg-base-200 rounded p-2">
                                <p class="text-xs font-semibold mb-1">Extracted Fields:</p>
                                <pre class="text-xs font-mono overflow-auto">{json.dumps(parsed_data, indent=2)}</pre>
                            </div>
                        </div>
                    </div>
                </div>
                ''')
            else:
                error = match['error']
                print(match)
                html_parts.append(f'''
                <div class="mb-3 p-3 bg-error/10 border border-error/30 rounded">
                    <div class="flex items-start gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-error flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                            <p class="text-xs font-semibold text-error mb-1">Line {line_num} - No Match</p>
                            <p class="text-xs text-base-content/70 mb-2 font-mono bg-base-200 p-2 rounded">{sample}</p>
                            <p class="text-xs text-error/80"><strong>Reason:</strong> {error}</p>
                        </div>
                    </div>
                </div>
                ''')
        
        html_parts.append('</div>')
    
    return ''.join(html_parts)
