#!/usr/bin/env python3
#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""
Pre-commit hook to check dependency licenses.

This script checks both Python (pyproject.toml) and Node.js (package.json) dependencies
to ensure they are properly documented in NOTICE.txt.
"""

import json
import os
import re
import requests
import subprocess
import sys
import tomllib
from datetime import datetime
from pathlib import Path

# Optional GitHub authentication to avoid rate limits
# Set GITHUB_TOKEN environment variable with a personal access token
GITHUB_TOKEN = os.getenv('GITHUB_TOKEN')
GITHUB_HEADERS = {'Authorization': f'token {GITHUB_TOKEN}'} if GITHUB_TOKEN else {}

# Custom dependencies that are always checked (in addition to pyproject.toml and package.json)
# These packages will be treated as if they were in a dependency file
# Format: "package_name": "github_repo_path_or_url"
CUSTOM_DEPENDENCIES = {
    # Add custom dependencies here that should always be checked
    # Example: "my-custom-package": "owner/repo" or "https://github.com/owner/repo/blob/main/LICENSE"
    "d3": "https://github.com/d3/d3/blob/main/LICENSE",
    "codemirror": "https://github.com/codemirror/dev/blob/main/LICENSE",
    "js-yaml": "https://github.com/nodeca/js-yaml/blob/master/LICENSE"
}

# Repository mappings for dependencies (fallback when automatic lookup fails)
# Format: "package_name": "github_repo_path" (e.g., "owner/repo")
REPOSITORY_MAPPINGS = {
    # Add package repository mappings here
    # Example: "some-package": "owner/repo"
    'certifi': 'https://github.com/certifi/python-certifi/blob/master/LICENSE',
    'cryptography': 'https://github.com/pyca/cryptography/blob/main/LICENSE',
    'gunicorn': 'https://github.com/benoitc/gunicorn/blob/master/LICENSE',
    'packaging': 'https://github.com/pypa/packaging/blob/main/LICENSE.APACHE',
    'pyyaml': 'https://github.com/yaml/pyyaml/blob/main/LICENSE',
    'daisyui': 'https://github.com/saadeghi/daisyui/blob/master/LICENSE',
    'postcss-cli': 'https://github.com/postcss/postcss-cli/blob/master/LICENSE',
    'gevent': 'https://github.com/gevent/gevent/blob/master/LICENSE',
    "anyio": "https://github.com/agronholm/anyio/blob/master/LICENSE",
    "charset-normalizer": "https://github.com/jawah/charset_normalizer/blob/master/LICENSE",
    "urllib3": "https://github.com/urllib3/urllib3/blob/main/LICENSE.txt",
    "psutil": "https://github.com/giampaolo/psutil/blob/master/LICENSE",
    "pydantic": "https://github.com/pydantic/pydantic/blob/main/LICENSE",
    "pydantic-core": "https://github.com/pydantic/pydantic-core/blob/main/LICENSE",
    "requests": "https://github.com/psf/requests/blob/main/LICENSE",
    "starlette": "https://github.com/encode/starlette/blob/master/LICENSE.md",
    "typing-inspection": "https://github.com/ilevkivskyi/typing_inspect/blob/master/LICENSE",
    "uvicorn": "https://github.com/encode/uvicorn/blob/master/LICENSE.md",
    "cffi": """Copyright (C) 2005-2007, James Bielman  <jamesjb@jamesjb.com>

Permission is hereby granted, free of charge, to any person
obtaining a copy of this software and associated documentation
files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use, copy,
modify, merge, publish, distribute, sublicense, and/or sell copies
of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be
included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT.  IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.""",
    "greenlet": "https://github.com/python-greenlet/greenlet/blob/master/LICENSE",
    "portalocker": "https://github.com/wolph/portalocker/blob/develop/LICENSE",
    "zope-event": "https://github.com/zopefoundation/zope.event/blob/master/LICENSE.txt",
    "postcss": """The MIT License (MIT)

