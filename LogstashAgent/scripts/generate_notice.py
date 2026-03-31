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
import re
import requests
import subprocess
import sys
import tomllib
from pathlib import Path

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
    'cryptography': 'https://github.com/pyca/cryptography/blob/main/LICENSE.APACHE',
    'gunicorn': 'https://github.com/benoitc/gunicorn/blob/master/LICENSE',
    'packaging': 'https://github.com/pypa/packaging/blob/main/LICENSE.APACHE',
    'pyyaml': 'https://github.com/yaml/pyyaml/blob/main/LICENSE',
    'daisyui': 'https://github.com/saadeghi/daisyui/blob/master/LICENSE',
    'postcss-cli': 'https://github.com/postcss/postcss-cli/blob/master/LICENSE',
}

# License validation patterns
LICENSE_PATTERNS = {
    "Public Domain",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "BSD",
    "BSD License",
    "BSD 2-Clause",
    "BSD 3-Clause",
    "Eclipse Distribution License - v 1.0",
    "Eclipse Distribution License",
    "MIT",
    "MIT License",
    "Bouncy Castle License",
    "CMU License",
    "MIT-CMU",
    "curl",
    "curl License",
    "Apache-1.1",
    "Apache-2.0",
    "Apache License 2.0",
    "Apache Software License",
    "Apache License",
    "Artistic-1.0",
    "Artistic License 1.0",
    "PHP-3.0",
    "PHP-3.01",
    "PHP License",
    "PSF-2.0",
    "Python Software Foundation License",
    "Python Software Foundation License 2.0",
    "Zlib",
    "zlib License",
    "zlib-acknowledgement",
    "zlib/libpng License",
    "BSL-1.0",
    "Boost Software License",
    "Boost Software License 1.0",
    "OpenSSL",
    "OpenSSL License",
    "WTFPL",
    "CC0-1.0",
    "CC-BY-4.0",
    "Creative Commons Zero v1.0 Universal",
    "Creative Commons Attribution 4.0 International",
    "Unlicense",
    "The Unlicense",
    "ISC",
    "ISC License",
    "ICU",
    "ICU License",
    "0BSD",
    "BSD Zero Clause License",
    "HPND",
    "Historical Permission Notice and Disclaimer",
    "BlueOak-1.0.0",
    "Blue Oak Model License 1.0.0",
    "ZPL-2.1",
    "Zope Public License 2.1",
    "Unicode-3.0",
    "Unicode License v3",
    "MPL-2.0",
    "Mozilla Public License 2.0",
    "Mozilla Public License 2.0 (MPL 2.0)",
    "MIT No Attribution",
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


def fetch_license_from_url(license_url, dep_name):
    """Fetch license text directly from a URL."""
    try:
        # Convert GitHub blob URLs to raw URLs
        if 'github.com' in license_url and '/blob/' in license_url:
            license_url = license_url.replace('github.com', 'raw.githubusercontent.com').replace('/blob/', '/')
        
        response = requests.get(license_url, timeout=10)
        
        if response.status_code == 200:
            # Extract license name from content if possible
            license_text = response.text
            license_name = "Unknown"
            
            # Try to detect license type from content
            for pattern in LICENSE_PATTERNS:
                if pattern.lower() in license_text.lower():
                    license_name = pattern
                    break
            
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
        response = requests.get(api_url, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            license_name = data.get('license', {}).get('name', '')
            license_url = data.get('download_url')
            
            if license_url:
                license_response = requests.get(license_url, timeout=10)
                if license_response.status_code == 200:
                    return {
                        'text': license_response.text,
                        'name': license_name,
                        'url': license_url
                    }
        
        print(f"Warning: Could not fetch license for {dep_name} ({repo_path})")
        return None
        
    except Exception as e:
        print(f"Error fetching license for {dep_name}: {e}")
        return None


def validate_license(license_name):
    """Validate if a license matches known patterns."""
    if not license_name:
        return False
    
    license_name = license_name.strip()
    
    # Direct match
    if license_name in LICENSE_PATTERNS:
        return True
    
    # Partial match for common variations
    for pattern in LICENSE_PATTERNS:
        if pattern.lower() in license_name.lower() or license_name.lower() in pattern.lower():
            return True
    
    return False


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


def append_to_notice(package_name, license_text):
    """Append a package entry with license text to NOTICE.txt."""
    notice_path = get_project_root() / "NOTICE.txt"

    entry = f"\n-------------- {package_name} -------------- \n"
    entry += license_text
    entry += "\n"

    with open(notice_path, "a", encoding="utf-8") as f:
        f.write(entry)

    print(f"Added {package_name} to NOTICE.txt")




def get_python_dependencies():
    """Get Python dependencies from pyproject.toml."""
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
        print("package.json not found")
        return []

    with open(package_json_path, "r", encoding="utf-8") as f:
        package_data = json.load(f)

    # Get both dependencies and devDependencies
    dependencies = {}
    dependencies.update(package_data.get("dependencies", {}))
    dependencies.update(package_data.get("devDependencies", {}))

    return [(name, 'nodejs') for name in dependencies.keys()]


def main():
    """Main entry point for the license checker."""
    print("Checking dependency licenses...")

    # Collect all dependencies
    print("\nCollecting dependencies...")
    python_deps = get_python_dependencies()
    nodejs_deps = get_nodejs_dependencies()
    
    # Add custom dependencies (treat them as 'custom' type)
    custom_deps = [(name, 'custom') for name in CUSTOM_DEPENDENCIES.keys()]
    
    all_deps = python_deps + nodejs_deps + custom_deps

    print(f"Found {len(all_deps)} total dependencies ({len(custom_deps)} custom)")

    # First, check if all dependencies are in NOTICE.txt
    notice_content = read_notice_file()
    missing_deps = []
    
    for dep_name, dep_type in all_deps:
        if not is_package_in_notice(dep_name, notice_content):
            missing_deps.append((dep_name, dep_type))
    
    # If all dependencies are in NOTICE.txt, we're done
    if not missing_deps:
        print("\n[OK] All dependencies are documented in NOTICE.txt")
        return 0
    
    print(f"\nFound {len(missing_deps)} dependencies missing from NOTICE.txt")
    print("Fetching licenses...\n")
    
    # Fetch licenses for missing dependencies
    errors = []
    for dep_name, dep_type in missing_deps:
        license_data = None
        
        # Check CUSTOM_DEPENDENCIES first (for custom dependencies)
        if dep_type == 'custom' and dep_name in CUSTOM_DEPENDENCIES:
            mapping_value = CUSTOM_DEPENDENCIES[dep_name]
            
            # If it's a direct URL, fetch from that URL
            if mapping_value.startswith('https://'):
                print(f"Fetching license for {dep_name} (custom) from direct URL...")
                license_data = fetch_license_from_url(mapping_value, dep_name)
            else:
                # It's a repo path, use GitHub API
                print(f"Fetching license for {dep_name} (custom) from {mapping_value}...")
                license_data = fetch_license_from_github(mapping_value, dep_name)
        # Check REPOSITORY_MAPPINGS for manual overrides
        elif dep_name in REPOSITORY_MAPPINGS:
            mapping_value = REPOSITORY_MAPPINGS[dep_name]
            
            # If it's a direct URL, fetch from that URL
            if mapping_value.startswith('https://'):
                print(f"Fetching license for {dep_name} from direct URL...")
                license_data = fetch_license_from_url(mapping_value, dep_name)
            else:
                # It's a repo path, use GitHub API
                print(f"Fetching license for {dep_name} from {mapping_value}...")
                license_data = fetch_license_from_github(mapping_value, dep_name)
        else:
            # Try to fetch repository URL from package registry
            print(f"Looking up {dep_name}...")
            repo_path = None
            
            if dep_type == 'python':
                repo_path = fetch_license_from_pypi(dep_name)
            elif dep_type == 'nodejs':
                repo_path = fetch_license_from_npm(dep_name)
            
            if repo_path:
                print(f"Fetching license for {dep_name} from {repo_path}...")
                license_data = fetch_license_from_github(repo_path, dep_name)
            else:
                errors.append(f"No repository found for {dep_name}")
                continue
        
        if not license_data:
            errors.append(f"Could not fetch license for {dep_name}")
            continue
        
        # Validate the license
        if not validate_license(license_data['name']):
            errors.append(f"License '{license_data['name']}' for {dep_name} is not in the approved list")
            continue
        
        # Add to NOTICE.txt
        append_to_notice(dep_name, license_data['text'])
    
    # Report errors
    if errors:
        print("\n[ERROR] License check failed with the following errors:")
        for error in errors:
            print(f"  - {error}")
        print("\nPlease add missing repository mappings to REPOSITORY_MAPPINGS in scripts/generate_notice.py")
        return 1

    print("\n[OK] All dependency licenses checked and updated successfully!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
