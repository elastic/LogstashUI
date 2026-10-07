#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Grok and Dissect debuggers: simulate patterns against sample logs."""

from django.shortcuts import render
from django.http import JsonResponse, HttpResponse

from .dissect import Dissector, DissectError, DissectFailure, field_path, looks_like_grok
from .grok import PATTERN_SETS, Grok, GrokError, load_patterns, looks_like_dissect, parse_patterns

import json
import html
import re
import time

import logging

logger = logging.getLogger(__name__)

GROK_MATCH_TIMEOUT = 2
# Applies to both debuggers, covering grok compilation as well as matching.
REQUEST_TIMEOUT = 15


def skipped_match(line_number, sample_line):
    """Result for a line that was not run because the request ran out of time."""
    return {'line_number': line_number, 'sample': sample_line, 'success': False,
            'error': f'Skipped: this simulation hit the {REQUEST_TIMEOUT} second limit.'}


def split_sample_lines(sample_data, multiline_mode):
    """Split debugger sample data into numbered events.

    Args:
        sample_data: Raw text from the Sample Data editor.
        multiline_mode: If True, the whole text is a single event.

    Returns:
        List of ``(line_number, text)`` tuples. Blank lines are skipped but keep
        their place in the numbering, so numbers match the editor's gutter.

    Example:
        >>> split_sample_lines("a\\n\\nb", False)
        [(1, 'a'), (3, 'b')]
    """
    if multiline_mode:
        return [(1, sample_data)] if sample_data.strip() else []
    return [(number, line) for number, line in enumerate(sample_data.split('\n'), 1) if line.strip()]

def message_html(message, css_class='text-base-content/60'):
    """Render a one-line message for the results area."""
    return f'<p class="text-sm italic {css_class}">{html.escape(message)}</p>'

def missing_input_html(sample_lines, pattern_lines, pattern_label):
    """Return a hint if sample data or patterns are missing, otherwise None."""
    if not pattern_lines:
        return message_html(f'Enter at least one {pattern_label} to simulate.')
    if not sample_lines:
        return message_html('Enter some sample data to simulate.')
    return None

def GrokDebugger(request):
    """Render the grok debugger page."""
    return render(request, 'grok_debugger.html')

def ecs_compatibility_param(data):
    """Read ``ecs_compatibility`` from request data, defaulting to Logstash 8+'s ``v8``."""
    value = data.get('ecs_compatibility', 'v8')
    return value if value in PATTERN_SETS else 'v8'

def get_grok_patterns(request):
    """Return the bundled grok patterns for an ``ecs_compatibility`` mode as JSON.

    Query parameters: ``ecs_compatibility`` (``v8``, ``v1`` or ``disabled``).

    Returns:
        JsonResponse ``{"patterns": {name: definition, ...}}``.
    """
    try:
        patterns = load_patterns(ecs_compatibility_param(request.GET))
    except OSError as e:
        logger.error(f"Failed to load grok patterns: {e}")
        return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'patterns': patterns})

def grok_pattern_warning(pattern, grok=None):
    """Return hints for common grok mistakes, or None.

    Example:
        >>> grok_pattern_warning("%{clientip} %{verb}")[:39]
        'This looks like a dissect pattern. Grok'
        >>> grok_pattern_warning("[%{HTTPDATE:ts}]")[:44]
        'An unescaped [ starts a regex character clas'
    """
    hints = []
    if looks_like_dissect(pattern):
        hints.append('This looks like a dissect pattern. Grok needs a pattern name for every field, '
                     'like %{WORD:verb}; use the Dissect Debugger for dissect patterns.')
    if re.search(r'(?<!\\)\[[^\]]*%\{', pattern):
        hints.append('An unescaped [ starts a regex character class, so [%{...}] matches a single character. '
                     r'Write \[ and \] to match literal brackets.')
    if grok and any(field_path(field) == ['message'] for field in grok.fields):
        hints.append('This pattern captures into message, which already holds the original line, so Logstash '
                     'turns message into an array. Add overwrite => ["message"] to the grok filter to replace it instead.')
    return ' '.join(hints) or None

