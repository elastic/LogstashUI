#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""In-app Markdown docs renderer with sidebar nav and changelog."""

from django.shortcuts import render
from django.conf import settings
from pathlib import Path
import markdown
import re
import yaml

from LogstashUI.paths import resolve_changelog_path, resolve_docs_dir

DOCS_BASE_DIR = resolve_docs_dir()
DOCS_DIR = DOCS_BASE_DIR / "docs"
if not DOCS_DIR.is_dir() and (DOCS_BASE_DIR / "docs" / "docs").is_dir():
    DOCS_DIR = DOCS_BASE_DIR / "docs" / "docs"
CHANGELOG_PATH = resolve_changelog_path()

# Manual title overrides for specific files/folders
TITLE_OVERRIDES = {
    'logstashui': 'LogstashUI',
    'logstashagent': 'LogstashAgent',
    'logstashagent.yml': 'logstashagent.yml',
    'logstashui.yml': 'logstashui.yml',
    'SNMP': 'SNMP',
    'rest_api': 'REST API Reference',
    'logstash_proxy': 'Logstash Tarball Proxy',
    'tsds_implementation': 'TSDS Implementation',
    'data_overview': 'Data Overview',
    'pipeline_generation': 'Pipeline Generation',
    'schema': 'Field Reference',
}

def get_display_title(filename):
    """Build a display title from a docs file or folder name.

    Checks ``TITLE_OVERRIDES`` first, then title-cases dashes/underscores.
    ``.yml`` names stay lowercase.

    Args:
        filename: File or directory name, with or without ``.md``.

    Returns:
        Title string for the sidebar and page heading.
    """
    # Remove .md extension if present for checking overrides
    name = filename.replace('.md', '')
    
    # Check manual overrides first (against name without .md)
    if name in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[name]
    
    # Also check the original filename
    if filename in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[filename]
    
    # Keep .yml files lowercase
    if name.endswith('.yml'):
        return name.lower()
    
    # Default: title case with dash/underscore handling
    return name.replace('-', ' ').replace('_', ' ').title()

def build_nav_tree(base_path, current_path=""):
    """Recursively build the sidebar tree from the docs directory.

    Titles come from filenames; file contents are not read. ``index.md``
    is omitted as a leaf (it is the folder page). Hidden names, Jekyll
    ``_`` prefixes, and the ``images`` folder are skipped.

    Args:
        base_path: Directory to scan.
        current_path: URL path accumulated from parent folders.

    Returns:
        List of dicts with ``title``, ``url``, ``children``, and
        ``is_folder``.
    """
    nav_items = []
    
    try:
        # Custom sort order for top-level items
        def sort_key(item):
            # Files (except index.md) come first
            if not item.is_dir() and item.name != 'index.md':
                return (0, item.name)
            
            # Then specific folders in order
            if item.is_dir():
                if item.name == 'logstashui':
                    return (1, 0, item.name)
                elif item.name == 'logstashagent':
                    return (1, 1, item.name)
                else:
                    return (1, 2, item.name)
            
            # index.md is handled separately (not in nav tree)
            return (2, item.name)
        
        items = sorted(base_path.iterdir(), key=sort_key)
        
        for item in items:
            # Skip hidden files, images folder, and Jekyll files
            if item.name.startswith(('.', '_')) or item.name == 'images':
                continue
            
            if item.is_dir():
                # Check if directory has an index.md
                index_file = item / "index.md"
                if index_file.exists():
                    # Get display title
                    title = get_display_title(item.name)
                    
                    # Build URL path
                    url_path = f"{current_path}/{item.name}" if current_path else item.name
                    
                    # Recursively get children
                    children = build_nav_tree(item, url_path)
                    
                    nav_items.append({
                        'title': title,
                        'url': f"/Documentation/{url_path}/",
                        'children': children,
                        'is_folder': True
                    })
            elif item.suffix == '.md' and item.name != 'index.md':
                # Individual markdown file (not index.md)
                # Get display title
                title = get_display_title(item.name)
                
                # Build URL path (remove .md extension)
                url_path = f"{current_path}/{item.stem}" if current_path else item.stem
                
                nav_items.append({
                    'title': title,
                    'url': f"/Documentation/{url_path}/",
                    'children': [],
                    'is_folder': False
                })
    except Exception as e:
        print(f"Error building nav tree: {e}")
    
    return nav_items