Copyright 2013 Andrey Sitnik <andrey@sitnik.es>

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE."""

}

# License validation patterns (ordered by specificity - more specific patterns first)
LICENSE_PATTERNS = [
    # Most specific/common patterns first
    "Apache-2.0 OR BSD-3-Clause",
    "Apache License 2.0",
    "Apache Software License",
    "Python Software Foundation License 2.0",
    "Python Software Foundation License",
    "BSD 3-Clause \"New\" or \"Revised\" License",
    "BSD 2-Clause \"Simplified\" License",
    "Creative Commons Zero v1.0 Universal",
    "Creative Commons Attribution 4.0 International",
    "Blue Oak Model License 1.0.0",
    "Boost Software License 1.0",
    "Zope Public License 2.1",
    "Eclipse Distribution License - v 1.0",
    "Historical Permission Notice and Disclaimer",
    "BSD Zero Clause License",
    "Artistic License 1.0",
    "zlib/libpng License",
    "Unicode License v3",
    "MIT No Attribution",
    "BSD-3-Clause",
    "BSD-2-Clause",
    "Apache-2.0",
    "Apache-1.1",
    "PSF-2.0",
    "Artistic-1.0",
    "PHP-3.0",
    "PHP-3.01",
    "BSL-1.0",
    "CC0-1.0",
    "CC-BY-4.0",
    "ZPL-2.1",
    "BlueOak-1.0.0",
    "Unicode-3.0",
    "MIT License",
    "BSD License",
    "Apache License",
    "ISC License",
    "OpenSSL License",
    "Boost Software License",
    "Eclipse Distribution License",
    "Bouncy Castle License",
    "CMU License",
    "PHP License",
    "zlib License",
    "The Unlicense",
    "BSD 3-Clause",
    "BSD 2-Clause",
    "zlib-acknowledgement",
    # Generic/short patterns last (prone to false positives)
    "Public Domain",
    "MIT-CMU",
    "Unlicense",
    "OpenSSL",
    "WTFPL",
    "HPND",
    "Zlib",
    "MIT",
    "BSD",
    "ISC",
    "0BSD",
    "ICU License",
    "ICU",
]

# Additional license patterns
LICENSE_PATTERNS_CONT = {
    "Elastic License",
    "Elastic-2.0",
    "ELv2",
    "Server Side Public License",
    "SSPL",
    "GNU General Public License",
    "GPL-2.0",
    "GPL-2.0-only",
    "GPL-2.0-or-later",
    "GPL-3.0",
    "GPL-3.0-only",
    "GPL-3.0-or-later",
    "GNU Lesser General Public License",
    "LGPL-2.1",
    "LGPL-2.1-only",
    "LGPL-2.1-or-later",
    "LGPL-3.0",
    "LGPL-3.0-only",
    "LGPL-3.0-or-later",
    "GNU Free Documentation License",
    "GFDL-1.3",
    "GFDL-1.3-only",
    "Mozilla Public License",
    "MPL-1.1",
    "MPL-2.0",
    "MPL/2.0",
    "Mozilla Public License 2.0",
    "Mozilla Public License 2.0 (MPL 2.0)",
    "Microsoft Reciprocal License",
    "MS-RL",
    "Common Development and Distribution License",
    "CDDL-1.0",
    "CDDL-1.1",
    "Nuclide License",
    "Eclipse Public License",
    "EPL-1.0",
    "EPL-2.0",
    "Common Public License",
    "CPL-1.0",
    "Intel Simplified Software License",
    "ISSL",
    "Apple Public Source License",
    "APSL-2.0",
    "Apache-1.0",
    "Apache License 1.0",
    "Microsoft .NET Library License",
    "Artistic-2.0",
    "Artistic License 2.0",
    "Sleepycat License",
    "Sleepycat",
    "Creative Commons Share Alike",
    "CC-BY-SA-4.0",
    "Detection Rule License",
    "DRL-1.0",
}


def get_project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent


def fetch_license_from_pypi(package_name):
    """Fetch license information from PyPI."""
    api_url = f"https://pypi.org/pypi/{package_name}/json"
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            info = data.get('info', {})
            
            # Get repository URL from project URLs
            project_urls = info.get('project_urls', {})
            repo_url = project_urls.get('Source') or project_urls.get('Repository') or project_urls.get('Homepage')
            
            if repo_url and 'github.com' in repo_url:
                # Extract owner/repo from GitHub URL
                match = re.search(r'github\.com/([^/]+/[^/]+)', repo_url)
                if match:
                    return match.group(1).rstrip('.git')
        
        return None
        
    except Exception as e:
        print(f"Error fetching PyPI metadata for {package_name}: {e}")
        return None


def fetch_license_from_npm(package_name):
    """Fetch license information from npm registry."""
    api_url = f"https://registry.npmjs.org/{package_name}"
    
    try:
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            
            # Get repository URL from latest version
            repository = data.get('repository', {})
            if isinstance(repository, dict):
                repo_url = repository.get('url', '')
            else:
                repo_url = repository
            
            if repo_url and 'github.com' in repo_url:
                # Extract owner/repo from GitHub URL
                match = re.search(r'github\.com/([^/]+/[^/]+)', repo_url)
                if match:
                    return match.group(1).rstrip('.git')
        
        return None
        
    except Exception as e:
        print(f"Error fetching npm metadata for {package_name}: {e}")
        return None


def detect_license_from_text(license_text):
    """Detect license type from license text content.
    
    Args:
        license_text: The full text of the license
        
    Returns:
        str: Detected license name or "Unknown"
    """
    # Check LICENSE_PATTERNS first (most permissive), then LICENSE_PATTERNS_CONT
    for pattern in LICENSE_PATTERNS:
        if pattern.lower() in license_text.lower():
            return pattern
    
    # If not found in LICENSE_PATTERNS, check LICENSE_PATTERNS_CONT
    for pattern in LICENSE_PATTERNS_CONT:
        if pattern.lower() in license_text.lower():
            return pattern
    
    return "Unknown"


def fetch_license_from_url(license_url, dep_name):
    """Fetch license text directly from a URL."""
    try:
        # Convert GitHub blob URLs to raw URLs
        if 'github.com' in license_url and '/blob/' in license_url:
            license_url = license_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        
        response = requests.get(license_url, timeout=10)
        
        if response.status_code == 200:
            license_text = response.text
            license_name = detect_license_from_text(license_text)
            
            return {
                'text': license_text,
                'name': license_name,
                'url': license_url
            }
        
        print(f"Warning: Could not fetch license from {license_url}")
        return None
        
    except Exception as e:
        print(f"Error fetching license from URL for {dep_name}: {e}")
        return None


def fetch_license_from_github(repo_path, dep_name):
    """Fetch license text and metadata from GitHub repository."""
    api_url = f"https://api.github.com/repos/{repo_path}/license"
    
    try:
        response = requests.get(api_url, headers=GITHUB_HEADERS, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            github_license_name = data.get('license', {}).get('name', '')
            license_url = data.get('download_url')
            
            if license_url:
                license_response = requests.get(license_url, headers=GITHUB_HEADERS, timeout=10)
                if license_response.status_code == 200:
                    license_text = license_response.text
                    
                    # Don't trust GitHub's license detection - parse the text ourselves
                    detected_license = detect_license_from_text(license_text)
                    
                    # If we couldn't detect it, fall back to GitHub's name
                    if detected_license == "Unknown" and github_license_name:
                        detected_license = github_license_name
                    
                    return {
                        'text': license_text,
                        'name': detected_license,
                        'url': license_url
                    }
                else:
                    print(f"Warning: Could not download license file for {dep_name} - HTTP {license_response.status_code}")
                    return None
            else:
                print(f"Warning: No license download URL found for {dep_name}")
                return None
        elif response.status_code == 403:
            # Check if it's a rate limit issue
            if 'X-RateLimit-Remaining' in response.headers and response.headers['X-RateLimit-Remaining'] == '0':
                reset_time = response.headers.get('X-RateLimit-Reset', 'unknown')
                print(f"ERROR: GitHub API rate limit exceeded for {dep_name}")
                print(f"       Rate limit resets at: {reset_time}")
            else:
                print(f"Warning: Access forbidden for {dep_name} ({repo_path}) - HTTP 403")
            return None
        elif response.status_code == 404:
            print(f"Warning: Repository or license not found for {dep_name} ({repo_path}) - HTTP 404")
            print(f"       Repository may not exist or may not have a license file")
            return None
        else:
            print(f"Warning: Could not fetch license for {dep_name} ({repo_path}) - HTTP {response.status_code}")
            return None
        
    except requests.exceptions.Timeout:
        print(f"Error: Request timeout while fetching license for {dep_name}")
        return None
    except requests.exceptions.ConnectionError:
        print(f"Error: Connection error while fetching license for {dep_name}")
        return None
    except Exception as e:
        print(f"Error fetching license for {dep_name}: {type(e).__name__}: {e}")
        return None


def validate_license(license_name):
    """Validate if a license matches known patterns.
    
    Returns:
        tuple: (is_valid, warning_message)
            - is_valid: True if license is in either list
            - warning_message: None if in LICENSE_PATTERNS, info string if in LICENSE_PATTERNS_CONT
    """
    if not license_name:
        return False, None
    
    license_name = license_name.strip()
    
    # Check LICENSE_PATTERNS - direct match
    if license_name in LICENSE_PATTERNS:
        return True, None
    
    # Check LICENSE_PATTERNS - partial match
    for pattern in LICENSE_PATTERNS:
        if pattern.lower() in license_name.lower() or license_name.lower() in pattern.lower():
            return True, None
    
    # Check LICENSE_PATTERNS_CONT - direct match
    if license_name in LICENSE_PATTERNS_CONT:
        warning = f"[INFO] '{license_name}' found in LICENSE_PATTERNS_CONT"
        return True, warning
    
    # Check LICENSE_PATTERNS_CONT - partial match
    for pattern in LICENSE_PATTERNS_CONT:
        if pattern.lower() in license_name.lower() or license_name.lower() in pattern.lower():
            warning = f"[INFO] '{license_name}' (matched '{pattern}') found in LICENSE_PATTERNS_CONT"
            return True, warning
    
    return False, None


def get_notice_header():
    """Generate the required NOTICE.txt header."""
    current_year = datetime.now().year
    return f"""LogstashUI