def simulate_grok(request):
    """Match grok patterns against sample lines and return an HTML fragment.

    POST fields: ``sample_data``, ``grok_pattern`` (one pattern per line),
    ``custom_patterns`` (pattern-file lines), ``ecs_compatibility`` and
    ``multiline_mode``. Matching follows the Logstash grok filter, see
    ``Utilities.grok``.

    Note:
        Response is HTML for htmx, not JSON.
    """
    if request.method != 'POST':
        return HttpResponse('<p class="text-error">Invalid request method</p>')

    sample_data, grok_pattern, custom_patterns = (
        request.POST.get(name, '').replace('\r\n', '\n') for name in ('sample_data', 'grok_pattern', 'custom_patterns')
    )
    multiline_mode = request.POST.get('multiline_mode', 'false').lower() == 'true'

    sample_lines = split_sample_lines(sample_data, multiline_mode)
    pattern_lines = [line for line in grok_pattern.split('\n') if line.strip()]
    missing = missing_input_html(sample_lines, pattern_lines, 'grok pattern')
    if missing:
        return HttpResponse(missing)

    patterns = {**load_patterns(ecs_compatibility_param(request.POST)), **parse_patterns(custom_patterns)}
    deadline = time.monotonic() + REQUEST_TIMEOUT
    results = []
    for pattern_idx, pattern in enumerate(pattern_lines, 1):
        pattern_result = {'pattern': pattern, 'pattern_number': pattern_idx, 'matches': []}
        try:
            grok = Grok(pattern, patterns, deadline=deadline)
        except TimeoutError:
            pattern_result['matches'] = [skipped_match(*line) for line in sample_lines]
            results.append(pattern_result)
            continue
        except GrokError as e:
            pattern_result['warning'] = grok_pattern_warning(pattern)
            for line_idx, sample_line in sample_lines:
                pattern_result['matches'].append({
                    'line_number': line_idx,
                    'sample': sample_line,
                    'success': False,
                    'error': f'Pattern compilation error: {e}',
                })
            results.append(pattern_result)
            continue
        pattern_result['warning'] = grok_pattern_warning(pattern, grok)

        for line_idx, sample_line in sample_lines:
            match = {'line_number': line_idx, 'sample': sample_line, 'success': False}
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                pattern_result['matches'].append(skipped_match(line_idx, sample_line))
                continue
            try:
                fields = grok.match(sample_line, timeout=min(GROK_MATCH_TIMEOUT, remaining))
            except TimeoutError:
                match['error'] = (f'_groktimeout: matching took longer than {GROK_MATCH_TIMEOUT} seconds, so the debugger '
                                  'stopped it. Logstash waits timeout_millis (30 seconds by default) before tagging the '
                                  'event _groktimeout.')
            else:
                if fields is not None:
                    match.update(success=True, parsed_data=fields)
                else:
                    try:
                        reason = grok.explain_failure(sample_line, timeout=min(GROK_MATCH_TIMEOUT, remaining),
                                                      deadline=deadline)
                    except TimeoutError:
                        reason = None
                    match['error'] = f"_grokparsefailure: {reason or 'the pattern did not match the input'}"
            pattern_result['matches'].append(match)
        results.append(pattern_result)

    return HttpResponse(generate_results_html(results))

def DissectDebugger(request):
    """Render the dissect debugger page."""
    return render(request, 'dissect_debugger.html')

def parse_convert_datatype(text):
    """Parse ``convert_datatype`` lines into a dict.

    Args:
        text: One conversion per line, ``field => int`` or ``field float``.

    Returns:
        Dict mapping field name to datatype.

    Raises:
        DissectError: If a line is malformed or names a type other than int or float.

    Example:
        >>> parse_convert_datatype("bytes => int\\nduration float")
        {'bytes': 'int', 'duration': 'float'}
    """
    conversions = {}
    for line in text.splitlines():
        parts = line.replace('=>', ' ').split()
        if len(parts) == 2:
            field_name, datatype = parts[0].strip('"\''), parts[1].strip('"\'')
            if datatype.lower() not in ('int', 'float'):
                raise DissectError(f"Unsupported datatype '{datatype}' for '{field_name}' (use int or float)")
            conversions[field_name] = datatype
        elif parts:
            raise DissectError(f"Invalid line: {line.strip()}")
    return conversions