def rewrite_image_paths(html_content):
    """Rewrite Markdown image URLs that contain ``/images/`` to ``/static/``.

    Handles ``docs/images/``, ``../images/``, and similar relative paths.

    Args:
        html_content: Rendered HTML.

    Returns:
        HTML with ``src`` rewritten.
    """
    # Match any path that contains /images/ and extract just the filename
    # This handles: docs/images/file.png, ../images/file.png, ../../images/file.png
    html_content = re.sub(
        r'src="[^"]*?/images/([^"]+)"',
        r'src="/static/\1"',
        html_content
    )
    
    # Also handle single quotes
    html_content = re.sub(
        r"src='[^']*?/images/([^']+)'",
        r"src='/static/\1'",
        html_content
    )
    
    return html_content

def convert_github_alerts(html_content):
    """Turn GitHub ``[!TIP]`` / ``[!NOTE]`` / ``[!WARNING]`` blockquotes into styled divs.

    Args:
        html_content: Rendered HTML.

    Returns:
        HTML with alert blockquotes replaced.
    """
    alert_types = {
        'TIP': {'icon': '💡', 'color': 'rgba(34, 197, 94, 0.15)', 'border': 'rgba(34, 197, 94, 0.5)'},
        'NOTE': {'icon': 'ℹ️', 'color': 'rgba(59, 130, 246, 0.15)', 'border': 'rgba(59, 130, 246, 0.5)'},
        'WARNING': {'icon': '⚠️', 'color': 'rgba(234, 179, 8, 0.15)', 'border': 'rgba(234, 179, 8, 0.5)'},
        'IMPORTANT': {'icon': '❗', 'color': 'rgba(168, 85, 247, 0.15)', 'border': 'rgba(168, 85, 247, 0.5)'},
        'CAUTION': {'icon': '🔥', 'color': 'rgba(239, 68, 68, 0.15)', 'border': 'rgba(239, 68, 68, 0.5)'},
    }
    
    for alert_type, style in alert_types.items():
        # Match to the closing </blockquote> so alerts containing lists or
        # code blocks (multi-element blockquotes) are converted too.
        pattern = rf'<blockquote>\s*<p>\[!{alert_type}\](.*?)</blockquote>'
        replacement = (
            f'<div style="background: {style["color"]}; border-left: 4px solid {style["border"]}; '
            f'padding: 1rem 1.5rem; border-radius: 0.5rem; margin: 1.5rem 0;">'
            f'<div style="display: flex; gap: 0.75rem; align-items: start;">'
            f'<span style="font-size: 1.25rem;">{style["icon"]}</span>'
            f'<div><strong>{alert_type.title()}</strong>\\1</div>'
            f'</div></div>'
        )
        html_content = re.sub(pattern, replacement, html_content, flags=re.DOTALL)
    
    return html_content

