#Copyright Elasticsearch B.V. and/or licensed to Elasticsearch B.V. under one
#or more contributor license agreements. Licensed under the Elastic License;
#you may not use this file except in compliance with the Elastic License.

from Common.logstash_config_parse import logstash_config_to_components
import pytest
import json
import os

# Load test cases from external files
def load_test_cases():
    """Load test cases from conversion_data directory."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    pipelines_dir = os.path.join(base_dir, "conversion_data", "pipelines")
    components_dir = os.path.join(base_dir, "conversion_data", "components")
    
    test_cases = []
    
    # Get all .conf files
    for filename in sorted(os.listdir(pipelines_dir)):
        if filename.endswith('.conf'):
            name = filename[:-5]  # Remove .conf extension
            
            # Load pipeline config
            pipeline_file = os.path.join(pipelines_dir, filename)
            with open(pipeline_file, 'r', encoding='utf-8') as f:
                pipeline = f.read()
            
            # Load components JSON
            components_file = os.path.join(components_dir, f"{name}.json")
            with open(components_file, 'r', encoding='utf-8') as f:
                components_json = json.load(f)
                # Convert back to JSON string for comparison
                components = json.dumps(components_json, indent=4)
            
            test_cases.append((name, pipeline, components))
    
    return test_cases

test_cases = load_test_cases()

@pytest.mark.parametrize(
    "name, pipeline, components",
    test_cases,
    ids=[case[0] for case in test_cases]
)
def test_pipeline_to_components(name, pipeline, components):
    assert logstash_config_to_components(pipeline) == components



