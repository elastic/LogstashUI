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
    print("AYAYAY")
    if not pipeline_name:
        return False, "Pipeline name cannot be empty"

    # Check if starts with letter or underscore
    if not re.match(r'^[a-zA-Z_]', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"

    # Check if contains only valid characters
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_\-]*$', pipeline_name):
        return False, f"Invalid pipeline [{pipeline_name}] ID received. Pipeline ID must begin with a letter or underscore and can contain only letters, underscores, dashes, hyphens, and numbers"

    return True, None