Copyright 2025-{current_year} Elasticsearch B.V.
"""


def ensure_notice_header():
    """Ensure NOTICE.txt has the required header at the top."""
    notice_path = get_project_root() / "NOTICE.txt"
    header = get_notice_header()
    
    if notice_path.exists():
        content = notice_path.read_text(encoding="utf-8")
        
        # Check if header is already present
        if not content.startswith("LogstashUI\nCopyright 2025-"):
            # Header missing or outdated, prepend it
            with open(notice_path, "w", encoding="utf-8") as f:
                f.write(header)
                if content and not content.startswith("\n"):
                    f.write("\n")
                f.write(content)
            print("Added/updated NOTICE.txt header")
        else:
            # Update year if needed
            current_year = datetime.now().year
            year_pattern = r"Copyright 2025-(\d{4})"
            match = re.search(year_pattern, content)
            if match and int(match.group(1)) < current_year:
                updated_content = re.sub(
                    year_pattern,
                    f"Copyright 2025-{current_year}",
                    content,
                    count=1
                )
                with open(notice_path, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                print(f"Updated copyright year to {current_year}")
    else:
        # Create new file with header
        with open(notice_path, "w", encoding="utf-8") as f:
            f.write(header)
        print("Created NOTICE.txt with header")


def read_notice_file():
    """Read the NOTICE.txt file and return its contents."""
    notice_path = get_project_root() / "NOTICE.txt"
    if notice_path.exists():
        return notice_path.read_text(encoding="utf-8")
    return ""


def is_package_in_notice(package_name, notice_content):
    """Check if a package is already mentioned in NOTICE.txt."""
    # Look for package name in section headers like "-------------- package-name --------------"
    pattern = rf"-+\s*{re.escape(package_name)}\s*-+"
    return bool(re.search(pattern, notice_content, re.IGNORECASE))


def append_to_notice(package_name, license_text, license_name=None):
    """Append a package's license to NOTICE.txt and update metadata."""
    notice_path = get_project_root() / "NOTICE.txt"
    metadata_path = get_project_root() / "scripts" / ".license_metadata.json"
    
    entry = f"\n-------------- {package_name} -------------- \n"
    entry += license_text
    entry += "\n"

    with open(notice_path, "a", encoding="utf-8") as f:
        f.write(entry)

    # Update metadata file
    metadata = {}
    if metadata_path.exists():
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
    
    metadata[package_name] = license_name or 'UNKNOWN'
    
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, sort_keys=True)

    print(f"Added {package_name} to NOTICE.txt")


