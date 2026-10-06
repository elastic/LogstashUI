#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Display-name and numeric helpers for monitoring and SNMP labels."""

import re

def _safe_get_numeric(data, default=0):
    """Coerce ``data`` to int or float, using ``default`` on failure.

    Lists yield the first element. Non-numeric values return ``default``.
    """
    if data is None:
        return default

    # If it's a list, try to get the first element
    if isinstance(data, list):
        if len(data) == 0:
            return default
        data = data[0]

    # Try to convert to the appropriate numeric type
    try:
        if isinstance(data, (int, float)):
            return data
        return float(data) if '.' in str(data) else int(data)
    except (ValueError, TypeError):
        return default


def _safe_extract_value(data, default=0):
    """Unwrap a monitoring field that may be a list or null.

    Returns the first non-empty list element, ``data`` itself, or ``default``.
    """
    if data is None:
        return default
    if isinstance(data, list):
        # If it's an empty list or list with no valid values, return default
        if not data or all(v is None or v == '' for v in data):
            return default
        # If it's a list with values, return the first non-null value
        for v in data:
            if v is not None and v != '':
                return v
        return default
    return data


def _format_uptime(milliseconds):
    """Format an uptime in milliseconds as ``Xd Yh``, ``Xh Ym``, or similar."""
    seconds = milliseconds // 1000
    minutes = seconds // 60
    hours = minutes // 60
    days = hours // 24

    if days > 0:
        return f"{days}d {hours % 24}h"
    elif hours > 0:
        return f"{hours}h {minutes % 60}m"
    elif minutes > 0:
        return f"{minutes}m {seconds % 60}s"
    else:
        return f"{seconds}s"


def format_display_name(name):
    """Turn a slug (``dell_x1026``, ``generic_interfaces.json``) into a label.

    SNMP template and profile ``name`` fields are stable keys used in
    pipelines and the official catalog; they should not be shown as-is.

    Args:
        name: Slug or filename.

    Returns:
        Title-cased label, or ``''`` if ``name`` is empty.

    Examples:
        format_display_name("dell_x1026")  # "Dell X1026"
        format_display_name("generic_interfaces.json")  # "Generic Interfaces"
    """
    if not name:
        return ''

    label = str(name)
    if label.endswith('.json'):
        label = label[:-5]

    return label.replace('_', ' ').replace('-', ' ').title()


def _sanitize_pipeline_name_component(name):
    """Lowercase a name for use in an ES pipeline id.

    Non ``[A-Za-z0-9_-]`` characters become underscores; runs of underscores
    collapse; leading/trailing underscores are stripped.
    """
    # Replace any character that isn't a letter, number, underscore, or hyphen with underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', name)
    # Remove consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized.lower()