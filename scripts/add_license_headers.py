#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import os
import sys
import argparse
from pathlib import Path

ELASTIC_LICENSE_TEXT = """Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
or more contributor license agreements. Licensed under the Elastic License;
you may not use this file except in compliance with the Elastic License."""

PYTHON_HEADER = '#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one\n#or more contributor license agreements. Licensed under the Elastic License;\n#you may not use this file except in compliance with the Elastic License.\n\n'

JS_HEADER = f"""/*
 * {ELASTIC_LICENSE_TEXT.replace(chr(10), chr(10) + ' * ')}
 */

"""

HTML_HEADER = f"""<!--
 * {ELASTIC_LICENSE_TEXT.replace(chr(10), chr(10) + ' * ')}
-->

"""

EXCLUDED_DIRS = {
    'node_modules',
    'venv',
    'env',
    '.venv',
    '.git',
    '__pycache__',
    'build',
    'dist',
    '.idea',
    'migrations',
    'staticfiles',
    'i18n'
}

EXCLUDED_FILES = {
    '__init__.py',
    'asgi.py',
    'wsgi.py',
    'manage.py',
    'settings.py',
    'apps.py',
    'postcss.config.js',
    'tailwind.config.js',
}

EXCLUDED_PATTERNS = [
    'codemirror.',
    'monokai.',
    'show-hint.',
    'd3.',
]


def should_exclude_file(file_path):
    """Check if file should be excluded based on patterns."""
    filename = os.path.basename(file_path)
    
    if filename in EXCLUDED_FILES:
        return True
    
    for pattern in EXCLUDED_PATTERNS:
        if pattern in filename:
            return True
    
    return False


def should_exclude_dir(dir_name):
    """Check if directory should be excluded."""
    return dir_name in EXCLUDED_DIRS


def has_license_header(content):
    """Check if file already has the Elastic license header."""
    return 'Elasticsearch B.V.' in content[:500] or 'Elastic License' in content[:500]


def get_header_for_file(file_ext):
    """Get the appropriate license header for file type."""
    if file_ext == '.py':
        return PYTHON_HEADER
    elif file_ext == '.js':
        return JS_HEADER
    elif file_ext == '.html':
        return HTML_HEADER
    return None


def add_header_to_python(content, header):
    """Add header to Python file, preserving shebang and encoding declarations."""
    lines = content.split('\n')
    insert_index = 0
    
    # Preserve shebang
    if lines and lines[0].startswith('#!'):
        insert_index = 1
    
    # Preserve encoding declarations
    while insert_index < len(lines) and insert_index < 3:
        line = lines[insert_index].strip()
        if line.startswith('#') and ('coding' in line or 'encoding' in line):
            insert_index += 1
        else:
            break
    
    # Insert header
    if insert_index > 0:
        return '\n'.join(lines[:insert_index]) + '\n' + header + '\n'.join(lines[insert_index:])
    else:
        return header + content


def add_header_to_html(content, header):
    """Add header to HTML file, before DOCTYPE if present."""
    return header + content


def add_header_to_js(content, header):
    """Add header to JavaScript file."""
    return header + content


def process_file(file_path, dry_run=False, verbose=False):
    """Process a single file to add license header."""
    file_ext = os.path.splitext(file_path)[1]
    
    if file_ext not in ['.py', '.js', '.html']:
        return False
    
    if should_exclude_file(file_path):
        if verbose:
            print(f"[SKIP] Excluded file: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        if verbose:
            print(f"[ERROR] Could not read file (encoding issue): {file_path}")
        return False
    except Exception as e:
        if verbose:
            print(f"[ERROR] Could not read file: {file_path} - {e}")
        return False
    
    if has_license_header(content):
        if verbose:
            print(f"[SKIP] Already has header: {file_path}")
        return False
    
    header = get_header_for_file(file_ext)
    if not header:
        return False
    
    if file_ext == '.py':
        new_content = add_header_to_python(content, header)
    elif file_ext == '.html':
        new_content = add_header_to_html(content, header)
    elif file_ext == '.js':
        new_content = add_header_to_js(content, header)
    else:
        return False
    
    if dry_run:
        print(f"[DRY-RUN] Would modify: {file_path}")
        return True
    else:
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(new_content)
            if verbose:
                print(f"[MODIFIED] {file_path}")
            return True
        except Exception as e:
            print(f"[ERROR] Could not write file: {file_path} - {e}")
            return False


def crawl_directory(root_dir, dry_run=False, verbose=False):
    """Crawl directory and process all eligible files."""
    modified_count = 0
    
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Remove excluded directories from search
        dirnames[:] = [d for d in dirnames if not should_exclude_dir(d)]
        
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if process_file(file_path, dry_run, verbose):
                modified_count += 1
    
    return modified_count


def main():
    parser = argparse.ArgumentParser(
        description='Add Elastic license headers to source code files.'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview which files would be modified without making changes'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Print detailed information about each file processed'
    )
    parser.add_argument(
        '--root',
        type=str,
        default=None,
        help='Root directory to crawl (defaults to logstashui directory)'
    )
    
    args = parser.parse_args()
    
    # Determine root directory
    if args.root:
        root_dir = args.root
    else:
        # Assume script is in scripts/ subdirectory
        script_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.join(script_dir, '..', 'logstashagent')
    
    root_dir = os.path.abspath(root_dir)
    
    if not os.path.isdir(root_dir):
        print(f"Error: Directory does not exist: {root_dir}")
        sys.exit(1)
    
    print(f"Scanning directory: {root_dir}")
    if args.dry_run:
        print("DRY-RUN MODE: No files will be modified\n")
    
    modified_count = crawl_directory(root_dir, args.dry_run, args.verbose)
    
    print(f"\n{'Would modify' if args.dry_run else 'Modified'} {modified_count} file(s)")


if __name__ == '__main__':
    main()