def get_production_dependency_tree():
    """Get the set of all production dependencies and their transitive dependencies."""
    pyproject_path = get_project_root() / "pyproject.toml"
    lock_path = get_project_root() / "uv.lock"
    
    if not pyproject_path.exists() or not lock_path.exists():
        return set()
    
    try:
        # Get direct production dependencies from pyproject.toml
        with open(pyproject_path, "rb") as f:
            pyproject = tomllib.load(f)
        
        prod_dependencies = pyproject.get("project", {}).get("dependencies", [])
        prod_deps = set()
        for dep in prod_dependencies:
            # Extract package name (remove version specifiers)
            package_name = re.split(r"[><=!]", dep)[0].strip().lower()
            prod_deps.add(package_name)
        
        print(f"DEBUG: Found {len(prod_deps)} direct production dependencies: {sorted(prod_deps)}")
        
        # Get lock file to find transitive dependencies
        with open(lock_path, "rb") as f:
            lock_data = tomllib.load(f)
        
        packages = lock_data.get("package", [])
        
        # Build dependency graph
        dep_graph = {}
        for pkg in packages:
            name = pkg.get('name', '').lower()
            deps = pkg.get('dependencies', [])
            dep_names = [d.get('name', '').lower() for d in deps if isinstance(d, dict) and 'name' in d]
            dep_graph[name] = dep_names
        
        # Find all transitive production dependencies using BFS
        all_prod_deps = set(prod_deps)
        to_process = list(prod_deps)
        
        while to_process:
            current = to_process.pop(0)
            if current in dep_graph:
                for dep in dep_graph[current]:
                    if dep not in all_prod_deps:
                        all_prod_deps.add(dep)
                        to_process.append(dep)
        
        print(f"DEBUG: Total production dependencies (including transitive): {len(all_prod_deps)}")
        return all_prod_deps
        
    except Exception as e:
        print(f"Warning: Could not determine production dependencies: {e}")
        return set()


