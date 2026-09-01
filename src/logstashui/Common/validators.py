#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

import re

def validate_pipeline_name(pipeline_name):
    """
    Validate pipeline name according to Elasticsearch rules.

    Pipeline ID must:
    - Begin with a letter or underscore
    - Contain only letters, underscores, dashes, hyphens, and numbers

    Args:
        pipeline_name (str): The pipeline name to validate

    Returns:
        tuple: (is_valid, error_message)
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
    """
    Validate a data stream namespace according to Elasticsearch rules.

    Namespace must:
    - Not be empty
    - Be lowercase only (no uppercase letters)
    - Contain only lowercase letters, digits, hyphens, and underscores
    - Not start with a hyphen or underscore
    - Not exceed 100 bytes

    Args:
        namespace (str): The namespace to validate

    Returns:
        tuple: (is_valid, error_message)
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