#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

"""Elasticsearch pipeline-id and data-stream namespace validators."""

import re

def validate_pipeline_name(pipeline_name):
    """Check a pipeline id against Elasticsearch naming rules.

    The id must begin with a letter or underscore and contain only letters,
    digits, underscores, and hyphens.

    Args:
        pipeline_name: Candidate pipeline id.

    Returns:
        ``(True, None)`` if valid, otherwise ``(False, error_message)``.

    Examples:
        ok, err = validate_pipeline_name("logs-nginx")
        ok, err = validate_pipeline_name("1bad")  # False
    """
    if not pipeline_name:
        return False, "Pipeline name cannot be empty"

    # Check if starts with letter or underscore
    if not re.match(r'^[a-zA-Z_]', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"

    # Check if contains only valid characters
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"

    return True, None


def validate_namespace(namespace):
    """Check a data-stream namespace against Elasticsearch index rules.

    Must be non-empty, lowercase, start with a letter or digit, contain only
    ``[a-z0-9_-]``, and be at most 100 bytes.

    Args:
        namespace: Candidate namespace.

    Returns:
        ``(True, None)`` if valid, otherwise ``(False, error_message)``.
    """
    if not namespace:
        return False, "Namespace cannot be empty"

    if len(namespace.encode('utf-8')) > 100:
        return False, "Namespace cannot exceed 100 bytes"

    if namespace != namespace.lower():
        return False, f"Namespace '{namespace}' must be lowercase. Elasticsearch index names do not allow uppercase characters"

    if not re.match(r'^[a-z0-9]', namespace):
        return False, f"Namespace '{namespace}' must begin with a lowercase letter or digit"

    if not re.match(r'^[a-z0-9][a-z0-9_\-]*$', namespace):
        return False, f"Namespace '{namespace}' contains invalid characters. Only lowercase letters, digits, hyphens, and underscores are allowed"

    return True, None