def get_python_dependencies():
    """Get all Python dependencies from uv.lock (only production dependencies and their transitive deps)."""
    lock_path = get_project_root() / "uv.lock"
    
    if not lock_path.exists():
        print("uv.lock not found, falling back to pyproject.toml")
        return get_python_dependencies_from_pyproject()
    
    try:
        # Get production dependency tree to include
        prod_deps = get_production_dependency_tree()
        
        with open(lock_path, "rb") as f:
            lock_data = tomllib.load(f)
        
        packages = lock_data.get("package", [])
        package_names = []
        total_in_lock = 0
        
        for pkg in packages:
            name = pkg.get('name', '')
            if name:
                total_in_lock += 1
                name_lower = name.lower()
                # Only include production dependencies (not dev)
                if name_lower in prod_deps:
                    package_names.append((name, 'python'))
        
        excluded = total_in_lock - len(package_names)
        print(f"Found {len(package_names)} production Python packages in uv.lock (excluded {excluded} dev dependencies)")
        return package_names
        
    except Exception as e:
        print(f"Error parsing uv.lock: {e}")
        print("Falling back to pyproject.toml")
        return get_python_dependencies_from_pyproject()


def get_python_dependencies_from_pyproject():
    """Get Python dependencies from pyproject.toml (top-level only - fallback)."""
    pyproject_path = get_project_root() / "pyproject.toml"

    if not pyproject_path.exists():
        print("pyproject.toml not found")
        return []

    with open(pyproject_path, "rb") as f:
        pyproject = tomllib.load(f)

    dependencies = pyproject.get("project", {}).get("dependencies", [])

    # Extract package names (remove version specifiers)
    package_names = []
    for dep in dependencies:
        package_name = re.split(r"[><=!]", dep)[0].strip()
        package_names.append((package_name, 'python'))

    return package_names


def get_nodejs_dependencies():
    """Get Node.js dependencies from package.json."""
    package_json_path = get_project_root() / "src" / "logstashui" / "theme" / "static_src" / "package.json"

    if not package_json_path.exists():
        print(f"package.json not found at: {package_json_path}")
        print(f"Project root: {get_project_root()}")
        return []

    with open(package_json_path, "r", encoding="utf-8") as f:
        package_data = json.load(f)

    # Get both dependencies and devDependencies
    dependencies = {}
    dependencies.update(package_data.get("dependencies", {}))
    dependencies.update(package_data.get("devDependencies", {}))

    return [(name, 'nodejs') for name in dependencies.keys()]


def get_license_metadata():
    """Load license metadata from .license_metadata.json.
    
    Returns:
        dict: Mapping of package_name to license_name
    """
    metadata_path = get_project_root() / "scripts" / ".license_metadata.json"
    
    if not metadata_path.exists():
        return {}
    
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: Could not load license metadata: {e}")
        return {}


def get_license_list_classification(license_name):
    """Determine which list a license belongs to.
    
    Returns:
        str: 'LICENSE_PATTERNS', 'LICENSE_PATTERNS_CONT', or 'NEITHER'
    """
    is_valid, warning = validate_license(license_name)
    
    if not is_valid:
        return 'NEITHER'
    
    # If there's a warning, it's in LICENSE_PATTERNS_CONT
    if warning:
        return 'LICENSE_PATTERNS_CONT'
    
    return 'LICENSE_PATTERNS'