def rewrite_doc_links(html_content):
    """Rewrite ``.md`` hrefs to in-app ``/Documentation/.../`` URLs.

    Preserves ``#anchor`` fragments. Covers absolute ``/docs/docs/`` paths
    and relative ``docs/docs/`` or ``path/file.md`` links.

    Args:
        html_content: Rendered HTML.

    Returns:
        HTML with documentation hrefs rewritten.

    Examples:
        /docs/docs/logstashui/index.md -> /Documentation/logstashui/
        docs/docs/logstashui/index.md -> /Documentation/logstashui/
        logstashui/index.md -> /Documentation/logstashui/
    """
    # All patterns preserve an optional #anchor fragment after the .md extension.

    # Pattern 1: /docs/docs/path/index.md -> /Documentation/path/ (absolute paths)
    html_content = re.sub(
        r'href="/docs/docs/([^"#]+)/index\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )

    # Pattern 2: /docs/docs/path/file.md -> /Documentation/path/file/ (absolute paths)
    html_content = re.sub(
        r'href="/docs/docs/([^"#]+)\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )

    # Pattern 3: docs/docs/path/index.md -> /Documentation/path/ (relative paths)
    html_content = re.sub(
        r'href="docs/docs/([^"#]+)/index\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )

    # Pattern 4: docs/docs/path/file.md -> /Documentation/path/file/ (relative paths)
    html_content = re.sub(
        r'href="docs/docs/([^"#]+)\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )

    # Pattern 5: path/index.md -> /Documentation/path/ (generic relative)
    html_content = re.sub(
        r'href="([^"/#][^"#]+)/index\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )

    # Pattern 6: path/file.md -> /Documentation/path/file/ (generic relative)
    html_content = re.sub(
        r'href="([^"/#][^"#]+)\.md((?:#[^"]*)?)"',
        r'href="/Documentation/\1/\2"',
        html_content
    )
    
    return html_content

def documentation_home(request):
    """Render ``docs/index.md`` as the documentation landing page."""
    index_path = DOCS_DIR / "index.md"
    
    if index_path.exists():
        with open(index_path, 'r', encoding='utf-8') as f:
            markdown_content = f.read()
        
        # Add markdown="1" attribute to details tags so md_in_html processes them
        markdown_content = re.sub(
            r'<details>',
            r'<details markdown="1">',
            markdown_content
        )
        
        md = markdown.Markdown(extensions=[
            'markdown.extensions.fenced_code',
            'markdown.extensions.tables',
            'markdown.extensions.toc',
            'markdown.extensions.md_in_html',
        ])
        html_content = md.convert(markdown_content)
        
        html_content = rewrite_image_paths(html_content)
        html_content = convert_github_alerts(html_content)
        html_content = rewrite_doc_links(html_content)
    else:
        html_content = "<p>README.md not found</p>"
    
    # Build navigation tree
    nav_tree = build_nav_tree(DOCS_DIR)
    
    # Add CHANGELOG as the last item
    nav_tree.append({
        'title': 'Changelog',
        'url': '/Documentation/changelog/',
        'children': [],
        'is_folder': False
    })
    
    context = {
        'content': html_content,
        'title': 'Documentation Home',
        'nav_tree': nav_tree,
    }
    
    return render(request, 'documentation.html', context)

def render_documentation(request, doc_path):
    """Render a docs page, folder index, or the changelog.

    Resolves ``{doc_path}/index.md``, then ``{doc_path}.md``. The special
    path ``changelog`` reads ``CHANGELOG.md``.

    Args:
        doc_path: URL path under ``/Documentation/``.

    Examples:
        /Documentation/logstashagent/configuration/ ->
            docs/docs/logstashagent/configuration/index.md
        /Documentation/logstashui/general/build/ ->
            docs/docs/logstashui/general/build.md
        /Documentation/changelog/ -> CHANGELOG.md
    """
    # Special case for CHANGELOG
    if doc_path == "changelog":
        if CHANGELOG_PATH.exists():
            with open(CHANGELOG_PATH, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            md = markdown.Markdown(extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.toc',
            ])
            html_content = md.convert(markdown_content)
            html_content = convert_github_alerts(html_content)
            
            nav_tree = build_nav_tree(DOCS_DIR)
            nav_tree.append({
                'title': 'Changelog',
                'url': '/Documentation/changelog/',
                'children': [],
                'is_folder': False
            })
            
            return render(request, 'documentation.html', {
                'content': html_content,
                'title': 'Changelog',
                'nav_tree': nav_tree,
            })
        else:
            html_content = "<p>CHANGELOG.md not found</p>"
            title = "Changelog Not Found"
            nav_tree = build_nav_tree(DOCS_DIR)
            nav_tree.append({
                'title': 'Changelog',
                'url': '/Documentation/changelog/',
                'children': [],
                'is_folder': False
            })
            return render(request, 'documentation.html', {
                'content': html_content,
                'title': title,
                'nav_tree': nav_tree,
            })
    
    # Try to find the markdown file
    # First try: path/index.md (for folders)
    md_path = DOCS_DIR / doc_path / "index.md"
    
    if not md_path.exists():
        # Second try: path.md (for individual files)
        md_path = DOCS_DIR / f"{doc_path}.md"
    
    if not md_path.exists():
        # File not found
        html_content = f"<p>Documentation not found: {doc_path}</p>"
        title = "Not Found"
    else:
        # Read and render the markdown file
        try:
            with open(md_path, 'r', encoding='utf-8') as f:
                markdown_content = f.read()
            
            # Add markdown="1" attribute to details tags
            markdown_content = re.sub(
                r'<details>',
                r'<details markdown="1">',
                markdown_content
            )
            
            md = markdown.Markdown(extensions=[
                'markdown.extensions.fenced_code',
                'markdown.extensions.tables',
                'markdown.extensions.toc',
                'markdown.extensions.md_in_html',
            ])
            html_content = md.convert(markdown_content)
            
            # Apply transformations
            html_content = rewrite_image_paths(html_content)
            html_content = convert_github_alerts(html_content)
            html_content = rewrite_doc_links(html_content)
            
            # Extract title from path
            title = doc_path.split('/')[-1].replace('-', ' ').replace('_', ' ').title()
        except Exception as e:
            html_content = f"<p>Error rendering documentation: {e}</p>"
            title = "Error"
    
    # Build navigation tree
    nav_tree = build_nav_tree(DOCS_DIR)
    
    # Add CHANGELOG as the last item
    nav_tree.append({
        'title': 'Changelog',
        'url': '/Documentation/changelog/',
        'children': [],
        'is_folder': False
    })
    
    context = {
        'content': html_content,
        'title': title,
        'nav_tree': nav_tree,
    }
    
    return render(request, 'documentation.html', context)