def simulate_dissect(request):
    """Run dissect patterns against sample lines and return an HTML fragment.

    POST fields: ``sample_data``, ``dissect_pattern`` (one pattern per line),
    ``convert_datatype``, ``multiline_mode``.

    Note:
        Response is HTML for htmx, not JSON.
    """
    if request.method != 'POST':
        return HttpResponse('<p class="text-error">Invalid request method</p>')

    sample_data, dissect_pattern, convert_datatype = (
        request.POST.get(name, '').replace('\r\n', '\n') for name in ('sample_data', 'dissect_pattern', 'convert_datatype')
    )
    multiline_mode = request.POST.get('multiline_mode', 'false').lower() == 'true'

    sample_lines = split_sample_lines(sample_data, multiline_mode)
    pattern_lines = [line for line in dissect_pattern.split('\n') if line.strip()]
    missing = missing_input_html(sample_lines, pattern_lines, 'dissect pattern')
    if missing:
        return HttpResponse(missing)
    try:
        conversions = parse_convert_datatype(convert_datatype)
    except DissectError as e:
        return HttpResponse(message_html(f'Options > convert_datatype: {e}', 'text-error'))

    deadline = time.monotonic() + REQUEST_TIMEOUT
    results = []
    for pattern_idx, pattern in enumerate(pattern_lines, 1):
        pattern_result = {'pattern': pattern, 'pattern_number': pattern_idx, 'matches': []}
        if looks_like_grok(pattern):
            pattern_result['warning'] = (
                'This looks like a grok pattern. Dissect matches literal text only, '
                'so grok pattern names and regex escapes are not supported.'
            )
        try:
            dissector = Dissector(pattern, conversions)
        except DissectError as e:
            for line_idx, sample_line in sample_lines:
                pattern_result['matches'].append({
                    'line_number': line_idx,
                    'sample': sample_line,
                    'success': False,
                    'error': f'Pattern compilation error: {e}',
                })
            results.append(pattern_result)
            continue

        for line_idx, sample_line in sample_lines:
            if time.monotonic() > deadline:
                pattern_result['matches'].append(skipped_match(line_idx, sample_line))
                continue
            match = {'line_number': line_idx, 'sample': sample_line}
            try:
                match.update(success=True, parsed_data=dissector.match(sample_line))
            except DissectFailure as e:
                match.update(success=False, error=f'_dissectfailure: {e}')
            pattern_result['matches'].append(match)
        results.append(pattern_result)

    return HttpResponse(generate_results_html(results))

def generate_results_html(results):
    """Render match/fail cards for each pattern and sample line.

    Args:
        results: List of pattern dicts with ``matches`` entries.

    Returns:
        HTML string.
    """
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
                <code class="text-sm font-mono text-base-content">{html.escape(pattern)}</code>
            </div>
        ''')
        if result.get('warning'):
            html_parts.append(
                f'<div class="alert alert-warning py-2 mb-4 text-sm">{html.escape(result["warning"])}</div>'
            )
        
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
                            <p class="text-xs text-base-content/70 mb-2 font-mono bg-base-200 p-2 rounded whitespace-pre-wrap break-all">{html.escape(sample)}</p>
                            <div class="bg-base-200 rounded p-2">
                                <p class="text-xs font-semibold mb-1">Extracted Fields:</p>
                                <pre class="text-xs font-mono overflow-auto">{html.escape(json.dumps(parsed_data, indent=2))}</pre>
                            </div>
                        </div>
                    </div>
                </div>
                ''')
            else:
                error = match['error']
                html_parts.append(f'''
                <div class="mb-3 p-3 bg-error/10 border border-error/30 rounded">
                    <div class="flex items-start gap-2">
                        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 text-error flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                        <div class="flex-1">
                            <p class="text-xs font-semibold text-error mb-1">Line {line_num} - No Match</p>
                            <p class="text-xs text-base-content/70 mb-2 font-mono bg-base-200 p-2 rounded whitespace-pre-wrap break-all">{html.escape(sample)}</p>
                            <p class="text-xs text-error/80"><strong>Reason:</strong> {html.escape(error)}</p>
                        </div>
                    </div>
                </div>
                ''')
        
        html_parts.append('</div>')
    
    return ''.join(html_parts)