def generate_dependency_tracking(all_deps, license_cache):
    """Generate .dependency_tracking.txt file with license classification.
    
    Args:
        all_deps: List of (dep_name, dep_type) tuples
        license_cache: Dict mapping dep_name to license_name
    """
    tracking_path = get_project_root() / "scripts" / ".dependency_tracking.txt"
    
    # Prepare data for table
    rows = []
    for dep_name, dep_type in sorted(all_deps, key=lambda x: x[0].lower()):
        license_name = license_cache.get(dep_name, 'UNKNOWN')
        classification = get_license_list_classification(license_name)
        rows.append((dep_name, dep_type, license_name, classification))
    
    # Calculate column widths
    max_name_len = max(len(row[0]) for row in rows) if rows else 20
    max_type_len = max(len(row[1]) for row in rows) if rows else 10
    max_license_len = max(len(row[2]) for row in rows) if rows else 30
    max_class_len = max(len(row[3]) for row in rows) if rows else 25
    
    # Ensure minimum widths
    name_width = max(max_name_len, len('Dependency'))
    type_width = max(max_type_len, len('Type'))
    license_width = max(max_license_len, len('License'))
    class_width = max(max_class_len, len('Classification'))
    
    # Generate table
    with open(tracking_path, 'w', encoding='utf-8') as f:
        # Header
        f.write(f"{'Dependency':<{name_width}} | {'Type':<{type_width}} | {'License':<{license_width}} | {'Classification':<{class_width}}\n")
        f.write(f"{'-' * name_width}-+-{'-' * type_width}-+-{'-' * license_width}-+-{'-' * class_width}\n")
        
        # Rows
        for dep_name, dep_type, license_name, classification in rows:
            f.write(f"{dep_name:<{name_width}} | {dep_type:<{type_width}} | {license_name:<{license_width}} | {classification:<{class_width}}\n")
    
    print(f"\nGenerated dependency tracking file: {tracking_path}")


def resolve_license_source(dep_name, mapping_value, source_type="mapping"):
    """Resolve license source from a mapping value (URL, inline text, or repo path).
    
    Args:
        dep_name: Name of the dependency
        mapping_value: Value from CUSTOM_DEPENDENCIES or REPOSITORY_MAPPINGS
        source_type: Description of source for logging ("custom" or "mapping")
        
    Returns:
        dict: License data with 'text', 'name', and 'url' keys, or None if fetch failed
    """
    # If it's a direct URL, fetch from that URL
    if mapping_value.startswith('https://'):
        print(f"Fetching license for {dep_name} ({source_type}) from direct URL...")
        return fetch_license_from_url(mapping_value, dep_name)
    
    # If it contains newlines, treat it as inline license text
    if '\n' in mapping_value:
        print(f"Using inline license text for {dep_name} ({source_type})...")
        detected_license = detect_license_from_text(mapping_value)
        return {
            'text': mapping_value,
            'name': detected_license,
            'url': 'inline'
        }
    
    # It's a repo path, use GitHub API
    print(f"Fetching license for {dep_name} ({source_type}) from {mapping_value}...")
    return fetch_license_from_github(mapping_value, dep_name)


def fetch_license_for_dependency(dep_name, dep_type):
    """Fetch license data for a single dependency.
    
    Args:
        dep_name: Name of the dependency
        dep_type: Type of dependency ('python', 'nodejs', or 'custom')
        
    Returns:
        dict: License data or None if fetch failed
    """
    # Check CUSTOM_DEPENDENCIES first (for custom dependencies)
    if dep_type == 'custom' and dep_name in CUSTOM_DEPENDENCIES:
        return resolve_license_source(dep_name, CUSTOM_DEPENDENCIES[dep_name], "custom")
    
    # Check REPOSITORY_MAPPINGS for manual overrides
    if dep_name in REPOSITORY_MAPPINGS:
        return resolve_license_source(dep_name, REPOSITORY_MAPPINGS[dep_name], "mapping")
    
    # Try to fetch repository URL from package registry
    print(f"Looking up {dep_name}...")
    repo_path = None
    
    if dep_type == 'python':
        repo_path = fetch_license_from_pypi(dep_name)
    elif dep_type == 'nodejs':
        repo_path = fetch_license_from_npm(dep_name)
    
    if repo_path:
        print(f"Fetching license for {dep_name} from {repo_path}...")
        return fetch_license_from_github(repo_path, dep_name)
    
    return None


def collect_all_dependencies():
    """Collect all dependencies from Python, Node.js, and custom sources.
    
    Returns:
        list: List of (dep_name, dep_type) tuples
    """
    print("\nCollecting dependencies...")
    python_deps = get_python_dependencies()
    nodejs_deps = get_nodejs_dependencies()
    custom_deps = [(name, 'custom') for name in CUSTOM_DEPENDENCIES.keys()]
    
    all_deps = python_deps + nodejs_deps + custom_deps
    print(f"Found {len(all_deps)} total dependencies ({len(custom_deps)} custom)")
    
    return all_deps


def identify_missing_dependencies(all_deps):
    """Identify which dependencies are missing from NOTICE.txt.
    
    Args:
        all_deps: List of (dep_name, dep_type) tuples
        
    Returns:
        list: List of (dep_name, dep_type) tuples for missing dependencies
    """
    notice_content = read_notice_file()
    missing_deps = []
    
    for dep_name, dep_type in all_deps:
        if not is_package_in_notice(dep_name, notice_content):
            missing_deps.append((dep_name, dep_type))
    
    return missing_deps


def process_missing_licenses(missing_deps, license_cache):
    """Fetch and add licenses for missing dependencies.
    
    Args:
        missing_deps: List of (dep_name, dep_type) tuples
        license_cache: Dict to populate with license names
        
    Returns:
        list: List of error messages (empty if all succeeded)
    """
    print(f"\nFound {len(missing_deps)} dependencies missing from NOTICE.txt")
    print("Fetching licenses...\n")
    
    errors = []
    
    for dep_name, dep_type in missing_deps:
        license_data = fetch_license_for_dependency(dep_name, dep_type)
        
        if not license_data:
            if dep_name not in REPOSITORY_MAPPINGS and dep_type != 'custom':
                errors.append(f"No repository found for {dep_name}")
            else:
                errors.append(f"Could not fetch license for {dep_name}")
            continue
        
        # Validate the license
        is_valid, warning = validate_license(license_data['name'])
        if not is_valid:
            errors.append(f"License '{license_data['name']}' for {dep_name} is not in LICENSE_PATTERNS or LICENSE_PATTERNS_CONT")
            continue
        
        # Cache license name for tracking
        license_cache[dep_name] = license_data['name']
        
        # Show info if in LICENSE_PATTERNS_CONT
        if warning:
            print(warning)
        
        # Add to NOTICE.txt with license name
        append_to_notice(dep_name, license_data['text'], license_data['name'])
    
    return errors


def main():
    """Main entry point for the license checker."""
    print("Checking dependency licenses...")
    
    # Show authentication status
    if GITHUB_TOKEN:
        print("[INFO] Using GitHub authentication (GITHUB_TOKEN found)")
    else:
        print("[INFO] No GitHub authentication (set GITHUB_TOKEN to avoid rate limits)")
    
    # Ensure NOTICE.txt has the required header
    ensure_notice_header()

    # Collect all dependencies
    all_deps = collect_all_dependencies()

    # Cache for license names (to generate tracking file)
    license_cache = {}

    # Load license metadata for tracking
    license_metadata = get_license_metadata()
    for dep_name, dep_type in all_deps:
        if dep_name in license_metadata:
            license_cache[dep_name] = license_metadata[dep_name]
    
    # Check if all dependencies are in NOTICE.txt
    missing_deps = identify_missing_dependencies(all_deps)
    
    # If all dependencies are in NOTICE.txt, generate tracking and exit
    if not missing_deps:
        print("\n[OK] All dependencies are documented in NOTICE.txt")
        generate_dependency_tracking(all_deps, license_cache)
        return 0
    
    # Fetch and process missing licenses
    errors = process_missing_licenses(missing_deps, license_cache)
    
    # Report errors
    if errors:
        print("\n[ERROR] License check failed with the following errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease add missing repository mappings to REPOSITORY_MAPPINGS in scripts/generate_notice.py")
        return 1

    print("\n[OK] All dependency licenses checked and updated successfully!")
    
    # Generate dependency tracking file
    generate_dependency_tracking(all_deps, license_cache)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
